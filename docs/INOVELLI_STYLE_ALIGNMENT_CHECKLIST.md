# Inovelli Switch Studio Style Alignment Checklist

Last updated: 2026-02-09  
Status: In progress

## Alignment Constraint
- Keep the current top strip status content in Presence & Zones:
  - monitored switch label
  - packet/command status
  - error/status text
  - last packet timing

## Goal
Bring current UI styling in line with the desired reference (`desired_style_reference.png` and `inovelli-redesign.jsx`) while preserving current app behavior and schema-driven controls.

## Phase A1: Design Tokens + Typography
- [x] SA-101 Normalize color tokens to desired dark-surface palette.
- [x] SA-102 Standardize border, shadow, and radius tokens to reduce visual noise.
- [x] SA-103 Finalize type scale and spacing rhythm (header/nav/sidebar/body).
- [x] SA-104 Ensure DM Sans is consistently applied across shell and controls.

Acceptance:
- Visual contrast and hierarchy match target direction without reducing readability.
- No functional regressions.

## Phase A2: App Shell + Navigation Polish
- [x] SA-201 Refine top header density and spacing to match target proportions.
- [x] SA-202 Refine primary tab bar visual weight and active state treatment.
- [x] SA-203 Keep and polish the status/meta strip (no removal of packet/monitor info).
- [x] SA-204 Tighten zone pills and meta chips to target compact style.

Acceptance:
- Shell visually matches target composition and spacing.
- Monitoring/status strip remains present and readable.

## Phase A3: Radar Workspace Fidelity
- [x] SA-301 Tune radar container styling (surface, borders, depth) to match target.
- [x] SA-302 Improve FOV rendering style (core + extended treatment) without changing behavior.
- [x] SA-303 Reduce grid/axis visual harshness and match target subtlety.
- [x] SA-304 Align standby chip styling and placement with target.

Acceptance:
- Map area looks visually aligned with target and remains responsive/stable.

## Phase A4: Right Panel Component System
- [x] SA-401 Restyle sidebar subtabs (`Controls & Zones`, `Configuration`, `View`) to target.
- [x] SA-402 Convert section styling from heavy cards to lighter grouped blocks.
- [x] SA-403 Align setting row pattern (`label + control`) with consistent rhythm.
- [x] SA-404 Upgrade controls (toggle/select/slider/button) to cohesive modern style.

Acceptance:
- Sidebar feels production-ready and visually consistent across all tabs.

## Phase A5: Data Table + Footer Actions
- [x] SA-501 Redesign target table to muted compact telemetry style.
- [x] SA-502 Align action badges (stationary/moving) to target look.
- [x] SA-503 Refine bottom dirty bar and button hierarchy to target.

Acceptance:
- Bottom data/action area matches desired polish and hierarchy.

## Phase A6: Motion + Interaction + QA
- [ ] SA-601 Normalize hover/focus/active states across interactive elements.
- [ ] SA-602 Validate reduced-motion behavior and keyboard focus visibility.
- [ ] SA-603 Verify desktop/mobile layout stability.
- [ ] SA-604 Run full automated test suite and manual ingress smoke checks.

Acceptance:
- No regressions in behavior, accessibility, or responsiveness.

## Validation Commands
- `node --test tests/frontend/*.test.js`
- `python -m unittest discover -s tests/python -p "test_*.py" -v`

## Execution Order
1. Phase A1
2. Phase A2
3. Phase A3
4. Phase A4
5. Phase A5
6. Phase A6
