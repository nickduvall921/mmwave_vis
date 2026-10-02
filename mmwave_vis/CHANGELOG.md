# Changelog


## [Unreleased]

### Changed
- New interface. The map is now drawn by the addon itself instead of Plotly, so the page no longer downloads 4.6 MB from cdn.plot.ly, and it stays smooth while people are being tracked.
- Settings moved into three tabs: Zones, Switch settings (anything sent to the switch) and Display (anything that only changes the page).
- Target reporting is an on/off switch at the top of Switch settings.
- Zones are listed with their sizes. Click one on the map or in the list to edit it, and use Add area to pick a free slot.
- The map always shows true scale. The "Lock square aspect ratio" toggle is gone because the map no longer stretches.
- Setup problems, connection drops and command results show above the map or as short pop-up messages instead of banners, pop-ups and browser alerts.
- The Movement recorder's "Apply to zone" is now "Use recording" inside the zone editor.
- The Z-Wave packet capture moved into the ⋮ menu.
- Light theme follows your system setting.
- Built for phones as well as desktops: square map, larger drag handles, Save and Cancel on the map while editing.

### Added
- Room layout (Display tab): drag the switch to where it sits, turn it the way it faces and draw your walls. Zones, people and the field of view move with it. Layouts are saved in the addon's `/data` folder against the switch's IEEE address, so every browser sees the same one and renaming the switch keeps it. If the addon can't write that folder, the page says the layout will be lost on restart. Nothing is sent to the switch.
- Zoom and pan on the map (scroll or pinch, drag to move), plus zoom, Fit zones and Full range buttons on the map. The buttons can be hidden in the Display tab.
- Saving or deleting a zone shows the change on the map straight away (dashed until the switch confirms it). The page asks the switch for its zones until the change shows up, so you no longer need to press Sync. If the change hasn't shown up after 18 seconds it is sent once more, and the page tells you if the switch never confirms. If the switch flips a stay zone, a notice above the map says so, with a button that turns on "Correct mirrored stay zones" and sends the zone again where you drew it.
- Hover coordinates on the map, in the switch's own centimetres.
- Save map image (⋮ menu), replacing Plotly's download button.
- Detection areas fill in on the map while someone is in them.
- The addon remembers the last switch you looked at and opens it again, or opens the only switch there is. On ZHA with more than one switch it waits for you to pick, because the addon follows one ZHA switch at a time and opening the page elsewhere would take it over.

### Fixed
- After the addon restarted or the connection dropped, the page reconnected but stopped receiving data until you picked the switch again. It now picks the switch back up as soon as the addon finds it again.
- Clear interference, Reset detection areas and Clear stay areas now ask before wiping zones.
- On ZHA, target reporting always showed as off, because the quirk exposes it as an on/off switch the addon didn't read. The setting now shows its real value, and the "target reporting is off" reminder works on ZHA.
- On ZHA the light level was never sent, so the empty Light reading is hidden there for now.
- On ZHA with the page open in two places, a zone save, interference command or Sync could go to the switch the other page had open. They now always go to the switch shown on the page that sent them.
- On ZHA the map updates by itself a few seconds after a zone save, Clear interference, Reset detection areas or Clear stay areas, without pressing Sync.
- On ZHA, settings from another device's entities could show up for the selected switch.
- The switch stores some zone edges 1 cm lower than they were sent (it keeps them as 32-bit floats in metres, so 105 comes back as 104 and 499 as 498). A backup restore reported those slots as not matching the backup, and a zone saved like that was never confirmed. Both now allow 1 cm.
- Backup restore could end with "slots don't match" when the switch dropped or delayed one of the writes sent close together (seen on firmware 1.02 through Zigbee2MQTT). Restore now sends again whatever didn't land, up to twice, instead of only re-sending mirrored stay zones.
- On Zigbee2MQTT, a switch whose name starts with another switch's name (say "Kitchen" and "Kitchen 2") could show the other switch's data, and the addon's own commands to a switch were read as reports from it.

## [3.2.8] - 2026-09-27

### Added
- **Issue #52 — zone backup and restore:** a new **Zone Backup** block under Maintenance saves the selected switch's detection, interference and stay zones (all 12 slots, including which are empty) to a JSON file, and puts them back after a reset or re-pair. Export first asks the switch to report its zones and waits until all three zone types have come back, so a half-loaded page can never produce a backup that would clear zones on restore. Import validates the file, asks for confirmation, writes each slot one at a time (600 ms apart so a slow Zigbee network keeps up), then keeps reading the zones back from the switch until every slot has held the same value on two reads in a row, and compares each with the backup; it only reports success when they match, and names any slot that doesn't. (Firmware 1.02 takes about 6 s to apply a zone write and briefly reports a stay zone as written before reporting it mirrored, so a single read can be misleading.) Stay zones that the firmware stored mirrored (the #41 width bug, confirmed on fw 1.02 and 1.03) are re-sent flipped once and re-checked, so they land correctly whether or not the stay-area auto-correct toggle is on. Detection area 1 (the room limits) is never cleared, a zone type missing from the file is left as it is, and the restore stops if the connection drops, the backend rejects a write, or a different switch is selected. Tested end to end on live VZM32-SN switches on ZHA (fw 1.03) and Zigbee2MQTT (fw 1.02), both of which mirror stay zones.

### Fixed
- **Zones could show up in the wrong slot on ZHA (and on the raw Z2M fallback):** zone reports were read only up to the report's `count`, and empty slots were dropped instead of kept in place. With area 2 empty and area 3 set, the page showed area 3's zone as area 2, and editing it wrote to the wrong slot. Both paths now read all four slots by position, like Zigbee2MQTT's own converter, and send empty slots as `null`. A live VZM32-SN always reports `count` 4, even when every slot is empty, so `count` is now only a sanity check (raw frames with a count above 4 are dropped). The raw Z2M decode moved to `utils.decode_raw_zones`, with tests for both paths.
- **The stay-area auto-correct and square-aspect toggles showed "Error: Unknown parameter: None":** the generic sidebar handler sent every sidebar input to the switch as a parameter, including these page-only toggles. It now skips inputs that don't map to a device parameter.
- **Older Z2M firmware reporting detection area 1 as flat attributes:** the page ignored `mmWaveHeightMin` / `mmWaveHeightMax`, so area 1 showed a default height (and a backup would have saved it).

### Changed
- Bumped version to 3.2.8.

## [3.2.7] - 2026-09-27

### Fixed
- **Issue #50 — interference zone height (Z) always showed 0 / 300 in the GUI:** the `interference_zones` handler replaced the `z_min`/`z_max` the switch reported with whatever the page was already showing, falling back to 0 / 300. After a reload, a device change or Force Sync the page therefore always showed 0 / 300, even though the switch held the configured values. It now shows the reported range, the same as detection and stay zones. Mostly visible on ZHA, where the zone report is the only source of these values.
- **Legacy raw target decoder is back to a 9-byte stride (supersedes the 3.2.4 change, PR #49):** each `reportTargetInfo` record is `x, y, z, dop` as little-endian int16 followed by a **one-byte** `id`, as captured from a live VZM32-SN (fw `0x01030102`) and as Zigbee2MQTT decodes it since herdsman-converters #12284. The 10-byte stride adopted in 3.2.4 followed a vendor doc error and garbled every target after the first. Only affects the raw-bytes fallback for Z2M older than 2.9. The decode now lives in `utils.decode_raw_targets`, with tests built from the captured frame.
- **ZHA quirk: only the first mmWave target in a frame was reported.** `report_target_info` (cluster 0xFC32, command 0x01) declares a fixed single-target schema, but the sensor repeats the `(x, y, z, dop, id)` block once per tracked target — up to four. Zigpy parsed target 1, logged the rest as leftover bytes at debug level, and the quirk emitted a single `mmwave_target_info` event, so a room with several people only ever produced one plotted target. The command schema is now `target_num` plus a trailing byte string, and `_parse_target_info()` re-splits the payload and fires one event per target (each carrying the existing `x/y/z/dop/id/target_num` keys plus a new `target_index`). Verified against a frame captured from live VZM32-SN firmware `0x01030102` (`1d 2f 12 38 01 | 01 b5 00 9e 00 08 00 c8 00 01` — a 9-byte per-target stride with a one-byte id), and cross-checked against zigbee-herdsman-converters, whose `report_target_info` converter decodes the same frame shape with `stride = 9` and `count = min(targetNum, floor(len/stride))`; a 3000-frame randomized differential test against a port of that converter finds no disagreements. The vendor cluster document's claim that `id` is `int16` does not match this firmware, so the wider stride is accepted only when the payload length can be explained no other way.
- **ZHA quirk: five config entities could not reach valid values.** `dimming_speed_up_local` capped at 126 (the device ships at 127, so the live value sat outside its own slider); `default_level_local` was 1-254 and `double_tap_up_level` / `double_tap_down_level` capped at 254, hiding the documented 255 sentinels (return-to-previous-level, send-ON, send-OFF); `mmwave_room_size_preset` allowed 0-5 when only 0-3 (Custom/Small/Medium/Large) exist. Ranges now match the Zigbee2MQTT converter, confirmed against a live Z2M VZM32-SN.
- **ZHA quirk: three attribute types disagreed with both upstream zha-quirks and Zigbee2MQTT.** `periodic_power_and_energy_reports` (0x0013) was declared `uint8_t` against an actual range of 0-32767, so writing any value above 255 raised `ValueError` before reaching the device (a live Z2M switch has it set to 3600); it is now `uint16_t`. `power_type` (0x0015) is back to `Bool` and `internal_temp_monitor` (0x0020) back to `int8s`.
- **ZHA quirk: a malformed button event took down the frame handler.** `BUTTONS[...]` / `PRESS_TYPES[...]` raised `KeyError` out of `handle_cluster_request` for any unrecognised button or press type; unknown values are now logged and ignored.
- **ZHA quirk: `bind()` dropped `**kwargs`,** narrowing the base-class signature that zigpy supports.

### Added
- **Z-Wave packet capture for Red Series testers (#42):** a faint **⋮** button in the header's top-right corner opens a panel that records the Z-Wave JS driver log through Home Assistant and offers it as a download. The VZW32-SN reports target positions on firmware 2.04+, but Z-Wave JS has no handler for Inovelli's Manufacturer Proprietary (0x91) frames, so they only show up in the driver log. While capturing, the driver log level is raised to `debug` (raw serial frames) and restored afterwards, including after a dropped connection; captures stop on their own after 15 minutes or 100,000 lines. The file header lists the Inovelli nodes on the network with their firmware. Works whichever `zigbee_stack` is selected.
- **Issue #7 — optional "Lock square aspect ratio" toggle (Radar Map Size, off by default):** the radar map otherwise stretches to fill the window and distorts the represented space. When enabled, the y-axis is constrained to the x-axis (`scaleanchor`/`scaleratio`) so the map keeps a true 1:1 cm-per-pixel aspect (letterboxing instead of stretching). Off by default to preserve the existing fill-the-window behaviour; the setting persists in `localStorage`.
- **Issue #41 — "Auto-correct stay-area inversion bug" toggle (Zone Editor, off by default):** the VZM32-SN firmware mirrors the width (X) axis of stay zones on apply, so a normally-entered zone otherwise needs applying twice. When enabled, the toggle pre-inverts stay-zone width (negate + swap, preserving min < max) so a single apply lands correctly. Detection/interference zones are unaffected. Off by default so the app never silently alters entered coordinates; the setting persists in `localStorage`.

### Changed
- **Issue #54 — `ZHADOC.md` covers HA 2026.8+ native VZM32-SN support:** the Visualizer still needs this repo's quirk, because the native one doesn't forward the switch's live target, area-occupancy or zone reports as events. The official-quirk prerequisite now applies only to HA 2026.7 and earlier.
- Bumped version to 3.2.7.
- `zha_quark/quark-ref.txt`: section 11.10 described a `handle_message()` raw-byte override that the quirk no longer has; it now documents the actual decode path. Section 3.2 documents `target_index` and the per-target event fan-out, and the parameter tables carry the corrected ranges.
- Removed the unused `_parse_area_report_raw()` helper left behind by that earlier raw decoder.
- **Issue #46 — ZHA 0xFC32 binding diagnosability:** the quirk now logs the ZDP bind result and the post-bind `query_areas` send at INFO (was DEBUG) so users can confirm in the HA log whether the bind fired and its ZDO status without enabling debug logging. The addon's "binding may be missing" warning now spells out the full fix sequence (reload quirk + restart, Reconfigure, enable the target-info switch), and `ZHADOC.md` gains a dedicated "No mmWave data / binding missing" troubleshooting section plus a note about stale entities left behind when migrating from the official Inovelli quirk.

## [3.2.6] - 2026-08-24

### Fixed
- **Issue #53 — ZHA: no switches found, log loops `connection lost (sent 1009 (message too big) frame exceeds limit of 1048576 bytes)`:** the `websockets` client caps incoming messages at 1 MiB by default. Right after authenticating, the addon fetches full registry dumps for device discovery (`config/device_registry/list`, `zha/devices` — the latter carries per-device cluster signatures plus neighbor/route tables), and on installs with enough devices/entities a response exceeds the cap, so the client closed the socket with code 1009 before discovery completed — then hit the same wall on every reconnect. Reproduced on a real ~30-addon install and verified fixed there. The connection now passes `max_size=None` (the peer is HA Core via the trusted local Supervisor proxy, so an incoming-size cap buys nothing), and a regression test pins the setting.

### Changed
- Bumped version to 3.2.6.

## [3.2.5] - 2026-07-26

### Fixed
- **Issue #46 — ZHA quirk detection gave a false all-clear:** `_check_quirk_ok` treated "cluster 0xFC32 present" as proof the Visualizer quirk was installed, but 0xFC32 is in the VZM32-SN's raw signature even with **no** quirk loaded, and `quirk_applied` is true for *any* quirk (including the official Inovelli one). Users whose Visualizer quirk never loaded — the exact failure in #46, where every mmWave entity sat `unavailable`/`restored: true` — still saw `quirk_ok: true` while the addon waited forever for FC32 data. Detection now checks the HA entity registry for the **"mmWave target info report"** switch, which only the Visualizer quirk creates (matched via `unique_id`/`entity_id`/`original_name`, so renames don't defeat it). When registry data is unavailable the old heuristic still applies as a fallback. The warning log now also distinguishes "official quirk still active" from "no quirk loaded at all", with pointers to the fix, and `quirk_ok` is refreshed for already-known devices on reconnect so the banner heals after the user corrects their install.
- **ZHADOC.md quirk install directions could strand the quirk in an unloaded directory:** the guide said to copy the files into `config/zha_custom_quirks/`, but the official Inovelli article it lists as a prerequisite installs to `config/zhacustomquirks/` (no underscores) and points `custom_quirks_path` there — following both verbatim leaves the Visualizer files in a directory ZHA never reads (or the official quirk still active), which presents exactly like #46. The guide now says to overwrite the official files in whatever directory `custom_quirks_path` points to, warns about the naming mismatch, adds a `__pycache__` cleanup step, fixes the repo file paths (`zha_quark/`, not `mmwave_vis/zha_quirk/`), and documents how to verify the right quirk is active via the "mmWave target info report" entity.

### Changed
- Bumped version to 3.2.5.

## [3.2.4] - 2026-04-23

### Fixed
- **Legacy raw-bytes target decoder used wrong 9-byte stride (mirrors upstream Z2M bug fixed in [Koenkk/zigbee-herdsman-converters#11915](https://github.com/Koenkk/zigbee-herdsman-converters/pull/11915), 2026-04-11):** the Inovelli `0xFC32` cluster's `reportTargetInfo` records are 10 bytes each (`x, y, z, dop, id` as little-endian int16), not 9 bytes with a uint8 id. Z2M had the same bug until herdsman PR #11915 corrected the stride and stopped clamping the ID to 0–255. Updated `_process_target_data` to match: stride 10, `id` parsed as int16LE. This path is dormant on Z2M ≥ 2.9 (3.2.2 already gates it off whenever parsed `mmwave_targets` is present), but pre-2.9 Z2M users who relied on the raw fallback now get correct coordinates for every target instead of garbage on target #2+.

### Changed
- Bumped version to 3.2.4.

## [3.2.3] - 2026-04-23

### Fixed
- **Issue #26 — Zone 1 occupancy not displayed:** the "Area 1 (Primary)" row under Live Sensors was actually wired to the device's global `occupancy` attribute (OR of all zones), and no `area1Val` element existed in the Zone Status section — so the JS loop that updates `area{1..4}Val` from `mmwave_area{i}_occupancy` silently skipped Zone 1. Relabeled the Live Sensors row to "Global Occupancy" (accurate to what it shows) and added the missing `area1Val` element so Zone 1's real per-area occupancy now renders alongside Zones 2–4.

### Changed
- Bumped version to 3.2.3.

## [3.2.2] - 2026-04-16

### Fixed
- **Live target tracking still empty / jumpy on Z2M 2.9.x+ (follow-up to 3.2.1):** when Z2M publishes a state message, it contains *both* the parsed `mmwave_targets` array *and* the legacy raw ZCL byte keys (`"0": 29, "1": 47, "2": 18, ...`). In Z2M 2.9+ the raw-byte layout at offset ≥ 6 is no longer the legacy target-report format, so decoding it yields garbage coordinates. Worse, the raw path ran first and claimed the shared 10 Hz throttle slot, silently dropping the correct parsed emit that 3.2.1 added. `on_message` now skips the raw `_process_target_data` call whenever parsed `mmwave_targets` is present in the same payload, letting the parsed path be authoritative. Zone decoding (cmd_id 2/3/4) is unaffected.

### Changed
- Bumped version to 3.2.2.

## [3.2.1] - 2026-04-16

### Fixed
- **HA addon install failing with "base name ($BUILD_FROM) should not be blank"** — `mmwave_vis/build.yaml` was missing, so the supervisor couldn't tell newer BuildKit which base image to substitute for `ARG BUILD_FROM`. Pinned `ghcr.io/home-assistant/{aarch64,amd64}-base:3.21`.
- **Issue #27 — radar empty on Z2M 2.9.x+:** Z2M ≥ 2.9.x now parses cluster `0xFC32` target reports into a top-level `mmwave_targets` array instead of forwarding raw ZCL bytes. The Z2M driver only recognized the raw format, so the frontend's `new_data` event never fired and the radar stayed empty. Zones kept working because they're rebuilt from the flat `mmWaveWidthMin/Max`-style config keys. Added a parsed-`mmwave_targets` path that shares a 10 Hz throttle with the raw path.
- **`TypeError: handle_connect() takes 0 positional arguments but 1 was given`** on every browser socket.io handshake — `python-socketio` ≥ 5.7 (which `flask-socketio==5.5.1` resolves to) passes an `auth` arg to the `connect` handler. Handler now accepts `auth=None`; value is unused (ingress handles auth upstream).
- **Docker publish workflow was never firing on releases** — releases created by another workflow using the default `GITHUB_TOKEN` do not emit downstream `release: published` events. Switched the trigger to `push: tags: ['v*']` so every release tag reliably kicks off the image build. Added a `tag` input to `workflow_dispatch` so past tags can be retroactively published: `gh workflow run docker.yml --ref main -f tag=vX.Y.Z`.

### Changed
- Bumped version to 3.2.1.

## [3.2.0] - 2026-04-16

### Added
- **Standalone Docker image:** A pre-built multi-arch image (linux/amd64 + linux/arm64) is now published to `ghcr.io/nickduvall921/mmwave_vis:latest` on every GitHub release. Users running Zigbee2MQTT outside of Home Assistant can now `docker compose up -d` instead of needing the HA Supervisor. A root-level `Dockerfile` and `docker-compose.yml` have been added for users who prefer to build locally.
- **MQTT TLS/SSL support:** New config keys / env vars `mqtt_use_tls`, `mqtt_tls_insecure`, and `mqtt_tls_ca_cert` (or `MQTT_USE_TLS` / `MQTT_TLS_INSECURE` / `MQTT_TLS_CA_CERT`) enable connections to brokers on port 8883 and similar, with optional custom-CA support for self-signed certificates.
- **Environment-variable configuration:** All config options (MQTT, ZHA, debug) now fall back to environment variables when `/data/options.json` is absent, so the same codebase runs unchanged as both an HA addon and a standalone Docker container. HA's `options.json` still takes precedence when present. The legacy `Z2M_BASE_TOPIC` env name (from the old `mmWave_vis_docker` repo) is still accepted for backwards compatibility.
- **Docker build workflow:** `.github/workflows/docker.yml` builds and pushes the multi-arch image to GHCR on each `release: published` event, or on manual dispatch.

### Changed
- Consolidated the separate `mmWave_vis_docker` repo into this repo. The old repo is deprecated — please migrate to `ghcr.io/nickduvall921/mmwave_vis:latest`.
- Bumped version to 3.2.0.

## [3.1.5] - 2026-04-08

### Fixed
- **"Unknown parameter: None" error when switching recording slots:** The global sidebar change-event handler was catching the recording slot dropdown and firing an `update_parameter` emit with `param: null`. Added `recording` prefix to the handler's exclusion list so recording controls are skipped.
- **NaN SVG rendering errors in radar chart:** Plotly produced `<path> attribute d: Expected number, "MNaN,NaN..."` errors from three sources: (1) `localStorage` restoration of chart axis ranges used `parseInt()` without NaN guards — a corrupted or empty stored value would propagate NaN into `layout.xaxis.range`; (2) `updateRadarScale()` persisted NaN to `localStorage` when an input field was cleared, corrupting future sessions; (3) device target payloads with NaN coordinates flowed directly into Plotly traces. Fixed with `isNaN()` guards on all three paths.

### Changed
- Bumped version to 3.1.5.

## [3.1.4] - 2026-03-23

### Added
- **Movement Recorder with 3 slots:** New standalone "Movement Recorder" section (separate from the zone editor) lets users record sensor data into up to 3 independent slots. Each slot is color-coded (orange, green, purple) and shows recorded dots with a dashed bounding box on the chart. After recording, use "Apply to Zone" to load any slot's bounds (plus configurable padding, default 20 cm) into the currently-editing zone. Slots persist across zone edits, so one recording session can be reused for multiple zones. Buffer capped at 5,000 points per slot.

### Changed
- Bumped version to 3.1.4.

## [3.1.3] - 2026-03-22

### Added
- **ZHA binding timeout warning (issue #18):** When a ZHA device is selected but no data arrives within 10 seconds, an amber warning banner appears explaining that the 0xFC32 cluster binding may be missing and directing the user to reconfigure the device in ZHA. The banner auto-dismisses when data starts flowing. Addresses the "switches listed, but never connect" scenario where commands go out but reports never come back.
- **8 binding-timeout tests:** `tests/test_zha_binding_timeout.py` verifies timer start/cancel, device switching, wrong-device events, dismiss-on-data, and idempotent cancel.

### Changed
- Bumped version to 3.1.3.

## [3.1.2] - 2026-03-22

### Fixed
- **Phantom `/get` and `/set` devices in device list (Z2M):** When Z2M echoes back the full device state on `…/get` or `…/set` response topics, the discovery logic treated them as new devices, creating phantom entries like `kitchen/get` alongside the real `kitchen` device. Fixed by filtering out any topic ending with `/get` or `/set` before device discovery.

### Added
- **38 discovery-filter tests:** `tests/test_z2m_discovery_filter.py` verifies `/get` and `/set` suffix rejection, cascading `/get/get` chains, case sensitivity, device names containing "get"/"set" as substrings (e.g. "gadget", "sunset"), bridge/system topics, custom base topics, and missing `mmWaveVersion` payloads.

### Changed
- Bumped version to 3.1.2.

## [3.1.1] - 2026-03-21

### Fixed
- **Device names containing `/` could not be saved (Z2M):** If a Z2M friendly name included a forward slash (e.g. `Switch w/ mmWave`), the MQTT topic parser split the name on `/` and discarded everything after it, causing the device to be discovered under the wrong name. Any attempt to save settings would publish to the wrong MQTT topic and silently fail. Fixed by joining all topic segments after the base with `/` (`'/'.join(parts[1:])`) to preserve the full name.

### Added
- **38 topic-parsing tests:** `tests/test_z2m_topic_parsing.py` verifies the friendly-name extraction round-trips correctly for forward slashes, `&`, `+`, `#`, `%`, brackets, quotes, emoji, CJK, Arabic, and realistic combinations like `"Switch w/ mmWave & Dimmer"`.

### Changed
- Bumped version to 3.1.1.

## [3.1.0] - 2026-03-20

### Fixed
- **Target Reporting banner not showing in ZHA mode:** The banner that warns when Target Info Reporting is disabled was silently dropped for ZHA users. ZHA `select` entities report their state as a display string (e.g. `"Disable (default)"`) rather than an integer string. The previous translation logic called `int(float(raw_state))`, which raised `ValueError` for display strings, causing `mmWaveTargetInfoReport` to be silently omitted from every `device_config` payload — so the banner condition was never triggered. Fixed by checking whether the raw state already matches a known display string before attempting integer conversion.

### Added
- **ZHA custom quirk detection:** The backend now checks whether the custom Inovelli ZHA quirk is installed when a device is discovered. Detection checks for cluster `0xFC32` (the mmWave custom cluster) in the device's endpoint cluster lists — the strongest indicator — and falls back to ZHA's generic `quirk_applied` flag. A warning banner appears in the UI when the quirk is not detected, explaining that target reporting and zone commands require the custom quirk. The banner is dismissed automatically if a subsequent force-sync confirms the quirk is present.
- **Unit test suite (116 tests):** New `tests/` directory with pytest covering `validate_parameter`, `safe_int`, `parse_signed_16`, `_translate_state`, and `_check_quirk_ok`. Tests run with `pytest tests/ -v` from the repo root (requires `pip install -r requirements-dev.txt`).

### Changed
- Pure utility functions (`validate_parameter`, `safe_int`, `parse_signed_16`) extracted from `app.py` into `mmwave_vis/utils.py` to enable isolated unit testing without triggering MQTT or config-file side effects on import.
- Quirk detection logic extracted into `ZHAClient._check_quirk_ok(dev)` static method for testability.
- Bumped version to 3.1.0.

## [2.2.1] - 2025-03-06

### Fixed
- **Flask compatibility crash:** Fixed `AttributeError: property 'session' of 'RequestContext' object has no setter` that prevented devices from loading for some users. Caused by unpinned Flask dependency resolving to 3.2.x during Docker build, which removed the `RequestContext.session` setter that flask-socketio relies on. Users who installed or rebuilt the addon after Flask 3.2 was published would hit this on every WebSocket connection.

### Changed
- Pinned Flask to `>=3.1,<3.2` in `requirements.txt` to ensure consistent builds across all users regardless of install timing.
- Added `manage_session=False` to the SocketIO constructor. The addon does not use Flask sessions, so this bypasses the session handling code path entirely as additional protection against future Flask version changes.

## [2.2.0] - 2025-03-04

### Fixed
- **Crash when `mmwave_detection_areas` is null ([#issue](https://github.com/nickduvall921/mmwave_vis/issues/15)):** Some switches report `mmwave_detection_areas: null` in their Z2M payload. The backend tried to call `.get("area1")` on `None`, crashing the entire message handler on every incoming message and preventing devices from appearing in the list.
- **Resilient message processing:** The monolithic MQTT message handler has been split into isolated stages (device discovery, target tracking, zone reports, config updates). A failure in one stage no longer kills processing for the others — previously a single crash would abort the entire handler, flooding logs and stalling the UI.
- **Defensive data access throughout backend:** `num_targets` and `num_zones` now use `safe_int()` with sanity bounds instead of raw payload values passed to `range()`. Target IDs, command actions, and device list lookups all guard against unexpected types. Stale device references after lock release are handled safely.
- **Frontend null guards:** `parseZ2MArea` now rejects non-object values. All three zone area handlers (`mmwave_detection_areas`, `mmwave_interference_areas`, `mmwave_stay_areas`) validate the payload is a dict before iterating, preventing crashes when Z2M sends `null` or unexpected types.

### Added
- **Target Reporting banner:** A compact info banner appears above the radar chart when a device has Target Info Reporting disabled, explaining why no position data is visible. Includes a one-click "Enable now" link that sends the setting to the switch and dismisses itself.

### Changed
- Bumped version to 2.2.0.

## [2.1.0] - 2025-02-17

### Fixed
- **Multi-user bug:** Each browser session now tracks its own selected device independently. Previously, two users opening the addon would fight over a single global device selection, causing cross-talk and missed data.
- **Thread safety:** Device list is now protected with locks to prevent crashes (`dictionary changed size during iteration`) when MQTT messages arrive while the cleanup thread runs.
- **Crash on non-dict MQTT payloads:** Fixed `TypeError: argument of type 'int' is not iterable` caused by Z2M publishing bare integers to parameter confirmation topics (e.g. `/set/mmWaveHoldTime`).
- **Internal code cleanup:** Byte parsing function moved out of loop to prevent fragile closure behavior.
- Wrapped all Plotly chart calls in try/catch to prevent UI crashes if chart element is unavailable.
- **Zone editing: non-target zones no longer draggable.** Shapes are only interactive when you click "Draw / Edit" on a specific zone. Previously, all zones became draggable whenever the editor was open, making selection difficult.
- **Zone editing: zones locked outside edit mode.** Zones on the radar map can no longer be accidentally dragged when no zone is selected for editing.

### Added
- **Connection status indicators:** Live Server and MQTT status dots in the status bar show green/red/pulsing states so you always know if the backend is connected.
- **Reconnection banner:** A banner appears when WebSocket disconnects and auto-dismisses on reconnect. MQTT broker disconnections are also surfaced.
- **Command error feedback:** Toast notifications appear when a command fails (e.g. no device selected, MQTT down, invalid parameter). Previously the UI silently did nothing.
- **Parameter validation:** All settings sent to the switch are now validated against a whitelist before being published to MQTT. Invalid or unexpected values are rejected with an error message instead of being forwarded blindly.
- **Accurate FOV overlay:** The radar grid now reflects the actual field of view instead of generic concentric circles. A solid cone shows the rated ±60° (120°) FOV, with a dimmer dashed cone showing the ±75° (150°) extended range observed in Inovelli beta testing. Range arcs are drawn at 1m intervals up to 6m with labels.
- **Non-target zone context during editing:** When editing a zone, other zones remain visible (dimmed) as scatter traces for spatial reference, but cannot be dragged or selected.

### Changed
- Bumped version to 2.1.0.
- Target table rendering now builds HTML in a single assignment instead of incremental `innerHTML +=`.
- On WebSocket reconnect, the frontend automatically re-subscribes to the previously selected device.
- Default radar map X scale widened from ±450cm to ±600cm to accommodate the full extended FOV cone.

## [2.0.2]

### Added
- Initial public release with live 2D radar tracking, multi-zone editor, interference management, and real-time sensor data.