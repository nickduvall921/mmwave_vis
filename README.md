# Inovelli Switch Studio

Home Assistant add-on for monitoring and configuring Inovelli Zigbee switches through Zigbee2MQTT, with a current focus on VZM32-SN mmWave presence features.

## Overview

Inovelli Switch Studio bridges Zigbee2MQTT and Home Assistant Ingress to provide:

- Live mmWave radar visualization
- Zone editing for detection, interference, and stay areas
- Schema-driven switch configuration UI
- Batched apply/discard editing workflow
- Per-device command and state feedback

The app discovers supported Inovelli devices from MQTT traffic and routes configuration changes to the currently selected device topic.

## Requirements

- Home Assistant OS or Home Assistant Supervised
- Zigbee2MQTT (ZHA is not supported by this add-on)
- Inovelli Zigbee switch(es)
- For radar/zone features: VZM32-SN mmWave model

## Installation

1. In Home Assistant, open `Settings -> Add-ons`.
2. Open the Add-on Store.
3. Add this repository URL under `Repositories`.
4. Install `Inovelli Switch Studio`.

## Add-on Configuration

Configure the add-on options before starting:

| Option | Description | Default |
|---|---|---|
| `mqtt_broker` | MQTT broker hostname | `core-mosquitto` |
| `mqtt_port` | MQTT broker port | `1883` |
| `mqtt_username` | MQTT username (if required) | `""` |
| `mqtt_password` | MQTT password (if required) | `""` |
| `mqtt_base_topic` | Zigbee2MQTT base topic | `"zigbee2mqtt"` |
| `switch_studio_ui` | Enable tabbed UI (`false` shows fallback legacy-focused layout) | `true` |

## Zigbee2MQTT Setup Notes (VZM32-SN)

For live target tracking and radar updates:

1. Bind `manuSpecificInovelliMMWave` on source endpoint 1 in Zigbee2MQTT.
2. Enable `mmWaveTargetInfoReport` when needed.

Switch Studio includes an in-app `Live Position Reporting` toggle and optional `Auto-off on disconnect` behavior to reduce accidental long-term reporting.

## Current UI Layout

### Presence & Zones

- Target reporting toggle
- Live radar map
- Target table
- Live sensors
- Zone status
- Zone editor
- Presence and motion controls
- Studio view/map settings
- Maintenance tools (auto-config interference, clear/reset actions)

### Load & Dimming

Frequently adjusted load behavior and dimming response controls.

### LED & Notifications

LED and notification configuration, including:

- Color preset selectors
- Brightness sliders
- Composite effect controls

### Buttons & Scenes

Scene and paddle interaction behavior.

### Power & Device

Operational power/device controls and diagnostics that are not classified as advanced.

### Advanced

- Set-and-forget configuration (including runtime options)
- `Fan Parameters (May Not Apply)` section for shared firmware fields that are not applicable to VZM32-SN

## Behavior Notes

- Changes are queued and shown as pending.
- `Apply` sends queued updates in batch.
- `Discard` reverts pending controls to latest device state.
- Device routing is session-scoped: each browser session can monitor/configure a different device safely.
- Legacy stored tab values are normalized automatically (`live`/`presence` -> `zones`, `maintenance` -> `advanced`).

## Testing

Backend tests:

```powershell
python -m unittest discover -s tests/python -p "test_*.py" -v
```

Frontend tests:

```powershell
node --test tests/frontend/*.test.js
```

Manual QA checklist:

`docs/HOME_ASSISTANT_INGRESS_QA_CHECKLIST.md`

## License

GNU General Public License v3.0
