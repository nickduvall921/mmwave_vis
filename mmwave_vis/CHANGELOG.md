# Changelog

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