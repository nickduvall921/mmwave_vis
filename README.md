# Inovelli Switch Studio for Z2M

**Live 2D presence tracking and interference zone configuration for Inovelli Smart Switches in Home Assistant.**

## Overview

Decodes Zigbee2MQTT payloads to visualize real-time MQTT data and configure detection, interference, and stay zones via MQTT commands. Built because I had a need for this when I was setting up my own mmWave Switches.



## ✨ Features

* **📡 Live 2D Radar Tracking:** See up to 3 simultaneous targets moving in real-time with historical comet tails.
* **📏 Dynamic Zone Configuration:** Visually define your detection room limits (Width, Depth, and Height).
* **🚫 Interference Management:** View, Auto-Config, and Clear interference zones directly from the UI to filter out moving fans, vents, and curtains.
* **🔄 Live Sensor Data:** streams Global Occupancy and Illuminance states via MQTT.
* **🧱 Multi-Zone Support:** Configure up to 4 areas per zone type.(Please update to latest version on Z2M)
* **✨ Vibe:** AI assisted in the design of this app

## 🛠️ Installation

### 1. Add this Repository to Home Assistant
1. Navigate to **Settings > Add-ons** in your Home Assistant dashboard.
2. Click the **ADD-ON STORE** button in the bottom right corner.
3. Click the **Three Dots (⋮)** in the top right corner and select **Repositories**.
4. Paste the URL of this GitHub repository and click **Add**.
5. Close the dialog. "Inovelli Switch Studio" will now appear at the bottom of the Add-on store.

## ⚙️ Configuration of Addon

Before starting the add-on, navigate to the **Configuration** tab. You need to connect Switch Studio to the MQTT broker that Zigbee2MQTT uses.

| Option | Description | Default |
|--------|-------------|---------|
| `mqtt_broker` | The hostname of your MQTT Broker | `core-mosquitto` |
| `mqtt_port` | The port your broker uses | `1883` |
| `mqtt_username` | Your MQTT username (if applicable) | `""` |
| `mqtt_password` | Your MQTT password (if applicable) | `""` |

*Note: If you use the standard Home Assistant Mosquitto broker add-on, the default settings will usually work out of the box.*

## 🎚️ Configuration of Inovelli Switches

1. You will need to bind "manuSpecificInovelliMMWave" to Source endpoint 1. You can do this under the switch’s device page in Z2M and then go to the "Bind" tab.
2. Click the Clusters dropdown and add "manuSpecificInovelliMMWave".
3. Then Click Bind. Should see a Green Bind Success message.
4. Lastly go to the Exposes tab and Enable "MmWaveTargetInfoReport". I would recommend disabling this when you don’t need it as it floods the ZigBee network when there is a target detected.


## 🚀 Usage Guide

1. **Select Switch:** Use the top-left dropdown to select your device. It may take a moment to populate as it waits for an MQTT message.
2. **Edit Zones:**
    - Open the Zone Editor sidebar.
    - Select a Target Zone (e.g., "Detection Area 1").
    - Click Draw / Edit.
    - Drag the box on the map or type exact coordinates (including Height/Z-axis) in the sidebar.
    - Click Apply Changes to save to the switch.
    - You can always click Force Sync to reload the state from the switch and make sure everything was sent to the switch correctly.
3. **Map Settings:** Use Studio View Settings to hide specific zones, toggle labels, or adjust the map boundaries (e.g., expand X/Y for large rooms).
4. **Auto-Config:** To mask fans/curtains, clear the room, turn on the moving object, and click Auto-Config Interference. Red zone should appear if sucsesful 

**Detection Area (Green/Blue):** This defines the active boundary of the sensor. The sensor only looks for motion inside this box. Anything happening outside these coordinates is completely ignored.
**Interference Area (Red):** This defines an exclusion zone. Any motion detected inside this box is discarded. This is used to mask out constant motion sources like ceiling fans, oscillating vents, or curtains blowing in the wind.
**Stay Area (Orange):** This defines a high-sensitivity zone specifically for stationary presence. It is intended for areas where people sit or lie down (e.g., a sofa, bed, or desk) to ensure the lights stay on even if you are moving very little (breathing/typing).

## Bugs
**Known Issues**
* Stay areas invert width when applyed. Just reapply to fix. This seems to be a z2m or switch issue as it happens in Z2M if you configure the zones manually.

**Bugs** Please open issues if you run into any bugs in the app. I will try and update the app in due time. I try and test as much as I can but I am limited by time.



## ⚠️ Requirements

* Home Assistant OS or Supervised.
* [Zigbee2MQTT V2.8.0 or higher](https://www.zigbee2mqtt.io/) (ZHA is not supported).
* At least one Inovelli mmWave Smart Switch.

## Licence
GNU General Public License v3.0
