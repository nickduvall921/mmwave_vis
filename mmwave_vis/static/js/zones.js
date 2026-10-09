// Zones: reading them from switch reports, the zone list, and the editor.

import { state, on, emit, ZONE_TYPES, AREAS, ZONE_KEYS, zoneName, slotName, customName } from './state.js';
import { $, h, toast, setNotice, clearNotice, confirmAction, span, plural, copyText } from './ui.js';
import { setName, setNames } from './names.js';

// Device payload that clears an area slot
export const EMPTY_AREA = { width_min: 0, width_max: 0, depth_min: 0, depth_max: 0, height_min: 0, height_max: 0 };
const NEW_ZONE = { x_min: -100, x_max: 100, y_min: 50, y_max: 250, z_min: -300, z_max: 300 };

// A report this soon after an interference command is a reply to something sent
// before it (Sync, the zone check below), not the command's result
const COMMAND_REPLY_MIN_MS = 1500;

const groupsRoot = $('#zoneGroups');
const editor = $('#zoneEditor');
const inputs = Object.fromEntries(ZONE_KEYS.map(k => [k, $('#edit' + k[0].toUpperCase() + k.slice(2, 3).toUpperCase() + k.slice(3))]));
const nameInput = $('#editName');
let activeDims = null;      // the dims line of the row being edited, updated live

// The switch keeps zone edges as 32-bit floats in metres and reports them truncated to
// whole centimetres, so about one value in sixteen comes back 1 cm lower than it was sent
// (105 → 104, 499 → 498; seen on firmware 0x01030102). Compare what the switch reports
// with what was sent using this much slack.
export const SWITCH_ROUNDING_CM = 1;

const near = (a, b, tol) => Math.abs(Number(a) - Number(b)) <= tol;

export function sameZone(a, b, tol = 0) {
    if (!a || !b) return !a && !b;
    return ZONE_KEYS.every(k => near(a[k], b[k], tol));
}

// True when `stored` is `expected` with its width (X) axis mirrored
export function isMirroredX(stored, expected, tol = 0) {
    return !!stored && !!expected &&
        near(stored.x_min, -expected.x_max, tol) && near(stored.x_max, -expected.x_min, tol) &&
        ['y_min', 'y_max', 'z_min', 'z_max'].every(k => near(stored[k], expected[k], tol));
}

// Whole numbers with each min below its max: the form the switch stores and reports
export function sorted(zone) {
    const pair = (a, b) => [parseInt(a, 10), parseInt(b, 10)].sort((p, q) => p - q);
    const [x0, x1] = pair(zone.x_min, zone.x_max);
    const [y0, y1] = pair(zone.y_min, zone.y_max);
    const [z0, z1] = pair(zone.z_min, zone.z_max);
    return { x_min: x0, x_max: x1, y_min: y0, y_max: y1, z_min: z0, z_max: z1 };
}

// --- Reading reports -------------------------------------------------------

// Zigbee2MQTT uses width/depth/height names, the addon's own reports x/y/z
export function parseArea(area) {
    if (!area || typeof area !== 'object') return null;
    let x0, x1, y0, y1, z0, z1;
    if ('width_min' in area) {
        x0 = area.width_min; x1 = area.width_max;
        y0 = area.depth_min; y1 = area.depth_max;
    } else if ('x_min' in area) {
        x0 = area.x_min; x1 = area.x_max;
        y0 = area.y_min; y1 = area.y_max;
    } else {
        return null;
    }
    if ('height_min' in area) { z0 = area.height_min; z1 = area.height_max; }
    else if ('z_min' in area) { z0 = area.z_min; z1 = area.z_max; }
    else { z0 = -300; z1 = 300; }
    if (x0 === 0 && x1 === 0 && y0 === 0 && y1 === 0) return null;
    return { x_min: x0, x_max: x1, y_min: y0, y_max: y1, z_min: z0, z_max: z1 };
}

// Store one reported slot; true when it differs from what the page had
function store(category, area, zone) {
    if (sameZone(zone, state.zones[category][area])) return false;
    state.zones[category][area] = zone;
    return true;
}

// Z2M republishes its whole cached state (zones included) on every target or
// occupancy report, so only redraw when a zone actually changed: rebuilding the
// list under the pointer swallows clicks on its buttons.
function afterReport(categories, zonesChanged) {
    const settled = settlePending(categories);
    pruneNames(categories);
    if (!zonesChanged && !settled) return;
    if (!state.edit) renderZoneList();     // while editing, endEdit() redraws the list
    emit('zones');
}

// A name belongs to a zone: when the switch reports a slot empty (cleared by a tool,
// another browser or a restore) and nothing is on its way to it, forget the name so it
// doesn't reappear on the next zone created there
function pruneNames(categories) {
    if (state.restoring) return;      // slots are empty for a moment while a restore writes them
    const drop = {};
    for (const key of Object.keys(state.zoneNames || {})) {
        const [category, area] = key.split(':');
        if (!categories.includes(category) || !state.zoneReportAt[category]) continue;
        if (state.zones[category] && state.zones[category][area]) continue;
        if (key in state.pending || (state.edit && state.edit.category === category && state.edit.area === area)) continue;
        drop[key] = '';
    }
    if (Object.keys(drop).length) setNames(drop);
}

function interferenceResult(active) {
    if (state.lastCommandId === null || Date.now() - state.lastCommandAt < COMMAND_REPLY_MIN_MS) return;
    if (active === 0) {
        toast(state.lastCommandId === 1 ? 'Scan finished. No interference found.' : 'Interference zones cleared.', 'success', 5000);
    } else {
        toast(`Auto-detect found ${plural(active, 'interference zone')}.`, 'info', 6000);
    }
    state.lastCommandId = null;
}

// A zone report event: a list of four slots, empty ones as null
export function applyZoneList(category, list) {
    // [] is the backend's "nothing reported yet" placeholder, not four empty slots
    if (!Array.isArray(list) || !list.length) return;
    state.zoneReportAt[category] = Date.now();
    let changed = false;
    for (let i = 0; i < 4; i++) changed = store(category, AREAS[i], parseArea(list[i])) || changed;
    afterReport([category], changed);
    if (category === 'mmwave_interference_areas') interferenceResult(list.filter(Boolean).length);
}

const FLAT_AREA1 = { mmWaveWidthMin: 'x_min', mmWaveWidthMax: 'x_max', mmWaveDepthMin: 'y_min', mmWaveDepthMax: 'y_max', mmWaveHeightMin: 'z_min', mmWaveHeightMax: 'z_max' };

// Zone fields inside a device_config (state) message
export function applyConfig(c) {
    const reported = [];
    let changed = false;
    for (const key of Object.keys(state.zoneReportAt)) if (key in c) state.zoneReportAt[key] = Date.now();

    // Older firmware reports detection area 1 as flat attributes
    if ('mmWaveWidthMin' in c) {
        state.zoneReportAt.mmwave_detection_areas = Date.now();
        const area1 = { ...(state.zones.mmwave_detection_areas.area1 || { x_min: -100, x_max: 100, y_min: 0, y_max: 600, z_min: -300, z_max: 300 }) };
        for (const [key, field] of Object.entries(FLAT_AREA1)) {
            const v = parseInt(c[key], 10);
            if (!Number.isNaN(v)) area1[field] = v;
        }
        changed = store('mmwave_detection_areas', 'area1', area1) || changed;
        reported.push('mmwave_detection_areas');
    }

    for (const { category } of ZONE_TYPES) {
        if (!(category in c)) continue;
        const raw = c[category];
        const areas = (raw && typeof raw === 'object' && !Array.isArray(raw)) ? raw : {};
        // Only the slots this message carries; a missing slot means "not in this message"
        for (const area of AREAS) if (area in areas) changed = store(category, area, parseArea(areas[area])) || changed;
        reported.push(category);
        if (category === 'mmwave_interference_areas' && state.lastCommandId === 3 && Object.keys(areas).length === 0) {
            interferenceResult(0);
        }
    }
    if (reported.length) afterReport(reported, changed);
}

// --- Writes waiting for the switch -------------------------------------------
// A saved or deleted zone only shows in the switch's reports once the switch
// has applied it (a few seconds). Until then the page draws what was saved and
// asks the switch for its zones now and then. Early reports don't count:
// Zigbee2MQTT publishes the written zone back once the switch acknowledges the
// write (sometimes 9 s later, after the switch has already reported the real
// value) and repeats it until the switch's next report, and through Zigbee2MQTT
// a stay zone is briefly reported as written before it's reported mirrored. So a
// write counts as confirmed once reports agree for STEADY_MS (with the switch
// asked again every POLL_RECHECK_MS meanwhile), and fails after CONFIRM_TIMEOUT_MS.
// The switch acknowledges every write but now and then drops one that arrives
// close behind another (seen through Zigbee2MQTT), so a write that still hasn't
// shown up after RESEND_MS is sent once more.

const QUIET_MS = { zha: 2000, z2m: 6500 };   // ignore reports this soon after a write
const STEADY_MS = { zha: 1000, z2m: 6000 };   // a stale value has lasted 3 s on Z2M
const POLL_FIRST_MS = 6000;
const POLL_EVERY_MS = 6000;
const POLL_RECHECK_MS = 1500;                 // once a report matches, look again soon
const RESEND_MS = 18000;
const CONFIRM_TIMEOUT_MS = 45000;
let confirmTimer = 0;
let flipNoticeFor = null;   // "category:area" the flipped-stay-zone notice is about

// Zones as the page should show them: the switch's reports with unconfirmed writes on top
export function displayZones() {
    const pending = Object.values(state.pending);
    if (!pending.length) return state.zones;
    const zones = {};
    for (const t of ZONE_TYPES) zones[t.category] = { ...state.zones[t.category] };
    for (const p of pending) zones[p.category][p.area] = p.zone;
    return zones;
}

export function pendingKeys() {
    return new Set(Object.keys(state.pending));
}

// `payload` is what was sent, kept for the one resend
function expectWrite(category, area, zone, payload) {
    const now = Date.now();
    const key = `${category}:${area}`;
    if (flipNoticeFor === key) dropFlipNotice();   // that zone is being saved again
    // `since` times the whole wait; `sentAt` the quiet spell after each send; `before` is
    // what the switch held when this was sent
    const before = state.zones[category][area];
    state.pending[key] = { category, area, zone: zone ? sorted(zone) : null, payload, before, since: now, sentAt: now, match: null, resent: false };
    if (!confirmTimer) confirmTimer = setTimeout(confirmTick, POLL_FIRST_MS);
}

function confirmTick() {
    confirmTimer = 0;
    const now = Date.now();
    for (const [key, p] of Object.entries(state.pending)) {
        if (now - p.since < CONFIRM_TIMEOUT_MS) continue;
        delete state.pending[key];
        toast(`The switch hasn't confirmed ${zoneName(p.category, p.area)} yet. Press Sync to check what it stored.`, 'error', 8000);
        if (!state.edit) renderZoneList();
        emit('zones');
    }
    const pending = Object.values(state.pending);
    if (!pending.length) return;
    const online = state.socket.connected && state.device;
    for (const p of pending) {
        if (online && !p.resent && !p.match && now - p.since >= RESEND_MS) {
            state.socket.emit('update_parameter', { param: p.category, value: { [p.area]: p.payload } });
            // Zigbee2MQTT echoes the resend straight back; start the quiet spell again
            Object.assign(p, { resent: true, sentAt: now, match: null });
        }
    }
    // While an interference command waits for its result, don't trigger reports that could be taken for it
    if (online && state.lastCommandId === null) state.socket.emit('send_command', 2);   // query_areas
    confirmTimer = setTimeout(confirmTick, pending.some(p => p.match) ? POLL_RECHECK_MS : POLL_EVERY_MS);
}

function classify(p) {
    const stored = state.zones[p.category][p.area];
    if (sameZone(stored, p.zone, SWITCH_ROUNDING_CM)) return 'exact';
    if (p.category === 'mmwave_stay_areas' && isMirroredX(stored, p.zone, SWITCH_ROUNDING_CM)) {
        // Saving a flipped zone again where it was drawn: until the switch applies the write
        // (it can take 15 s), the old flipped value is still what it reports
        return sameZone(stored, p.before) ? null : 'mirrored';
    }
    return null;
}

// Called for every report that carries zones; true when a write was confirmed
function settlePending(categories) {
    const now = Date.now();
    const quiet = QUIET_MS[state.stack] ?? QUIET_MS.z2m;
    const steady = STEADY_MS[state.stack] ?? STEADY_MS.z2m;
    let settled = false;
    for (const [key, p] of Object.entries(state.pending)) {
        if (!categories.includes(p.category) || now - p.sentAt < quiet) continue;
        const kind = classify(p);
        if (!kind || !p.match || p.match.kind !== kind) {
            p.match = kind ? { kind, at: now } : null;
            continue;
        }
        if (now - p.match.at < steady) continue;
        delete state.pending[key];
        settled = true;
        const name = zoneName(p.category, p.area);
        if (kind === 'exact') {
            toast(p.zone ? `${name} saved.` : `${name} deleted.`, 'success');
        } else {
            flippedNotice(p);
        }
    }
    return settled;
}

// The write landed, but the switch flipped it left to right (#41). The map shows what the
// switch really holds. Opening the zone and saving it again would keep it where it is now,
// so offer to change the correction setting and send the zone again as it was drawn.
function dropFlipNotice() {
    flipNoticeFor = null;
    clearNotice('stayFlip');
}

function flippedNotice(p) {
    const name = zoneName(p.category, p.area);
    const turnOn = !state.stayInvert;
    flipNoticeFor = `${p.category}:${p.area}`;
    setNotice('stayFlip', {
        tone: 'warning',
        title: `The switch stored ${name} flipped left to right.`,
        text: turnOn
            ? 'This firmware mirrors stay zones. Turn on "Correct mirrored stay zones" and send it again where you drew it?'
            : 'This firmware doesn\'t seem to mirror stay zones. Turn off "Correct mirrored stay zones" and send it again where you drew it?',
        action: { label: turnOn ? 'Turn on and resend' : 'Turn off and resend', onClick: () => resendFlipped(p, turnOn) },
    });
}

function resendFlipped(p, invert) {
    dropFlipNotice();
    if (needDevice()) return;
    if (!isMirroredX(state.zones[p.category][p.area], p.zone, SWITCH_ROUNDING_CM)) {
        toast(`${zoneName(p.category, p.area)} has changed since, so nothing was sent.`, 'error');
        return;
    }
    const box = $('#toggleStayInvert');
    box.checked = invert;
    box.dispatchEvent(new Event('change'));   // display.js keeps the setting
    writeZone(p.category, p.area, p.zone);
}

// Forget unconfirmed writes (another switch was selected, or a restore rewrites every slot)
export function clearPending() {
    state.pending = {};
    clearTimeout(confirmTimer);
    confirmTimer = 0;
    dropFlipNotice();
}

// --- Writing ---------------------------------------------------------------

// Device write format for one area. Shared by the editor and backup restore.
export function zoneToDevicePayload(category, zone) {
    const s = sorted(zone);
    // The firmware mirrors the width (X) axis of stay areas (#41). With the
    // correction on, pre-mirror X (negate and swap, keeping min < max) so a
    // single write stores what was drawn. Other zone types are unaffected.
    const mirror = state.stayInvert && category === 'mmwave_stay_areas';
    return {
        width_min: mirror ? -s.x_max : s.x_min, width_max: mirror ? -s.x_min : s.x_max,
        depth_min: s.y_min, depth_max: s.y_max, height_min: s.z_min, height_max: s.z_max,
    };
}

// --- Zone list ---------------------------------------------------------------

function dims(z) {
    return `W ${span(z.x_min, z.x_max)} · D ${span(z.y_min, z.y_max)} · H ${span(z.z_min, z.z_max)}`;
}

// The row's title: the user's name with the slot underneath it, or just the slot
function nameNodes(category, area) {
    const custom = customName(category, area);
    return custom
        ? [h('span', { class: 'name' }, custom, h('span', { class: 'slot' }, slotName(category, area)))]
        : [h('span', { class: 'name' }, slotName(category, area))];
}

// ZHA has no per-area entities; this template sensor (as in ZHADOC.md) gives one
export function zhaAreaSensorYaml(ieee, n, name) {
    const label = (name || `mmWave area ${n}`).replace(/"/g, '\'');
    const digits = String(ieee).toLowerCase().replace(/^0x/, '').replace(/:/g, '');
    return [
        'template:',
        '  - trigger:',
        '      - platform: event',
        '        event_type: zha_event',
        '        event_data:',
        `          device_ieee: "${ieee}"`,
        '          command: mmwave_anyone_in_area',
        '    binary_sensor:',
        `      - name: "${label} occupied"`,
        `        unique_id: mmwave_${digits}_area${n}`,
        `        state: "{{ trigger.event.data.args.area${n} == 1 }}"`,
        '        device_class: occupancy',
        '',
    ].join('\n');
}

async function copyAndSay(text, what) {
    if (await copyText(text)) toast(`Copied ${what}.`, 'success', 2500);
    else toast('Couldn\'t copy. Select the text and copy it yourself.', 'error');
}

// Under a detection area: the Home Assistant entity that follows it, or on ZHA the
// YAML for a sensor that does (ZHA only sends area occupancy as an event)
function entityLine(category, area) {
    if (category !== 'mmwave_detection_areas') return null;
    const info = state.deviceInfo;
    if (!info || info.topic !== state.device) return null;
    const n = area.slice(4);
    if (state.stack === 'z2m') {
        const id = info.entities && info.entities[area];
        if (!id) return null;
        return h('div', { class: 'zone-entity' },
            h('code', { title: 'Home Assistant entity for this area' }, id),
            h('button', { class: 'btn link', type: 'button', onclick: () => copyAndSay(id, id) }, 'Copy'));
    }
    if (state.stack === 'zha' && info.ieee) {
        return h('div', { class: 'zone-entity' },
            h('span', null, 'No entity in ZHA for this area.'),
            h('button', {
                class: 'btn link', type: 'button', title: 'A template sensor for configuration.yaml that follows this area',
                onclick: () => copyAndSay(zhaAreaSensorYaml(info.ieee, n, customName(category, area) || `${state.deviceName} area ${n}`), 'the sensor YAML'),
            }, 'Copy sensor YAML'));
    }
    return null;
}

export function renderZoneList() {
    activeDims = null;
    const edit = state.edit;
    const zones = displayZones();
    const sections = ZONE_TYPES.map(type => {
        const filled = AREAS.filter(a => zones[type.category][a]);
        const section = h('section', { class: 'section' },
            h('div', { class: 'section-head' },
                h('h2', null, type.title, h('span', { class: 'count' }, `${filled.length} of 4`)),
                filled.length < 4 && !edit
                    ? h('button', { class: 'btn link', type: 'button', onclick: () => startAdd(type.category) }, 'Add area')
                    : null));

        const isNewHere = edit && edit.isNew && edit.category === type.category;
        if (!filled.length && !isNewHere) section.append(h('div', { class: 'empty-line' }, `No ${type.group} areas`));

        for (const area of filled) {
            const active = edit && edit.category === type.category && edit.area === area;
            const saving = !active && `${type.category}:${area}` in state.pending;
            const z = active ? edit.draft : zones[type.category][area];
            const dimsNode = h('span', { class: 'dims' }, dims(z));
            if (active) activeDims = dimsNode;
            section.append(h('button', {
                class: 'zone-row' + (active ? ' active' : ''), type: 'button',
                'aria-expanded': active ? 'true' : null,
                onclick: () => active ? null : switchTo(type.category, area),
            },
                h('i', { class: `swatch ${type.cls}` }),
                h('span', null, ...nameNodes(type.category, area), dimsNode),
                h('span', { class: 'go' + (saving ? ' saving' : '') }, active ? 'Editing' : saving ? 'Saving…' : 'Edit')));
            const entity = active ? null : entityLine(type.category, area);
            if (active) section.append(editor);
            else if (entity) section.append(entity);
        }
        if (isNewHere) {
            activeDims = h('span', { class: 'dims' }, dims(edit.draft));
            section.append(h('div', { class: 'zone-row active' },
                h('i', { class: `swatch ${type.cls}` }),
                h('span', null, h('span', { class: 'name', id: 'newZoneName' }, `New ${slotName(edit.category, edit.area).toLowerCase()}`), activeDims),
                h('span', { class: 'go' }, 'Adding')));
            section.append(editor);
        }
        return section;
    });
    if (!edit) {
        editor.hidden = true;
        groupsRoot.after(editor);
    }
    groupsRoot.replaceChildren(...sections);
}

// --- Editing -----------------------------------------------------------------

function fillInputs() {
    const d = state.edit.draft;
    for (const k of ZONE_KEYS) {
        const v = String(d[k]);
        if (inputs[k].value !== v) inputs[k].value = v;
    }
    if (activeDims) activeDims.textContent = dims(d);
}

function renderSlotPicker() {
    const pick = $('#slotPick');
    const edit = state.edit;
    pick.hidden = !edit || !edit.isNew;
    if (pick.hidden) return;
    const zones = displayZones();
    $('#slotSeg').replaceChildren(...AREAS.map(area => h('button', {
        type: 'button',
        'aria-pressed': String(area === edit.area),
        disabled: !!zones[edit.category][area],
        onclick: () => {
            edit.area = area;
            renderSlotPicker();
            const name = $('#newZoneName');
            if (name) name.textContent = `New ${slotName(edit.category, area).toLowerCase()}`;
            nameInput.placeholder = slotName(edit.category, area);
            emit('edit');
        },
    }, area.slice(4))));
}

function needDevice() {
    if (state.device) return false;
    toast('Choose a switch first.', 'error');
    return true;
}

export function startEdit(category, area, draft = null) {
    if (state.arranging) emit('arrange', false);
    const current = displayZones()[category][area];
    state.edit = { category, area, draft: { ...(draft || current || NEW_ZONE) }, original: current ? { ...current } : null, isNew: !current };
    renderZoneList();
    editor.hidden = false;
    fillInputs();
    // A new zone starts unnamed, even if the slot once held a named one
    nameInput.value = current ? customName(category, area) : '';
    nameInput.placeholder = slotName(category, area);
    renderSlotPicker();
    $('#btnDeleteZone').hidden = !current;
    emit('edit');
}

// A new zone of this type in the first free slot, starting from `draft` (e.g. around
// where someone sat). False when every slot is taken.
export function startNewZone(category, draft) {
    if (needDevice()) return false;
    const area = AREAS.find(a => !displayZones()[category][a]);
    if (!area) {
        toast(`All four ${ZONE_TYPES.find(t => t.category === category).group} areas are in use.`, 'error');
        return false;
    }
    startEdit(category, area, sorted(draft));
    emit('show-editor');
    return true;
}

function startAdd(category) {
    if (needDevice()) return;
    const zones = displayZones();
    const area = AREAS.find(a => !zones[category][a]);
    if (area) startEdit(category, area);
}

function hasChanges() {
    const e = state.edit;
    return !!e && (!sameZone(e.draft, e.original) || nameInput.value.trim() !== customName(e.category, e.area));
}

async function switchTo(category, area) {
    if (state.edit && hasChanges()) {
        const ok = await confirmAction(`Discard your changes to ${zoneName(state.edit.category, state.edit.area)}?`, { confirm: 'Discard' });
        if (!ok) return;
    }
    startEdit(category, area);
}

// Called when a zone is clicked on the map
export function editFromMap(category, area) {
    switchTo(category, area);
    emit('show-editor');
}

export function endEdit() {
    if (!state.edit) return;
    state.edit = null;
    renderZoneList();
    emit('edit');
}

export function cancelEdit() {
    endEdit();
    state.socket.emit('force_sync');
}

// The map moved the draft
export function draftFromMap() {
    if (state.edit) fillInputs();
}

function draftFromInputs() {
    if (!state.edit) return;
    const values = {};
    for (const k of ZONE_KEYS) {
        const v = parseInt(inputs[k].value, 10);
        if (Number.isNaN(v)) return;          // still typing ("-")
        values[k] = v;
    }
    Object.assign(state.edit.draft, values);
    if (activeDims) activeDims.textContent = dims(state.edit.draft);
    emit('draft');
}

export function saveEdit() {
    const e = state.edit;
    if (!e || needDevice()) return;
    const d = e.draft;
    if (d.x_min === d.x_max || d.y_min === d.y_max) {
        toast('A zone needs some width and depth.', 'error');
        return;
    }
    const key = `${e.category}:${e.area}`;
    const oldName = customName(e.category, e.area);
    const moved = e.isNew || !sameZone(d, e.original);
    setName(e.category, e.area, nameInput.value);
    if (!moved) {
        // Only the name changed: nothing to send to the switch
        endEdit();
        if (oldName !== customName(e.category, e.area)) toast('Name saved.', 'success', 2500);
        return;
    }
    const undoEntry = {
        label: `${e.isNew ? 'Added' : 'Changed'} ${zoneName(e.category, e.area)}`,
        writes: [{ category: e.category, area: e.area, zone: e.original, after: sorted(d) }],
        names: { [key]: oldName },
    };
    emit('undoable', undoEntry);
    writeZone(e.category, e.area, d, { undo: undoEntry });
    endEdit();
}

// Send one zone to the switch (null clears the slot) and wait for it to show up in reports.
// `undo` is the undo entry for this change: its toast then offers to take it back.
export function writeZone(category, area, zone, { message = null, undo = null } = {}) {
    const payload = zone ? zoneToDevicePayload(category, zone) : EMPTY_AREA;
    state.socket.emit('update_parameter', { param: category, value: { [area]: payload } });
    expectWrite(category, area, zone, payload);
    emit('zones');
    if (!state.edit) renderZoneList();
    toast(message || `${zone ? 'Saving' : 'Deleting'} ${zoneName(category, area)}…`, 'info', undo ? 6000 : 4000,
        undo ? { label: 'Undo', onClick: () => emit('undo', undo) } : null);
}

async function deleteEdit() {
    const e = state.edit;
    if (!e || e.isNew || needDevice()) return;
    const name = zoneName(e.category, e.area);
    const ok = await confirmAction(`Delete ${name} from the switch?`, { confirm: 'Delete', danger: true });
    if (!ok || state.edit !== e) return;
    const key = `${e.category}:${e.area}`;
    const oldName = customName(e.category, e.area);
    endEdit();
    const undoEntry = {
        label: `Deleted ${name}`,
        writes: [{ category: e.category, area: e.area, zone: e.original, after: null }],
        names: { [key]: oldName },
    };
    emit('undoable', undoEntry);
    writeZone(e.category, e.area, null, { message: `Deleting ${name}…`, undo: undoEntry });
    setName(e.category, e.area, '');
}

export function resetZones(emptyZones) {
    clearPending();
    state.edit = null;
    state.zones = emptyZones;
    renderZoneList();
    emit('edit');
    emit('zones');
}

export function initZones() {
    for (const input of Object.values(inputs)) {
        input.addEventListener('input', draftFromInputs);
        input.addEventListener('change', () => { if (state.edit) fillInputs(); });
    }
    $('#btnSaveZone').addEventListener('click', saveEdit);
    $('#btnCancelEdit').addEventListener('click', cancelEdit);
    $('#btnDeleteZone').addEventListener('click', deleteEdit);
    nameInput.addEventListener('keydown', e => { if (e.key === 'Enter') saveEdit(); });
    // A name or the switch's HA entities changed: redraw the list (not mid-edit) and the map labels
    const refresh = () => {
        if (!state.edit) renderZoneList();
        emit('zones');
    };
    on('names', refresh);
    on('device-info', refresh);
    renderZoneList();
}
