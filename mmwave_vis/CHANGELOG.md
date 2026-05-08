# Changelog


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