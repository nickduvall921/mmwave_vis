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
import traceback
import time
import threading
from flask import Flask, render_template, request
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

ZIGBEE_STACK    = config.get('zigbee_stack', 'z2m').lower().strip()
DEBUG           = bool(config.get('debug', False))
MQTT_BROKER     = config.get('mqtt_broker', 'core-mosquitto')
MQTT_PORT       = int(config.get('mqtt_port', 1883))
MQTT_USERNAME   = config.get('mqtt_username', '')
MQTT_PASSWORD   = config.get('mqtt_password', '')
MQTT_BASE_TOPIC = config.get('mqtt_base_topic', 'zigbee2mqtt')
HA_URL          = config.get('ha_url', 'http://supervisor')

# SUPERVISOR_TOKEN is auto-injected by HA when homeassistant_api: true is set
# in config.yaml. The ha_token config field is a manual fallback — generate a
# long-lived access token from your HA profile page if needed.
_supervisor_token = os.environ.get('SUPERVISOR_TOKEN', '')
_config_token     = config.get('ha_token', '')
HA_TOKEN          = _supervisor_token or _config_token

# ---------------------------------------------------------------------------
# Startup diagnostics
# ---------------------------------------------------------------------------
print(f"Zigbee stack : {ZIGBEE_STACK}", flush=True)
print(f"Debug mode   : {'ON' if DEBUG else 'OFF'}", flush=True)

if ZIGBEE_STACK == 'zha':
    print(f"ZHA ha_url   : {HA_URL}", flush=True)
    if _supervisor_token:
        if DEBUG:
            print(f"ZHA token    : SUPERVISOR_TOKEN (len={len(_supervisor_token)}, "
                  f"first6={_supervisor_token[:6]}, last6={_supervisor_token[-6:]})", flush=True)
        else:
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
    validate_parameter, safe_int, parse_signed_16,
)


# ---------------------------------------------------------------------------
# Helpers shared by both stacks
# ---------------------------------------------------------------------------

def get_sessions_for_topic(topic):
    with session_topics_lock:
        return [sid for sid, t in session_topics.items() if t == topic]


def emit_to_topic_subscribers(event, data, topic):
    """Emit a socket.io event to all sessions currently watching a given device."""
    for sid in get_sessions_for_topic(topic):
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

        self._client = mqtt.Client()
        if MQTT_USERNAME and MQTT_PASSWORD:
            self._client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
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
            if not isinstance(payload, dict):
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
            with self.device_list_lock:
                fname = next(
                    (n for n, d in self.device_list.items() if topic.startswith(d['topic'])),
                    None
                )
                if not fname:
                    return
                device_topic = self.device_list[fname]['topic']

            # --- Raw ZCL byte packets (cluster 0xFC32) ---
            is_raw = (payload.get("0") == 29 and payload.get("1") == 47 and payload.get("2") == 18)
            if is_raw:
                cmd_id = payload.get("4")
                if cmd_id == 1:
                    try:
                        self._process_target_data(payload, fname, device_topic)
                    except Exception as e:
                        print(f"Z2M: target data error: {e}", flush=True)
                elif cmd_id in [2, 3, 4]:
                    try:
                        self._process_zone_report(payload, cmd_id, fname, device_topic)
                    except Exception as e:
                        print(f"Z2M: zone report error (cmd={cmd_id}): {e}", flush=True)

            # --- Modern Z2M target payload (already parsed by converters) ---
            if "mmwave_targets" in payload:
                try:
                    self._process_mmwave_targets(payload.get("mmwave_targets"), fname, device_topic)
                except Exception as e:
                    print(f"Z2M: mmwave_targets error: {e}", flush=True)

            # --- Standard Z2M state update ---
            try:
                self._process_state_update(payload, fname, device_topic)
            except Exception as e:
                print(f"Z2M: state update error for {fname}: {e}", flush=True)

        except Exception as e:
            print(f"Z2M: unhandled error on {msg.topic}: {e}", flush=True)
            traceback.print_exc()

    def _emit_target_data(self, fname, device_topic, targets, seq=None):
        current_time = time.time()
        with self.device_list_lock:
            last_update = self.device_list.get(fname, {}).get('last_update', 0)
        if (current_time - last_update) < 0.1:
            return  # Throttle to ~10 Hz max
        with self.device_list_lock:
            if fname in self.device_list:
                self.device_list[fname]['last_update'] = current_time

        event_payload = {"targets": targets}
        if seq is not None:
            event_payload["seq"] = seq

        emit_to_topic_subscribers(
            'new_data',
            {'topic': device_topic, 'payload': event_payload},
            device_topic
        )

    def _process_target_data(self, payload, fname, device_topic):
        num_targets = safe_int(payload.get("5"), 0)
        if not (0 <= num_targets <= 10):
            return

        targets = []
        offset  = 6
        for _ in range(num_targets):
            if str(offset + 8) not in payload:
                break
            targets.append({
                "id":  safe_int(payload.get(str(offset + 8)), 0),
                "x":   parse_signed_16(payload, offset),
                "y":   parse_signed_16(payload, offset + 2),
                "z":   parse_signed_16(payload, offset + 4),
                "dop": parse_signed_16(payload, offset + 6),
            })
            offset += 9

        self._emit_target_data(fname, device_topic, targets, seq=payload.get("3"))

    def _process_mmwave_targets(self, mmwave_targets, fname, device_topic):
        if not isinstance(mmwave_targets, list):
            return

        targets = []
        for target in mmwave_targets:
            if not isinstance(target, dict):
                continue
            targets.append({
                "id":  safe_int(target.get("id"), 0),
                "x":   safe_int(target.get("x"), 0),
                "y":   safe_int(target.get("y"), 0),
                "z":   safe_int(target.get("z"), 0),
                "dop": safe_int(target.get("dop"), 0),
            })
            if len(targets) >= 10:
                break

        self._emit_target_data(fname, device_topic, targets)

    def _process_zone_report(self, payload, cmd_id, fname, device_topic):
        num_zones = safe_int(payload.get("5"), 0)
        if not (0 <= num_zones <= 10):
            return

        zones  = []
        offset = 6
        for _ in range(num_zones):
            if str(offset + 11) not in payload:
                break
            x_min = parse_signed_16(payload, offset)
            x_max = parse_signed_16(payload, offset + 2)
            y_min = parse_signed_16(payload, offset + 4)
            y_max = parse_signed_16(payload, offset + 6)
            z_min = parse_signed_16(payload, offset + 8)
            z_max = parse_signed_16(payload, offset + 10)
            if x_max != 0 or x_min != 0 or y_max != 0 or y_min != 0:
                zones.append({
                    "x_min": x_min, "x_max": x_max,
                    "y_min": y_min, "y_max": y_max,
                    "z_min": z_min, "z_max": z_max,
                })
            offset += 12

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
        print(f"Z2M: {zone_label} zones updated ({len(zones)} active).", flush=True)

    def _process_state_update(self, payload, fname, device_topic):
        config_payload = {k: v for k, v in payload.items() if not k.isdigit()}
        if not config_payload:
            return

        emit_to_topic_subscribers('device_config', {'topic': device_topic, 'payload': config_payload}, device_topic)

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
        self._zha = ZHAClient(HA_URL, HA_TOKEN, socketio, debug=DEBUG)

    def start(self):
        self._zha.start()

    def get_device_list_snapshot(self):
        # Return copies so callers cannot mutate internal state
        return [dict(d) for d in self._zha.device_list.values()]

    def set_device(self, sid, new_topic):
        with session_topics_lock:
            session_topics[sid] = new_topic
        ieee = self._topic_to_ieee(new_topic)
        if ieee:
            self._zha.set_device(ieee, new_topic, sid=sid)
        else:
            print(f"ZHA: unknown topic {new_topic}", flush=True)

    def update_parameter(self, sid, param, value):
        with session_topics_lock:
            topic = session_topics.get(sid)
        if not topic:
            socketio.emit('command_error', {'error': 'No device selected'}, to=sid)
            return
        is_valid, error_msg = validate_parameter(param, value)
        if not is_valid:
            socketio.emit('command_error', {'error': error_msg}, to=sid)
            return
        self._zha.update_parameter(param, value)
        socketio.emit('command_ack', {'param': param, 'status': 'sent'}, to=sid)

    def send_command(self, sid, cmd_action):
        with session_topics_lock:
            topic = session_topics.get(sid)
        if not topic:
            socketio.emit('command_error', {'error': 'No device selected'}, to=sid)
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
        ieee = self._topic_to_ieee(topic)
        if not ieee:
            socketio.emit('command_error', {'error': 'Device not found'}, to=sid)
            return
        self._zha.force_sync(sid=sid)

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

driver.start()


# ===========================================================================
# Flask-SocketIO handlers — stack-agnostic
# ===========================================================================

@socketio.on('connect')
def handle_connect():
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


@socketio.on('change_device')
def handle_change_device(new_topic):
    driver.set_device(request.sid, new_topic)


@socketio.on('update_parameter')
def handle_update_parameter(data):
    driver.update_parameter(request.sid, data.get('param'), data.get('value'))


@socketio.on('send_command')
def handle_command(cmd_action):
    driver.send_command(request.sid, cmd_action)


@socketio.on('force_sync')
def handle_force_sync():
    driver.force_sync(request.sid)


# ===========================================================================
# Flask route
# ===========================================================================

@app.route('/')
def index():
    return render_template(
        'index.html',
        ingress_path=request.headers.get('X-Ingress-Path', ''),
        zigbee_stack=ZIGBEE_STACK,
    )


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)