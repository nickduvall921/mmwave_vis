# Inovelli mmWave Visualizer for Z2M

**Live 2D presence tracking and interference zone configuration for Inovelli Smart Switches in Home Assistant.**

## Overview

Inovelli mmWave Visualizer. Built this because it was kinda a pain to config the switches without being able to visulaize what was actually going on.

## ✨ Features

* **📡 Live 2D Radar Tracking:** See up to 3 simultaneous targets moving in real-time with historical comet tails.
* **📏 Dynamic Zone Configuration:** Visually define your detection room limits (Width, Depth, and Height) instantly.
* **🚫 Interference Management:** View, Auto-Config, and Clear interference zones directly from the UI to filter out moving fans, vents, and curtains.
* **🔄 Live Sensor Data:** Stream live Occupancy and Illuminance states directly from the switch.
* **🔄 Lots of Vibes:** Yes, it was vibe coded. This is also still an early version but it works for my purposes already so may or may not have many updates.

## 🛠️ Installation

### 1. Add this Repository to Home Assistant
1. Navigate to **Settings > Add-ons** in your Home Assistant dashboard.
2. Click the **ADD-ON STORE** button in the bottom right corner.
3. Click the **Three Dots (⋮)** in the top right corner and select **Repositories**.
4. Paste the URL of this GitHub repository and click **Add**.
5. Close the dialog. "Inovelli mmWave Visualizer" will now appear at the bottom of the Add-on store.

### 2. Install the Add-on
1. Click on **Inovelli mmWave Visualizer** and click **Install**.
2. Once installed, toggle on **Show in sidebar**.

## ⚙️ Configuration of Addon

Before starting the add-on, navigate to the **Configuration** tab. You need to connect the visualizer to the MQTT broker that Zigbee2MQTT uses.

| Option | Description | Default |
|--------|-------------|---------|
| `mqtt_broker` | The hostname of your MQTT Broker | `core-mosquitto` |
| `mqtt_port` | The port your broker uses | `1883` |
| `mqtt_username` | Your MQTT username (if applicable) | `""` |
| `mqtt_password` | Your MQTT password (if applicable) | `""` |

*Note: If you use the standard Home Assistant Mosquitto broker add-on, the default settings will usually work out of the box.*

## ⚙️ Configuration of Inovelli Switches

1. You will need to bind "manuSpecificInovelliMMWave" to Source endpoint 1. You can do this under the switch’s device page in Z2M and then go to the "Bind" tab.
2. Click the Clusters dropdown and add "manuSpecificInovelliMMWave".
3. Then Click Bind. Should see a Green Bind Success message.
4. Lastly go to the Exposes tab and Enable "MmWaveTargetInfoReport". I would recommend disabling this when you don’t need it as it floods the ZigBee network when there is a target detected.


## 🚀 Usage Guide

1. **Start the Add-on** and click **Open Web UI** (or use the Sidebar link).
2. **Select your Switch:** Use the dropdown in the top left to select your Inovelli switch. The add-on will automatically read the latest configuration. May take a bit for them to populate as they need to send a mqtt message to be found.
3. **Tracking Data:** Move in front of the switch. You will see colored dots representing targets. 
    * **Orange** = Moving Away
    * **Green** = Approaching
    * **Gray** = Stationary
4. **Auto-Config Interference:** Ensure the room is clear of people, but turn on fans or objects that cause false positives. Click the **Auto-Config** button. After 5 seconds, the switch will map the moving objects as red "interference zones" and ignore them.
5. **Data Update:** We can only display what has been sent. This program just listens for mqtt messages, decodes them and displays them. if nothing is sent then nothing is displayed

## ⚠️ Requirements

* Home Assistant OS or Supervised.
* [Zigbee2MQTT](https://www.zigbee2mqtt.io/) (ZHA is not supported).
* At least one Inovelli mmWave Smart Switch.