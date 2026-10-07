// Display tab: what the map shows, the map range, and the room layout.

import { state, emit } from './state.js';
import * as prefs from './prefs.js';
import { $, toast, confirmAction } from './ui.js';
import { DEFAULT_RANGE } from './radar.js';
import { displayZones } from './zones.js';

// [checkbox id, localStorage key, visibility field, default]
const TOGGLES = [
    ['vizToggleGrid', 'vizShowGrid', 'grid', true],
    ['vizToggleLabels', 'vizShowLabels', 'labels', true],
    ['vizToggleZValues', 'vizShowZValues', 'heights', false],
    ['vizToggleDetection', 'vizShowDetection', 'detection', true],
    ['vizToggleStay', 'vizShowStay', 'stay', true],
    ['vizToggleInterference', 'vizShowInterference', 'interference', true],
];
const RANGE_KEYS = { xMin: 'vizXMin', xMax: 'vizXMax', yMin: 'vizYMin', yMax: 'vizYMax' };
const EMPTY_LAYOUT = { x: 0, y: 0, rot: 0, room: null };
const LAYOUT_LIMIT = 10000;   // cm either way; the addon refuses a layout beyond this
const MIN_ROOM = 20;          // cm

let radar = null;
let saveTimer = 0;

// --- Visibility --------------------------------------------------------------

function initVisibility() {
    const vis = { det: [] };
    for (const [id, key, field, def] of TOGGLES) {
        const box = $('#' + id);
        vis[field] = box.checked = prefs.getBool(key, def);
        box.addEventListener('change', () => {
            prefs.set(key, box.checked);
            radar.setVisibility({ [field]: box.checked });
        });
    }
    for (let i = 1; i <= 4; i++) {
        const box = $('#vizToggleDetection' + i);
        vis.det.push(box.checked = prefs.getBool('vizShowDetection' + i, true));
        box.addEventListener('change', () => {
            prefs.set('vizShowDetection' + i, box.checked);
            const det = [1, 2, 3, 4].map(n => $('#vizToggleDetection' + n).checked);
            radar.setVisibility({ det });
        });
    }
    radar.setVisibility(vis);

    // Zoom buttons on the map (−, +, Fit zones, Full range); the same actions stay in this tab
    const zoom = $('#vizToggleZoom');
    zoom.checked = prefs.getBool('vizShowZoomButtons', true);
    $('#map').classList.toggle('no-zoom-controls', !zoom.checked);
    zoom.addEventListener('change', () => {
        prefs.set('vizShowZoomButtons', zoom.checked);
        $('#map').classList.toggle('no-zoom-controls', !zoom.checked);
    });

    const stay = $('#toggleStayInvert');
    stay.checked = state.stayInvert = prefs.getBool('stayInvertEnabled', false);
    stay.addEventListener('change', () => {
        state.stayInvert = stay.checked;
        prefs.set('stayInvertEnabled', stay.checked);
    });
}

// --- Map range ---------------------------------------------------------------

function fillRange(range) {
    for (const [field, key] of Object.entries(RANGE_KEYS)) {
        const input = $('#' + key);
        if (document.activeElement !== input) input.value = Math.round(range[field]);
    }
}

function saveRange(range) {
    for (const [field, key] of Object.entries(RANGE_KEYS)) prefs.set(key, Math.round(range[field]));
}

export function applyRange(range) {
    if (!range) return;
    radar.setRange(range);
    fillRange(range);
    saveRange(range);
}

// The map was panned or zoomed
export function rangeFromMap(range, final) {
    fillRange(range);
    if (final) saveRange(range);
}

function rangeFromInputs() {
    const r = {};
    for (const [field, key] of Object.entries(RANGE_KEYS)) r[field] = parseInt($('#' + key).value, 10);
    if (Object.values(r).some(Number.isNaN)) { toast('Fill in all four range values.', 'error'); return; }
    if (r.xMin >= r.xMax || r.yMin >= r.yMax) { toast('Each "from" value has to be below its "to" value.', 'error'); return; }
    applyRange(r);
}

export function fitZones() { applyRange(radar.zonesRange(displayZones())); }
export function fullRange() { applyRange(radar.fullRange()); }

function initRange() {
    const r = {};
    for (const [field, key] of Object.entries(RANGE_KEYS)) r[field] = prefs.getInt(key, DEFAULT_RANGE[field]);
    if (r.xMin >= r.xMax || r.yMin >= r.yMax) Object.assign(r, DEFAULT_RANGE);
    radar.setRange(r);
    fillRange(r);
    $('#rangeApply').addEventListener('click', rangeFromInputs);
    for (const key of Object.values(RANGE_KEYS)) {
        $('#' + key).addEventListener('keydown', e => { if (e.key === 'Enter') rangeFromInputs(); });
    }
    $('#rangeFit').addEventListener('click', fitZones);
    $('#rangeFull').addEventListener('click', fullRange);
}

// --- Room layout -------------------------------------------------------------

export function fillLayout() {
    const l = state.layout;
    const set = (id, v) => { const input = $('#' + id); if (document.activeElement !== input) input.value = Math.round(v); };
    set('layoutX', l.x);
    set('layoutY', l.y);
    set('layoutRot', l.rot);
    $('#btnRoom').textContent = l.room ? 'Remove room outline' : 'Add room outline';
    $('#roomFields').hidden = !l.room;
    if (l.room) {
        set('roomW', l.room.x_max - l.room.x_min);
        set('roomD', l.room.y_max - l.room.y_min);
    }
}

function copyLayout(l) {
    return { x: l.x, y: l.y, rot: l.rot, room: l.room ? { ...l.room } : null };
}

// Whole centimetres and degrees, within what the addon accepts, and a room with some size
function tidyLayout(l) {
    const c = v => Math.min(LAYOUT_LIMIT, Math.max(-LAYOUT_LIMIT, Math.round(Number(v) || 0)));
    l.x = c(l.x);
    l.y = c(l.y);
    l.rot = ((Math.round(Number(l.rot) || 0) % 360) + 360) % 360;
    if (l.room) {
        const r = l.room;
        for (const [lo, hi] of [['x_min', 'x_max'], ['y_min', 'y_max']]) {
            r[lo] = c(r[lo]);
            r[hi] = c(r[hi]);
            if (r[hi] - r[lo] < MIN_ROOM) {
                if (r[lo] + MIN_ROOM <= LAYOUT_LIMIT) r[hi] = r[lo] + MIN_ROOM;
                else r[lo] = r[hi] - MIN_ROOM;
            }
        }
    }
    return l;
}

const sameLayout = (a, b) => JSON.stringify(a) === JSON.stringify(b);

function scheduleSave() {
    clearTimeout(saveTimer);
    const topic = state.device;
    const layout = copyLayout(state.layout);
    const isEmpty = !layout.x && !layout.y && !layout.rot && !layout.room;
    saveTimer = setTimeout(() => {
        if (!topic) return;
        state.socket.emit('save_layout', { topic, layout: isEmpty ? null : layout }, ack => {
            if (ack && ack.error) toast(`The room layout wasn't saved: ${ack.error}`, 'error', 6000);
            else if (ack && ack.warning) toast(`Room layout saved for now. ${ack.warning}`, 'error', 8000);
        });
    }, 400);
}

function needDevice() {
    if (state.device) return false;
    toast('Choose a switch first.', 'error');
    return true;
}

// Every layout change from the page goes through here
function changeLayout(mutate) {
    if (needDevice()) return;
    const l = copyLayout(state.layout);
    mutate(l);
    tidyLayout(l);
    state.layout = l;
    radar.setLayout(l);
    fillLayout();
    scheduleSave();
}

// The map moved the switch or the room
export function layoutFromMap(layout, final) {
    state.layout = copyLayout(layout);
    if (final) {
        tidyLayout(state.layout);
        if (!sameLayout(state.layout, layout)) radar.setLayout(state.layout);
    }
    fillLayout();
    if (final) scheduleSave();
}

// A layout arrived from the addon (device change, or another browser saved one)
export function layoutFromServer(layout) {
    // A save still waiting on its timer already holds its own switch and layout, so let it run
    state.layout = layout ? copyLayout(layout) : { ...EMPTY_LAYOUT };
    radar.setLayout(state.layout);
    fillLayout();
}

function defaultRoom() {
    // Around detection area 1 when there is one, otherwise a 6 × 4.5 m room in front of the switch
    const a1 = state.zones.mmwave_detection_areas.area1;
    const pts = a1
        ? [[a1.x_min, a1.y_min], [a1.x_max, a1.y_min], [a1.x_max, a1.y_max], [a1.x_min, a1.y_max]]
        : [[-300, 0], [300, 0], [300, 450], [-300, 450]];
    pts.push([0, 0]);   // the switch sits on a wall
    const box = radar.boxAround(pts);
    const r10 = v => Math.round(v / 10) * 10;
    return { x_min: r10(box.x_min), x_max: r10(box.x_max), y_min: r10(box.y_min), y_max: r10(box.y_max) };
}

function initLayout() {
    const num = id => parseInt($('#' + id).value, 10);
    $('#layoutX').addEventListener('change', () => { const v = num('layoutX'); if (!Number.isNaN(v)) changeLayout(l => { l.x = v; }); });
    $('#layoutY').addEventListener('change', () => { const v = num('layoutY'); if (!Number.isNaN(v)) changeLayout(l => { l.y = v; }); });
    $('#layoutRot').addEventListener('change', () => { const v = num('layoutRot'); if (!Number.isNaN(v)) changeLayout(l => { l.rot = v; }); });
    $('#btnTurnLeft').addEventListener('click', () => changeLayout(l => { l.rot += 90; }));
    $('#btnTurnRight').addEventListener('click', () => changeLayout(l => { l.rot -= 90; }));
    $('#btnRoom').addEventListener('click', () => changeLayout(l => { l.room = l.room ? null : defaultRoom(); }));
    $('#roomW').addEventListener('change', () => {
        const v = num('roomW');
        if (v >= MIN_ROOM) changeLayout(l => { if (l.room) l.room.x_max = l.room.x_min + v; });
    });
    $('#roomD').addEventListener('change', () => {
        const v = num('roomD');
        if (v >= MIN_ROOM) changeLayout(l => { if (l.room) l.room.y_max = l.room.y_min + v; });
    });
    $('#btnLayoutReset').addEventListener('click', async () => {
        if (needDevice()) return;
        if (!await confirmAction('Put the switch back in the middle with no room outline?', { confirm: 'Reset layout' })) return;
        changeLayout(l => Object.assign(l, EMPTY_LAYOUT));
        fullRange();
    });
    $('#btnArrange').addEventListener('click', () => {
        if (!state.arranging && needDevice()) return;
        emit('arrange', !state.arranging);
    });
    fillLayout();
}

export function initDisplay(radarInstance) {
    radar = radarInstance;
    initVisibility();
    initRange();
    initLayout();
}
