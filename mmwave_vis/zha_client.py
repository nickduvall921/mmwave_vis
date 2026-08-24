"""
ZHA WebSocket Client for Inovelli mmWave Visualizer
====================================================
Maintains a persistent connection to the Home Assistant WebSocket API,
listens for zha_event events from Inovelli VZM32-SN switches, and
translates them into the same socket.io emits the Z2M backend produces.

Threading model: a single daemon thread runs a blocking WebSocket receive
loop (websockets.sync.client), matching the paho-mqtt loop_start() pattern
used by Z2MDriver. Outgoing commands are sent from any thread via _send(),
which holds a lock on the WebSocket object.

Authentication: uses SUPERVISOR_TOKEN (auto-injected by HA when
homeassistant_api: true is set in config.yaml) as both the HTTP Authorization
header on the WebSocket upgrade request and the access_token in the HA auth
message. Falls back to the ha_token config field if SUPERVISOR_TOKEN is empty.

Debug mode: when debug=True, logs all incoming WebSocket event messages and
all outgoing zone/target/config emits. Result-type messages (command acks)
are not logged to avoid flooding the output at high command rates.

Requires: websockets >= 12.0 (uses websockets.sync.client for thread compat)
"""

import json
import time
import threading
import logging
import urllib.request
import urllib.error

from websockets.sync.client import connect as ws_connect

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cluster / Manufacturer Constants
# ---------------------------------------------------------------------------
CLUSTER_MMWAVE = 64562   # 0xFC32 — mmWave presence cluster
CLUSTER_DIMMER = 64561   # 0xFC31 — switch/dimmer cluster
MANUFACTURER   = 4655    # 0x122F — Inovelli
ENDPOINT       = 1

# Attribute IDs on CLUSTER_MMWAVE (0xFC32)
ATTR_HEIGHT_MIN         = 0x0065   # int16 cm — Detection Area 0 Z min
ATTR_HEIGHT_MAX         = 0x0066   # int16 cm — Detection Area 0 Z max
ATTR_WIDTH_MIN          = 0x0067   # int16 cm — Detection Area 0 X min
ATTR_WIDTH_MAX          = 0x0068   # int16 cm — Detection Area 0 X max
ATTR_DEPTH_MIN          = 0x0069   # int16 cm — Detection Area 0 Y min
ATTR_DEPTH_MAX          = 0x006A   # int16 cm — Detection Area 0 Y max
ATTR_TARGET_INFO_REPORT = 0x006B   # uint8  0/1
ATTR_STAY_LIFE          = 0x006C   # uint32 ms
ATTR_DETECT_SENSITIVITY = 0x0070   # uint8  0-2
ATTR_DETECT_TRIGGER     = 0x0071   # uint8  0-2
ATTR_HOLD_TIME          = 0x0072   # uint32 ms

# Attribute IDs on CLUSTER_DIMMER (0xFC31)
ATTR_ROOM_SIZE_PRESET   = 0x0075   # uint8 0-5
ATTR_LIGHT_ON_PRESENCE  = 0x006E   # uint8 0-6 (wired device control)

# Command IDs on CLUSTER_MMWAVE
CMD_CONTROL    = 0x00   # mmwave_control_command  (control_id: uint8)
CMD_SET_INTERF = 0x01   # set_interference_area
CMD_SET_DETECT = 0x02   # set_detection_area
CMD_SET_STAY   = 0x03   # set_stay_area

# ---------------------------------------------------------------------------
# String ↔ integer lookup tables
# Frontend uses Z2M-style display strings; ZHA attributes use integers.
# ---------------------------------------------------------------------------

SENSITIVITY_MAP = {
    "Low":            0,
    "Medium":         1,
    "High (default)": 2,
}

TRIGGER_MAP = {
    "Fast (0.2s, default)": 0,
    "Medium (1s)":          1,
    "Slow (5s)":            2,
}

ROOM_SIZE_MAP = {
    "Custom": 0,
    "Small":  1,
    "Medium": 2,
    "Large":  3,
}

WIRED_DEVICE_MAP = {
    "Disabled":                    0,
    "Occupancy (default)":         1,
    "Vacancy":                     2,
    "Wasteful Occupancy":          3,
    "Mirrored Occupancy":          4,
    "Mirrored Vacancy":            5,
    "Mirrored Wasteful Occupancy": 6,
}

# Reverse maps for translating HA entity state integers back to frontend strings
_REVERSE_SENSITIVITY  = {v: k for k, v in SENSITIVITY_MAP.items()}
_REVERSE_TRIGGER      = {v: k for k, v in TRIGGER_MAP.items()}
_REVERSE_ROOM_SIZE    = {v: k for k, v in ROOM_SIZE_MAP.items()}
_REVERSE_WIRED_DEVICE = {v: k for k, v in WIRED_DEVICE_MAP.items()}
_REVERSE_TARGET_INFO  = {0: "Disable (default)", 1: "Enable"}

# Entity suffix → (reverse_map | None, frontend_param_name)
# Used by _sync_entity_states to translate /api/states into device_config emits.
# None reverse_map = numeric param, pass through as int.
_ENTITY_SUFFIX_MAP = {
    "mmwave_detect_sensitivity":  (_REVERSE_SENSITIVITY,  "mmWaveDetectSensitivity"),
    "mmwave_detect_trigger":      (_REVERSE_TRIGGER,      "mmWaveDetectTrigger"),
    "mmwave_hold_time":           (None,                  "mmWaveHoldTime"),
    "mmwave_stay_life":           (None,                  "mmWaveStayLife"),
    "mmwave_target_info_report":  (_REVERSE_TARGET_INFO,  "mmWaveTargetInfoReport"),
    "mmwave_room_size_preset":    (_REVERSE_ROOM_SIZE,    "mmWaveRoomSizePreset"),
    "light_on_presence_behavior": (_REVERSE_WIRED_DEVICE, "mmwaveControlWiredDevice"),
}


# ---------------------------------------------------------------------------
# Target accumulator
# ---------------------------------------------------------------------------
class _TargetAccumulator:
    """
    ZHA fires mmwave_target_info once per detected target per ~1 Hz cycle.
    We collect events into a short time window then flush as a single batch,
    matching the Z2M behaviour where all targets arrive in one message.

    Call clear() when an all-clear signal is received to prevent stale
    targets from being emitted after the room empties.
    """
    WINDOW_S = 0.15   # 150 ms — safe margin under the 1 Hz report cadence

    def __init__(self, flush_cb):
        self._flush_cb = flush_cb   # callable(targets: list[dict])
        self._targets  = {}         # target_id → target dict
        self._timer    = None
        self._lock     = threading.Lock()

    def add(self, target: dict):
        with self._lock:
            self._targets[target["id"]] = target
            if self._timer is None:
                self._timer = threading.Timer(self.WINDOW_S, self._flush)
                self._timer.daemon = True
                self._timer.start()

    def _flush(self):
        with self._lock:
            targets       = list(self._targets.values())
            self._targets = {}
            self._timer   = None
        if targets:
            self._flush_cb(targets)

    def clear(self):
        """Cancel any pending flush and discard buffered targets."""
        with self._lock:
            if self._timer:
                self._timer.cancel()
            self._targets = {}
            self._timer   = None


# ---------------------------------------------------------------------------
# ZHAClient
# ---------------------------------------------------------------------------
class ZHAClient:
    """
    Persistent Home Assistant WebSocket client for mmWave event processing.

    Public API (called from app.py / ZHADriver):
        start()                  — spawn the background listener thread
        stop()                   — signal the thread to exit
        set_device(ieee, topic)  — switch the actively monitored device
        update_parameter(p, v)   — write a config parameter to the device
        send_control_command(n)  — send a maintenance command (0–5)
        force_sync(sid)          — re-emit cached state + query device
    """

    RECONNECT_DELAY_S     = 5
    RECONNECT_DELAY_MAX_S = 60   # exponential backoff ceiling

    def __init__(self, ha_url: str, ha_token: str, socketio, debug: bool = False):
        """
        ha_url   : HA base URL, e.g. "http://supervisor". The WebSocket
                   proxy URL (ws://supervisor/core/websocket) is always used
                   regardless of this value — ha_url only affects REST calls.
        ha_token : SUPERVISOR_TOKEN or long-lived access token.
        socketio : Flask-SocketIO instance.
        debug    : If True, log incoming ZHA events and outgoing emits.
        """
        self.ha_url   = ha_url.rstrip("/")
        self.ha_token = ha_token
        self.socketio = socketio
        self.debug    = debug

        # Currently monitored device
        self._ieee  = None   # IEEE address string
        self._topic = None   # Synthetic "zha/<ieee>" topic key

        # WebSocket state
        self._ws          = None
        self._ws_lock     = threading.Lock()
        self._msg_id      = 1
        self._msg_id_lock = threading.Lock()

        # Target batch accumulator
        self._accum = _TargetAccumulator(self._on_targets_ready)

        # Device cache:  ieee → { friendly_name, topic, ieee, ha_device_id,
        #                         interference_zones, detection_zones,
        #                         stay_zones, last_seen }
        self.device_list: dict = {}

        self._stop_event = threading.Event()

        # Binding timeout: fires if no zha_event arrives from the monitored
        # device within BINDING_TIMEOUT_S seconds of selecting it.
        self.BINDING_TIMEOUT_S = 10.0
        self._binding_timer: threading.Timer | None = None

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def start(self):
        """Spawn the background WebSocket listener thread."""
        t = threading.Thread(target=self._run, name="zha-ws-listener", daemon=True)
        t.start()

    def stop(self):
        self._stop_event.set()

    def set_device(self, ieee: str, topic: str, sid: str = None):
        """Switch the actively monitored device. Re-emits cached zones."""
        self._accum.clear()
        self._ieee  = ieee
        self._topic = topic
        print(f"ZHA: monitoring {ieee}", flush=True)

        dev = self.device_list.get(ieee, {})
        for key in ("interference_zones", "detection_zones", "stay_zones"):
            cached = dev.get(key)
            if cached is not None:
                self.socketio.emit(key, {"topic": topic, "payload": cached})

        # Tell the frontend whether the custom ZHA quirk is installed
        emit_kwargs = {"to": sid} if sid else {}
        self.socketio.emit("zha_device_info", {
            "ieee":     ieee,
            "quirk_ok": dev.get("quirk_ok", True),
        }, **emit_kwargs)

        self.query_areas()

        # Start binding timeout — if no data arrives within the window,
        # warn the user that the 0xFC32 binding may be missing.
        self._start_binding_timer()

    def query_areas(self):
        """Send control_id=2 to make the device report all zone configs."""
        self._issue_command(CMD_CONTROL, {"control_id": 2})

    def send_control_command(self, action_id: int):
        """
        Send a maintenance command by numeric ID. Mirrors app.py action_map:
            0 = factory reset mmWave module
            1 = auto-generate interference area
            2 = query areas (same as query_areas)
            3 = clear all interference areas
            4 = reset detection areas to defaults
            5 = clear all stay areas
        """
        self._issue_command(CMD_CONTROL, {"control_id": action_id})

    def update_parameter(self, param: str, value):
        """
        Translate a Z2M-style parameter write into the appropriate ZHA
        cluster command or attribute write.
        """
        if not self._ieee:
            return

        # Zone area writes → ZHA cluster commands
        if param == "mmwave_detection_areas":
            self._write_zone_areas(CMD_SET_DETECT, value)
        elif param == "mmwave_interference_areas":
            self._write_zone_areas(CMD_SET_INTERF, value)
        elif param == "mmwave_stay_areas":
            self._write_zone_areas(CMD_SET_STAY, value)

        # Enum attributes — convert display string → integer
        elif param == "mmWaveDetectSensitivity":
            self._write_enum_attr(ATTR_DETECT_SENSITIVITY, value, SENSITIVITY_MAP, param)
        elif param == "mmWaveDetectTrigger":
            self._write_enum_attr(ATTR_DETECT_TRIGGER, value, TRIGGER_MAP, param)
        elif param == "mmWaveTargetInfoReport":
            self._write_attr(ATTR_TARGET_INFO_REPORT, 1 if value == "Enable" else 0)
        elif param == "mmWaveRoomSizePreset":
            self._write_enum_attr(ATTR_ROOM_SIZE_PRESET, value, ROOM_SIZE_MAP, param,
                                  cluster=CLUSTER_DIMMER)
        elif param == "mmwaveControlWiredDevice":
            self._write_enum_attr(ATTR_LIGHT_ON_PRESENCE, value, WIRED_DEVICE_MAP, param,
                                  cluster=CLUSTER_DIMMER)

        # Numeric attributes
        elif param == "mmWaveHoldTime":
            self._write_attr(ATTR_HOLD_TIME, int(value))
        elif param == "mmWaveStayLife":
            self._write_attr(ATTR_STAY_LIFE, int(value))

        # Detection Area 0 individual axis attributes (legacy / convenience)
        elif param == "mmWaveWidthMin":
            self._write_attr(ATTR_WIDTH_MIN, int(value))
        elif param == "mmWaveWidthMax":
            self._write_attr(ATTR_WIDTH_MAX, int(value))
        elif param == "mmWaveDepthMin":
            self._write_attr(ATTR_DEPTH_MIN, int(value))
        elif param == "mmWaveDepthMax":
            self._write_attr(ATTR_DEPTH_MAX, int(value))
        elif param == "mmWaveHeightMin":
            self._write_attr(ATTR_HEIGHT_MIN, int(value))
        elif param == "mmWaveHeightMax":
            self._write_attr(ATTR_HEIGHT_MAX, int(value))

        else:
            log.debug(f"ZHA: unhandled parameter: {param}={value}")

    def force_sync(self, sid=None):
        """
        Re-emit cached zones, query the device for fresh zone data, and
        read current attribute values from HA entity states so the sidebar
        dropdowns/sliders populate correctly.

        sid: emit only to this session if provided; broadcast if None.
        """
        if not self._ieee or not self._topic:
            return

        # 1. Re-emit cached zones immediately
        dev = self.device_list.get(self._ieee, {})
        for key in ("interference_zones", "detection_zones", "stay_zones"):
            cached = dev.get(key)
            if cached is not None:
                payload = {"topic": self._topic, "payload": cached}
                if sid:
                    self.socketio.emit(key, payload, to=sid)
                else:
                    self.socketio.emit(key, payload)

        # 2. Re-emit quirk status so the banner stays correct after a sync
        emit_kwargs = {"to": sid} if sid else {}
        self.socketio.emit("zha_device_info", {
            "ieee":     self._ieee,
            "quirk_ok": dev.get("quirk_ok", True),
        }, **emit_kwargs)

        # 3. Request fresh zone data from the device
        self.query_areas()

        # 4. Read sidebar attribute values from HA entity states (background)
        threading.Thread(
            target=self._sync_entity_states,
            args=(dev.get("ha_device_id"), sid),
            daemon=True
        ).start()

    # -----------------------------------------------------------------------
    # Internal: Binding timeout
    # -----------------------------------------------------------------------

    def _start_binding_timer(self):
        """Cancel any existing timer, then start a new one."""
        self._cancel_binding_timer()
        self._binding_timer = threading.Timer(
            self.BINDING_TIMEOUT_S, self._emit_binding_warning
        )
        self._binding_timer.daemon = True
        self._binding_timer.start()

    def _cancel_binding_timer(self):
        """Cancel the binding timer if one is running."""
        if self._binding_timer is not None:
            self._binding_timer.cancel()
            self._binding_timer = None

    def _emit_binding_warning(self):
        """Called by the timer thread when no data has arrived in time."""
        ieee = self._ieee
        if not ieee:
            return
        print(
            f"ZHA: WARNING — no data received from {ieee} after "
            f"{self.BINDING_TIMEOUT_S:.0f}s. Cluster 0xFC32 binding may be "
            f"missing. Reconfigure the device in ZHA to re-establish it.",
            flush=True,
        )
        self.socketio.emit("zha_binding_warning", {"ieee": ieee, "show": True})

    def _clear_binding_warning(self):
        """Cancel the timer and dismiss the frontend banner."""
        self._cancel_binding_timer()
        self.socketio.emit("zha_binding_warning", {"show": False})

    # -----------------------------------------------------------------------
    # Internal: WebSocket lifecycle
    # -----------------------------------------------------------------------

    def _ws_url(self):
        # The HA Supervisor WebSocket proxy URL is always fixed.
        # Per HA addon developer docs:
        # https://developers.home-assistant.io/docs/apps/communication
        if self.ha_url.startswith("https"):
            return "wss://supervisor/core/websocket"
        return "ws://supervisor/core/websocket"

    def _next_id(self):
        with self._msg_id_lock:
            mid = self._msg_id
            self._msg_id += 1
        return mid

    def _send(self, msg: dict):
        """Thread-safe WebSocket send. Silently drops if not connected."""
        if self.debug:
            try:
                preview = json.dumps(msg, default=str)
                if len(preview) > 400:
                    preview = preview[:400] + "..."
            except Exception:
                preview = str(msg)[:400]
            print(f"[DEBUG] ZHA WS send: {preview}", flush=True)
        with self._ws_lock:
            if self._ws:
                try:
                    self._ws.send(json.dumps(msg))
                except Exception as e:
                    log.warning(f"ZHA WS send error: {e}")

    def _run(self):
        """Main loop: connect → authenticate → listen. Reconnects on failure."""
        delay = self.RECONNECT_DELAY_S
        while not self._stop_event.is_set():
            try:
                self._connect_and_listen()
                delay = self.RECONNECT_DELAY_S  # reset backoff on clean exit
            except Exception as e:
                err = str(e)
                if "502" in err:
                    # HTTP 502 = HA Core not ready yet (Supervisor proxy has nowhere to forward)
                    print(f"ZHA: HA Core not ready (502), retrying in {delay}s...", flush=True)
                elif "auth_invalid" in err or "auth failed" in err.lower():
                    print(f"ZHA: authentication failed — check token. Retrying in {delay}s...", flush=True)
                else:
                    print(f"ZHA: connection lost ({e}), retrying in {delay}s...", flush=True)
                self.socketio.emit("mqtt_status", {
                    "connected": False,
                    "error":     f"HA WebSocket: {e}",
                })
                time.sleep(delay)
                delay = min(delay * 2, self.RECONNECT_DELAY_MAX_S)

    def _connect_and_listen(self):
        url = self._ws_url()
        print(f"ZHA: connecting to {url}", flush=True)

        if not self.ha_token:
            raise RuntimeError(
                "No token available. Ensure homeassistant_api: true is in config.yaml "
                "and the addon has been fully restarted, or set ha_token in Configuration."
            )

        # max_size=None lifts the websockets default 1 MiB cap on incoming
        # messages. The discovery fetches (config/device_registry/list,
        # zha/devices) exceed 1 MiB on large installs, which closed the
        # socket with code 1009 before discovery could finish (issue #53).
        # The peer is the trusted local Supervisor proxy, so no cap is needed.
        with ws_connect(
            url,
            additional_headers={"Authorization": f"Bearer {self.ha_token}"},
            max_size=None,
        ) as ws:
            with self._ws_lock:
                self._ws = ws

            # HA sends auth_required immediately on connect
            msg = json.loads(ws.recv())
            if msg.get("type") != "auth_required":
                raise RuntimeError(f"Unexpected first message: {msg}")

            # Authenticate using SUPERVISOR_TOKEN as the access_token
            ws.send(json.dumps({"type": "auth", "access_token": self.ha_token}))
            msg = json.loads(ws.recv())
            if msg.get("type") != "auth_ok":
                raise RuntimeError(f"ZHA auth failed: {msg}")

            print("ZHA: Connected to Home Assistant WebSocket API successfully.", flush=True)
            self.socketio.emit("mqtt_status", {"connected": True})

            # Discover devices before subscribing to events (no race window)
            self._discover_devices(ws)

            # Subscribe to zha_event
            sub_id = self._next_id()
            ws.send(json.dumps({
                "id":         sub_id,
                "type":       "subscribe_events",
                "event_type": "zha_event",
            }))
            ws.recv()  # consume subscription result

            # Receive loop
            while not self._stop_event.is_set():
                self._handle_message(json.loads(ws.recv()))

    # -----------------------------------------------------------------------
    # Internal: Device discovery
    # All three fetches run synchronously before the zha_event subscription
    # is established — so no incoming events can race with them.
    # -----------------------------------------------------------------------

    def _ws_fetch(self, ws, msg_type: str) -> list:
        """Send a WebSocket request and wait for its result. Returns result list."""
        req_id = self._next_id()
        ws.send(json.dumps({"id": req_id, "type": msg_type}))
        for _ in range(30):   # ~30 messages worth of patience
            raw = ws.recv()
            msg = json.loads(raw)
            if msg.get("id") == req_id and msg.get("type") == "result":
                return msg.get("result") or []
        log.warning(f"ZHA: no result received for {msg_type}")
        return []

    def _fetch_area_map(self, ws) -> dict:
        """Return area_id → display name from the HA area registry."""
        areas = self._ws_fetch(ws, "config/area_registry/list")
        return {a["area_id"]: a.get("name", a["area_id"]) for a in areas}

    def _fetch_device_registry(self, ws) -> dict:
        """
        Return ieee_lower → registry entry from the HA device registry.

        Device registry entries contain:
          name_by_user : user-assigned name (may be null)
          name         : HA auto-generated name
          area_id      : area slug (may be null)
          connections  : [["zigbee", "<ieee>"], ...]
        """
        entries  = self._ws_fetch(ws, "config/device_registry/list")
        registry = {}
        for entry in entries:
            for conn_type, conn_id in (entry.get("connections") or []):
                if conn_type == "zigbee":
                    registry[conn_id.lower()] = entry
        return registry

    def _fetch_entity_registry(self, ws) -> dict:
        """
        Return ha_device_id → [entity registry entries] from the HA entity
        registry. Used by _check_quirk_ok to detect whether the Visualizer
        quirk (as opposed to the official Inovelli quirk, or no quirk at
        all) is active for a device.
        """
        entries   = self._ws_fetch(ws, "config/entity_registry/list")
        by_device = {}
        for entry in entries:
            device_id = entry.get("device_id")
            if device_id:
                by_device.setdefault(device_id, []).append(entry)
        return by_device

    def _discover_devices(self, ws):
        """
        Build the device list by combining the ZHA device list, HA device
        registry (for user-assigned names), and area registry (for locations).

        Device name priority:
          1. name_by_user from HA device registry  — set on the device page in HA
          2. name from HA device registry          — auto-generated (e.g. "Kitchen Switch")
          3. model string from ZHA                 — hardware model e.g. "VZM32-SN"
          4. IEEE address                          — last resort

        Area name appended with " — <Area>" only if not already in the base name.
        """
        area_map     = self._fetch_area_map(ws)
        dev_registry = self._fetch_device_registry(ws)
        ent_registry = self._fetch_entity_registry(ws)
        zha_devices  = self._ws_fetch(ws, "zha/devices")

        found = []
        for dev in zha_devices:
            manufacturer = (dev.get("manufacturer") or "").lower()
            model        = (dev.get("model") or "").lower()

            if not ("inovelli" in manufacturer and "vzm32" in model):
                continue

            ieee         = dev["ieee"]
            topic        = f"zha/{ieee}"
            ha_device_id = dev.get("device_reg_id") or dev.get("id") or None
            model_str    = (dev.get("model") or "").strip()

            reg_entry = dev_registry.get(ieee.lower(), {})
            reg_name  = (reg_entry.get("name_by_user") or reg_entry.get("name") or "").strip()
            base_name = reg_name or model_str or ieee

            area_id      = reg_entry.get("area_id") or dev.get("area_id") or ""
            area_display = area_map.get(area_id, "").strip() if area_id else ""
            if area_display and area_display.lower() not in base_name.lower():
                friendly_name = f"{base_name} — {area_display}"
            else:
                friendly_name = base_name

            entities = ent_registry.get(ha_device_id) if ha_device_id else None
            quirk_ok = self._check_quirk_ok(dev, entities)
            if not quirk_ok:
                if self._legacy_quirk_ok(dev):
                    # Some quirk is applied / 0xFC32 is in the signature, but
                    # the Visualizer-only entity is missing — almost always the
                    # official Inovelli quirk still loading instead of ours.
                    print(f"ZHA: WARNING — {ieee} has a quirk applied, but it is "
                          "not the Visualizer quirk (the 'mmWave target info "
                          "report' switch entity is missing). The official "
                          "Inovelli quirk is likely still active. Copy this "
                          "repo's quirk files over the official ones in the "
                          "directory your configuration.yaml custom_quirks_path "
                          "points to, restart HA, then Reconfigure the device. "
                          "See ZHADOC.md.", flush=True)
                else:
                    print(f"ZHA: WARNING — no custom mmWave quirk detected on {ieee}. "
                          "Target reporting and zone commands will not work. "
                          "Check custom_quirks_path in configuration.yaml and "
                          "see ZHADOC.md.", flush=True)

            if ieee in self.device_list:
                # Already discovered on a previous connect — refresh the quirk
                # status so the frontend banner heals after the user fixes the
                # quirk and HA restarts (which also reconnects this socket).
                self.device_list[ieee]["quirk_ok"] = quirk_ok

            if ieee not in self.device_list:
                print(f"ZHA: discovered {friendly_name} ({ieee})", flush=True)
                self.device_list[ieee] = {
                    "friendly_name":      friendly_name,
                    "topic":              topic,
                    "ieee":               ieee,
                    "ha_device_id":       ha_device_id,
                    "quirk_ok":           quirk_ok,
                    "interference_zones": [],
                    "detection_zones":    [],
                    "stay_zones":         [],
                    "last_seen":          time.time(),
                }
                found.append(self.device_list[ieee])

        if found:
            self.socketio.emit("device_list", list(self.device_list.values()))

    # -----------------------------------------------------------------------
    # Internal: Incoming message routing
    # -----------------------------------------------------------------------

    def _handle_message(self, msg: dict):
        msg_type = msg.get("type")

        # Debug: log event-type messages (not result acks — those flood the log)
        if self.debug and msg_type == "event":
            try:
                preview = json.dumps(msg, default=str)
                if len(preview) > 400:
                    preview = preview[:400] + "..."
            except Exception:
                preview = str(msg)[:400]
            print(f"[DEBUG] ZHA WS event: {preview}", flush=True)

        if msg_type != "event":
            return

        data = msg.get("event", {}).get("data", {})
        ieee = data.get("device_ieee")

        if ieee and ieee in self.device_list:
            self.device_list[ieee]["last_seen"] = time.time()

        if ieee != self._ieee or not self._topic:
            return

        # Data arrived from the monitored device — binding is working.
        self._clear_binding_warning()

        command = data.get("command")
        args    = data.get("args", {})

        if command == "mmwave_target_info":
            self._on_target_info(args)
        elif command == "mmwave_anyone_in_area":
            self._on_anyone_in_area(args)
        elif command == "mmwave_report_interference_area":
            self._on_zone_report("interference_zones", args)
        elif command == "mmwave_report_detection_area":
            self._on_zone_report("detection_zones", args)
        elif command == "mmwave_report_stay_area":
            self._on_zone_report("stay_zones", args)

    # -----------------------------------------------------------------------
    # Internal: ZHA event → socket.io emit handlers
    # -----------------------------------------------------------------------

    def _on_target_info(self, args: dict):
        """
        mmwave_target_info fires once per target per ~1 Hz.
        Accumulate and flush as a batch to match Z2M's bundled format.
        """
        self._accum.add({
            "id" : args.get("id",  0),
            "x"  : args.get("x",  0),
            "y"  : args.get("y",  0),
            "z"  : args.get("z",  0),
            "dop": args.get("dop", 0),
        })

    def _on_targets_ready(self, targets: list):
        """Called by _TargetAccumulator after the batch window closes."""
        if self.debug:
            print(f"[DEBUG] emit new_data: {len(targets)} target(s) → {targets}", flush=True)
        self.socketio.emit("new_data", {
            "topic":   self._topic,
            "payload": {
                "seq":     0,   # ZHA doesn't provide sequence numbers
                "targets": targets,
            }
        })

    def _on_anyone_in_area(self, args: dict):
        """
        Translate mmwave_anyone_in_area → device_config emit so the frontend's
        occupancy badge and zone status indicators update correctly.
        Clears the target accumulator when the room is fully empty to prevent
        stale positions from persisting after an all-clear.
        """
        config_payload = {}
        for i in range(1, 5):
            key = f"area{i}"
            if key in args:
                config_payload[f"mmwave_area{i}_occupancy"] = bool(args[key])

        any_occupied = any(config_payload.values()) if config_payload else False
        config_payload["occupancy"] = any_occupied

        if not any_occupied:
            self._accum.clear()

        self.socketio.emit("device_config", {
            "topic":   self._topic,
            "payload": config_payload,
        })

    def _on_zone_report(self, zone_key: str, args: dict):
        """
        Translate mmwave_report_*_area → zone list emit.

        ZHA event payload:
            { "count": N,
              "area1": { width_min, width_max, depth_min, depth_max,
                         height_min, height_max },
              "area2": { ... }, ... }

        Some firmware reports count=4 even for empty zone sets, using
        x=0, y=0, z=±600 as sentinel values for unused slots. We filter
        those out by requiring non-zero x or y coordinates.
        """
        count = int(args.get("count", 0))
        zones = []

        for i in range(1, count + 1):
            area = args.get(f"area{i}")
            if not isinstance(area, dict):
                continue

            x_min = area.get("width_min",  0)
            x_max = area.get("width_max",  0)
            y_min = area.get("depth_min",  0)
            y_max = area.get("depth_max",  0)
            z_min = area.get("height_min", 0)
            z_max = area.get("height_max", 0)

            # Skip empty sentinel slots (all x and y coordinates are zero)
            if x_min == 0 and x_max == 0 and y_min == 0 and y_max == 0:
                continue

            zones.append({
                "x_min": x_min, "x_max": x_max,
                "y_min": y_min, "y_max": y_max,
                "z_min": z_min, "z_max": z_max,
            })

        if self._ieee in self.device_list:
            self.device_list[self._ieee][zone_key] = zones

        if self.debug:
            print(f"[DEBUG] emit {zone_key}: {len(zones)} active zones → {zones}", flush=True)

        self.socketio.emit(zone_key, {"topic": self._topic, "payload": zones})

    # -----------------------------------------------------------------------
    # Internal: force_sync entity state read
    # -----------------------------------------------------------------------

    def _sync_entity_states(self, ha_device_id: str | None, sid):
        """
        Read current HA entity states and emit the translated values as
        device_config so the sidebar dropdowns/sliders populate correctly.

        We GET /api/states and match entities by entity_id suffix against
        the known attribute names in _ENTITY_SUFFIX_MAP. Filtering by
        device_id is not reliable (it's not exposed in /api/states attributes),
        so we rely on suffix matching alone, which is sufficient since all
        VZM32-SN entities have unique suffix names.
        """
        try:
            states = self._rest_get("/states")
        except Exception as e:
            log.warning(f"ZHA: force_sync entity read failed: {e}")
            return

        if not isinstance(states, list):
            return

        config_payload = {}
        for state in states:
            entity_id = state.get("entity_id", "")
            raw_state = state.get("state")
            if raw_state in (None, "unavailable", "unknown"):
                continue

            for suffix, (reverse_map, param_name) in _ENTITY_SUFFIX_MAP.items():
                if entity_id.endswith(f"_{suffix}"):
                    translated = self._translate_state(raw_state, reverse_map)
                    if translated is not None:
                        config_payload[param_name] = translated
                    break

        if config_payload:
            payload = {"topic": self._topic, "payload": config_payload}
            if sid:
                self.socketio.emit("device_config", payload, to=sid)
            else:
                self.socketio.emit("device_config", payload)

    # Entity created only by the Visualizer quirk's 0xFC32 declarations.
    # Neither the official Inovelli quirk nor a quirk-less device has it,
    # so its presence in the entity registry is the one signal that
    # distinguishes "the Visualizer quirk is active" from "some quirk is
    # applied" or "0xFC32 merely exists in the device signature".
    _VISUALIZER_MARKER = "mmwave_target_info_report"

    @classmethod
    def _check_quirk_ok(cls, dev: dict, entities: list | None = None) -> bool:
        """
        Return True if the *Visualizer* mmWave ZHA quirk appears to be
        active for this device.

        Detection strategy (strongest signal first):
          1. Entity-registry check: the Visualizer quirk declares a
             "mmWave target info report" switch that the official Inovelli
             quirk does not. When registry entries for the device are
             available, require that marker entity. This catches the
             issue #46 failure mode: 0xFC32 sits in the device's raw
             signature (so cluster checks pass) and quirk_applied is True
             for *any* quirk — while the Visualizer quirk never loaded.
          2. Fallback when no registry data is available (older HA, fetch
             failure): the pre-3.2.5 heuristic in _legacy_quirk_ok.
        """
        marker = cls._has_visualizer_entity(entities)
        if marker is not None:
            return marker
        return cls._legacy_quirk_ok(dev)

    @classmethod
    def _has_visualizer_entity(cls, entities: list | None) -> bool | None:
        """
        Look for the Visualizer-only marker entity among a device's entity
        registry entries. Returns True/False when entries are available,
        or None when there is nothing to inspect (registry fetch failed or
        the device has no registered entities) so the caller can fall back
        to weaker heuristics instead of raising a false warning.

        Matches on unique_id, entity_id, and original_name — the unique_id
        ("<ieee>-1-mmwave_target_info_report") and original_name ("mmWave
        target info report") survive a user renaming the entity in HA.
        """
        if not entities:
            return None
        for entry in entities:
            if not isinstance(entry, dict):
                continue
            haystacks = (
                entry.get("unique_id") or "",
                entry.get("entity_id") or "",
                (entry.get("original_name") or "").replace(" ", "_"),
            )
            if any(cls._VISUALIZER_MARKER in h.lower() for h in haystacks):
                return True
        return False

    @staticmethod
    def _legacy_quirk_ok(dev: dict) -> bool:
        """
        Pre-3.2.5 heuristic, kept as a fallback when entity-registry data
        is unavailable. Weak on purpose: 0xFC32 appears in the device's
        raw signature even with no quirk installed, and quirk_applied is
        True for *any* quirk (including the official one) — so this can
        only confirm the mmWave cluster exists, not which quirk is active.
        """
        for ep in (dev.get("endpoints") or []):
            for key in ("input_cluster_ids", "in_cluster_ids", "cluster_ids"):
                if CLUSTER_MMWAVE in (ep.get(key) or []):
                    return True
        return bool(dev.get("quirk_applied", False))

    @staticmethod
    def _translate_state(raw_state: str, reverse_map: dict | None):
        """Convert a raw HA state string to the value the frontend expects.

        ZHA number entities return integer strings ("0", "1", ...).
        ZHA select entities return display strings ("Disable (default)", "Enable", ...).
        Both cases are handled here.
        """
        if reverse_map is not None:
            # ZHA select entities: state is already the display string.
            # Check for an exact match among the known display values.
            if raw_state in reverse_map.values():
                return raw_state
        try:
            int_val = int(float(raw_state))
        except (ValueError, TypeError):
            return None
        if reverse_map is not None:
            return reverse_map.get(int_val)   # enum → display string
        return int_val                         # numeric → pass through

    # -----------------------------------------------------------------------
    # Internal: outgoing commands / attribute writes
    # -----------------------------------------------------------------------

    def _issue_command(self, command: int, params: dict, cluster: int = CLUSTER_MMWAVE):
        """
        Send zha.issue_zigbee_cluster_command via the open WebSocket.
        The REST /api/services/zha/* endpoint is deprecated in recent HA
        versions — WebSocket call_service is the correct approach.
        """
        if not self._ieee:
            return
        self._ws_call_service("zha", "issue_zigbee_cluster_command", {
            "ieee":         self._ieee,
            "endpoint_id":  ENDPOINT,
            "cluster_id":   cluster,
            "cluster_type": "in",
            "command":      command,
            "command_type": "server",
            "params":       params,
            "manufacturer": MANUFACTURER,
        })

    def _write_attr(self, attr_id: int, value, cluster: int = CLUSTER_MMWAVE):
        """Send zha.set_zigbee_cluster_attribute via the open WebSocket."""
        if not self._ieee:
            return
        self._ws_call_service("zha", "set_zigbee_cluster_attribute", {
            "ieee":         self._ieee,
            "endpoint_id":  ENDPOINT,
            "cluster_id":   cluster,
            "cluster_type": "in",
            "attribute":    attr_id,
            "value":        value,
            "manufacturer": MANUFACTURER,
        })

    def _write_enum_attr(self, attr_id: int, value: str, lookup: dict,
                         param_name: str, cluster: int = CLUSTER_MMWAVE):
        """Convert a display string to int via lookup, then write the attribute."""
        int_val = lookup.get(value)
        if int_val is not None:
            self._write_attr(attr_id, int_val, cluster=cluster)
        else:
            log.warning(f"ZHA: unknown value '{value}' for {param_name}")

    def _ws_call_service(self, domain: str, service: str, service_data: dict):
        """
        Send a call_service message over the open WebSocket.
        Fire-and-forget — we don't wait for the result message.
        _send() is thread-safe.
        """
        self._send({
            "id":           self._next_id(),
            "type":         "call_service",
            "domain":       domain,
            "service":      service,
            "service_data": service_data,
        })

    def _write_zone_areas(self, command_id: int, value: dict):
        """
        Translate the frontend's zone area payload into ZHA set_*_area commands.

        Frontend sends: { "area1": { width_min, width_max, depth_min,
                                     depth_max, height_min, height_max }, ... }
        ZHA area_id:    area1 → 0, area2 → 1, area3 → 2, area4 → 3
        A zeroed area represents a delete — send zeros to clear that slot.
        """
        for area_key, area_data in value.items():
            if not isinstance(area_data, dict):
                continue
            try:
                area_id = int(area_key.replace("area", "")) - 1
            except ValueError:
                continue
            self._issue_command(command_id, {
                "area_id": area_id,
                "x_min":   int(area_data.get("width_min",  0)),
                "x_max":   int(area_data.get("width_max",  0)),
                "y_min":   int(area_data.get("depth_min",  0)),
                "y_max":   int(area_data.get("depth_max",  0)),
                "z_min":   int(area_data.get("height_min", 0)),
                "z_max":   int(area_data.get("height_max", 0)),
            })

    # -----------------------------------------------------------------------
    # Internal: HA REST API helper
    # -----------------------------------------------------------------------

    def _rest_get(self, path: str):
        """
        GET from the HA REST API via the Supervisor proxy.
        path must start with / and must NOT include the /api prefix,
        e.g. "/states" → http://supervisor/core/api/states
        """
        url = "http://supervisor/core/api" + path
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self.ha_token}",
                "Content-Type":  "application/json",
            },
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())