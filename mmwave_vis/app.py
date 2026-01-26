import json
import os
import traceback
import time
import gc # Added for memory management
import threading # Added for background watchdog

from flask import Flask, render_template, request
from flask_socketio import SocketIO
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
except FileNotFoundError:
    print("No options.json found. Using defaults.", flush=True)
    MQTT_BROKER = 'core-mosquitto'
    MQTT_PORT = 1883
    MQTT_USERNAME = ''
    MQTT_PASSWORD = ''

Z2M_BASE_TOPIC = "zigbee2mqtt"

app = Flask(__name__)
# Standard threading to prevent Home Assistant CPU lockup
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

current_topic = None
# Stores device names, topics, and cached zone configurations
device_list = {} 
last_update_time = 0

def on_connect(client, userdata, flags, rc):
    print(f"Connected to MQTT Broker with code {rc}", flush=True)
    client.subscribe(f"{Z2M_BASE_TOPIC}/#")

def on_message(client, userdata, msg):
    global device_list, last_update_time
    try:
        topic = msg.topic
        
        # 1. THE FAST-BAIL FILTER (CPU/MEMORY SAVER)
        # Only decode the raw payload, do NOT parse JSON yet.
        payload_str = msg.payload.decode().strip()
        
        # 0. SAFETY CHECK: Ensure valid JSON wrapper
        if not payload_str or not payload_str.startswith('{'):
            return 
            
        # 2. DISCOVERY BYPASS
        # If the message is not for our current topic, check if it's an Inovelli device.
        # We do a fast string search for "mmWaveVersion" before doing expensive JSON parsing.
        if topic != current_topic:
            if "mmWaveVersion" not in payload_str:
                return # Ignore all other Zigbee devices (bulbs, temp sensors, etc.)
                
            # It IS an mmWave device. Now we parse the JSON to add it to the list.
            payload = json.loads(payload_str)
            topic_parts = topic.split('/')
            if len(topic_parts) == 2:
                friendly_name = topic_parts[1]
                if friendly_name not in device_list:
                    print(f"Discovered Inovelli mmWave Switch: {friendly_name}", flush=True)
                    device_list[friendly_name] = {'friendly_name': friendly_name, 'topic': topic, 'interference_zones': []}
                    socketio.emit('device_list', [d for d in device_list.values()])
            return # Done with discovery

        # 3. CURRENT DEVICE PROCESSING
        # If we reach here, the topic matches our currently monitored switch.
        # Now it is safe to parse the JSON.
        payload = json.loads(payload_str)

        fname = next((name for name, data in device_list.items() if data['topic'] == current_topic), None)
        if not fname: return

        # --- EMIT FULL CONFIG TO UI (For both mmWave and Standard switches) ---
        if "state" in payload or "illuminance" in payload:
            socketio.emit('device_config', payload)

        # --- CPU SAVER: IGNORE RAW BYTE PARSING FOR NON-MMWAVE SWITCHES ---
        is_mmwave = payload.get("mmWaveVersion") is not None

        # --- A) EXTRACT STANDARD DETECTION ZONE ---
        if "mmWaveDepthMax" in payload:
            zone_config = {
                "x_min": int(payload.get("mmWaveWidthMin", -400) or -400),
                "x_max": int(payload.get("mmWaveWidthMax", 400) or 400),
                "y_min": int(payload.get("mmWaveDepthMin", 0) or 0),
                "y_max": int(payload.get("mmWaveDepthMax", 600) or 600)
            }
            
            # Cache and emit to UI if changed
            if 'zone_config' not in device_list[fname] or device_list[fname]['zone_config'] != zone_config:
                device_list[fname]['zone_config'] = zone_config
                socketio.emit('zone_config', zone_config)

        # --- B) PROCESS RAW BYTES (ZCL Cluster 0xFC32) ---
        if payload.get("0") == 29 and payload.get("1") == 47 and payload.get("2") == 18:
            cmd_id = payload.get("4")
            
            # Bitwise parser for Signed Int16 (Fixed NoneType handling)
            def get_int16(idx):
                low = int(payload.get(str(idx)) or 0)
                high = int(payload.get(str(idx+1)) or 0)
                val = (high << 8) | low
                return val if val < 32768 else val - 65536

            # --- 0x01: Report Target Info (Movement Data) ---
            if cmd_id == 1:
                # CPU THROTTLE: 10Hz Max
                current_time = time.time()
                if (current_time - last_update_time) < 0.1:
                    return 
                last_update_time = current_time

                seq_num = payload.get("3")
                num_targets = payload.get("5", 0)
                targets = []
                offset = 6

                for _ in range(num_targets):
                    if str(offset+8) not in payload: break
                    targets.append({
                        "id": int(payload.get(str(offset+8)) or 0),
                        "x": get_int16(offset), "y": get_int16(offset+2),
                        "z": get_int16(offset+4), "dop": get_int16(offset+6)
                    })
                    offset += 9
                
                # Send to browser
                socketio.emit('new_data', {"seq": seq_num, "targets": targets})

                # MEMORY LEAK FIX: Explicitly delete the array to free RAM immediately
                del targets

            # --- 0x02: Report Interference Area ---
            elif cmd_id == 2 and fname:
                try:
                    int_zones = []
                    offset = 6  # Start reading coordinate data at Key 6
                    num_zones = payload.get("5", 0) # Key 5 contains the Number of Zones
                    
                    # Loop based on actual number of zones
                    for _ in range(num_zones):
                        if str(offset+11) not in payload: break
                        x_min = get_int16(offset)
                        x_max = get_int16(offset+2)
                        y_min = get_int16(offset+4)
                        y_max = get_int16(offset+6)
                        
                        # Only add zones with valid coordinates
                        if x_max > x_min and y_max > y_min:
                            int_zones.append({"x_min": x_min, "x_max": x_max, "y_min": y_min, "y_max": y_max})
                        
                        # Standard offset for current firmware is 12 bytes per zone
                        offset += 12
                    
                    # Cache and emit interference zones
                    device_list[fname]['interference_zones'] = int_zones
                    print(f"Interference Zones Updated for {fname}: {int_zones}", flush=True)
                    socketio.emit('interference_zones', int_zones)

                    # MEMORY LEAK FIX: Clean up
                    del int_zones
                    
                except Exception as parse_error:
                    print(f"Warning: Interference zone packet offset mismatch. Firmware may have updated: {parse_error}", flush=True)

    except Exception as e:
        print(f"Error parsing message on topic {msg.topic}: {e}", flush=True)
        traceback.print_exc()

mqtt_client = mqtt.Client()
if MQTT_USERNAME and MQTT_PASSWORD:
    mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

try:
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    mqtt_client.loop_start()
except Exception as e:
    print(f"Connection Failed: {e}", flush=True)


# --- WEBSOCKET HANDLERS ---
@socketio.on('request_devices')
def handle_request_devices():
    socketio.emit('device_list', [d for d in device_list.values()])

@socketio.on('change_device')
def handle_change_device(new_topic):
    global current_topic
    current_topic = new_topic
    print(f"Switched monitoring to: {new_topic}", flush=True)
    
    # Send cached configurations immediately upon switch
    device_data = next((data for data in device_list.values() if data['topic'] == new_topic), None)
    if device_data:
        if 'zone_config' in device_data: socketio.emit('zone_config', device_data['zone_config'])
        if 'interference_zones' in device_data: socketio.emit('interference_zones', device_data['interference_zones'])


# --- PARAMETER CONFIGURATOR ---
@socketio.on('update_parameter')
def handle_update_parameter(data):
    if not current_topic: return
    
    param = data.get('param')
    value = data.get('value')

    # Convert numeric strings back to ints
    if isinstance(value, str) and value.lstrip('-').isnumeric():
        value = int(value)

    # Validated Z2M JSON Structure for setting attributes
    control_payload = { param: value }
    
    set_topic = f"{current_topic}/set"
    mqtt_client.publish(set_topic, json.dumps(control_payload))
    print(f"Updated {param} to {value} via {set_topic}", flush=True)


# --- FORCE SYNC (FETCH LATEST STATE) ---
@socketio.on('force_sync')
def handle_force_sync():
    if not current_topic: return
    
    # 1. INSTANT UI RESET: Send the cached coordinates to the browser immediately
    device_data = next((data for data in device_list.values() if data['topic'] == current_topic), None)
    if device_data:
        if 'zone_config' in device_data: socketio.emit('zone_config', device_data['zone_config'])
        if 'interference_zones' in device_data: socketio.emit('interference_zones', device_data['interference_zones'])

    # 2. FETCH LATEST FROM SWITCH: Ask Z2M to read the live values
    get_topic = f"{current_topic}/get"
    payload = {
        "state": "",
        "occupancy": "",
        "illuminance": "",
        "mmWaveDepthMax": "",
        "mmWaveDepthMin": "",
        "mmWaveWidthMax": "",
        "mmWaveWidthMin": "",
        "mmWaveHeightMax": "",
        "mmWaveHeightMin": "",
        "mmWaveDetectSensitivity": "",
        "mmWaveDetectTrigger": "",
        "mmWaveHoldTime": "",
        "mmWaveStayLife": "",
        "mmWaveRoomSizePreset": "",
        "mmWaveTargetInfoReport": "",
        "mmWaveVersion": ""
    }
    
    mqtt_client.publish(get_topic, json.dumps(payload))
    print(f"Force Sync Requested via {get_topic}", flush=True)


# --- CONTROL COMMAND SENDER ---
@socketio.on('send_command')
def handle_command(cmd_action):
    if not current_topic: return
    
    # Map UI button integers to the exact Zigbee2MQTT ZCL strings
    action_map = {
        0: "reset_mmwave_module",
        1: "set_interference",
        2: "obtain_interference",
        3: "clear_interference"
    }

    cmd_string = action_map.get(int(cmd_action))

    if not cmd_string:
        print(f"Unknown command action: {cmd_action}", flush=True)
        return

    # Validated Z2M JSON Structure
    control_payload = {
        "mmwave_control_commands": {
            "controlID": cmd_string
        }
    }
    
    set_topic = f"{current_topic}/set"
    mqtt_client.publish(set_topic, json.dumps(control_payload))
    print(f"Sent mmWave Command: {cmd_string} to {set_topic}", flush=True)


# --- MEMORY LEAK WATCHDOG ---
# Forces Python to clear orphaned socket/thread memory every 30 seconds
def memory_cleanup():
    while True:
        time.sleep(30) 
        gc.collect()

cleanup_thread = threading.Thread(target=memory_cleanup, daemon=True)
cleanup_thread.start()


# --- ROUTES ---
@app.route('/')
def index():
    ingress_path = request.headers.get('X-Ingress-Path', '')
    return render_template('index.html', ingress_path=ingress_path)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)