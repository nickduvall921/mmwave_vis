"""
Inovelli mmWave Visualizer — Backend
=====================================
Real-time MQTT/ZHA-to-WebSocket bridge for Home Assistant Ingress.

Supports two Zigbee stacks, selected via the addon Configuration tab:
  zigbee_stack: "z2m"  — Zigbee2MQTT over MQTT (original behaviour)
  zigbee_stack: "zha"  — ZHA via the Home Assistant WebSocket API

All socket.io event handlers are stack-agnostic — they delegate to a
driver object (Z2MDriver or ZHADriver) that implements a common interface.
The frontend receives identical events regardless of which stack is active.

Debug mode (debug: true in config):
  Logs every socket.io emit and, for ZHA, every raw WebSocket message
  received from HA. Useful for verifying data flow when troubleshooting
  a new installation. Safe to leave enabled — output is truncated at
  300–400 chars per message.
"""

import json
import os
import signal
import sys
import traceback
import time
import threading
from collections import deque

# Keep a copy of recent console output for the diagnostics file. This has to
# happen before SocketIO() below, whose log handler holds on to sys.stderr.
import logtap
logtap.install()

from flask import Flask, Response, render_template, request
from flask_socketio import SocketIO, emit
import paho.mqtt.client as mqtt
import logging

# Suppress Werkzeug's development-server banner — not useful in an addon
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# ---------------------------------------------------------------------------
# Load Home Assistant addon configuration
# ---------------------------------------------------------------------------
CONFIG_PATH = '/data/options.json'

try:
    with open(CONFIG_PATH) as f:
        config = json.load(f)
except FileNotFoundError:
    print("No options.json found — using built-in defaults.", flush=True)
    config = {}

def _cfg(key, env_name, default, cast=str):
    """Resolve a config value.

    Precedence: options.json (HA addon) > environment variable (standalone Docker) > default.
    Empty strings and None are treated as "not set" so env vars can still override
    placeholder values written into options.json by the HA UI.
    """
    val = config.get(key)
    if val not in (None, ''):
        return cast(val)
    env_val = os.environ.get(env_name)
    if env_val not in (None, ''):
        return cast(env_val)
    return default


def _as_bool(v):
    return str(v).lower() in ('true', '1', 'yes', 'on')


ZIGBEE_STACK    = _cfg('zigbee_stack',    'ZIGBEE_STACK',    'z2m').lower().strip()
DEBUG           = _as_bool(_cfg('debug',  'DEBUG',           False))
MQTT_BROKER     = _cfg('mqtt_broker',     'MQTT_BROKER',     'core-mosquitto')
MQTT_PORT       = _cfg('mqtt_port',       'MQTT_PORT',       1883, int)
MQTT_USERNAME   = _cfg('mqtt_username',   'MQTT_USERNAME',   '')
MQTT_PASSWORD   = _cfg('mqtt_password',   'MQTT_PASSWORD',   '')
# Accept both MQTT_BASE_TOPIC and legacy Z2M_BASE_TOPIC (used by the old mmWave_vis_docker repo)
MQTT_BASE_TOPIC = (
    _cfg('mqtt_base_topic', 'MQTT_BASE_TOPIC', None)
    or os.environ.get('Z2M_BASE_TOPIC')
    or 'zigbee2mqtt'
)
HA_URL          = _cfg('ha_url',          'HA_URL',          'http://supervisor')
# Where room layouts are saved. /data persists across addon updates (and is the
# mapped volume in the standalone Docker setup).
DATA_DIR        = os.environ.get('DATA_DIR', '/data')

# MQTT TLS/SSL (for standalone Docker users with TLS-enabled brokers)
MQTT_USE_TLS      = _as_bool(_cfg('mqtt_use_tls',      'MQTT_USE_TLS',      False))
MQTT_TLS_INSECURE = _as_bool(_cfg('mqtt_tls_insecure', 'MQTT_TLS_INSECURE', False))
MQTT_TLS_CA_CERT  = _cfg('mqtt_tls_ca_cert',           'MQTT_TLS_CA_CERT',  '')

# SUPERVISOR_TOKEN is auto-injected by HA when homeassistant_api: true is set
# in config.yaml. The ha_token config field is a manual fallback — generate a
# long-lived access token from your HA profile page if needed.
_supervisor_token = os.environ.get('SUPERVISOR_TOKEN', '')
_config_token     = config.get('ha_token', '') or os.environ.get('HA_TOKEN', '')
HA_TOKEN          = _supervisor_token or _config_token

# ---------------------------------------------------------------------------
# Startup diagnostics
# ---------------------------------------------------------------------------
print(f"Zigbee stack : {ZIGBEE_STACK}", flush=True)
print(f"Debug mode   : {'ON' if DEBUG else 'OFF'}", flush=True)
if ZIGBEE_STACK == 'z2m':
    print(f"MQTT broker  : {MQTT_BROKER}:{MQTT_PORT}", flush=True)
    print(f"MQTT topic   : {MQTT_BASE_TOPIC}", flush=True)
    if MQTT_USE_TLS:
        tls_note = f"enabled (insecure={'yes' if MQTT_TLS_INSECURE else 'no'}"
        if MQTT_TLS_CA_CERT:
            tls_note += f", ca={MQTT_TLS_CA_CERT}"
        tls_note += ")"
        print(f"MQTT TLS     : {tls_note}", flush=True)

if ZIGBEE_STACK == 'zha':
    print(f"ZHA ha_url   : {HA_URL}", flush=True)
    if _supervisor_token:
        print(f"ZHA token    : SUPERVISOR_TOKEN (len={len(_supervisor_token)})", flush=True)
    elif _config_token:
        print(f"ZHA token    : ha_token from config (len={len(_config_token)})", flush=True)
    else:
        print(
            "ZHA WARNING  : No token found.\n"
            "               Ensure homeassistant_api: true is set in config.yaml\n"
            "               and the addon has been fully stopped and restarted.\n"
            "               Alternatively, set ha_token in the addon Configuration\n"
            "               tab using a long-lived access token from your HA profile.",
            flush=True
        )

# ---------------------------------------------------------------------------
# Flask + Socket.IO
# ---------------------------------------------------------------------------
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', manage_session=False)

# ---------------------------------------------------------------------------
# Per-session device tracking  (socket session id → device topic/key)
# ---------------------------------------------------------------------------
session_topics      = {}
session_topics_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Parameter validation + parsing utilities  (shared by both stacks)
# ---------------------------------------------------------------------------
from utils import (
    VALID_PARAMETERS, VALID_ZONE_KEYS, ZONE_COORD_RANGE,
    validate_parameter, safe_int, decode_raw_targets, decode_raw_zones,
    normalize_layout, layout_key, normalize_zone_names, is_fresh_target_frame, target_frame_mark,
)
from layout_store import LayoutStore
import device_info
import diagnostics
import ha_ws
from history import History

layout_store = LayoutStore(os.path.join(DATA_DIR, 'layouts.json'))
zone_name_store = LayoutStore(os.path.join(DATA_DIR, 'zone_names.json'),
                              normalize=normalize_zone_names, label='Zone names')

HA_WS_URL = ha_ws.ws_url(HA_URL)
registry = ha_ws.RegistryCache(HA_TOKEN, HA_WS_URL)

PACKET_RING = 150   # recent messages per switch, for the diagnostics file

# History key (ieee:<addr>) → the topic pages watch, so live events reach them
_history_topics = {}


def _on_history_event(key, event):
    topic = _history_topics.get(key)
    if topic:
        emit_to_topic_subscribers('history_event', {'topic': topic, 'event': event}, topic)


history = History(DATA_DIR, on_event=_on_history_event)


def history_key(topic, ieee):
    """History is only kept per IEEE address, so a renamed switch keeps its history."""
    if not ieee:
        return None
    key = layout_key(topic, ieee)
    _history_topics[key] = topic
    return key


# ---------------------------------------------------------------------------
# Helpers shared by both stacks
# ---------------------------------------------------------------------------

def get_sessions_for_topic(topic):
    with session_topics_lock:
        return [sid for sid, t in session_topics.items() if t == topic]


def emit_to_topic_subscribers(event, data, topic, skip_sid=None):
    """Emit a socket.io event to all sessions currently watching a given device."""
    for sid in get_sessions_for_topic(topic):
        if sid != skip_sid:
            socketio.emit(event, data, to=sid)


# ===========================================================================
# Z2M DRIVER
# Wraps the original paho-MQTT logic. Exposes the same interface as ZHADriver
# so the socket.io handlers below need no stack-awareness.
# ===========================================================================

class Z2MDriver:

    def __init__(self):
        self.device_list      = {}
        self.device_list_lock = threading.Lock()
        self.mqtt_connected   = False
        self._ieee_by_name    = {}   # from Z2M's retained bridge/devices list
        self._bridge_entries  = {}   # friendly name → VZM32 entry from bridge/devices
        self.bridge_info      = None # harmless summary of bridge/info
        self._facts           = {}   # friendly name → latest firmware/link facts from its state
        self._last_targets    = {}   # friendly name → mark of the last target report recorded (stale re-publish check)
        self.packets          = {}   # friendly name → recent raw messages (diagnostics)

        self._client = mqtt.Client()
        if MQTT_USERNAME and MQTT_PASSWORD:
            self._client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        if MQTT_USE_TLS:
            if MQTT_TLS_CA_CERT:
                self._client.tls_set(ca_certs=MQTT_TLS_CA_CERT)
            else:
                self._client.tls_set()
            if MQTT_TLS_INSECURE:
                self._client.tls_insecure_set(True)
        self._client.on_connect    = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message    = self._on_message

    # --- Lifecycle ---

    def start(self):
        try:
            self._client.connect(MQTT_BROKER, MQTT_PORT, 60)
            self._client.loop_start()
        except Exception as e:
            print(f"MQTT Connection Failed: {e}", flush=True)

        threading.Thread(target=self._cleanup_loop, daemon=True).start()

    # --- Public interface ---

    def get_device_list_snapshot(self):
        with self.device_list_lock:
            return [dict(d) for d in self.device_list.values()]

    def _remember_ieee(self, devices):
        # Friendly names can be changed in Z2M; the IEEE address can't, so room
        # layouts are keyed by it when Z2M has told us the mapping.
        names = {
            d['friendly_name']: d['ieee_address']
            for d in devices
            if isinstance(d, dict) and isinstance(d.get('friendly_name'), str)
            and isinstance(d.get('ieee_address'), str)
        }
        # Firmware details, kept only for the mmWave switches
        entries = {}
        for d in devices:
            if not isinstance(d, dict) or not isinstance(d.get('friendly_name'), str):
                continue
            model = f"{d.get('model_id') or ''} {(d.get('definition') or {}).get('model') or ''}"
            if 'VZM32' in model.upper():
                entries[d['friendly_name']] = {k: d.get(k) for k in (
                    'ieee_address', 'software_build_id', 'date_code', 'model_id', 'power_source')}
        with self.device_list_lock:
            self._ieee_by_name = names
            self._bridge_entries = entries

    def history_key_for(self, fname, topic):
        with self.device_list_lock:
            ieee = self._ieee_by_name.get(fname)
        return history_key(topic, ieee)

    def device_facts(self, topic, force=False):
        """(ieee, bridge entry, latest state facts, last_seen) for device_info."""
        prefix = f"{MQTT_BASE_TOPIC}/"
        fname = topic[len(prefix):] if isinstance(topic, str) and topic.startswith(prefix) else None
        with self.device_list_lock:
            dev = self.device_list.get(fname) or {}
            return (self._ieee_by_name.get(fname), dict(self._bridge_entries.get(fname) or {}),
                    dict(self._facts.get(fname) or {}), dev.get('last_seen'))

    def diagnostics_parts(self, topic):
        prefix = f"{MQTT_BASE_TOPIC}/"
        fname = topic[len(prefix):] if isinstance(topic, str) and topic.startswith(prefix) else None
        with self.device_list_lock:
            dev = json.loads(json.dumps(self.device_list.get(fname) or {}, default=str))
            facts = dict(self._facts.get(fname) or {})
            packets = list(self.packets.get(fname) or [])
        return {
            'driver': {'stack': 'z2m', 'mqtt_connected': self.mqtt_connected, 'base_topic': MQTT_BASE_TOPIC,
                       'switches': len(self.device_list)},
            'stack_versions': {'zigbee2mqtt': self.bridge_info},
            'device': dev, 'settings': facts.get('state'), 'packets': packets,
        }

    def ieee_for_topic(self, topic):
        prefix = f"{MQTT_BASE_TOPIC}/"
        if not isinstance(topic, str) or not topic.startswith(prefix):
            return None
        with self.device_list_lock:
            return self._ieee_by_name.get(topic[len(prefix):])

    def set_device(self, sid, new_topic):
        with session_topics_lock:
            session_topics[sid] = new_topic
        print(f"Session {sid[:8]} monitoring: {new_topic}", flush=True)

        with self.device_list_lock:
            device_data = next(
                (d for d in self.device_list.values() if d['topic'] == new_topic), None
            )
            if device_data:
                cached = {
                    'zone_config':        dict(device_data.get('zone_config', {})),
                    'interference_zones': list(device_data.get('interference_zones', [])),
                    'detection_zones':    list(device_data.get('detection_zones', [])),
                    'stay_zones':         list(device_data.get('stay_zones', [])),
                }

        if device_data:
            socketio.emit('zone_config',        {'topic': new_topic, 'payload': cached['zone_config']},        to=sid)
            socketio.emit('interference_zones', {'topic': new_topic, 'payload': cached['interference_zones']}, to=sid)
            socketio.emit('detection_zones',    {'topic': new_topic, 'payload': cached['detection_zones']},    to=sid)
            socketio.emit('stay_zones',         {'topic': new_topic, 'payload': cached['stay_zones']},         to=sid)

    def update_parameter(self, sid, param, value):
        with session_topics_lock:
            topic = session_topics.get(sid)
        if not topic:
            socketio.emit('command_error', {'error': 'No device selected'}, to=sid)
            return

        is_valid, error_msg = validate_parameter(param, value)
        if not is_valid:
            print(f"Parameter validation failed: {error_msg}", flush=True)
            socketio.emit('command_error', {'error': error_msg}, to=sid)
            return

        with self.device_list_lock:
            fname = next((n for n, d in self.device_list.items() if d['topic'] == topic), None)

        # Legacy fallback: older firmware uses flat top-level attributes for Detection Area 1
        # instead of the nested mmwave_detection_areas structure used by newer versions.
        if fname and param == "mmwave_detection_areas" and isinstance(value, dict) and "area1" in value:
            with self.device_list_lock:
                use_nested = self.device_list.get(fname, {}).get('use_nested_area1', False)
            if not use_nested:
                try:
                    z = value["area1"]
                    legacy = {
                        "mmWaveWidthMin":  int(z.get("width_min",  0)),
                        "mmWaveWidthMax":  int(z.get("width_max",  0)),
                        "mmWaveDepthMin":  int(z.get("depth_min",  0)),
                        "mmWaveDepthMax":  int(z.get("depth_max",  0)),
                        "mmWaveHeightMin": int(z.get("height_min", 0)),
                        "mmWaveHeightMax": int(z.get("height_max", 0)),
                    }
                    self._client.publish(f"{topic}/set", json.dumps(legacy))
                    socketio.emit('command_ack', {'param': param, 'status': 'sent_legacy'}, to=sid)
                    return
                except Exception as e:
                    socketio.emit('command_error', {'error': f'Legacy mapping failed: {e}'}, to=sid)
                    return

        if isinstance(value, str) and value.lstrip('-').isnumeric():
            value = int(value)
        self._client.publish(f"{topic}/set", json.dumps({param: value}))
        socketio.emit('command_ack', {'param': param, 'status': 'sent'}, to=sid)

    def send_command(self, sid, cmd_action):
        with session_topics_lock:
            topic = session_topics.get(sid)
        if not topic:
            socketio.emit('command_error', {'error': 'No device selected'}, to=sid)
            return
        if not self.mqtt_connected:
            socketio.emit('command_error', {'error': 'MQTT broker is not connected'}, to=sid)
            return

        try:
            cmd_int = int(cmd_action)
        except (ValueError, TypeError):
            socketio.emit('command_error', {'error': f'Invalid command: {cmd_action}'}, to=sid)
            return

        action_map = {
            0: "reset_mmwave_module",
            1: "set_interference",
            2: "query_areas",
            3: "clear_interference",
            4: "reset_detection_area",
            5: "clear_stay_areas",
        }
        cmd_string = action_map.get(cmd_int)
        if cmd_string:
            self._client.publish(
                f"{topic}/set",
                json.dumps({"mmwave_control_commands": {"controlID": cmd_string}})
            )
            socketio.emit('command_ack', {'command': cmd_string, 'status': 'sent'}, to=sid)
        else:
            socketio.emit('command_error', {'error': f'Unknown command: {cmd_action}'}, to=sid)

    def force_sync(self, sid):
        with session_topics_lock:
            topic = session_topics.get(sid)
        if not topic:
            return  # No device selected yet — silent, expected on page load

        if not self.mqtt_connected:
            socketio.emit('command_error', {'error': 'MQTT broker is not connected'}, to=sid)
            return

        with self.device_list_lock:
            device_data = next(
                (d for d in self.device_list.values() if d['topic'] == topic), None
            )
            if device_data:
                cached = {
                    'zone_config':        dict(device_data.get('zone_config', {})),
                    'interference_zones': list(device_data.get('interference_zones', [])),
                    'detection_zones':    list(device_data.get('detection_zones', [])),
                    'stay_zones':         list(device_data.get('stay_zones', [])),
                }

        if device_data:
            socketio.emit('zone_config',        {'topic': topic, 'payload': cached['zone_config']},        to=sid)
            socketio.emit('interference_zones', {'topic': topic, 'payload': cached['interference_zones']}, to=sid)
            socketio.emit('detection_zones',    {'topic': topic, 'payload': cached['detection_zones']},    to=sid)
            socketio.emit('stay_zones',         {'topic': topic, 'payload': cached['stay_zones']},         to=sid)

        # Request a fresh state dump and zone report from the switch
        get_payload = {
            "state": "", "occupancy": "", "illuminance": "",
            "mmWaveDepthMax": "", "mmWaveDepthMin": "",
            "mmWaveWidthMax": "", "mmWaveWidthMin": "",
            "mmWaveHeightMax": "", "mmWaveHeightMin": "",
            "mmWaveDetectSensitivity": "", "mmWaveDetectTrigger": "",
            "mmWaveHoldTime": "", "mmWaveStayLife": "",
            "mmWaveRoomSizePreset": "", "mmWaveTargetInfoReport": "",
            "mmWaveVersion": "", "mmwaveControlWiredDevice": ""
        }
        self._client.publish(f"{topic}/get", json.dumps(get_payload))
        self._client.publish(
            f"{topic}/set",
            json.dumps({"mmwave_control_commands": {"controlID": "query_areas"}})
        )
        print(f"Z2M force_sync sent to {topic}", flush=True)

    # --- MQTT callbacks ---

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.mqtt_connected = True
            print("MQTT: connected to broker.", flush=True)
            client.subscribe(f"{MQTT_BASE_TOPIC}/#")
            socketio.emit('mqtt_status', {'connected': True})
        else:
            self.mqtt_connected = False
            print(f"MQTT: connection failed (rc={rc}).", flush=True)
            socketio.emit('mqtt_status', {'connected': False, 'error': f'Connection code: {rc}'})

    def _on_disconnect(self, client, userdata, rc):
        self.mqtt_connected = False
        print(f"MQTT: disconnected from broker (rc={rc}).", flush=True)
        socketio.emit('mqtt_status', {'connected': False, 'error': 'Broker disconnected'})

    def _on_message(self, client, userdata, msg):
        try:
            topic       = msg.topic
            payload_str = msg.payload.decode().strip()
            if not payload_str:
                return
            try:
                payload = json.loads(payload_str)
            except json.JSONDecodeError:
                return
            if topic == f"{MQTT_BASE_TOPIC}/bridge/devices" and isinstance(payload, list):
                self._remember_ieee(payload)
                return
            if not isinstance(payload, dict):
                return
            if topic == f"{MQTT_BASE_TOPIC}/bridge/info":
                # bridge/info also carries the network key; keep only the version bits
                self.bridge_info = diagnostics.z2m_bridge_summary(payload)
                return

            # --- Device discovery ---
            try:
                # Z2M echoes the full device state (including mmWaveVersion)
                # on …/get and …/set response topics.  Exclude those so we
                # only discover devices from their base topic publish.
                if (
                    topic.startswith(MQTT_BASE_TOPIC)
                    and "mmWaveVersion" in payload
                    and not topic.endswith("/get")
                    and not topic.endswith("/set")
                ):
                    parts = topic.split('/')
                    if len(parts) >= 2:
                        fname = '/'.join(parts[1:])
                        with self.device_list_lock:
                            is_new = fname not in self.device_list
                            if is_new:
                                print(f"Z2M: discovered {fname}", flush=True)
                                self.device_list[fname] = {
                                    'friendly_name':      fname,
                                    'topic':              f"{MQTT_BASE_TOPIC}/{fname}",
                                    'interference_zones': [],
                                    'detection_zones':    [],
                                    'stay_zones':         [],
                                    'use_nested_area1':   False,
                                    'zone_config': {
                                        "x_min": -100, "x_max": 100,
                                        "y_min": 0,    "y_max": 600,
                                        "z_min": -300, "z_max": 300,
                                    },
                                    'last_update': 0,
                                    'last_seen':   time.time(),
                                }
                            else:
                                self.device_list[fname]['last_seen'] = time.time()
                        if is_new:
                            socketio.emit('device_list', self.get_device_list_snapshot())
            except Exception as e:
                print(f"Z2M: device discovery error for {topic}: {e}", flush=True)

            # --- Identify device ---
            # Exact topic only: <device>/set and <device>/get are this addon's own
            # commands echoed back by the broker (not switch state), and a prefix
            # match would also hand "Hall Switch 2" messages to "Hall Switch".
            with self.device_list_lock:
                fname = next(
                    (n for n, d in self.device_list.items() if topic == d['topic']),
                    None
                )
                if not fname:
                    return
                device_topic = self.device_list[fname]['topic']
                ring = self.packets.get(fname)
                if ring is None:
                    ring = self.packets[fname] = deque(maxlen=PACKET_RING)
                ring.append((time.time(), payload_str[:800]))

            # --- Raw ZCL byte packets (cluster 0xFC32) ---
            # Z2M 2.9+ publishes a top-level parsed `mmwave_targets` array
            # AND still leaves the raw ZCL bytes in numbered keys of the
            # same message. In 2.9 the byte layout at offset >=6 no longer
            # matches the legacy format, so decoding it yields garbage
            # coordinates. Worse, because it runs first it claims the 10 Hz
            # throttle slot and the correct parsed path (handled in
            # _process_state_update) gets silently dropped. Skip the raw
            # target decode whenever parsed targets are present and let the
            # parsed path be authoritative.
            has_parsed_targets = isinstance(payload.get("mmwave_targets"), list)
            is_raw = (payload.get("0") == 29 and payload.get("1") == 47 and payload.get("2") == 18)
            if is_raw:
                cmd_id = payload.get("4")
                if cmd_id == 1 and not has_parsed_targets:
                    try:
                        self._process_target_data(payload, fname, device_topic)
                    except Exception as e:
                        print(f"Z2M: target data error: {e}", flush=True)
                elif cmd_id in [2, 3, 4]:
                    try:
                        self._process_zone_report(payload, cmd_id, fname, device_topic)
                    except Exception as e:
                        print(f"Z2M: zone report error (cmd={cmd_id}): {e}", flush=True)

            # --- Standard Z2M state update ---
            try:
                self._process_state_update(payload, fname, device_topic)
            except Exception as e:
                print(f"Z2M: state update error for {fname}: {e}", flush=True)

        except Exception as e:
            print(f"Z2M: unhandled error on {msg.topic}: {e}", flush=True)
            traceback.print_exc()

    def _emit_targets(self, targets, fname, device_topic, seq):
        """
        Throttled emit of parsed target data on the 'new_data' socket event.
        Shared by both the raw-ZCL path (_process_target_data) and the parsed
        mmwave_targets path in _process_state_update, so a single 10 Hz cap
        applies across both in case a Z2M version emits both formats.
        """
        current_time = time.time()
        with self.device_list_lock:
            last_update = self.device_list.get(fname, {}).get('last_update', 0)
        if (current_time - last_update) < 0.1:
            return  # Throttle to ~10 Hz max
        with self.device_list_lock:
            if fname in self.device_list:
                self.device_list[fname]['last_update'] = current_time

        emit_to_topic_subscribers(
            'new_data',
            {'topic': device_topic, 'payload': {'seq': seq, 'targets': targets}},
            device_topic
        )

    def _process_target_data(self, payload, fname, device_topic):
        # Legacy raw-bytes path for pre-2.9 Z2M (no top-level mmwave_targets).
        # Each target is a 9-byte record matching the upstream Inovelli FC32
        # cluster reportTargetInfo command — x, y, z, dop as little-endian int16
        # followed by id as a signed int8. Inovelli's mmWave docs briefly listed
        # id as int16 (10-byte stride), which herdsman-converters PR #11915
        # (merged 2026-04-11) implemented and we mirrored in v3.2.4. Inovelli
        # later corrected the docs — id is int8 — and PR #12284 (merged
        # 2026-05-23) reverted Z2M back to the 9-byte stride. Mirror that
        # correction here so the raw fallback matches real device traffic.
        targets = decode_raw_targets(payload)
        if targets is None:
            return

        self._record_targets(fname, device_topic, targets, payload)
        self._emit_targets(targets, fname, device_topic, seq=payload.get("3"))

    def _record_targets(self, fname, device_topic, targets, payload):
        # Z2M re-publishes its cached state (old report included) on every other
        # attribute change; only a report that differs from the last one is new
        if not is_fresh_target_frame(payload, self._last_targets.get(fname)):
            return
        self._last_targets[fname] = target_frame_mark(payload)
        try:
            key = self.history_key_for(fname, device_topic)
            if key:
                history.on_targets(key, targets)
        except Exception as e:
            print(f"Z2M: history error: {e}", flush=True)

    def _record_state(self, fname, device_topic, payload):
        """Occupancy, area, light and target-report changes for the history timeline."""
        state = {}
        if 'occupancy' in payload:
            state['occupancy'] = payload['occupancy']
        for i in range(1, 5):
            k = f'mmwave_area{i}_occupancy'
            if k in payload:
                state[f'area{i}'] = payload[k]
        if 'state' in payload:
            state['light'] = payload['state']
        if 'mmWaveTargetInfoReport' in payload:
            state['reporting'] = payload['mmWaveTargetInfoReport']
        if not state:
            return
        try:
            key = self.history_key_for(fname, device_topic)
            if key:
                history.on_state(key, state)
        except Exception as e:
            print(f"Z2M: history error: {e}", flush=True)

    def _remember_facts(self, fname, payload):
        keep = {k: payload[k] for k in ('mmWaveVersion', 'linkquality', 'update', 'last_seen') if k in payload}
        settings = {k: v for k, v in payload.items()
                    if (k.startswith('mmWave') or k.startswith('mmwave')) and k != 'mmwave_targets'}
        with self.device_list_lock:
            facts = self._facts.setdefault(fname, {})
            facts.update(keep)
            facts.setdefault('state', {}).update(settings)

    def _process_zone_report(self, payload, cmd_id, fname, device_topic):
        zones = decode_raw_zones(payload)
        if zones is None:
            return

        event_map = {
            2: ('interference_zones', 'Interference'),
            3: ('detection_zones',    'Detection'),
            4: ('stay_zones',         'Stay'),
        }
        event_name, zone_label = event_map[cmd_id]

        with self.device_list_lock:
            if fname in self.device_list:
                self.device_list[fname][event_name] = zones

        emit_to_topic_subscribers(event_name, {'topic': device_topic, 'payload': zones}, device_topic)
        print(f"Z2M: {zone_label} zones updated ({sum(1 for z in zones if z)} active).", flush=True)

    def _process_state_update(self, payload, fname, device_topic):
        config_payload = {k: v for k, v in payload.items() if not k.isdigit()}
        if not config_payload:
            return

        self._record_state(fname, device_topic, config_payload)
        self._remember_facts(fname, config_payload)
        emit_to_topic_subscribers('device_config', {'topic': device_topic, 'payload': config_payload}, device_topic)

        # Parsed target info (Z2M 2.9.x+ — issue #27). Older Z2M publishes
        # raw ZCL bytes handled in _process_target_data; newer Z2M parses
        # cluster 0xFC32 target reports into a top-level mmwave_targets array
        # with shape [{id, x, y, z, dop}, ...] — exactly what the frontend
        # expects. _emit_targets applies the shared 10 Hz throttle so we
        # don't double-emit if a Z2M version sends both formats.
        parsed_targets = config_payload.get("mmwave_targets")
        if isinstance(parsed_targets, list):
            self._record_targets(fname, device_topic, parsed_targets, payload)
            self._emit_targets(parsed_targets, fname, device_topic, seq=None)

        zone_snapshot = None
        needs_emit    = False

        with self.device_list_lock:
            if fname not in self.device_list:
                return

            # Detect whether this firmware uses nested area1 or flat top-level attributes
            if "mmwave_detection_areas" in config_payload:
                areas    = config_payload["mmwave_detection_areas"]
                has_data = False
                if isinstance(areas, dict):
                    a1 = areas.get("area1")
                    if isinstance(a1, dict):
                        has_data = any(
                            isinstance(v, (int, float)) and v != 0
                            for v in a1.values()
                        )
                self.device_list[fname]['use_nested_area1'] = has_data

            current_zone = self.device_list[fname]['zone_config']
            field_map = {
                "mmWaveWidthMin":  "x_min", "mmWaveWidthMax":  "x_max",
                "mmWaveDepthMin":  "y_min", "mmWaveDepthMax":  "y_max",
                "mmWaveHeightMin": "z_min", "mmWaveHeightMax": "z_max",
            }
            for mqtt_key, zone_key in field_map.items():
                if mqtt_key in config_payload:
                    current_zone[zone_key] = safe_int(config_payload[mqtt_key])
                    needs_emit = True

            if needs_emit:
                self.device_list[fname]['zone_config'] = current_zone
                zone_snapshot = dict(current_zone)

        if needs_emit and zone_snapshot:
            emit_to_topic_subscribers('zone_config', {'topic': device_topic, 'payload': zone_snapshot}, device_topic)

    def _cleanup_loop(self):
        """Remove devices not seen for over 1 hour."""
        while True:
            time.sleep(60)
            current_time = time.time()
            with self.device_list_lock:
                stale = [k for k, v in self.device_list.items()
                         if (current_time - v.get('last_seen', 0)) > 3600]
                for key in stale:
                    del self.device_list[key]
            if stale:
                socketio.emit('device_list', self.get_device_list_snapshot())


# ===========================================================================
# ZHA DRIVER
# Thin wrapper around ZHAClient. Exposes the same interface as Z2MDriver.
# ===========================================================================

class ZHADriver:

    def __init__(self):
        from zha_client import ZHAClient
        self._zha = ZHAClient(HA_URL, HA_TOKEN, socketio, debug=DEBUG, history=history,
                              history_key=history_key)
        self._attrs = {}       # ieee → attributes read from the switch (cached; they're radio reads)
        self._attrs_lock = threading.Lock()

    def start(self):
        self._zha.start()

    def get_device_list_snapshot(self):
        # Return copies so callers cannot mutate internal state. list() first:
        # the listener thread can change the dict while a page asks for it.
        return [dict(d) for d in list(self._zha.device_list.values())]

    def device_facts(self, topic, force=False):
        """(ieee, zha/device info, attributes read from the switch) for device_info."""
        ieee = self._topic_to_ieee(topic) if isinstance(topic, str) else None
        if not ieee or not HA_TOKEN:
            return ieee, {}, {}
        zha_dev = {}
        with self._attrs_lock:
            attrs = None if force else self._attrs.get(ieee)
        try:
            with ha_ws.HAConnection(HA_TOKEN, HA_WS_URL) as ha:
                zha_dev = ha.request('zha/device', ieee=ieee) or {}
                if attrs is None:
                    attrs = {}
                    complete = True
                    for name, cluster, attr, manufacturer in (
                            ('mmwave_version', 0xFC32, 0x0073, 0x122F),
                            ('sw_build_id', 0x0000, 0x4000, None)):
                        req = {'ieee': ieee, 'endpoint_id': 1, 'cluster_id': cluster,
                               'cluster_type': 'in', 'attribute': attr}
                        if manufacturer:
                            req['manufacturer'] = manufacturer
                        try:
                            attrs[name] = ha.request('zha/devices/clusters/attributes/value', **req)
                        except ha_ws.HAError as e:
                            print(f"ZHA: couldn't read {name} from {ieee}: {e}", flush=True)
                            complete = False
                        if attrs.get(name) in (None, '', 'None'):   # the switch didn't answer
                            complete = False
                    # Only keep a full answer; a missed read is tried again next time
                    if complete:
                        with self._attrs_lock:
                            self._attrs[ieee] = attrs
        except ha_ws.HAError as e:
            print(f"ZHA: device info for {ieee} failed: {e}", flush=True)
        dev = self._zha.device_list.get(ieee) or {}
        if not zha_dev.get('sw_version') and dev.get('sw_version'):
            zha_dev['sw_version'] = dev['sw_version']
        return ieee, zha_dev, attrs or {}

    def diagnostics_parts(self, topic):
        ieee = self._topic_to_ieee(topic) if isinstance(topic, str) else None
        dev = json.loads(json.dumps(self._zha.device_list.get(ieee) or {}, default=str))
        states = {role: st for (i, role), st in list(self._zha._entity_state.items()) if i == ieee}
        return {
            'driver': {'stack': 'zha', 'connected': self._zha._ws is not None, 'watched': self._zha._ieee,
                       'switches': len(self._zha.device_list),
                       'entity_subscription': len(self._zha._entity_index)},
            'stack_versions': None,
            'device': dev, 'settings': states, 'packets': list(self._zha.packets.get(ieee) or []),
        }

    def set_device(self, sid, new_topic):
        with session_topics_lock:
            session_topics[sid] = new_topic
        ieee = self._topic_to_ieee(new_topic)
        if ieee:
            self._zha.set_device(ieee, new_topic, sid=sid)
        else:
            print(f"ZHA: unknown topic {new_topic}", flush=True)

    def _target_session_device(self, sid):
        """IEEE of the switch this browser has selected, made the monitored one.

        ZHAClient watches a single switch for every browser, and its writes go to
        that switch. If another browser has since selected a different one, point
        it back at this browser's switch so a command never lands on the wrong device.
        Returns None (after telling the browser) when no known switch is selected.
        """
        with session_topics_lock:
            topic = session_topics.get(sid)
        if not topic:
            socketio.emit('command_error', {'error': 'No device selected'}, to=sid)
            return None
        ieee = self._topic_to_ieee(topic)
        if not ieee or ieee not in self._zha.device_list:
            socketio.emit('command_error', {'error': 'Device not found'}, to=sid)
            return None
        if self._zha._ieee != ieee:
            self._zha.set_device(ieee, topic, sid=sid)
        return ieee

    def update_parameter(self, sid, param, value):
        is_valid, error_msg = validate_parameter(param, value)
        if not is_valid:
            socketio.emit('command_error', {'error': error_msg}, to=sid)
            return
        if not self._target_session_device(sid):
            return
        self._zha.update_parameter(param, value)
        socketio.emit('command_ack', {'param': param, 'status': 'sent'}, to=sid)

    def send_command(self, sid, cmd_action):
        if not self._target_session_device(sid):
            return
        try:
            self._zha.send_control_command(int(cmd_action))
            socketio.emit('command_ack', {'command': cmd_action, 'status': 'sent'}, to=sid)
        except Exception as e:
            socketio.emit('command_error', {'error': str(e)}, to=sid)

    def force_sync(self, sid):
        with session_topics_lock:
            topic = session_topics.get(sid)
        if not topic:
            return  # No device selected yet — silent, expected on page load
        if not self._target_session_device(sid):
            return
        self._zha.force_sync(sid=sid)

    def ieee_for_topic(self, topic):
        return self._topic_to_ieee(topic) if isinstance(topic, str) else None

    def _topic_to_ieee(self, topic: str):
        """Reverse-lookup IEEE address from a zha/<ieee> topic string."""
        for ieee, dev in self._zha.device_list.items():
            if dev.get('topic') == topic:
                return ieee
        # Direct parse as fallback
        if topic.startswith("zha/"):
            return topic[4:]
        return None


# ===========================================================================
# Debug-aware socket.io emit wrapper
#
# Intercepts every socketio.emit call and prints a truncated preview when
# debug=true. Wrapping at this level means all emits from both drivers are
# covered without modifying individual call sites.
# ===========================================================================

_original_socketio_emit = socketio.emit

def _debug_emit(event, data=None, **kwargs):
    if DEBUG:
        try:
            preview = json.dumps(data, default=str)
            if len(preview) > 300:
                preview = preview[:300] + "..."
        except Exception:
            preview = str(data)[:300]
        print(f"[DEBUG] emit → {event}: {preview}", flush=True)
    return _original_socketio_emit(event, data, **kwargs)

socketio.emit = _debug_emit


# ===========================================================================
# Driver instantiation
# ===========================================================================

if ZIGBEE_STACK == 'zha':
    driver = ZHADriver()
else:
    if ZIGBEE_STACK != 'z2m':
        print(f"Warning: unknown zigbee_stack '{ZIGBEE_STACK}', defaulting to z2m.", flush=True)
    driver = Z2MDriver()

history.start()
driver.start()


def _shutdown(signum, frame):
    """Addon stop: write out the history still in memory, then exit."""
    try:
        history.close()
    except Exception as e:
        print(f"History: couldn't save on shutdown ({e})", flush=True)
    os._exit(0)


try:
    signal.signal(signal.SIGTERM, _shutdown)
except ValueError:   # not the main thread (e.g. imported by a tool)
    pass


# ===========================================================================
# Z-Wave JS packet capture (diagnostic, independent of zigbee_stack)
# ===========================================================================

def _read_addon_version():
    # config.yaml is copied into the image alongside app.py
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.yaml'),
                  encoding='utf-8') as f:
            for line in f:
                if line.startswith('version:'):
                    return line.split(':', 1)[1].strip().strip('"\'')
    except OSError:
        pass
    return 'unknown'

ADDON_VERSION = _read_addon_version()

from zwave_capture import ZWaveCapture
zwave_capture = ZWaveCapture(HA_URL, HA_TOKEN, socketio, addon_version=ADDON_VERSION)


# ===========================================================================
# Flask-SocketIO handlers — stack-agnostic
# ===========================================================================

@socketio.on('connect')
def handle_connect(auth=None):
    # python-socketio >= 5.7 passes an `auth` positional arg to the connect
    # handler. Older versions don't. Accept it optionally for compatibility
    # with both — the value is unused (ingress handles auth upstream).
    # For ZHA we send optimistic connected=True; ZHAClient will correct it
    # via a mqtt_status emit if the WebSocket is actually down.
    is_connected = True if ZIGBEE_STACK == 'zha' else driver.mqtt_connected
    emit('mqtt_status', {'connected': is_connected})
    emit('device_list', driver.get_device_list_snapshot())
    emit('stack_info',  {'stack': ZIGBEE_STACK})


@socketio.on('disconnect')
def handle_disconnect():
    with session_topics_lock:
        session_topics.pop(request.sid, None)


@socketio.on('request_devices')
def handle_request_devices():
    emit('device_list', driver.get_device_list_snapshot())


def _layout_key(topic):
    # By IEEE address when known, so a layout survives renaming the switch
    return layout_key(topic, driver.ieee_for_topic(topic))


def _get_layout(topic):
    layout = layout_store.get(_layout_key(topic))
    # A layout saved before Z2M told us the switch's IEEE address is under its topic
    return layout if layout is not None else layout_store.get(topic)


def _get_zone_names(topic):
    names = zone_name_store.get(_layout_key(topic))
    return names if names is not None else zone_name_store.get(topic)


_device_info_cache = {}


def build_device_info(topic, force=False):
    """Firmware, link quality, update and HA entities for one switch (slow: HA round trips)."""
    if ZIGBEE_STACK == 'zha':
        ieee, zha_dev, attrs = driver.device_facts(topic, force)
        info = device_info.zha_info(ieee, zha_dev, attrs)
    else:
        ieee, entry, facts, last_seen = driver.device_facts(topic)
        info = device_info.z2m_info(ieee, entry, facts, last_seen)
    reg = registry.lookup(ieee, force=force) if ieee else None
    update_entity = ((reg or {}).get('roles') or {}).get('update')
    update_state = ha_ws.rest_state(HA_TOKEN, update_entity) if update_entity else None
    device_info.apply_registry(info, reg, update_state)
    info['topic'] = topic
    info['ha_available'] = bool(HA_TOKEN)
    info['ha_error'] = registry.error
    _device_info_cache[topic] = info
    return info


def _send_device_info(sid, topic, force=False):
    try:
        info = build_device_info(topic, force)
    except Exception as e:
        print(f"Device info for {topic} failed: {e}", flush=True)
        traceback.print_exc()
        return
    socketio.emit('device_info', info, to=sid)


@socketio.on('change_device')
def handle_change_device(new_topic):
    driver.set_device(request.sid, new_topic)
    if isinstance(new_topic, str) and new_topic:
        emit('layout', {'topic': new_topic, 'layout': _get_layout(new_topic)})
        emit('zone_names', {'topic': new_topic, 'names': _get_zone_names(new_topic)})
        socketio.start_background_task(_send_device_info, request.sid, new_topic)


@socketio.on('refresh_device_info')
def handle_refresh_device_info(topic):
    if isinstance(topic, str) and topic:
        socketio.start_background_task(_send_device_info, request.sid, topic, True)


@socketio.on('save_zone_names')
def handle_save_zone_names(data):
    """Zone names (display only). The return value is the acknowledgement."""
    if not isinstance(data, dict) or not isinstance(data.get('topic'), str) or not data['topic']:
        return {'error': 'Zone names need a switch'}
    topic = data['topic']
    names, error = normalize_zone_names(data.get('names'))
    if error:
        return {'error': error}
    key = _layout_key(topic)
    error = zone_name_store.set(key, names)
    if error:
        return {'error': error}
    if key != topic and zone_name_store.get(topic) is not None:
        zone_name_store.set(topic, None)
    emit_to_topic_subscribers('zone_names', {'topic': topic, 'names': names}, topic, skip_sid=request.sid)
    ack = {'ok': True, 'names': names}
    if zone_name_store.write_error:
        ack['warning'] = zone_name_store.write_error
    return ack


# --- History (heat map + timeline) ---

def _history_key_for_topic(topic):
    if not isinstance(topic, str) or not topic:
        return None
    return history_key(topic, driver.ieee_for_topic(topic))


def _number(value, default=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
        return default
    return value


@socketio.on('get_history_settings')
def handle_get_history_settings(data=None):
    return history.settings()


@socketio.on('set_history_settings')
def handle_set_history_settings(data):
    if not isinstance(data, dict):
        return {'error': 'Bad settings'}
    enabled = data.get('enabled') if isinstance(data.get('enabled'), bool) else None
    days = _number(data.get('days'))
    result = history.set_settings(enabled=enabled, days=int(days) if days is not None else None)
    socketio.emit('history_settings', result)
    return result


@socketio.on('history_stats')
def handle_history_stats(topic):
    stats = history.stats(_history_key_for_topic(topic))
    stats['has_ieee'] = bool(isinstance(topic, str) and driver.ieee_for_topic(topic))
    return stats


@socketio.on('get_heatmap')
def handle_get_heatmap(data):
    if not isinstance(data, dict):
        return {'error': 'Bad request'}
    t0, t1 = _number(data.get('from')), _number(data.get('to'))
    if t0 is None or t1 is None or t1 <= t0:
        return {'error': 'Pick a time range'}
    return history.heatmap(_history_key_for_topic(data.get('topic')), t0, t1)


@socketio.on('get_events')
def handle_get_events(data):
    if not isinstance(data, dict):
        return {'error': 'Bad request'}
    t0, t1 = _number(data.get('from')), _number(data.get('to'))
    if t0 is None or t1 is None:
        return {'error': 'Pick a time range'}
    return {'events': history.events(_history_key_for_topic(data.get('topic')), t0, t1)}


@socketio.on('get_clip')
def handle_get_clip(data):
    if not isinstance(data, dict) or _number(data.get('t')) is None:
        return {'error': 'Bad request'}
    return {'clip': history.clip(_history_key_for_topic(data.get('topic')), data['t'])}


@socketio.on('clear_history')
def handle_clear_history(topic):
    key = _history_key_for_topic(topic)
    if not key:
        return {'error': 'No switch selected'}
    history.clear(key)
    return {'ok': True}


@socketio.on('save_layout')
def handle_save_layout(data):
    """Save where a switch sits in its room (display only). A null layout removes it.

    The return value is the socket.io acknowledgement the page waits for.
    Other pages watching the same switch get the new layout straight away.
    """
    if not isinstance(data, dict):
        return {'error': 'Bad layout message'}
    topic = data.get('topic')
    if not isinstance(topic, str) or not topic:
        return {'error': 'Layout needs a switch'}
    layout = None
    if data.get('layout') is not None:
        layout, error = normalize_layout(data['layout'])
        if error:
            return {'error': error}
    key = _layout_key(topic)
    error = layout_store.set(key, layout)
    if error:
        return {'error': error}
    if key != topic and layout_store.get(topic) is not None:
        layout_store.set(topic, None)   # moved to the IEEE key
    emit_to_topic_subscribers('layout', {'topic': topic, 'layout': layout}, topic, skip_sid=request.sid)
    ack = {'ok': True, 'layout': layout}
    if layout_store.write_error:
        ack['warning'] = layout_store.write_error
    return ack


@socketio.on('update_parameter')
def handle_update_parameter(data):
    driver.update_parameter(request.sid, data.get('param'), data.get('value'))


@socketio.on('send_command')
def handle_command(cmd_action):
    driver.send_command(request.sid, cmd_action)


@socketio.on('force_sync')
def handle_force_sync():
    driver.force_sync(request.sid)


@socketio.on('zwave_capture_start')
def handle_zwave_capture_start():
    zwave_capture.start()


@socketio.on('zwave_capture_stop')
def handle_zwave_capture_stop():
    zwave_capture.stop()


@socketio.on('zwave_capture_status')
def handle_zwave_capture_status():
    emit('zwave_capture_status', zwave_capture.status())


# ===========================================================================
# Flask route
# ===========================================================================

@app.route('/')
def index():
    return render_template(
        'index.html',
        ingress_path=request.headers.get('X-Ingress-Path', ''),
        zigbee_stack=ZIGBEE_STACK,
        version=ADDON_VERSION,
    )


@app.route('/diagnostics')
def diagnostics_download():
    """Everything about the selected switch and the addon for a bug report (secrets removed)."""
    topic = request.args.get('topic') or ''
    parts = driver.diagnostics_parts(topic) if topic else {'driver': None, 'device': None,
                                                           'settings': None, 'packets': [], 'stack_versions': None}
    ha_config = ha_ws.rest_get(HA_TOKEN, '/config') if HA_TOKEN else None
    stack_versions = dict(parts.get('stack_versions') or {})
    if isinstance(ha_config, dict):
        stack_versions['home_assistant'] = ha_config.get('version')
    device = parts.get('device') or {}
    info = _device_info_cache.get(topic)
    report = diagnostics.build_report(
        addon={'version': ADDON_VERSION, 'stack': ZIGBEE_STACK, 'python': sys.version.split()[0],
               'debug': DEBUG, 'home_assistant_api': bool(HA_TOKEN)},
        options={k: v for k, v in config.items()},
        stack_versions=stack_versions,
        driver=parts.get('driver'),
        device={'selected': topic, 'entry': device, 'info': info},
        zones={k: device.get(k) for k in ('detection_zones', 'interference_zones', 'stay_zones')},
        settings=parts.get('settings'),
        layout=_get_layout(topic) if topic else None,
        zone_names=_get_zone_names(topic) if topic else None,
        history=history.stats(_history_key_for_topic(topic)) if topic else history.settings(),
        packets=parts.get('packets'),
        log_lines=logtap.lines(600),
    )
    stamp = time.strftime('%Y%m%d_%H%M%S', time.gmtime())
    return Response(
        json.dumps(report, indent=1, default=str),
        mimetype='application/json',
        headers={'Content-Disposition': f'attachment; filename="mmwave_vis_diagnostics_{stamp}.json"',
                 'Cache-Control': 'no-store'},
    )


@app.route('/zwave_capture.log')
def zwave_capture_download():
    text = zwave_capture.export_text()
    if text is None:
        return Response("No finished Z-Wave capture to download.", status=404, mimetype='text/plain')
    return Response(
        text,
        mimetype='text/plain',
        headers={'Content-Disposition': f'attachment; filename="{zwave_capture.export_filename()}"'},
    )


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)