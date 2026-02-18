"""
Inovelli mmWave Visualizer Backend
Provides a real-time MQTT-to-WebSocket bridge for Home Assistant Ingress.
Handles device discovery, Zigbee byte array decoding, and two-way configuration.
"""

import json
import os
import traceback
import time
import threading
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
from flask_socketio import join_room, leave_room
import paho.mqtt.client as mqtt
import logging

# Suppress the Werkzeug development server warning
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# --- LOAD HOME ASSISTANT CONFIGURATION ---
CONFIG_PATH = '/data/options.json'

try:
    with open(CONFIG_PATH) as f:
        config = json.load(f)
        MQTT_BROKER = config.get('mqtt_broker', 'core-mosquitto')
        MQTT_PORT = int(config.get('mqtt_port', 1883))
        MQTT_USERNAME = config.get('mqtt_username', '')
        MQTT_PASSWORD = config.get('mqtt_password', '')
        MQTT_BASE_TOPIC = config.get('mqtt_base_topic', 'zigbee2mqtt')
except FileNotFoundError:
    print("No options.json found. Using defaults.", flush=True)
    MQTT_BROKER = 'core-mosquitto'
    MQTT_PORT = 1883
    MQTT_USERNAME = ''
    MQTT_PASSWORD = ''
    MQTT_BASE_TOPIC = 'zigbee2mqtt'

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# --- FIX #1: Per-session device tracking instead of global current_topic ---
# Maps socket session ID -> device topic
session_topics = {}
session_topics_lock = threading.Lock()

# --- FIX #3: Thread-safe device list with lock ---
device_list = {}
device_list_lock = threading.Lock()

# --- FIX #6: Track MQTT connection state ---
mqtt_connected = False

# --- FIX #10: Parameter validation whitelist ---
VALID_PARAMETERS = {
    # String-value parameters (value must match one of the allowed options)
    'mmWaveDetectSensitivity': {
        'type': 'enum',
        'options': ['Low', 'Medium', 'High (default)']
    },
    'mmWaveDetectTrigger': {
        'type': 'enum',
        'options': ['Fast (0.2s, default)', 'Medium (1s)', 'Slow (5s)']
    },
    'mmWaveRoomSizePreset': {
        'type': 'enum',
        'options': ['Custom', 'Small', 'Medium', 'Large']
    },
    'mmWaveTargetInfoReport': {
        'type': 'enum',
        'options': ['Disable (default)', 'Enable']
    },
    'mmwaveControlWiredDevice': {
        'type': 'enum',
        'options': [
            'Disabled', 'Occupancy (default)', 'Vacancy',
            'Wasteful Occupancy', 'Mirrored Occupancy',
            'Mirrored Vacancy', 'Mirrored Wasteful Occupancy'
        ]
    },
    # Numeric parameters
    'mmWaveHoldTime': {'type': 'int', 'min': 0, 'max': 28800},
    'mmWaveStayLife': {'type': 'int', 'min': 0, 'max': 28800},
    # Zone composite parameters (validated structurally)
    'mmwave_detection_areas': {'type': 'zone_composite'},
    'mmwave_interference_areas': {'type': 'zone_composite'},
    'mmwave_stay_areas': {'type': 'zone_composite'},
}

# Valid keys inside a zone area payload
VALID_ZONE_KEYS = {'width_min', 'width_max', 'depth_min', 'depth_max', 'height_min', 'height_max'}
ZONE_COORD_RANGE = (-10000, 10000)  # Reasonable cm range


def validate_parameter(param, value):
    """
    Validate a parameter name and value against the whitelist.
    Returns (is_valid: bool, error_message: str or None).
    """
    if param not in VALID_PARAMETERS:
        return False, f"Unknown parameter: {param}"

    schema = VALID_PARAMETERS[param]
    ptype = schema['type']

    if ptype == 'enum':
        if not isinstance(value, str) or value not in schema['options']:
            return False, f"Invalid value '{value}' for {param}. Allowed: {schema['options']}"
        return True, None

    elif ptype == 'int':
        try:
            int_val = int(value)
        except (ValueError, TypeError):
            return False, f"Parameter {param} requires an integer, got: {value}"
        if int_val < schema['min'] or int_val > schema['max']:
            return False, f"Parameter {param} value {int_val} out of range [{schema['min']}, {schema['max']}]"
        return True, None

    elif ptype == 'zone_composite':
        if not isinstance(value, dict):
            return False, f"Parameter {param} expects a dict, got: {type(value).__name__}"
        for area_key, area_val in value.items():
            if not area_key.startswith('area') or not area_key[4:].isdigit():
                return False, f"Invalid area key: {area_key}"
            area_num = int(area_key[4:])
            if area_num < 1 or area_num > 4:
                return False, f"Area number out of range: {area_key}"
            if not isinstance(area_val, dict):
                return False, f"Area {area_key} value must be a dict"
            if not set(area_val.keys()).issubset(VALID_ZONE_KEYS):
                unknown = set(area_val.keys()) - VALID_ZONE_KEYS
                return False, f"Unknown zone keys in {area_key}: {unknown}"
            for coord_key, coord_val in area_val.items():
                try:
                    v = int(coord_val)
                except (ValueError, TypeError):
                    return False, f"Zone coordinate {coord_key} must be an integer"
                if v < ZONE_COORD_RANGE[0] or v > ZONE_COORD_RANGE[1]:
                    return False, f"Zone coordinate {coord_key}={v} out of range"
        return True, None

    return False, f"Unknown parameter type: {ptype}"


def safe_int(value, default=0):
    """Safely converts a value to int."""
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (ValueError, TypeError):
        return default


# --- FIX #2: Parse bytes as a module-level function, not redefined inside loops ---
def parse_signed_16(payload, idx):
    """Parse a signed 16-bit little-endian value from two consecutive payload bytes."""
    try:
        low = int(payload.get(str(idx)) or 0)
        high = int(payload.get(str(idx + 1)) or 0)
        return int.from_bytes([low, high], byteorder='little', signed=True)
    except (ValueError, TypeError, OverflowError):
        return 0


def get_device_list_snapshot():
    """Return a thread-safe copy of the device list for emitting."""
    with device_list_lock:
        return [dict(d) for d in device_list.values()]


def get_sessions_for_topic(topic):
    """Return list of session IDs currently monitoring a given topic."""
    with session_topics_lock:
        return [sid for sid, t in session_topics.items() if t == topic]


def emit_to_topic_subscribers(event, data, topic):
    """Emit an event only to sessions monitoring the given device topic."""
    sids = get_sessions_for_topic(topic)
    for sid in sids:
        socketio.emit(event, data, to=sid)


# --- MQTT CALLBACKS ---

def on_connect(client, userdata, flags, rc):
    global mqtt_connected
    if rc == 0:
        mqtt_connected = True
        print(f"Connected to MQTT Broker", flush=True)
        client.subscribe(f"{MQTT_BASE_TOPIC}/#")
        # Broadcast connection state to all clients
        socketio.emit('mqtt_status', {'connected': True})
    else:
        mqtt_connected = False
        print(f"MQTT connection failed with code {rc}", flush=True)
        socketio.emit('mqtt_status', {'connected': False, 'error': f'Connection code: {rc}'})


def on_disconnect(client, userdata, rc):
    global mqtt_connected
    mqtt_connected = False
    print(f"Disconnected from MQTT Broker (rc={rc})", flush=True)
    socketio.emit('mqtt_status', {'connected': False, 'error': 'Broker disconnected'})


def on_message(client, userdata, msg):
    try:
        topic = msg.topic
        payload_str = msg.payload.decode().strip()

        if not payload_str:
            return

        try:
            payload = json.loads(payload_str)
        except json.JSONDecodeError:
            return

        # Skip non-dict payloads (e.g. bare ints from /set/paramName topics)
        if not isinstance(payload, dict):
            return

        # --- DEVICE DISCOVERY ---
        if topic.startswith(MQTT_BASE_TOPIC):
            if "mmWaveVersion" in payload:
                parts = topic.split('/')
                if len(parts) >= 2:
                    friendly_name = parts[1]

                    with device_list_lock:
                        is_new = friendly_name not in device_list
                        if is_new:
                            print(f"Discovered Inovelli mmWave Switch: {friendly_name}", flush=True)
                            device_list[friendly_name] = {
                                'friendly_name': friendly_name,
                                'topic': f"{MQTT_BASE_TOPIC}/{friendly_name}",
                                'interference_zones': [],
                                'detection_zones': [],
                                'stay_zones': [],
                                'use_nested_area1': False,
                                'zone_config': {
                                    "x_min": -100, "x_max": 100,
                                    "y_min": 0, "y_max": 600,
                                    "z_min": -300, "z_max": 300
                                },
                                'last_update': 0,
                                'last_seen': time.time()
                            }
                        else:
                            device_list[friendly_name]['last_seen'] = time.time()

                    if is_new:
                        socketio.emit('device_list', get_device_list_snapshot())

        # --- IDENTIFY DEVICE ---
        with device_list_lock:
            fname = next((name for name, data in device_list.items()
                          if topic.startswith(data['topic'])), None)
            if not fname:
                return
            device_topic = device_list[fname]['topic']

        # --- PROCESS RAW BYTES (ZCL Cluster 0xFC32) ---
        is_raw_packet = (payload.get("0") == 29 and
                         payload.get("1") == 47 and
                         payload.get("2") == 18)

        if is_raw_packet:
            cmd_id = payload.get("4")

            # --- 0x01: Target Info Reporting (Movement Data) ---
            if cmd_id == 1:
                current_time = time.time()
                with device_list_lock:
                    last_update = device_list[fname].get('last_update', 0)

                if (current_time - last_update) >= 0.1:
                    with device_list_lock:
                        device_list[fname]['last_update'] = current_time

                    seq_num = payload.get("3")
                    num_targets = payload.get("5", 0)
                    targets = []
                    offset = 6

                    for _ in range(num_targets):
                        if str(offset + 8) not in payload:
                            break
                        targets.append({
                            "id": int(payload.get(str(offset + 8)) or 0),
                            "x": parse_signed_16(payload, offset),
                            "y": parse_signed_16(payload, offset + 2),
                            "z": parse_signed_16(payload, offset + 4),
                            "dop": parse_signed_16(payload, offset + 6)
                        })
                        offset += 9

                    emit_to_topic_subscribers(
                        'new_data',
                        {'topic': device_topic, 'payload': {"seq": seq_num, "targets": targets}},
                        device_topic
                    )

            # --- 0x02 (Interference), 0x03 (Detection), 0x04 (Stay) Areas ---
            elif cmd_id in [2, 3, 4]:
                try:
                    zones = []
                    offset = 6
                    num_zones = payload.get("5", 0)

                    for _ in range(num_zones):
                        if str(offset + 11) not in payload:
                            break

                        x_min = parse_signed_16(payload, offset)
                        x_max = parse_signed_16(payload, offset + 2)
                        y_min = parse_signed_16(payload, offset + 4)
                        y_max = parse_signed_16(payload, offset + 6)
                        z_min = parse_signed_16(payload, offset + 8)
                        z_max = parse_signed_16(payload, offset + 10)

                        if (x_max != 0 or x_min != 0 or y_max != 0 or y_min != 0):
                            zones.append({
                                "x_min": x_min, "x_max": x_max,
                                "y_min": y_min, "y_max": y_max,
                                "z_min": z_min, "z_max": z_max
                            })

                        offset += 12

                    # Store and emit based on Command ID
                    event_map = {
                        2: ('interference_zones', 'Interference'),
                        3: ('detection_zones', 'Detection'),
                        4: ('stay_zones', 'Stay')
                    }
                    event_name, zone_label = event_map[cmd_id]

                    with device_list_lock:
                        device_list[fname][event_name] = zones

                    emit_to_topic_subscribers(
                        event_name,
                        {'topic': device_topic, 'payload': zones},
                        device_topic
                    )
                    print(f"{zone_label} Zones Updated: {zones}", flush=True)

                except Exception as parse_error:
                    print(f"Warning: Zone packet offset mismatch: {parse_error}", flush=True)

        # --- STANDARD STATE UPDATE ---
        config_payload = {k: v for k, v in payload.items() if not k.isdigit()}

        if config_payload:
            emit_to_topic_subscribers(
                'device_config',
                {'topic': device_topic, 'payload': config_payload},
                device_topic
            )

            with device_list_lock:
                # Check nested mode for Zone 1
                if "mmwave_detection_areas" in config_payload:
                    a1 = config_payload["mmwave_detection_areas"].get("area1")
                    has_data = False
                    if a1 and isinstance(a1, dict):
                        for val in a1.values():
                            if isinstance(val, (int, float)) and val != 0:
                                has_data = True
                                break
                    device_list[fname]['use_nested_area1'] = has_data

                # Update standard global zone
                needs_emit = False
                current_zone = device_list[fname]['zone_config']

                field_map = {
                    "mmWaveWidthMin": "x_min", "mmWaveWidthMax": "x_max",
                    "mmWaveDepthMin": "y_min", "mmWaveDepthMax": "y_max",
                    "mmWaveHeightMin": "z_min", "mmWaveHeightMax": "z_max"
                }
                for mqtt_key, zone_key in field_map.items():
                    if mqtt_key in config_payload:
                        current_zone[zone_key] = safe_int(config_payload[mqtt_key])
                        needs_emit = True

                if needs_emit:
                    device_list[fname]['zone_config'] = current_zone
                    zone_snapshot = dict(current_zone)

            if needs_emit:
                emit_to_topic_subscribers(
                    'zone_config',
                    {'topic': device_topic, 'payload': zone_snapshot},
                    device_topic
                )

    except Exception as e:
        print(f"Error processing message on {msg.topic}: {e}", flush=True)
        traceback.print_exc()


# --- MQTT CLIENT SETUP ---
mqtt_client = mqtt.Client()
if MQTT_USERNAME and MQTT_PASSWORD:
    mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect = on_disconnect
mqtt_client.on_message = on_message

try:
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    mqtt_client.loop_start()
except Exception as e:
    print(f"MQTT Connection Failed: {e}", flush=True)


# --- WEBSOCKET HANDLERS ---

@socketio.on('connect')
def handle_connect():
    """Send MQTT status and device list on new client connection."""
    emit('mqtt_status', {'connected': mqtt_connected})
    emit('device_list', get_device_list_snapshot())


@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    with session_topics_lock:
        session_topics.pop(sid, None)


@socketio.on('request_devices')
def handle_request_devices():
    emit('device_list', get_device_list_snapshot())


@socketio.on('change_device')
def handle_change_device(new_topic):
    sid = request.sid
    with session_topics_lock:
        session_topics[sid] = new_topic
    print(f"Session {sid[:8]} now monitoring: {new_topic}", flush=True)

    with device_list_lock:
        device_data = next((data for data in device_list.values()
                            if data['topic'] == new_topic), None)
        if device_data:
            cached = {
                'zone_config': dict(device_data.get('zone_config', {})),
                'interference_zones': list(device_data.get('interference_zones', [])),
                'detection_zones': list(device_data.get('detection_zones', [])),
                'stay_zones': list(device_data.get('stay_zones', [])),
            }

    if device_data:
        emit('zone_config', {'topic': new_topic, 'payload': cached['zone_config']})
        emit('interference_zones', {'topic': new_topic, 'payload': cached['interference_zones']})
        emit('detection_zones', {'topic': new_topic, 'payload': cached['detection_zones']})
        emit('stay_zones', {'topic': new_topic, 'payload': cached['stay_zones']})


@socketio.on('update_parameter')
def handle_update_parameter(data):
    sid = request.sid
    with session_topics_lock:
        topic = session_topics.get(sid)
    if not topic:
        emit('command_error', {'error': 'No device selected'})
        return

    param = data.get('param')
    value = data.get('value')

    # --- FIX #10: Validate before publishing ---
    is_valid, error_msg = validate_parameter(param, value)
    if not is_valid:
        print(f"Parameter validation failed: {error_msg}", flush=True)
        emit('command_error', {'error': error_msg})
        return

    # Identify device for legacy fallback
    with device_list_lock:
        fname = next((name for name, d in device_list.items()
                       if d['topic'] == topic), None)

    # Fallback Logic: Intercept writes to mmwave_detection_areas:area1
    if fname and param == "mmwave_detection_areas" and isinstance(value, dict) and "area1" in value:
        with device_list_lock:
            use_nested = device_list.get(fname, {}).get('use_nested_area1', False)

        if not use_nested:
            try:
                z_data = value["area1"]
                legacy_payload = {
                    "mmWaveWidthMin": int(z_data.get("width_min", 0)),
                    "mmWaveWidthMax": int(z_data.get("width_max", 0)),
                    "mmWaveDepthMin": int(z_data.get("depth_min", 0)),
                    "mmWaveDepthMax": int(z_data.get("depth_max", 0)),
                    "mmWaveHeightMin": int(z_data.get("height_min", 0)),
                    "mmWaveHeightMax": int(z_data.get("height_max", 0))
                }
                mqtt_client.publish(f"{topic}/set", json.dumps(legacy_payload))
                print(f"Mapped Area 1 write to Top Level params for {fname}", flush=True)
                emit('command_ack', {'param': param, 'status': 'sent_legacy'})
                return
            except Exception as e:
                print(f"Error mapping legacy zone: {e}", flush=True)
                emit('command_error', {'error': f'Legacy mapping failed: {e}'})
                return

    # Standard publish
    if isinstance(value, str) and value.lstrip('-').isnumeric():
        value = int(value)

    control_payload = {param: value}
    mqtt_client.publish(f"{topic}/set", json.dumps(control_payload))
    emit('command_ack', {'param': param, 'status': 'sent'})


@socketio.on('force_sync')
def handle_force_sync():
    sid = request.sid
    with session_topics_lock:
        topic = session_topics.get(sid)
    if not topic:
        emit('command_error', {'error': 'No device selected'})
        return

    if not mqtt_connected:
        emit('command_error', {'error': 'MQTT broker is not connected'})
        return

    # 1. Emit cached data
    with device_list_lock:
        device_data = next((data for data in device_list.values()
                            if data['topic'] == topic), None)
        if device_data:
            cached = {
                'zone_config': dict(device_data.get('zone_config', {})),
                'interference_zones': list(device_data.get('interference_zones', [])),
                'detection_zones': list(device_data.get('detection_zones', [])),
                'stay_zones': list(device_data.get('stay_zones', [])),
            }

    if device_data:
        emit('zone_config', {'topic': topic, 'payload': cached['zone_config']})
        emit('interference_zones', {'topic': topic, 'payload': cached['interference_zones']})
        emit('detection_zones', {'topic': topic, 'payload': cached['detection_zones']})
        emit('stay_zones', {'topic': topic, 'payload': cached['stay_zones']})

    # 2. Trigger Z2M read
    payload = {
        "state": "", "occupancy": "", "illuminance": "",
        "mmWaveDepthMax": "", "mmWaveDepthMin": "",
        "mmWaveWidthMax": "", "mmWaveWidthMin": "",
        "mmWaveHeightMax": "", "mmWaveHeightMin": "",
        "mmWaveDetectSensitivity": "", "mmWaveDetectTrigger": "",
        "mmWaveHoldTime": "", "mmWaveStayLife": "",
        "mmWaveRoomSizePreset": "", "mmWaveTargetInfoReport": "",
        "mmWaveVersion": "", "mmwaveControlWiredDevice": ""
    }
    mqtt_client.publish(f"{topic}/get", json.dumps(payload))

    # 3. Trigger mmWave Module Report
    cmd_payload = {"mmwave_control_commands": {"controlID": "query_areas"}}
    mqtt_client.publish(f"{topic}/set", json.dumps(cmd_payload))
    print(f"Force Sync sent to {topic}", flush=True)


@socketio.on('send_command')
def handle_command(cmd_action):
    sid = request.sid
    with session_topics_lock:
        topic = session_topics.get(sid)
    if not topic:
        emit('command_error', {'error': 'No device selected'})
        return

    if not mqtt_connected:
        emit('command_error', {'error': 'MQTT broker is not connected'})
        return

    action_map = {
        0: "reset_mmwave_module",
        1: "set_interference",
        2: "query_areas",
        3: "clear_interference",
        4: "reset_detection_area",
        5: "clear_stay_areas"
    }
    cmd_string = action_map.get(int(cmd_action))
    if cmd_string:
        mqtt_client.publish(
            f"{topic}/set",
            json.dumps({"mmwave_control_commands": {"controlID": cmd_string}})
        )
        emit('command_ack', {'command': cmd_string, 'status': 'sent'})
    else:
        emit('command_error', {'error': f'Unknown command: {cmd_action}'})


def cleanup_stale_devices():
    """Remove devices not seen for over 1 hour."""
    while True:
        time.sleep(60)
        current_time = time.time()
        with device_list_lock:
            stale_keys = [k for k, v in device_list.items()
                          if (current_time - v.get('last_seen', 0)) > 3600]
            for key in stale_keys:
                del device_list[key]
        if stale_keys:
            socketio.emit('device_list', get_device_list_snapshot())


cleanup_thread = threading.Thread(target=cleanup_stale_devices, daemon=True)
cleanup_thread.start()


@app.route('/')
def index():
    return render_template('index.html',
                           ingress_path=request.headers.get('X-Ingress-Path', ''))


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)