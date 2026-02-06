# Home Assistant Ingress QA Checklist

Last updated: 2026-02-06

## Test Environment
- Home Assistant running the `Inovelli Switch Studio` add-on.
- Zigbee2MQTT connected with at least one `VZM32-SN` device available.
- Add-on configured with valid MQTT credentials and restarted after config changes.

## 1. Launch and Connectivity
- Open the add-on via Home Assistant Ingress.
- Confirm the UI loads without blank sections or JavaScript errors.
- Confirm logs show:
  - `Connected to MQTT Broker with code 0 (Connection accepted)`
  - `Subscribed to topic: zigbee2mqtt/#`
- Confirm at least one switch is discovered in the device selector.

## 2. Device Selection and Session Isolation
- Open two browser sessions (or two different browsers) to the add-on.
- Select different devices in each session.
- Change one writable parameter in session A and verify:
  - Session A publishes to `session A topic/set`.
  - Session B does not switch devices automatically.
- Confirm no cross-session collisions in logs.

## 3. Live and Presence Data
- Verify `Live` tab updates occupancy, area occupancy badges, and illuminance.
- Verify `Presence` tab fields populate from device config.
- Trigger `Force Sync` and confirm:
  - `.../get` publish appears in logs.
  - `query_areas` publish appears in logs.
  - No traceback/errors are logged for `/get` responses.

## 4. Zones Workflow
- Open `Zones` tab and edit one detection area.
- Apply changes and verify `mmwave_detection_areas` publish payload is correct.
- Run `Auto-Config Interference` and verify result feedback appears.
- Run `Clear Interference` and verify interference areas clear and status updates.
- Validate invalid coordinate input is blocked with a visible error message.

## 5. Core Config Tabs
- `Load & Dimming`: change one numeric and one enum setting, then apply.
- `LED & Notifications`: change one LED setting and one composite field.
- `Buttons & Scenes`: change one scene/button behavior parameter.
- `Power & Device`: verify diagnostics render as read-only where appropriate.
- Confirm `Apply` and `Discard` workflows behave correctly with dirty-state indicator.

## 6. Regression and Mobile
- Reload page and confirm active tab persistence works.
- Validate layout on mobile width (< 900 px): tabs and controls remain usable.
- Confirm no regressions in radar visualization and target table updates.

## 7. Log Review Exit Criteria
- No `Traceback` entries during normal use.
- No `Error processing message on .../get` entries.
- All command writes emit `command_result` with status `sent` or clear errors.
- Discovery, zone editing, force sync, and tab navigation all pass.
