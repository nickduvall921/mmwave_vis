# Gemini Context: Inovelli mmWave Visualizer Add-on

## Project Overview
I am developing a custom Home Assistant Local Add-on called "mmWave Radar". It provides a real-time 2D Plotly visualization of tracking data from Inovelli mmWave smart switches (Model VZM32-SN) using MQTT over WebSockets.

## Tech Stack
* **Host:** Home Assistant OS (Add-on architecture using `config.yaml`, `Dockerfile`, `run.sh`)
* **Backend:** Python 3.12 (Flask, Flask-SocketIO, Paho-MQTT 1.6.1)
* **Frontend:** HTML5, JavaScript (Socket.IO client, Plotly.js)
* **Data Source:** Zigbee2MQTT (parsing raw Zigbee Cluster 0xFC32 byte arrays)

## Current Architecture Status
1. **MQTT Parsing:** The app subscribes to `zigbee2mqtt/#`, auto-discovers switches with "Inovelli" in the friendly name, and parses the custom `0xFC32` cluster data.
2. **Byte Decoders:**
    * **Command 1 (Targets):** Parses X, Y, Z, Doppler, and ID for up to 3 targets.
    * **Command 2 (Interference):** Parses X/Y coordinates for up to 4 interference zones starting at Key 6.
3. **WebSockets:** The backend pushes data instantly to the frontend.
4. **Ingress:** The app uses Home Assistant Ingress (`X-Ingress-Path`) so the UI loads securely inside the HA sidebar.

## Advanced Control API (Zigbee2MQTT)
The app features two-way communication using Zigbee2MQTT's undocumented composite endpoints.
* **Topic:** `zigbee2mqtt/[FRIENDLY_NAME]/set`
* **Valid JSON Syntax:** `{"mmwave_control_commands": {"controlID": "[COMMAND_STRING]"}}`
* **Mapped Commands:**
    * `set_interference` (Triggers 5-second Auto-Config scan)
    * `clear_interference` (Deletes all zones)
    * `reset_mmwave_module` (Reboots the sensor)

## File Structure
`/addons/mmwave_viz/`
├── `config.yaml` (Defines Ingress, options schema, and metadata)
├── `Dockerfile` (Builds the Python 3 slim image with requirements)
├── `run.sh` (Entry point for HA Supervisor)
├── `requirements.txt` (flask, flask-socketio, paho-mqtt==1.6.1, eventlet)
├── `app.py` (Flask server, MQTT Client, Byte parser, WebSocket emitter)
└── `templates/`
    └── `index.html` (Plotly UI with live table and dynamic device selector)

## Known Quirks / Rules
* **Paho-MQTT Version:** Must use `paho-mqtt==1.6.1` (V2.0 causes fatal connection errors).
* **Ingress Path:** Front-end JS must use `{{ ingress_path }}/socket.io` for the websocket connection.
* **Non-JSON Filtering:** Z2M sends status strings (e.g. "online"). The parser ignores payloads that do not `startswith('{')` to prevent JSON Decode errors.
* **Math Safety:** Raw data from MQTT includes strings/nulls. `get_int16()` uses `int(payload.get())` to prevent TypeErrors during bitwise shifting.
* **ControlID Strictness:** Zigbee2MQTT rejects snake_case, integers, or missing keys for `mmwave_control_commands`. It strictly demands the exact string names from the `inovelli.ts` source code definitions.
* **Empty Zones:** Z2M reports empty interference zones as `0` coordinates. Front-end logic handles this by actively hiding the `rect` shapes in Plotly rather than drawing invisible dots.