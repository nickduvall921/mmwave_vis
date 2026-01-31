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

current_topic = None

# Stores device names, topics, config, and throttling timers
# Structure: {
#   'friendly_name': str, 
#   'topic': str, 
#   'interference_zones': [], 
#   'last_update': float, 
#   'last_seen': float
# }
device_list = {} 

def on_connect(client, userdata, flags, rc):
    print(f"Connected to MQTT Broker with code {rc}", flush=True)
    client.subscribe(f"{MQTT_BASE_TOPIC}/#")

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
            # Silently ignore malformed JSON to prevent log flooding
            return

        # --- DEVICE DISCOVERY ---
        # Check if message is from our base topic and looks like an mmWave device
        if topic.startswith(MQTT_BASE_TOPIC):
            # If we haven't seen this device before and it reports mmWave version
            if "mmWaveVersion" in payload:
                # Extract friendly name (handling potential trailing subtopics like /get or /set)
                # Structure is typically: base_topic/friendly_name
                parts = topic.split('/')
                if len(parts) >= 2:
                    friendly_name = parts[1]
                    
                    if friendly_name not in device_list:
                        print(f"Discovered Inovelli mmWave Switch: {friendly_name}", flush=True)
                        device_list[friendly_name] = {
                            'friendly_name': friendly_name, 
                            'topic': f"{MQTT_BASE_TOPIC}/{friendly_name}", 
                            'interference_zones': [],
                            'last_update': 0,
                            'last_seen': time.time()
                        }
                        socketio.emit('device_list', [d for d in device_list.values()])
                    else:
                        # Update heartbeat
                        device_list[friendly_name]['last_seen'] = time.time()

        # --- CURRENT DEVICE PROCESSING ---
        # Find device in our list based on the incoming topic
        fname = next((name for name, data in device_list.items() if topic.startswith(data['topic'])), None)
        if not fname: return

        # Emit standard HA states (Occupancy, Illuminance, etc.)
        if "state" in payload or "illuminance" in payload:
            socketio.emit('device_config', payload)

        # --- EXTRACT STANDARD DETECTION ZONE ---
        if "mmWaveDepthMax" in payload:
            zone_config = {
                "x_min": int(payload.get("mmWaveWidthMin", -400) or -400),
                "x_max": int(payload.get("mmWaveWidthMax", 400) or 400),
                "y_min": int(payload.get("mmWaveDepthMin", 0) or 0),
                "y_max": int(payload.get("mmWaveDepthMax", 600) or 600)
            }
            
            # Cache and emit to UI if the zone has changed
            if 'zone_config' not in device_list[fname] or device_list[fname]['zone_config'] != zone_config:
                device_list[fname]['zone_config'] = zone_config
                socketio.emit('zone_config', zone_config)

        # --- PROCESS RAW BYTES (ZCL Cluster 0xFC32) ---
        # Check for signature byte keys indicating a raw packet
        if payload.get("0") == 29 and payload.get("1") == 47 and payload.get("2") == 18:
            cmd_id = payload.get("4")
            
            # --- 0x01: Target Info Reporting (Movement Data) ---
            if cmd_id == 1:
                # Per-Device Throttling (10Hz Max)
                current_time = time.time()
                if (current_time - device_list[fname].get('last_update', 0)) < 0.1:
                    return 
                device_list[fname]['last_update'] = current_time

                seq_num = payload.get("3")
                num_targets = payload.get("5", 0)
                targets = []
                offset = 6

                for _ in range(num_targets):
                    # Ensure we have enough data bytes remaining
                    if str(offset+8) not in payload: break
                    
                    # Optimized Parsing using int.from_bytes (Little Endian)
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
                
                socketio.emit('new_data', {"seq": seq_num, "targets": targets})

            # --- 0x02: Interference Area Reporting ---
            elif cmd_id == 2:
                try:
                    int_zones = []
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
                        
                        # Only append zones with valid non-zero configurations
                        if x_max > x_min and y_max > y_min:
                            int_zones.append({"x_min": x_min, "x_max": x_max, "y_min": y_min, "y_max": y_max})
                        
                        offset += 12
                    
                    device_list[fname]['interference_zones'] = int_zones
                    print(f"Interference Zones Updated for {fname}: {int_zones}", flush=True)
                    socketio.emit('interference_zones', int_zones)
                    
                except Exception as parse_error:
                    print(f"Warning: Interference zone packet offset mismatch: {parse_error}", flush=True)

    except Exception as e:
        print(f"Error processing message on {msg.topic}: {e}", flush=True)
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

    # Convert numeric strings back to integers
    if isinstance(value, str) and value.lstrip('-').isnumeric():
        value = int(value)

    control_payload = { param: value }
    set_topic = f"{current_topic}/set"
    mqtt_client.publish(set_topic, json.dumps(control_payload))
    print(f"Updated {param} to {value} via {set_topic}", flush=True)


# --- FORCE SYNC ---
@socketio.on('force_sync')
def handle_force_sync():
    """
    Sends an empty payload to the /get topic to force Z2M to refresh attributes.
    """
    if not current_topic: return
    
    # Instant UI reset using cached data
    device_data = next((data for data in device_list.values() if data['topic'] == current_topic), None)
    if device_data:
        if 'zone_config' in device_data: socketio.emit('zone_config', device_data['zone_config'])
        if 'interference_zones' in device_data: socketio.emit('interference_zones', device_data['interference_zones'])

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

    control_payload = {
        "mmwave_control_commands": {
            "controlID": cmd_string
        }
    }
    
    set_topic = f"{current_topic}/set"
    mqtt_client.publish(set_topic, json.dumps(control_payload))
    print(f"Sent mmWave Command: {cmd_string} to {set_topic}", flush=True)


# --- STALE DEVICE CLEANUP ---
# Removes devices from the list if they haven't been seen in 1 hour
def cleanup_stale_devices():
    while True:
        time.sleep(60) # Run every minute
        current_time = time.time()
        stale_threshold = 3600 # 1 Hour
        
        # Identify stale keys (avoid modifying dict while iterating)
        stale_keys = [
            name for name, data in device_list.items() 
            if (current_time - data.get('last_seen', 0)) > stale_threshold
        ]
        
        for key in stale_keys:
            print(f"Removing stale device from memory: {key}", flush=True)
            del device_list[key]
            
        # Push update to UI if devices were removed
        if stale_keys:
            socketio.emit('device_list', [d for d in device_list.values()])

cleanup_thread = threading.Thread(target=cleanup_stale_devices, daemon=True)
cleanup_thread.start()


# --- ROUTES ---
@app.route('/')
def index():
    ingress_path = request.headers.get('X-Ingress-Path', '')
    return render_template('index.html', ingress_path=ingress_path)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)