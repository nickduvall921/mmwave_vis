# Inovelli mmWave Visualizer for Z2M and ZHA(Experimental)

**Live 2D presence tracking and zone configuration for Inovelli mmWave Smart Switches in Home Assistant.**

[![Open your Home Assistant instance and show the add add-on repository dialog with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fnickduvall921%2Fmmwave_vis)

## Screenshots

| Live Radar Tracking | Zone Editor |
|---|---|
| ![Radar View](screenshots/radar-view.png) | ![Zone Editor](screenshots/zone-editor.png) |

## Overview

Decodes Zigbee2MQTT payloads to visualize real-time MQTT data and configure detection, interference, and stay zones via MQTT commands. The radar overlay reflects the sensors actual field of view (120°–150°) with range arcs at 1m intervals up to 6m.

ZHA support has just been added experimentally. Requires a custom Quark that I have built to be installed in ZHA.
[ZHA DOC HERE](ZHADOC.md)

## Features

- **Live 2D Radar Tracking** — See up to 3 simultaneous targets moving in real-time with historical comet tails and an accurate FOV overlay.
- **Dynamic Zone Configuration** — Visually draw and edit detection room limits (Width, Depth, and Height) directly on the radar map.
- **Interference Management** — View, Auto-Config, and Clear interference zones to filter out fans, vents, and curtains.
- **Multi-Zone Support** — Configure up to 4 areas per zone type (Detection, Interference, Stay).
- **Zone Backup** — Export a switch's zones to a file and import them back after a reset or re-pair (Maintenance → Zone Backup).
- **Live Sensor Data** — Streams Occupancy and Illuminance states in real-time via MQTT.
- **Connection Status** — Live indicators for WebSocket and MQTT broker connectivity with automatic reconnection.

## Installation

Two install paths are supported from the same codebase:

- **Home Assistant Addon** — Recommended if you run Home Assistant. Integrates with the Supervisor, uses ingress, and picks up the `SUPERVISOR_TOKEN` automatically for ZHA mode.
- **Standalone Docker** — For users running Zigbee2MQTT in Docker or on a separate machine from Home Assistant.

### Home Assistant Addon

#### Quick Install

Click the button below to add this repository to your Home Assistant instance:

[![Add Repository](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fnickduvall921%2Fmmwave_vis)

#### Manual Install

1. Navigate to **Settings → Add-ons** in your Home Assistant dashboard.
2. Click the **Add-on Store** button (bottom right).
3. Click the **three dots (⋮)** in the top right and select **Repositories**.
4. Paste this URL and click **Add**:
   ```
   https://github.com/nickduvall921/mmwave_vis
   ```
5. Close the dialog. **Inovelli mmWave Visualizer** will appear at the bottom of the Add-on Store.

### Standalone Docker

A pre-built multi-arch image (linux/amd64, linux/arm64) is published to GitHub Container Registry on every release:

```
ghcr.io/nickduvall921/mmwave_vis:latest
```

#### 1. Create a `docker-compose.yml`

```yaml
services:
  mmwave-visualizer:
    image: ghcr.io/nickduvall921/mmwave_vis:latest
    container_name: mmwave_vis
    ports:
      - "5000:5000"
    volumes:
      - ./mmwave_data:/data
    environment:
      - ZIGBEE_STACK=z2m
      - MQTT_BROKER=192.168.1.XX    # Change to your broker IP
      - MQTT_PORT=1883
      - MQTT_USERNAME=              # Optional
      - MQTT_PASSWORD=              # Optional
      - MQTT_BASE_TOPIC=zigbee2mqtt
    restart: unless-stopped
```

#### 2. Start the container

```bash
docker compose up -d
```

#### 3. Open the UI

Navigate to `http://<your-ip>:5000`.

#### Environment Variables

| Variable | Description | Default |
|---|---|---|
| `ZIGBEE_STACK` | `z2m` or `zha` | `z2m` |
| `MQTT_BROKER` | MQTT broker host | `core-mosquitto` |
| `MQTT_PORT` | MQTT broker port | `1883` |
| `MQTT_USERNAME` | MQTT username | `""` |
| `MQTT_PASSWORD` | MQTT password | `""` |
| `MQTT_BASE_TOPIC` | Zigbee2MQTT base topic (also accepts `Z2M_BASE_TOPIC`) | `zigbee2mqtt` |
| `MQTT_USE_TLS` | Enable TLS/SSL | `false` |
| `MQTT_TLS_INSECURE` | Skip cert verification (not recommended) | `false` |
| `MQTT_TLS_CA_CERT` | Path to custom CA certificate file | `""` |
| `HA_URL` | Home Assistant URL (ZHA mode only) | `http://supervisor` |
| `HA_TOKEN` | Long-lived access token (ZHA mode only) | `""` |
| `DEBUG` | Verbose logging | `false` |

#### TLS/SSL

To connect to a TLS-enabled broker (e.g. on port 8883):

```yaml
environment:
  - MQTT_BROKER=your-broker
  - MQTT_PORT=8883
  - MQTT_USE_TLS=true
```

For self-signed certificates, mount your CA cert and reference it:

```yaml
volumes:
  - ./mmwave_data:/data
  - ./ca.crt:/data/ca.crt

environment:
  - MQTT_USE_TLS=true
  - MQTT_TLS_CA_CERT=/data/ca.crt
```

> ⚠️ `MQTT_TLS_INSECURE=true` disables all certificate verification. Only use this on trusted local networks — it defeats the purpose of TLS.

> **Migrating from `mmWave_vis_docker`?** The image path has changed from `ghcr.io/nickduvall921/mmwave_vis_docker:main` to `ghcr.io/nickduvall921/mmwave_vis:latest`. The legacy `Z2M_BASE_TOPIC` env var is still accepted as a fallback, but `MQTT_BASE_TOPIC` is preferred.

## Configuration(Z2M)

Before starting the add-on, go to the **Configuration** tab and connect it to your MQTT broker.

| Option | Description | Default |
|--------|-------------|---------|
| `mqtt_broker` | Hostname of your MQTT Broker | `core-mosquitto` |
| `mqtt_port` | Broker port | `1883` |
| `mqtt_username` | MQTT username (if applicable) | `""` |
| `mqtt_password` | MQTT password (if applicable) | `""` |
| `mqtt_base_topic` | Base topic for Zigbee2MQTT | `zigbee2mqtt` |

> **Note:** If you use the standard Home Assistant Mosquitto broker add-on, the defaults should work out of the box.

## Switch Setup (Required)(Z2M)

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

## Red Series (Z-Wave) Testers

Z-Wave switches aren't supported yet. The VZW32-SN reports target positions on firmware 2.04 and later, but Z-Wave JS doesn't pass those frames on to Home Assistant and their format isn't published. If you own a VZW32-SN, the faint **⋮** button in the top-right corner of the addon opens a packet capture that records the Z-Wave JS driver log (it works whichever Zigbee stack the addon is set to). Attach the downloaded file to [#42](https://github.com/nickduvall921/mmwave_vis/issues/42) to help get support added.

## Requirements

- Home Assistant OS or Supervised
- [Zigbee2MQTT](https://www.zigbee2mqtt.io/) v2.8.0 or higher (ZHA is not supported)
- At least one Inovelli mmWave Smart Switch

## License

GNU General Public License v3.0