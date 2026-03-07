# Inovelli mmWave Visualizer for Z2M

**Live 2D presence tracking and zone configuration for Inovelli mmWave Smart Switches in Home Assistant.**

[![Open your Home Assistant instance and show the add add-on repository dialog with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fnickduvall921%2Fmmwave_vis)

## Screenshots

| Live Radar Tracking | Zone Editor |
|---|---|
| ![Radar View](screenshots/radar-view.png) | ![Zone Editor](screenshots/zone-editor.png) |

## Overview

Decodes Zigbee2MQTT payloads to visualize real-time MQTT data and configure detection, interference, and stay zones via MQTT commands. The radar overlay reflects the sensors actual field of view (120°–150°) with range arcs at 1m intervals up to 6m.

## Features

- **Live 2D Radar Tracking** — See up to 3 simultaneous targets moving in real-time with historical comet tails and an accurate FOV overlay.
- **Dynamic Zone Configuration** — Visually draw and edit detection room limits (Width, Depth, and Height) directly on the radar map.
- **Interference Management** — View, Auto-Config, and Clear interference zones to filter out fans, vents, and curtains.
- **Multi-Zone Support** — Configure up to 4 areas per zone type (Detection, Interference, Stay).
- **Live Sensor Data** — Streams Occupancy and Illuminance states in real-time via MQTT.
- **Connection Status** — Live indicators for WebSocket and MQTT broker connectivity with automatic reconnection.

## Installation

### Quick Install

Click the button below to add this repository to your Home Assistant instance:

[![Add Repository](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fnickduvall921%2Fmmwave_vis)

### Manual Install

1. Navigate to **Settings → Add-ons** in your Home Assistant dashboard.
2. Click the **Add-on Store** button (bottom right).
3. Click the **three dots (⋮)** in the top right and select **Repositories**.
4. Paste this URL and click **Add**:
   ```
   https://github.com/nickduvall921/mmwave_vis
   ```
5. Close the dialog. **Inovelli mmWave Visualizer** will appear at the bottom of the Add-on Store.

## Configuration

Before starting the add-on, go to the **Configuration** tab and connect it to your MQTT broker.

| Option | Description | Default |
|--------|-------------|---------|
| `mqtt_broker` | Hostname of your MQTT Broker | `core-mosquitto` |
| `mqtt_port` | Broker port | `1883` |
| `mqtt_username` | MQTT username (if applicable) | `""` |
| `mqtt_password` | MQTT password (if applicable) | `""` |
| `mqtt_base_topic` | Base topic for Zigbee2MQTT | `zigbee2mqtt` |

> **Note:** If you use the standard Home Assistant Mosquitto broker add-on, the defaults should work out of the box.

## Switch Setup (Required)

1. Go to your switch's device page in Zigbee2MQTT → **Bind** tab.
2. In the **Clusters** dropdown, add `manuSpecificInovelliMMWave`.
3. Click **Bind**. You should see a green "Bind Success" message.
4. Go to the **Exposes** tab and enable **MmWaveTargetInfoReport**.

> **Note:** Disable Target Info Reporting when not actively using the visualizer, as it generates significant Zigbee network traffic when targets are detected. The visualizer will show a banner reminder if reporting is disabled.

## Usage

1. **Select a Switch** — Use the dropdown at the top to select your device. It may take a moment to populate as it waits for an MQTT message.

2. **View Live Tracking** — The radar map shows real-time target positions within the sensor's field of view. The solid cone represents the rated 120° FOV, and the dashed cone shows the extended ~150° range observed in practice.

3. **Edit Zones:**
   - Open the **Zone Editor** in the sidebar.
   - Select a Target Zone (e.g., "Detection Area 1").
   - Click **Draw / Edit**.
   - Drag the zone on the map or type exact coordinates (including Height/Z-axis) in the sidebar.
   - Click **Apply Changes** to save to the switch.
   - Click **Force Sync** to reload the state from the switch and verify.

4. **Auto-Config Interference:** Clear the room, turn on the moving object (fan, vent, etc.), and click **Auto-Config Interference**. A red exclusion zone should appear.

## Understanding the Zones

**Detection Area (Blue/Green)** — The active boundary of the sensor. Only motion inside this box is tracked. Anything outside is ignored.

**Interference Area (Red)** — An exclusion zone. Motion detected inside is discarded. Used to mask constant motion sources like ceiling fans or curtains.

**Stay Area (Orange)** — A high-sensitivity zone for stationary presence. Intended for areas where people sit or lie down (sofa, bed, desk) to keep lights on during minimal movement.

## Known Limitations

1. **Radar persistence:** The switch does not send an "all clear" when there is no motion. The last tracked target stays on the radar indefinitely after it leaves. Refer to the Occupancy status or packet age to determine if the area is clear.

2. **Network glitches:** On slow Zigbee networks, a drawn zone may briefly disappear after saving if the MQTT command fails to reach the switch. Re-apply the zone if this happens.

## Known Issues

- Stay areas may invert width when applied. Re-apply to fix. This appears to be a Z2M or switch-level issue.

Please open an issue on GitHub if you encounter any bugs.

## Requirements

- Home Assistant OS or Supervised
- [Zigbee2MQTT](https://www.zigbee2mqtt.io/) v2.8.0 or higher (ZHA is not supported)
- At least one Inovelli mmWave Smart Switch

## License

GNU General Public License v3.0