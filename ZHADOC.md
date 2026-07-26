# Using the mmWave Visualizer with ZHA

This guide covers how to set up the mmWave Visualizer addon when you are using **ZHA** (Zigbee Home Automation) instead of Zigbee2MQTT.

> **Note:** The ZHA integration is experimental and may have unknown issues. I fully expect some stuff not to work right now.

---

## Prerequisites

- Home Assistant with ZHA configured
- At least one **Inovelli VZM32-SN** switch paired to ZHA
- The mmWave Visualizer addon installed
- Custom ZHA Quirk installed in HA

---

## Setup

### 1. Install the Custom Quirk

> **Note:** This quirk is experimental and may have bugs. If you find one, please open an issue on GitHub with the `ZHA` label.

Before proceeding, make sure you have already installed and tested the official Inovelli Quirk:
https://help.inovelli.com/en/articles/13019007-blue-series-mmwave-presence-dimmer-switch-zha-custom-quirk-install

This repo includes two files that replace the official quirk:

```
zha_quark/__init__.py
zha_quark/VZM32SN.py
```

Copy them into the **same `inovelli/` directory the official quirk files are in** — that is, inside whatever directory your `configuration.yaml` `custom_quirks_path` points to — **overwriting** the official `__init__.py` and `VZM32SN.py`.

> **Heads-up on directory names:** Inovelli's install guide names the folder `/config/zhacustomquirks/`, while older versions of this guide said `/config/zha_custom_quirks/`. The folder name itself doesn't matter — what matters is that the files sit inside the one directory `custom_quirks_path` points to. Do **not** create a second quirks directory: files outside `custom_quirks_path` are silently ignored, and leaving the official files in the active directory keeps the official quirk running. Both mistakes look like "quirk installed but no mmWave data" (see Troubleshooting).

If you followed Inovelli's guide, the layout is:

```
/config/
├── configuration.yaml          ← contains custom_quirks_path (below)
└── zhacustomquirks/
    └── inovelli/
        ├── __init__.py         ← replaced with this repo's copy
        └── VZM32SN.py          ← replaced with this repo's copy
```

If you haven't already, tell ZHA where to find custom quirks by adding the following to your `configuration.yaml` (the path must match where you actually put the files):

```yaml
zha:
  custom_quirks_path: /config/zhacustomquirks/
```

Then:

1. Delete the `__pycache__` folder inside `inovelli/` if one exists — stale compiled copies of the official quirk can otherwise keep loading.
2. Restart Home Assistant.
3. **Reconfigure** the device in ZHA (device page → ⋮ menu → *Reconfigure*) so the 0xFC32 binding is created. Without this step the switch has nowhere to send mmWave reports.

#### Verify the quirk is active

After the restart, the VZM32-SN device page in HA should show a new **"mmWave target info report"** switch entity. That entity is created only by this repo's quirk, so it's the definitive check:

- **Entity missing, and the other mmWave entities are unavailable** (showing `restored: true` in Developer Tools → States) → no quirk loaded at all this boot. Check that `custom_quirks_path` points at the right directory and look for import errors in the HA log.
- **Entity missing, but mmWave entities work** → the *official* quirk is still active. Make sure you overwrote the files in the directory `custom_quirks_path` actually points to.
- **Entity present** → the Visualizer quirk is loaded. If the visualizer still shows no data, Reconfigure the device (step 3 above).

### 2. Configure the Addon

Install the addon using the links in the README, then open the **Configuration** tab on the addon page in HA.

- Set `zigbee_stack` to `zha` for ZHA, or `z2m` for Zigbee2MQTT
- All other settings can be left as-is if running within HA
- If you run into issues, enable the **Debug** toggle for more diagnostic output in the log

---

## Home Assistant Integration

### Per-Area Presence Sensors 

The VZM32-SN supports up to 4 independently configured detection zones. To expose per-area occupancy as binary sensors in HA, add the following to your `configuration.yaml`:

```yaml
template:
  - trigger:
      - platform: event
        event_type: zha_event
        event_data:
          device_ieee: "YOUR_DEVICE_IEEE"
          command: "mmwave_anyone_in_area"
    binary_sensor:
      - name: "mmWave Area 1 Occupied"
        unique_id: mmwave_area1_occupied
        state: "{{ trigger.event.data.args.area1 == 1 }}"
        device_class: occupancy
      - name: "mmWave Area 2 Occupied"
        unique_id: mmwave_area2_occupied
        state: "{{ trigger.event.data.args.area2 == 1 }}"
        device_class: occupancy
      - name: "mmWave Area 3 Occupied"
        unique_id: mmwave_area3_occupied
        state: "{{ trigger.event.data.args.area3 == 1 }}"
        device_class: occupancy
      - name: "mmWave Area 4 Occupied"
        unique_id: mmwave_area4_occupied
        state: "{{ trigger.event.data.args.area4 == 1 }}"
        device_class: occupancy
```

Replace `YOUR_DEVICE_IEEE` with the IEEE address of your VZM32-SN, found on the device page in ZHA.

Sensors will show `unavailable` until the first presence event fires after HA restarts, which happens automatically on the next presence change.

---

## Notes

Device names come from your HA device registry. To rename a device, go to **Settings → Devices & Services → Zigbee Home Automation**, find the device, and edit its name there.

---

## Troubleshooting

### No devices appear in the dropdown

- Confirm your VZM32-SN is paired and showing as available in ZHA
- Check the addon log for `ZHA: discovered ...` messages — if none appear, the addon may not be reaching HA

### "not the Visualizer quirk" / "no custom mmWave quirk detected" warning in the log

The addon checks for the **"mmWave target info report"** switch entity, which only this repo's quirk creates.

- `... has a quirk applied, but it is not the Visualizer quirk` — the official Inovelli quirk (or another quirk) is loading instead of this repo's files. Overwrite the official `__init__.py` and `VZM32SN.py` in the directory your `custom_quirks_path` points to, delete `__pycache__`, restart HA.
- `no custom mmWave quirk detected` — no quirk loaded at all. Verify `custom_quirks_path` in `configuration.yaml` matches where the files are, and check the HA log for quirk import errors.

After fixing, restart HA and **Reconfigure** the device in ZHA (see *Verify the quirk is active* above).

### Entities unavailable and no mmWave data after switching quirks

If every mmWave entity shows `unavailable` with `restored: true` (Developer Tools → States), ZHA created no mmWave entities on the last boot — the quirk did not load. This is an installation issue, not a device problem: see the directory-name heads-up in *Install the Custom Quirk*.

### "No token found" warning in the log

The addon cannot authenticate to Home Assistant. Try a full stop and start of the addon (not just a restart).

If that still doesn't work, you can set a token manually:

1. In HA, go to your **Profile** page → scroll to **Long-Lived Access Tokens** → create one
2. In the addon Configuration tab, paste it into the `ha_token` field
3. Restart the addon

### 502 error on startup

HA Core wasn't fully ready when the addon started. The addon will retry automatically every few seconds — wait about 30 seconds and check the log again. This usually resolves on its own after a reboot.

### Settings (sensitivity, hold time, etc.) not showing correct values after selecting a device

Click the **Sync** button. This triggers a fresh read of all settings from the device and populates the sidebar.

### Stay zone coordinates invert after being set

This is a known firmware bug on the VZM32-SN. Re-applying the zone will invert the coordinates back to the correct values.