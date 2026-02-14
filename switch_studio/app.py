"""
Inovelli Switch Studio Backend
Provides a real-time MQTT-to-WebSocket bridge for Home Assistant Ingress.
Handles device discovery, Zigbee byte array decoding, and two-way configuration.
"""

import json
import os
import traceback
import time
import threading 
import copy
import hashlib
from flask import Flask, render_template, request
from flask_socketio import SocketIO
import paho.mqtt.client as mqtt
import logging
try:
    from .schema_service import SchemaService
except ImportError:
    from schema_service import SchemaService

# Suppress the Werkzeug development server warning
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# --- LOAD HOME ASSISTANT CONFIGURATION ---
CONFIG_PATH = '/data/options.json'
MQTT_CONNACK_REASON = {
    0: "Connection accepted",
    1: "Unacceptable protocol version",
    2: "Identifier rejected",
    3: "Server unavailable",
    4: "Bad username or password",
    5: "Not authorized",
}
TEST_MODE = str(os.environ.get("SWITCH_STUDIO_TEST_MODE", "")).strip().lower() in {"1", "true", "yes", "on"}


def _config_first(config_obj, keys, default_value):
    for key in keys:
        if key in config_obj and config_obj.get(key) is not None:
            return config_obj.get(key)
    return default_value


def _file_sha256_prefix(path, length=12):
    try:
        with open(path, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        return digest[:length]
    except Exception:
        return "unavailable"


def _as_int_or_none(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped == "":
            return None
        try:
            return int(stripped)
        except ValueError:
            try:
                return int(float(stripped))
            except ValueError:
                return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value, default=False):
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return bool(default)


def _normalize_basic_state(value):
    if isinstance(value, bool):
        return 'ON' if value else 'OFF', None

    if isinstance(value, (int, float)):
        return ('ON' if int(value) != 0 else 'OFF'), None

    if isinstance(value, str):
        normalized = value.strip().upper()
        if normalized in {'ON', 'OFF', 'TOGGLE'}:
            return normalized, None
        if normalized in {'TRUE', 'YES', '1'}:
            return 'ON', None
        if normalized in {'FALSE', 'NO', '0'}:
            return 'OFF', None

    return None, "State must be ON, OFF, TOGGLE, or a boolean"


def _normalize_basic_brightness(value):
    parsed = _as_int_or_none(value)
    if parsed is None:
        return None, "Brightness must be a numeric value from 0 to 254"

    if parsed < 0:
        parsed = 0
    if parsed > 254:
        parsed = 254
    return parsed, None

try:
    with open(CONFIG_PATH) as f:
        config = json.load(f)
        MQTT_BROKER = _config_first(config, ['mqtt_broker', 'broker', 'host'], 'core-mosquitto')
        MQTT_PORT = int(_config_first(config, ['mqtt_port', 'port'], 1883))
        MQTT_USERNAME = str(_config_first(config, ['mqtt_username', 'mqtt_user', 'username'], '') or '')
        MQTT_PASSWORD = str(_config_first(config, ['mqtt_password', 'mqtt_pass', 'password'], '') or '')
        MQTT_BASE_TOPIC = str(_config_first(config, ['mqtt_base_topic', 'base_topic'], 'zigbee2mqtt') or 'zigbee2mqtt')
        SWITCH_STUDIO_UI = _as_bool(_config_first(config, ['switch_studio_ui'], True), True)
except FileNotFoundError:
    print("No options.json found. Using defaults.", flush=True)
    MQTT_BROKER = 'core-mosquitto'
    MQTT_PORT = 1883
    MQTT_USERNAME = ''
    MQTT_PASSWORD = ''
    MQTT_BASE_TOPIC = 'zigbee2mqtt'
    SWITCH_STUDIO_UI = True

APP_DIR = os.path.dirname(os.path.abspath(__file__))
SCHEMA_DEFINITION_PATHS = [
    os.path.join(APP_DIR, 'zigbee2mqtt_definition.md'),
    os.path.join(APP_DIR, 'zigbee2mqtt_definition.json'),
    os.path.join(os.path.dirname(APP_DIR), 'zigbee2mqtt_definition.md'),
    '/app/zigbee2mqtt_definition.md',
]
schema_service = SchemaService(definition_paths=SCHEMA_DEFINITION_PATHS)
print(
    f"Schema loaded: source={schema_service.schema.get('source')} path={schema_service.schema.get('source_path')}",
    flush=True
)
print(
    f"MQTT config: broker={MQTT_BROKER} port={MQTT_PORT} base_topic={MQTT_BASE_TOPIC} "
    f"username_set={'yes' if MQTT_USERNAME else 'no'} password_set={'yes' if MQTT_PASSWORD else 'no'} "
    f"switch_studio_ui={'enabled' if SWITCH_STUDIO_UI else 'disabled'}",
    flush=True
)
template_path = os.path.join(APP_DIR, 'templates', 'index.html')
template_fingerprint = _file_sha256_prefix(template_path)
template_tabs_enabled = False
try:
    with open(template_path, encoding='utf-8') as f:
        template_tabs_enabled = 'data-tab-target="load"' in f.read()
except Exception:
    template_tabs_enabled = False
print(
    f"UI template fingerprint: {template_fingerprint} tabs_enabled={'yes' if template_tabs_enabled else 'no'}",
    flush=True
)

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Stores device names, topics, config, and throttling timers
device_list = {}
device_list_lock = threading.Lock()

# Stores per-socket selected MQTT topic to avoid cross-session command routing
session_topics = {}
session_topics_lock = threading.Lock()
# Stores per-socket preference for auto-disabling target reporting on disconnect
session_reporting_auto_off = {}
session_reporting_auto_off_lock = threading.Lock()


def get_device_snapshot():
    with device_list_lock:
        return copy.deepcopy(list(device_list.values()))


def get_device_by_topic(topic):
    with device_list_lock:
        for data in device_list.values():
            if data.get('topic') == topic:
                return copy.deepcopy(data)
    return None


def set_session_topic(sid, topic):
    with session_topics_lock:
        session_topics[sid] = topic


def get_session_topic(sid):
    with session_topics_lock:
        return session_topics.get(sid)


def clear_session_topic(sid):
    with session_topics_lock:
        session_topics.pop(sid, None)


def has_session_for_topic(topic):
    if not topic:
        return False
    with session_topics_lock:
        return any(active_topic == topic for active_topic in session_topics.values())


def set_session_reporting_auto_off(sid, enabled):
    with session_reporting_auto_off_lock:
        session_reporting_auto_off[sid] = bool(enabled)


def get_session_reporting_auto_off(sid):
    with session_reporting_auto_off_lock:
        return bool(session_reporting_auto_off.get(sid, False))


def clear_session_reporting_auto_off(sid):
    with session_reporting_auto_off_lock:
        session_reporting_auto_off.pop(sid, None)


def resolve_target_reporting_value(enabled):
    schema = schema_service.get_schema() or {}
    field = None
    for entry in schema.get('fields', []) or []:
        if isinstance(entry, dict) and entry.get('name') == 'mmWaveTargetInfoReport':
            field = entry
            break

    values = [value for value in (field or {}).get('values', []) if isinstance(value, str)]
    if values:
        token = 'enable' if enabled else 'disable'
        for value in values:
            if token in value.lower():
                return value
        return values[-1] if enabled else values[0]

    return 'Enable' if enabled else 'Disable (default)'


def emit_device_delta(kind, payload, topic=None, room=None):
    socketio.emit(
        'device_delta',
        {
            'kind': kind,
            'topic': topic,
            'payload': payload,
            'ts': time.time()
        },
        room=room
    )


def emit_device_list(room=None):
    devices = get_device_snapshot()
    socketio.emit('device_list', devices, room=room)
    emit_device_delta('device_list', {'devices': devices}, room=room)


def build_device_snapshot(topic):
    device_data = get_device_by_topic(topic)
    if not device_data:
        return None

    payload = {
        'friendly_name': device_data.get('friendly_name'),
        'zone_config': device_data.get('zone_config'),
        'interference_zones': device_data.get('interference_zones', []),
        'detection_zones': device_data.get('detection_zones', []),
        'stay_zones': device_data.get('stay_zones', []),
        'last_config': device_data.get('last_config', {}),
        'last_seen': device_data.get('last_seen')
    }
    return {'topic': topic, 'payload': payload, 'ts': time.time()}


def emit_device_snapshot(topic, room=None):
    snapshot = build_device_snapshot(topic)
    if not snapshot:
        return
    socketio.emit('device_snapshot', snapshot, room=room)


def emit_command_result(sid, action, status, topic=None, request_id=None, message=None, payload=None, rc=None):
    result = {
        'action': action,
        'status': status,
        'topic': topic,
        'request_id': request_id,
        'ts': time.time()
    }
    if message:
        result['message'] = message
    if payload is not None:
        result['payload'] = payload
    if rc is not None:
        result['rc'] = rc

    socketio.emit('command_result', result, room=sid)


def emit_schema_model(room=None):
    socketio.emit('schema_model', schema_service.get_schema(), room=room)


def build_force_sync_payload():
    schema = schema_service.get_schema() or {}
    payload = {}
    for field in schema.get('fields', []) or []:
        if not isinstance(field, dict):
            continue
        name = field.get('name')
        if not name:
            continue
        if not field.get('can_read'):
            continue
        payload[name] = ""

    # The Zigbee2MQTT definition can expose light controls through nested features.
    # Keep these keys explicitly requested so quick controls stay in sync.
    payload.setdefault("state", "")
    payload.setdefault("brightness", "")

    if payload:
        return payload

    # Conservative fallback if schema is unavailable.
    return {
        "state": "", "brightness": "", "occupancy": "", "illuminance": "",
        "mmWaveDepthMax": "", "mmWaveDepthMin": "", "mmWaveWidthMax": "", "mmWaveWidthMin": "",
        "mmWaveHeightMax": "", "mmWaveHeightMin": "", "mmWaveDetectSensitivity": "",
        "mmWaveDetectTrigger": "", "mmWaveHoldTime": "", "mmWaveStayLife": "",
        "mmWaveRoomSizePreset": "", "mmWaveTargetInfoReport": "", "mmWaveVersion": "",
        "mmwaveControlWiredDevice": ""
    }


def on_connect(client, userdata, flags, rc):
    reason = MQTT_CONNACK_REASON.get(rc, "Unknown")
    print(f"Connected to MQTT Broker with code {rc} ({reason})", flush=True)
    if rc == 0:
        subscribe_topic = f"{MQTT_BASE_TOPIC}/#"
        client.subscribe(subscribe_topic)
        print(f"Subscribed to topic: {subscribe_topic}", flush=True)
    else:
        print(
            "MQTT connection was not accepted. Check broker host/port and credentials in add-on Configuration.",
            flush=True
        )

def on_message(client, userdata, msg):
    global device_list
    try:
        topic = msg.topic
        payload_str = msg.payload.decode().strip()
        
        # --- ROBUST JSON PARSING ---
        if not payload_str:
            return
            
        try:
            payload = json.loads(payload_str)
        except json.JSONDecodeError:
            return

        # Zigbee2MQTT bridge topics may publish arrays/literals; this app only processes object payloads.
        if not isinstance(payload, dict):
            return

        # --- DEVICE DISCOVERY ---
        if topic.startswith(MQTT_BASE_TOPIC):
            payload_keys = [k for k in payload.keys() if isinstance(k, str)]
            has_mmwave_key = (
                "mmWaveVersion" in payload
                or any(key.startswith("mmWave") or key.startswith("mmwave_") for key in payload_keys)
            )
            if has_mmwave_key:
                parts = topic.split('/')
                if len(parts) >= 2:
                    friendly_name = parts[1]
                    if friendly_name and friendly_name != 'bridge':
                        discovered = False
                        with device_list_lock:
                            if friendly_name not in device_list:
                                print(f"Discovered Inovelli Switch: {friendly_name}", flush=True)
                                device_list[friendly_name] = {
                                    'friendly_name': friendly_name, 
                                    'topic': f"{MQTT_BASE_TOPIC}/{friendly_name}", 
                                    'interference_zones': [],
                                    'detection_zones': [],
                                    'stay_zones': [],
                                    'zone_config': {"x_min": -400, "x_max": 400, "y_min": 0, "y_max": 600},
                                    'last_config': {},
                                    'last_update': 0,
                                    'last_seen': time.time()
                                }
                                discovered = True
                            else:
                                device_list[friendly_name]['last_seen'] = time.time()

                        if discovered:
                            emit_device_list()

        # --- CURRENT DEVICE PROCESSING ---
        fname = None
        device_topic = None
        with device_list_lock:
            for name, data in device_list.items():
                if topic == data['topic']:
                    fname = name
                    device_topic = data['topic']
                    break
        if not fname: return

        # --- PROCESS RAW BYTES (ZCL Cluster 0xFC32) ---
        is_raw_packet = payload.get("0") == 29 and payload.get("1") == 47 and payload.get("2") == 18

        if is_raw_packet:
            cmd_id = payload.get("4")
            
            # --- 0x01: Target Info Reporting (Movement Data) ---
            if cmd_id == 1:
                current_time = time.time()
                should_process = False
                with device_list_lock:
                    device_data = device_list.get(fname)
                    if device_data and (current_time - device_data.get('last_update', 0)) >= 0.1:
                        device_data['last_update'] = current_time
                        should_process = True

                if should_process:
                    seq_num = payload.get("3")
                    num_targets = payload.get("5", 0)
                    targets = []
                    offset = 6

                    for _ in range(num_targets):
                        if str(offset+8) not in payload: break
                        
                        def parse_bytes(idx):
                            try:
                                low = int(payload.get(str(idx)) or 0)
                                high = int(payload.get(str(idx+1)) or 0)
                                return int.from_bytes([low, high], byteorder='little', signed=True)
                            except:
                                return 0

                        targets.append({
                            "id": int(payload.get(str(offset+8)) or 0),
                            "x": parse_bytes(offset),
                            "y": parse_bytes(offset+2),
                            "z": parse_bytes(offset+4),
                            "dop": parse_bytes(offset+6)
                        })
                        offset += 9
                    
                    socketio.emit('new_data', {'topic': device_topic, 'payload': {"seq": seq_num, "targets": targets}})
                    emit_device_delta('new_data', {"seq": seq_num, "targets": targets}, topic=device_topic)

            # --- 0x02 (Interference), 0x03 (Detection), 0x04 (Stay) Areas ---
            elif cmd_id in [2, 3, 4]:
                try:
                    zones = []
                    offset = 6  
                    num_zones = payload.get("5", 0) 
                    
                    for _ in range(num_zones):
                        if str(offset+11) not in payload: break
                        
                        def parse_bytes(idx):
                            low = int(payload.get(str(idx)) or 0)
                            high = int(payload.get(str(idx+1)) or 0)
                            return int.from_bytes([low, high], byteorder='little', signed=True)

                        x_min = parse_bytes(offset)
                        x_max = parse_bytes(offset+2)
                        y_min = parse_bytes(offset+4)
                        y_max = parse_bytes(offset+6)
                        z_min = parse_bytes(offset+8)
                        z_max = parse_bytes(offset+10)
                        
                        # Append if it looks like a valid configured zone (has dimensions)
                        # We use a loose check (x_max > x_min) to allow 0-based zones if valid, 
                        # but typically 0,0,0,0,0,0 is an empty zone.
                        if (x_max != 0 or x_min != 0 or y_max != 0 or y_min != 0):
                            zones.append({
                                "x_min": x_min, "x_max": x_max, 
                                "y_min": y_min, "y_max": y_max,
                                "z_min": z_min, "z_max": z_max
                            })
                        
                        offset += 12
                    
                    # Store and Emit based on Command ID
                    if cmd_id == 2:
                        with device_list_lock:
                            if fname in device_list:
                                device_list[fname]['interference_zones'] = zones
                        socketio.emit('interference_zones', {'topic': device_topic, 'payload': zones})
                        emit_device_delta('interference_zones', zones, topic=device_topic)
                        print(f"Interference Zones Updated: {zones}", flush=True)
                    elif cmd_id == 3:
                        with device_list_lock:
                            if fname in device_list:
                                device_list[fname]['detection_zones'] = zones
                        socketio.emit('detection_zones', {'topic': device_topic, 'payload': zones})
                        emit_device_delta('detection_zones', zones, topic=device_topic)
                        print(f"Detection Zones Updated: {zones}", flush=True)
                    elif cmd_id == 4:
                        with device_list_lock:
                            if fname in device_list:
                                device_list[fname]['stay_zones'] = zones
                        socketio.emit('stay_zones', {'topic': device_topic, 'payload': zones})
                        emit_device_delta('stay_zones', zones, topic=device_topic)
                        print(f"Stay Zones Updated: {zones}", flush=True)
                    
                except Exception as parse_error:
                    print(f"Warning: Zone packet offset mismatch: {parse_error}", flush=True)
        
        # --- STANDARD STATE UPDATE ---
        config_payload = {k: v for k, v in payload.items() if not k.isdigit()}
        
        if config_payload:
            socketio.emit('device_config', {'topic': device_topic, 'payload': config_payload})
            emit_device_delta('device_config', config_payload, topic=device_topic)

            # Update Standard Global Zone (Attributes 103-106)
            needs_emit = False
            zone_payload = None

            with device_list_lock:
                device_data = device_list.get(fname)
                if device_data:
                    if not isinstance(device_data.get('last_config'), dict):
                        device_data['last_config'] = {}
                    device_data['last_config'].update(config_payload)

                    current_zone = dict(device_data.get('zone_config', {"x_min": -400, "x_max": 400, "y_min": 0, "y_max": 600}))

                    if "mmWaveWidthMin" in config_payload:
                        parsed = _as_int_or_none(config_payload.get("mmWaveWidthMin"))
                        if parsed is not None:
                            current_zone["x_min"] = parsed
                            needs_emit = True
                    if "mmWaveWidthMax" in config_payload:
                        parsed = _as_int_or_none(config_payload.get("mmWaveWidthMax"))
                        if parsed is not None:
                            current_zone["x_max"] = parsed
                            needs_emit = True
                    if "mmWaveDepthMin" in config_payload:
                        parsed = _as_int_or_none(config_payload.get("mmWaveDepthMin"))
                        if parsed is not None:
                            current_zone["y_min"] = parsed
                            needs_emit = True
                    if "mmWaveDepthMax" in config_payload:
                        parsed = _as_int_or_none(config_payload.get("mmWaveDepthMax"))
                        if parsed is not None:
                            current_zone["y_max"] = parsed
                            needs_emit = True

                    if needs_emit:
                        device_data['zone_config'] = current_zone
                        zone_payload = copy.deepcopy(current_zone)

            if zone_payload:
                socketio.emit('zone_config', {'topic': device_topic, 'payload': zone_payload})
                emit_device_delta('zone_config', zone_payload, topic=device_topic)

    except Exception as e:
        print(f"Error processing message on {msg.topic}: {e}", flush=True)
        traceback.print_exc()

mqtt_client = mqtt.Client()
if MQTT_USERNAME or MQTT_PASSWORD:
    mqtt_client.username_pw_set(MQTT_USERNAME or '', MQTT_PASSWORD or None)

mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

try:
    if not TEST_MODE:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()
except Exception as e:
    print(f"Connection Failed: {e}", flush=True)


def publish_json(topic, payload, origin, sid=None):
    payload_str = json.dumps(payload)
    print(f"[MQTT-PUBLISH] origin={origin} sid={sid or '-'} topic={topic} payload={payload_str}", flush=True)
    try:
        publish_result = mqtt_client.publish(topic, payload_str)
        rc = getattr(publish_result, 'rc', None)
        ok = (rc == mqtt.MQTT_ERR_SUCCESS)
        return ok, rc
    except Exception as publish_error:
        print(
            f"[MQTT-PUBLISH-ERROR] origin={origin} sid={sid or '-'} topic={topic} error={publish_error}",
            flush=True
        )
        return False, str(publish_error)


# --- WEBSOCKET HANDLERS ---
@socketio.on('connect')
def handle_socket_connect():
    print(f"WebSocket connected: sid={request.sid}", flush=True)
    set_session_reporting_auto_off(request.sid, False)
    emit_schema_model(room=request.sid)


@socketio.on('disconnect')
def handle_socket_disconnect():
    sid = request.sid
    current_topic = get_session_topic(sid)
    should_auto_off = get_session_reporting_auto_off(sid)
    clear_session_topic(sid)
    clear_session_reporting_auto_off(sid)

    if should_auto_off and current_topic and not has_session_for_topic(current_topic):
        disable_value = resolve_target_reporting_value(False)
        payload = {'mmWaveTargetInfoReport': disable_value}
        ok, rc = publish_json(f"{current_topic}/set", payload, origin='auto_disable_target_reporting', sid=sid)
        if ok:
            print(
                f"Auto-disabled mmWave target reporting on disconnect: topic={current_topic} sid={sid}",
                flush=True
            )
        else:
            print(
                f"Failed to auto-disable mmWave target reporting on disconnect: topic={current_topic} sid={sid} rc={rc}",
                flush=True
            )

    print(f"WebSocket disconnected: sid={request.sid}", flush=True)


@socketio.on('request_devices')
def handle_request_devices():
    emit_device_list(room=request.sid)


@socketio.on('request_schema')
def handle_request_schema():
    emit_schema_model(room=request.sid)

@socketio.on('change_device')
def handle_change_device(new_topic):
    if not new_topic:
        clear_session_topic(request.sid)
        return

    set_session_topic(request.sid, new_topic)
    print(f"Switched monitoring to: {new_topic} (sid={request.sid})", flush=True)
    emit_device_delta('selected_device', {'topic': new_topic}, topic=new_topic, room=request.sid)
    emit_device_snapshot(new_topic, room=request.sid)

    device_data = get_device_by_topic(new_topic)
    if device_data:
        if 'zone_config' in device_data: 
            socketio.emit('zone_config', {'topic': new_topic, 'payload': device_data['zone_config']}, room=request.sid)
        if 'interference_zones' in device_data: 
            socketio.emit('interference_zones', {'topic': new_topic, 'payload': device_data['interference_zones']}, room=request.sid)
        if 'detection_zones' in device_data:
            socketio.emit('detection_zones', {'topic': new_topic, 'payload': device_data['detection_zones']}, room=request.sid)
        if 'stay_zones' in device_data:
            socketio.emit('stay_zones', {'topic': new_topic, 'payload': device_data['stay_zones']}, room=request.sid)


@socketio.on('set_reporting_auto_off')
def handle_set_reporting_auto_off(data):
    enabled = False
    if isinstance(data, dict):
        enabled = _as_bool(data.get('enabled'), False)
    else:
        enabled = _as_bool(data, False)

    set_session_reporting_auto_off(request.sid, enabled)
    emit_command_result(
        request.sid,
        action='set_reporting_auto_off',
        status='sent',
        topic=get_session_topic(request.sid),
        payload={'enabled': enabled}
    )


@socketio.on('set_target_reporting')
def handle_set_target_reporting(data):
    request_id = data.get('request_id') if isinstance(data, dict) else None
    current_topic = get_session_topic(request.sid)
    if not current_topic:
        emit_command_result(
            request.sid,
            action='set_target_reporting',
            status='error',
            request_id=request_id,
            message='No device selected'
        )
        return

    enabled = False
    if isinstance(data, dict):
        enabled = _as_bool(data.get('enabled'), False)
    else:
        enabled = _as_bool(data, False)

    target_value = resolve_target_reporting_value(enabled)
    payload = {'mmWaveTargetInfoReport': target_value}
    ok, rc = publish_json(
        f"{current_topic}/set",
        payload,
        origin='set_target_reporting',
        sid=request.sid
    )
    emit_command_result(
        request.sid,
        action='set_target_reporting',
        status='sent' if ok else 'error',
        topic=current_topic,
        request_id=request_id,
        payload={'enabled': enabled, 'value': target_value},
        rc=rc,
        message=None if ok else 'MQTT publish failed'
    )


@socketio.on('set_basic_control')
def handle_set_basic_control(data):
    request_id = data.get('request_id') if isinstance(data, dict) else None
    current_topic = get_session_topic(request.sid)
    if not current_topic:
        emit_command_result(
            request.sid,
            action='set_basic_control',
            status='error',
            request_id=request_id,
            message='No device selected'
        )
        return

    if not isinstance(data, dict):
        emit_command_result(
            request.sid,
            action='set_basic_control',
            status='error',
            topic=current_topic,
            request_id=request_id,
            message='Invalid payload'
        )
        return

    control_payload = {}
    errors = []

    if 'state' in data:
        normalized_state, state_error = _normalize_basic_state(data.get('state'))
        if state_error:
            errors.append(state_error)
        else:
            control_payload['state'] = normalized_state

    if 'brightness' in data:
        normalized_brightness, brightness_error = _normalize_basic_brightness(data.get('brightness'))
        if brightness_error:
            errors.append(brightness_error)
        else:
            control_payload['brightness'] = normalized_brightness

    if errors:
        emit_command_result(
            request.sid,
            action='set_basic_control',
            status='error',
            topic=current_topic,
            request_id=request_id,
            payload={k: v for k, v in data.items() if k in {'state', 'brightness'}},
            message='; '.join(errors)
        )
        return

    if not control_payload:
        emit_command_result(
            request.sid,
            action='set_basic_control',
            status='error',
            topic=current_topic,
            request_id=request_id,
            message='Missing state or brightness'
        )
        return

    ok, rc = publish_json(
        f"{current_topic}/set",
        control_payload,
        origin='set_basic_control',
        sid=request.sid
    )
    emit_command_result(
        request.sid,
        action='set_basic_control',
        status='sent' if ok else 'error',
        topic=current_topic,
        request_id=request_id,
        payload=control_payload,
        rc=rc,
        message=None if ok else 'MQTT publish failed'
    )


@socketio.on('update_parameter')
def handle_update_parameter(data):
    request_id = data.get('request_id') if isinstance(data, dict) else None
    current_topic = get_session_topic(request.sid)
    if not current_topic:
        emit_command_result(
            request.sid,
            action='update_parameter',
            status='error',
            request_id=request_id,
            message='No device selected'
        )
        return

    if not isinstance(data, dict):
        emit_command_result(
            request.sid,
            action='update_parameter',
            status='error',
            topic=current_topic,
            request_id=request_id,
            message='Invalid payload'
        )
        return

    param = data.get('param')
    if not param:
        emit_command_result(
            request.sid,
            action='update_parameter',
            status='error',
            topic=current_topic,
            request_id=request_id,
            message='Missing param'
        )
        return

    value = data.get('value')

    is_valid, validation_error, normalized_value, is_unknown_field = schema_service.validate_update(param, value)
    if not is_valid:
        emit_command_result(
            request.sid,
            action='update_parameter',
            status='error',
            topic=current_topic,
            request_id=request_id,
            payload={param: value},
            message=validation_error
        )
        return

    control_payload = {param: normalized_value}
    ok, rc = publish_json(f"{current_topic}/set", control_payload, origin='update_parameter', sid=request.sid)
    emit_command_result(
        request.sid,
        action='update_parameter',
        status='sent' if ok else 'error',
        topic=current_topic,
        request_id=request_id,
        payload=control_payload,
        rc=rc,
        message='Sent without schema validation (unknown field)' if (ok and is_unknown_field) else (None if ok else 'MQTT publish failed')
    )


@socketio.on('force_sync')
def handle_force_sync(data=None):
    request_id = data.get('request_id') if isinstance(data, dict) else None
    current_topic = get_session_topic(request.sid)
    if not current_topic:
        emit_command_result(
            request.sid,
            action='force_sync',
            status='error',
            request_id=request_id,
            message='No device selected'
        )
        return
    
    # 1. Emit cached data
    emit_device_snapshot(current_topic, room=request.sid)
    device_data = get_device_by_topic(current_topic)
    if device_data:
        if 'zone_config' in device_data: socketio.emit('zone_config', {'topic': current_topic, 'payload': device_data['zone_config']}, room=request.sid)
        if 'interference_zones' in device_data: socketio.emit('interference_zones', {'topic': current_topic, 'payload': device_data['interference_zones']}, room=request.sid)
        if 'detection_zones' in device_data: socketio.emit('detection_zones', {'topic': current_topic, 'payload': device_data['detection_zones']}, room=request.sid)
        if 'stay_zones' in device_data: socketio.emit('stay_zones', {'topic': current_topic, 'payload': device_data['stay_zones']}, room=request.sid)

    # 2. Trigger Z2M read
    payload = build_force_sync_payload()
    ok_get, rc_get = publish_json(f"{current_topic}/get", payload, origin='force_sync_get', sid=request.sid)
    emit_command_result(
        request.sid,
        action='force_sync_get',
        status='sent' if ok_get else 'error',
        topic=current_topic,
        request_id=request_id,
        payload=payload,
        rc=rc_get,
        message=None if ok_get else 'MQTT publish failed'
    )
    
    # 3. Trigger mmWave Module Report (Query Areas)
    # This forces the sensor to output packets 0x02, 0x03, 0x04
    cmd_payload = { "mmwave_control_commands": { "controlID": "query_areas" } }
    ok_cmd, rc_cmd = publish_json(f"{current_topic}/set", cmd_payload, origin='force_sync_query_areas', sid=request.sid)
    emit_command_result(
        request.sid,
        action='force_sync_query_areas',
        status='sent' if ok_cmd else 'error',
        topic=current_topic,
        request_id=request_id,
        payload=cmd_payload,
        rc=rc_cmd,
        message=None if ok_cmd else 'MQTT publish failed'
    )
    print(f"Force Sync (Z2M Read + Query Areas) sent to {current_topic} (sid={request.sid})", flush=True)


@socketio.on('send_command')
def handle_command(cmd_action):
    current_topic = get_session_topic(request.sid)
    if not current_topic:
        emit_command_result(
            request.sid,
            action='send_command',
            status='error',
            message='No device selected'
        )
        return

    action_map = { 0: "reset_mmwave_module", 1: "set_interference", 2: "query_areas", 3: "clear_interference", 4: "reset_detection_area", 5: "clear_stay_areas" }
    try:
        cmd_action_int = int(cmd_action)
    except (TypeError, ValueError):
        emit_command_result(
            request.sid,
            action='send_command',
            status='error',
            topic=current_topic,
            message='Invalid command action'
        )
        return

    cmd_string = action_map.get(cmd_action_int)
    if cmd_string:
        cmd_payload = {"mmwave_control_commands": {"controlID": cmd_string}}
        ok, rc = publish_json(
            f"{current_topic}/set",
            cmd_payload,
            origin='send_command',
            sid=request.sid
        )
        emit_command_result(
            request.sid,
            action='send_command',
            status='sent' if ok else 'error',
            topic=current_topic,
            payload={'action_id': cmd_action_int, 'controlID': cmd_string},
            rc=rc,
            message=None if ok else 'MQTT publish failed'
        )
    else:
        emit_command_result(
            request.sid,
            action='send_command',
            status='error',
            topic=current_topic,
            payload={'action_id': cmd_action_int},
            message='Unknown command action'
        )


def cleanup_stale_devices():
    while True:
        time.sleep(60)
        current_time = time.time()
        with device_list_lock:
            stale_keys = [k for k, v in device_list.items() if (current_time - v.get('last_seen', 0)) > 3600]
            for key in stale_keys:
                del device_list[key]
        if stale_keys:
            emit_device_list()

cleanup_thread = None
if not TEST_MODE:
    cleanup_thread = threading.Thread(target=cleanup_stale_devices, daemon=True)
    cleanup_thread.start()

@app.route('/')
def index():
    return render_template(
        'index.html',
        ingress_path=request.headers.get('X-Ingress-Path', ''),
        switch_studio_ui=SWITCH_STUDIO_UI
    )

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
