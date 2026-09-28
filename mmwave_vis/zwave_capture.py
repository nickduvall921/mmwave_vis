"""
Z-Wave JS packet capture (diagnostic)
=====================================
Records Z-Wave JS driver log output through Home Assistant so owners of a
Red Series VZW32-SN can share the switch's mmWave target frames.

Firmware 2.04+ reports target positions when parameter 107 has value 1 set,
but Z-Wave JS has no handler for Inovelli's Manufacturer Proprietary (0x91)
frames, so they never reach HA as values or events. The driver still logs
every inbound frame: the raw serial hex at `debug` level and the decoded
command tree at `verbose`. While a capture runs, the driver log level is
raised to `debug` (zwave_js/update_log_config) and restored on stop.

Uses the same Supervisor WebSocket proxy and token as the ZHA client, so it
works with either zigbee_stack setting. The zwave_js/* commands used here are
admin-only; the Supervisor token authenticates as an admin user.
"""

import json
import re
import threading
import time
from datetime import datetime, timezone

from websockets.sync.client import connect as ws_connect


# zwave-js log levels, least to most verbose
LOG_LEVELS    = ["error", "warn", "info", "http", "verbose", "debug", "silly"]
CAPTURE_LEVEL = "debug"

MAX_LINES         = 100_000
MAX_DURATION_S    = 15 * 60
STATUS_INTERVAL_S = 1.0
RECV_TIMEOUT_S    = 0.5
REQUEST_TIMEOUT_S = 15

# Decoded 0x91 frames show up in the driver log as "[ManufacturerProprietaryCC]"
PROPRIETARY_MARKER = "ManufacturerProprietary"

# zwave_js device identifiers look like "<home_id>-<node_id>"
_NODE_IDENT_RE = re.compile(r"^\d+-(\d+)$")


class CaptureError(RuntimeError):
    pass


class ZWaveCapture:
    """
    One capture at a time. start()/stop() are called from socket.io handlers;
    the capture itself runs on a background thread that owns its own HA
    WebSocket connection. Status is pushed to every client on the
    'zwave_capture_status' event.
    """

    def __init__(self, ha_url: str, ha_token: str, socketio, addon_version: str = "unknown"):
        self.ha_token      = ha_token
        self.socketio      = socketio
        self.addon_version = addon_version
        # Same fixed Supervisor proxy URL as ZHAClient._ws_url
        self.ws_url = ("wss" if ha_url.startswith("https") else "ws") + "://supervisor/core/websocket"

        self._lock       = threading.Lock()
        self._stop_event = threading.Event()
        self._thread     = None
        self._msg_id     = 1
        self._reset()

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def start(self) -> bool:
        """Begin a new capture, discarding any previous one. False if one is running."""
        with self._lock:
            if self._state in ("starting", "capturing", "stopping"):
                return False
            self._reset()
            self._state      = "starting"
            self._started_at = time.time()
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, name="zwave-capture", daemon=True)
            self._thread.start()
        self._emit_status(force=True)
        return True

    def stop(self):
        with self._lock:
            if self._state not in ("starting", "capturing"):
                return
            self._state = "stopping"
        self._stop_event.set()
        self._emit_status(force=True)

    def status(self) -> dict:
        with self._lock:
            end = self._stopped_at or time.time()
            return {
                "state":          self._state,
                "error":          self._error,
                "note":           self._note,
                "lines":          len(self._lines),
                "proprietary":    self._proprietary,
                "elapsed":        int(end - self._started_at) if self._started_at else 0,
                "max_duration":   MAX_DURATION_S,
                "entry_title":    self._entry_title,
                "devices":        list(self._devices),
                "level_original": self._orig_config.get("level"),
                "has_data":       bool(self._lines) and self._state in ("stopped", "error"),
            }

    def export_text(self):
        """The finished capture as a text file, or None if there is nothing to download."""
        with self._lock:
            if not self._lines or self._state not in ("stopped", "error"):
                return None
            lines = list(self._lines)
            header = self._header()
        return "\n".join(header + [""] + lines) + "\n"

    def export_filename(self) -> str:
        ts = datetime.fromtimestamp(self._started_at or time.time(), timezone.utc)
        return f"zwave_capture_{ts:%Y%m%d_%H%M%S}.log"

    # -----------------------------------------------------------------------
    # Capture thread
    # -----------------------------------------------------------------------

    def _reset(self):
        self._state        = "idle"
        self._error        = None
        self._note         = None
        self._lines        = []
        self._proprietary  = 0
        self._started_at   = None
        self._stopped_at   = None
        self._entry_title  = None
        self._devices      = []
        self._orig_config  = {}   # log config keys we changed → original values
        self._restored     = False
        self._last_status  = 0.0

    def _run(self):
        entry_id = None
        try:
            if not self.ha_token:
                raise CaptureError(
                    "No Home Assistant token available (homeassistant_api must be enabled)."
                )
            with ws_connect(
                self.ws_url,
                additional_headers={"Authorization": f"Bearer {self.ha_token}"},
                max_size=None,
            ) as ws:
                self._authenticate(ws)

                entry = self._find_entry(ws)
                entry_id = entry["entry_id"]
                devices = self._find_inovelli_nodes(ws, entry_id)
                with self._lock:
                    self._entry_title = entry.get("title") or "Z-Wave JS"
                    self._devices     = devices

                self._raise_log_level(ws, entry_id)

                sub_id = self._request(ws, {"type": "zwave_js/subscribe_log_updates",
                                            "entry_id": entry_id}, want_id=True)
                with self._lock:
                    if self._state == "starting":
                        self._state = "capturing"
                self._emit_status(force=True)

                self._capture_loop(ws, sub_id)

                self._request(ws, {"type": "unsubscribe_events", "subscription": sub_id},
                              sub_id=sub_id)
                self._restore_log_level(ws, entry_id)
        except Exception as e:
            with self._lock:
                self._error = str(e) or type(e).__name__
            print(f"Z-Wave capture: {self._error}", flush=True)
        finally:
            if self._orig_config and not self._restored and entry_id:
                self._restore_on_new_connection(entry_id)
            with self._lock:
                self._state      = "error" if self._error else "stopped"
                self._stopped_at = time.time()
            print(f"Z-Wave capture: {self._state} after {len(self._lines)} lines "
                  f"({self._proprietary} Manufacturer Proprietary).", flush=True)
            self._emit_status(force=True)

    def _capture_loop(self, ws, sub_id):
        deadline = self._started_at + MAX_DURATION_S
        while not self._stop_event.is_set():
            note = None
            if time.time() >= deadline:
                note = f"Stopped automatically at the {MAX_DURATION_S // 60}-minute limit."
            elif len(self._lines) >= MAX_LINES:
                note = f"Stopped automatically at the {MAX_LINES:,}-line limit."
            if note:
                with self._lock:
                    self._note = note
                return
            try:
                raw = ws.recv(timeout=RECV_TIMEOUT_S)
            except TimeoutError:
                self._emit_status()
                continue
            self._dispatch(json.loads(raw), sub_id)
            self._emit_status()

    def _dispatch(self, msg: dict, sub_id):
        if msg.get("type") != "event" or msg.get("id") != sub_id:
            return
        event = msg.get("event") or {}
        if event.get("type") != "log_message":
            return
        message = (event.get("log_message") or {}).get("message", [])
        lines = message.splitlines() if isinstance(message, str) else [str(m).rstrip("\n") for m in message]
        with self._lock:
            room = MAX_LINES - len(self._lines)
            if room <= 0:
                return
            lines = lines[:room]
            self._lines.extend(lines)
            self._proprietary += sum(1 for line in lines if PROPRIETARY_MARKER in line)

    # -----------------------------------------------------------------------
    # HA WebSocket helpers
    # -----------------------------------------------------------------------

    def _authenticate(self, ws):
        try:
            msg = json.loads(ws.recv(timeout=REQUEST_TIMEOUT_S))
            if msg.get("type") != "auth_required":
                raise CaptureError(f"Unexpected first message from HA: {msg.get('type')}")
            ws.send(json.dumps({"type": "auth", "access_token": self.ha_token}))
            msg = json.loads(ws.recv(timeout=REQUEST_TIMEOUT_S))
        except TimeoutError:
            raise CaptureError("Timed out connecting to Home Assistant.") from None
        if msg.get("type") != "auth_ok":
            raise CaptureError("Home Assistant rejected the addon's token.")

    def _request(self, ws, payload: dict, want_id: bool = False, sub_id=None):
        """
        Send one command and wait for its result. Log events that arrive
        while waiting (only possible during teardown) are still recorded.
        Returns the result, or the request id when want_id is set.
        """
        req_id = self._msg_id
        self._msg_id += 1
        ws.send(json.dumps({"id": req_id, **payload}))
        deadline = time.time() + REQUEST_TIMEOUT_S
        while True:
            remaining = deadline - time.time()
            try:
                if remaining <= 0:
                    raise TimeoutError
                msg = json.loads(ws.recv(timeout=remaining))
            except TimeoutError:
                raise CaptureError(f"Timed out waiting for {payload['type']}.") from None
            if msg.get("id") == req_id and msg.get("type") == "result":
                if not msg.get("success"):
                    err = msg.get("error") or {}
                    raise CaptureError(f"{payload['type']} failed: {err.get('message') or err.get('code')}")
                return req_id if want_id else msg.get("result")
            if sub_id is not None:
                self._dispatch(msg, sub_id)

    def _find_entry(self, ws) -> dict:
        entries = self._request(ws, {"type": "config_entries/get", "domain": "zwave_js"}) or []
        # An ignored discovery (e.g. a USB stick HA offered to set up) is an entry too
        entries = [e for e in entries if e.get("source") != "ignore"]
        loaded = [e for e in entries if e.get("state") == "loaded"]
        if not loaded:
            if entries:
                raise CaptureError("The Z-Wave JS integration is set up but not loaded in Home Assistant.")
            raise CaptureError("No Z-Wave JS integration found in Home Assistant.")
        return loaded[0]

    def _find_inovelli_nodes(self, ws, entry_id: str) -> list:
        """Inovelli devices on this Z-Wave network, for the file header and the UI."""
        try:
            devices = self._request(ws, {"type": "config/device_registry/list"}) or []
        except CaptureError:
            return []
        found = []
        for d in devices:
            if entry_id not in (d.get("config_entries") or []):
                continue
            if "inovelli" not in (d.get("manufacturer") or "").lower():
                continue
            node_id = None
            for ident in d.get("identifiers") or []:
                if len(ident) == 2 and ident[0] == "zwave_js":
                    m = _NODE_IDENT_RE.match(str(ident[1]))
                    if m:
                        node_id = int(m.group(1))
                        break
            found.append({
                "node_id":  node_id,
                "model":    d.get("model") or "",
                "firmware": d.get("sw_version") or "",
                "name":     d.get("name_by_user") or d.get("name") or "",
            })
        found.sort(key=lambda x: (x["node_id"] is None, x["node_id"] or 0))
        return found

    def _raise_log_level(self, ws, entry_id: str):
        config = self._request(ws, {"type": "zwave_js/get_log_config", "entry_id": entry_id}) or {}
        changes = {}
        if config.get("enabled") is False:
            changes["enabled"] = True
        level = str(config.get("level") or "info").lower()
        if level not in LOG_LEVELS or LOG_LEVELS.index(level) < LOG_LEVELS.index(CAPTURE_LEVEL):
            changes["level"] = CAPTURE_LEVEL
        if not changes:
            return
        self._request(ws, {"type": "zwave_js/update_log_config", "entry_id": entry_id, "config": changes})
        with self._lock:
            self._orig_config = {k: config.get(k) for k in changes}

    def _restore_log_level(self, ws, entry_id: str, sub_id=None):
        if not self._orig_config or self._restored:
            return
        original = {k: v for k, v in self._orig_config.items() if v is not None}
        if original:
            self._request(ws, {"type": "zwave_js/update_log_config", "entry_id": entry_id,
                               "config": original}, sub_id=sub_id)
        self._restored = True

    def _restore_on_new_connection(self, entry_id: str):
        """The capture socket died mid-capture; put the log level back anyway."""
        try:
            with ws_connect(
                self.ws_url,
                additional_headers={"Authorization": f"Bearer {self.ha_token}"},
                max_size=None,
            ) as ws:
                self._authenticate(ws)
                self._restore_log_level(ws, entry_id)
        except Exception as e:
            print(f"Z-Wave capture: could not restore the Z-Wave JS log level ({e}). "
                  f"Set it back under Settings → Z-Wave JS → Logs if needed.", flush=True)

    # -----------------------------------------------------------------------
    # Output
    # -----------------------------------------------------------------------

    def _emit_status(self, force: bool = False):
        now = time.time()
        if not force and now - self._last_status < STATUS_INTERVAL_S:
            return
        self._last_status = now
        self.socketio.emit("zwave_capture_status", self.status())

    def _header(self) -> list:
        """File header; caller holds self._lock."""
        def iso(ts):
            return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if ts else "-"

        if self._orig_config.get("level"):
            level_line = f"{CAPTURE_LEVEL} (was {self._orig_config['level']}, " \
                         f"{'restored' if self._restored else 'NOT restored'})"
        else:
            level_line = "unchanged (already at debug or more verbose)"

        header = [
            "# Inovelli mmWave Visualizer - Z-Wave JS packet capture",
            f"# addon version: {self.addon_version}",
            f"# started:  {iso(self._started_at)}",
            f"# stopped:  {iso(self._stopped_at)}",
            f"# Z-Wave JS entry: {self._entry_title or '-'}",
            f"# driver log level during capture: {level_line}",
            f"# lines: {len(self._lines)}   lines mentioning {PROPRIETARY_MARKER}: {self._proprietary}",
        ]
        if self._devices:
            header.append("# Inovelli nodes on this network:")
            for d in self._devices:
                header.append(f"#   node {d['node_id'] if d['node_id'] is not None else '?':<4} "
                              f"{d['model']:<10} fw {d['firmware'] or '?':<8} {d['name']}")
        else:
            header.append("# Inovelli nodes on this network: none found in the device registry")
        if self._note:
            header.append(f"# note: {self._note}")
        if self._error:
            header.append(f"# error: {self._error}")
        return header
