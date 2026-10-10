// Config tab: every setting the switch has, grouped, each with an ⓘ explaining it.
// It's built from the settings catalogue (assets/settings.json), which the addon also
// checks every write against. Values are the ones Zigbee2MQTT uses; on ZHA the addon
// converts them. Changes go to the switch at once (risky ones after a confirmation)
// and count as saved when the switch reports the new value back.

import { state, on } from './state.js';
import * as prefs from './prefs.js';
import { $, h, setText, toast, confirmAction, duration, infoButton } from './ui.js';

const CONFIRM_MS = { z2m: 10000, zha: 15000 };   // ZHA reads the value back after 1.5 s, one radio read at a time
const SAVED_MS = 2500;
const READ_GIVE_UP_MS = 30000;   // Zigbee2MQTT says nothing about a setting it couldn't read

let catalog = null;
let catalogKeys = new Set();
let tabOpen = false;
const rows = new Map();        // key → { s, row, info, control, note, mark, text }
const groups = [];             // { g, el, count, keys }
const pending = new Map();     // key → { value, timer }
const requested = new Set();   // settings asked from this switch since it was selected
const unread = new Set();      // settings the switch didn't answer (ZHA)
let reading = null;            // { left: Set, total } while "Refresh Values" runs
let stateArrived = false;      // the switch's state has come in since it was selected
let readWhenState = false;     // the tab opened before that, so read what's missing once it has
let stateTimer = 0;
const STATE_WAIT_MS = 5000;

const socket = () => state.socket;
const known = key => state.settings[key];
const has = key => known(key) !== undefined && known(key) !== null;
const usable = s => !(state.stack === 'zha' && s.zha === false);
const optionsFor = s => (s.options || []).filter(o => !(o.zhaOnly && state.stack !== 'zha'));

// --- What a value means ------------------------------------------------------------------

const secs = x => (x < 60 ? `${+x.toFixed(2)} s` : duration(x));
const percentOfLevel = n => `${Math.max(n > 0 ? 1 : 0, Math.min(100, Math.round((n / 254) * 100)))}%`;

function hueColor(n) {
    return n >= 255 ? '#ffffff' : `hsl(${Math.round((n / 255) * 360)} 95% 55%)`;
}

// Text that says what a value means: "2.5 s", "Last brightness", "Blue", "34%"
function describe(s, value) {
    if (value === undefined || value === null || value === '') return '';
    if (s.options) {
        const o = s.options.find(x => x.value === value);
        return o ? (o.label || o.value) : String(value);
    }
    const n = Number(value);
    if (!Number.isFinite(n)) return String(value);
    const preset = (s.presets || []).find(p => p.raw === n);
    if (preset) return preset.label;
    switch (s.format) {
        case 'tenths': return secs(n / 10);
        case 'seconds': return secs(n);
        case 'steps50ms': return secs(n * 0.05);
        case 'sixtieths': return secs(n / 60);
        case 'level': return percentOfLevel(n);
        case 'percent': return `${n}%`;
        case 'hundredthsKwh': return `${+(n / 100).toFixed(2)} kWh`;
        case 'celsius': return `${n} °C`;
        case 'version': return [n >>> 24, (n >>> 16) & 255, (n >>> 8) & 255, n & 255].join('.');
        case 'hue':
        case 'ledHue': {
            // Name the nearest colour on the wheel
            const named = (s.presets || []).filter(p => p.raw < 255);
            let best = null;
            for (const p of named) {
                const d = Math.min(Math.abs(p.raw - n), 255 - Math.abs(p.raw - n));
                if (!best || d < best.d) best = { d, p };
            }
            return best ? (best.d === 0 ? best.p.label : `Near ${best.p.label.toLowerCase()}`) : String(n);
        }
        default: return '';
    }
}

const isDefault = (s, value) => s.default === undefined || String(value) === String(s.default);

// --- Building the tab -----------------------------------------------------------------------

function makeControl(s, id) {
    if (s.readOnly) return h('output', { id, class: 'cfg-readonly' }, '–');
    if (s.control === 'toggle') {
        const off = s.options.find(o => o.value !== s.on);
        return h('input', { type: 'checkbox', role: 'switch', class: 'switch', id, dataset: { on: s.on, off: off.value } });
    }
    if (s.control === 'select') {
        return h('select', { id },
            h('option', { value: '', disabled: true }, '–'),
            optionsFor(s).map(o => h('option', { value: o.value }, o.label || o.value)));
    }
    if (s.format === 'hue' || s.format === 'ledHue') {
        return h('input', { type: 'range', id, min: s.min, max: s.max, step: 1, class: 'hue-range' });
    }
    return h('input', { type: 'number', id, min: s.min, max: s.max, step: 1, inputmode: 'numeric', placeholder: '–' });
}

function buildRow(s) {
    const id = `cfg-${s.key}`;
    const infoId = `${id}-info`;
    const control = makeControl(s, id);
    const note = h('span', { class: 'cfg-note' });
    const mark = h('span', { class: 'cfg-mark', 'aria-hidden': 'true' });
    const swatch = (s.format === 'hue' || s.format === 'ledHue') ? h('span', { class: 'cfg-swatch', 'aria-hidden': 'true' }) : null;
    const row = h('div', { class: 'cfg-row', dataset: { key: s.key } },
        h('span', { class: 'label-info' }, mark, h('label', { for: id }, s.title), infoButton(infoId, `About ${s.title.toLowerCase()}`)),
        h('span', { class: 'cfg-value' }, h('span', { class: 'cfg-control' }, swatch, control), note));
    const reset = !s.readOnly && s.default !== undefined
        ? h('button', { class: 'btn link', type: 'button', onclick: () => change(r, s.default) }, 'Reset to default')
        : null;
    const meta = [];
    if (!s.readOnly && s.default !== undefined) meta.push(`Default: ${describe(s, s.default) || s.default}${s.options ? '' : ` (${s.default})`}.`);
    if (s.control === 'number' && !s.readOnly) meta.push(`Range ${s.min} to ${s.max}.`);
    meta.push(`Parameter ${s.param}, ${s.key}.`);
    const info = h('div', { class: 'info-panel', id: infoId, hidden: true },
        s.help.split('\n\n').map(p => h('p', null, p)),
        s.quirkUpdate ? h('p', { class: 'zha-only' }, 'On ZHA this needs the quirk from Visualizer 4.2 or later; older copies of the quirk don\'t know this setting.') : null,
        h('p', { class: 'cfg-meta' }, meta.join(' '), reset ? ' ' : null, reset));
    const r = { s, row, info, control, note, mark, swatch, text: `${s.title} ${s.sub || ''} ${s.help} ${s.key}`.toLowerCase() };

    if (control.tagName === 'INPUT' && control.type === 'range') {
        control.addEventListener('input', () => renderNote(r, Number(control.value)));
    }
    if (!s.readOnly) control.addEventListener('change', () => change(r, controlValue(r)));
    rows.set(s.key, r);
    return [row, info];
}

function buildGroup(g) {
    const settings = catalog.settings.filter(s => s.group === g.id && usable(s));
    if (!settings.length) return null;
    const count = h('span', { class: 'count' });
    const body = [];
    let sub = null;
    for (const s of settings) {
        if (s.sub && s.sub !== sub) body.push(h('h3', { class: 'cfg-sub' }, s.sub));
        sub = s.sub;
        body.push(...buildRow(s));
    }
    const el = h('details', { class: 'section cfg-group', dataset: { group: g.id } },
        h('summary', null, h('span', null, g.title, count)),
        g.help ? h('p', { class: 'cfg-group-help' }, g.help) : null,
        body);
    el.open = openGroups().includes(g.id);
    el.addEventListener('toggle', () => {
        if (filtering()) return;            // opened by the search, not the person
        const open = new Set(openGroups());
        if (el.open) open.add(g.id); else open.delete(g.id);
        prefs.set('configOpen', [...open].join(','));
        if (el.open && tabOpen) readMissing(settings.map(s => s.key));
    });
    const entry = { g, el, count, keys: settings.map(s => s.key) };
    groups.push(entry);
    return el;
}

const openGroups = () => (prefs.get('configOpen') || 'presence').split(',').filter(Boolean);

function build() {
    const root = $('#cfgGroups');
    rows.clear();
    groups.length = 0;
    root.replaceChildren(...catalog.groups.map(buildGroup).filter(Boolean));
    renderAll();
}

// --- Showing values ---------------------------------------------------------------------------

function controlValue(r) {
    const c = r.control;
    if (c.type === 'checkbox') return c.dataset[c.checked ? 'on' : 'off'];
    return c.value;
}

function showValue(r, value) {
    const c = r.control;
    const missing = value === undefined || value === null;
    if (r.s.readOnly) {
        setText(c, missing ? '–' : describe(r.s, value) || String(value));
    } else if (c.type === 'checkbox') {
        c.checked = value === c.dataset.on;
        c.indeterminate = missing;
    } else if (c.tagName === 'SELECT') {
        let v = missing ? '' : String(value);
        if (v && ![...c.options].some(o => o.value === v)) {
            // A value this page doesn't know (newer firmware?); show it rather than a blank
            c.append(h('option', { value: v, dataset: { extra: '1' } }, `${v}`));
        }
        c.value = v;
    } else if (document.activeElement !== c) {
        c.value = missing ? (c.type === 'range' ? c.min : '') : String(value);
    }
    renderNote(r, value);
}

function renderNote(r, value) {
    const s = r.s;
    const p = pending.get(s.key);
    let text = '';
    let tone = '';
    if (p) { text = 'Saving…'; tone = 'busy'; }
    else if (r.saved) { text = 'Saved'; tone = 'good'; }
    else if (r.failed) { text = r.failed; tone = 'bad'; }
    else if (value === undefined || value === null) {
        text = unread.has(s.key) ? 'Couldn\'t read' : (requested.has(s.key) ? 'Reading…' : '');
        tone = unread.has(s.key) ? 'bad' : '';
    } else if (!s.options && s.format && !s.readOnly) text = describe(s, value);
    setText(r.note, text);
    r.note.dataset.tone = tone;
    if (r.swatch) {
        const n = Number(value);
        const follows = s.format === 'ledHue' && n === 255;
        r.swatch.style.background = Number.isFinite(n) && value !== undefined && value !== null && !follows ? hueColor(n) : 'transparent';
        r.swatch.classList.toggle('follows', follows);
    }
    const changed = !s.readOnly && value !== undefined && value !== null && !isDefault(s, value);
    r.mark.classList.toggle('on', changed);
    r.mark.title = changed ? 'Changed from the default' : '';
}

function renderAll() {
    for (const r of rows.values()) showValue(r, pending.has(r.s.key) ? pending.get(r.s.key).value : known(r.s.key));
    renderCounts();
    applyFilter();
}

function renderCounts() {
    for (const { el, count, keys } of groups) {
        const changed = keys.filter(k => { const r = rows.get(k); return !r.s.readOnly && has(k) && !isDefault(r.s, known(k)); }).length;
        setText(count, changed ? `${changed} changed` : '');
        el.classList.toggle('has-changes', changed > 0);
    }
}

// --- Search and filter ------------------------------------------------------------------------

const search = () => $('#cfgSearch');
const changedOnly = () => $('#cfgChanged');
const filtering = () => !!(search().value.trim() || changedOnly().checked);

// "p13" finds parameter 13 itself (not 130 to 134); other words match the title, help or key
const matchesWord = (r, w) => (/^p\d+$/.test(w) ? r.s.param === Number(w.slice(1)) : r.text.includes(w));

function applyFilter() {
    const q = search().value.trim().toLowerCase();
    const onlyChanged = changedOnly().checked;
    const open = openGroups();
    for (const { g, el, keys } of groups) {
        let any = false;
        for (const key of keys) {
            const r = rows.get(key);
            const match = (!q || q.split(/\s+/).every(w => matchesWord(r, w))) &&
                (!onlyChanged || (!r.s.readOnly && has(key) && !isDefault(r.s, known(key))));
            r.row.hidden = !match;
            if (!match) r.info.hidden = true;
            any = any || match;
        }
        for (const subhead of el.querySelectorAll('.cfg-sub')) {
            // A subheading shows while any of its rows do
            let n = subhead.nextElementSibling, visible = false;
            while (n && !n.classList.contains('cfg-sub')) { if (n.classList.contains('cfg-row') && !n.hidden) visible = true; n = n.nextElementSibling; }
            subhead.hidden = !visible;
        }
        el.hidden = !any;
        el.open = filtering() ? any : open.includes(g.id);
    }
    const shown = [...rows.values()].filter(r => !r.row.hidden).length;
    setText($('#cfgEmpty'), filtering() && !shown ? 'No settings match.' : '');
}

// --- Reading from the switch --------------------------------------------------------------------

function readMissing(keys) {
    if (!state.device || !catalog) return;
    const want = keys.filter(k => !has(k) && !requested.has(k) && usable(rows.get(k).s));
    if (!want.length) return;
    want.forEach(k => requested.add(k));
    socket().emit('read_settings', { keys: want });
    for (const k of want) renderNote(rows.get(k), known(k));
    giveUpLater(want);
}

function giveUpLater(keys) {
    const device = state.device;
    setTimeout(() => {
        if (state.device !== device) return;
        const missing = keys.filter(k => !has(k) && !unread.has(k));
        if (missing.length) notRead(missing);
    }, state.stack === 'zha' ? READ_GIVE_UP_MS + keys.length * 1000 : READ_GIVE_UP_MS);
}

function notRead(keys) {
    for (const key of keys) {
        unread.add(key);
        const r = rows.get(key);
        if (r) renderNote(r, known(key));
    }
    gotValues(keys);
}

function readAll() {
    if (!state.device) { toast('Choose a switch first.', 'error'); return; }
    const keys = [...rows.keys()];
    keys.forEach(k => { requested.add(k); unread.delete(k); });
    socket().emit('read_settings', { keys });
    // ZHA sends each setting as it's read. Zigbee2MQTT sends its whole state with every
    // message, so there's no telling a fresh answer from the old one
    if (state.stack === 'zha') {
        reading = { left: new Set(keys), total: keys.length };
        renderReading();
        giveUpLater(keys);
    } else {
        setText($('#cfgStatus'), 'Asked the switch for every setting; any that changed update as it answers.');
    }
}

function renderReading() {
    let text = '';
    if (reading) {
        const done = reading.total - reading.left.size;
        text = reading.left.size
            ? `Reading settings from the switch… ${done} of ${reading.total}`
            : `Read ${reading.total - [...unread].filter(k => rows.has(k)).length} of ${reading.total} settings from the switch.`;
    }
    setText($('#cfgStatus'), text);
}

function gotValues(keys) {
    if (!reading) return;
    for (const k of keys) reading.left.delete(k);
    renderReading();
}

// --- Changing a setting ----------------------------------------------------------------------------

async function change(r, value) {
    const s = r.s;
    if (!state.device) { toast('Choose a switch first.', 'error'); showValue(r, known(s.key)); return; }
    if (s.control === 'number') {
        const n = Number(value);
        if (value === '' || !Number.isInteger(n) || n < s.min || n > s.max) {
            toast(`${s.title} takes a whole number from ${s.min} to ${s.max}.`, 'error');
            showValue(r, known(s.key));
            return;
        }
        value = n;
    }
    if (has(s.key) && String(value) === String(known(s.key)) && !pending.has(s.key)) {
        showValue(r, known(s.key));
        return;
    }
    // Ask first, but only in the direction that can cause trouble (switching smart bulb mode
    // or the paddle lock off again is always fine)
    if (s.risky && (!s.riskyTo || s.riskyTo.includes(String(value)))) {
        const to = describe(s, value) || value;
        if (!await confirmAction(`${s.risky} Change ${s.title.toLowerCase()} to ${to}?`, { confirm: 'Change', danger: true })) {
            showValue(r, known(s.key));
            return;
        }
    }
    send(r, value);
}

function send(r, value) {
    const key = r.s.key;
    clearPending(key);
    r.saved = false;
    r.failed = '';
    const device = state.device;
    const timer = setTimeout(() => {
        if (state.device !== device || !pending.has(key)) return;
        pending.delete(key);
        r.failed = 'Not confirmed';
        showValue(r, known(key));
        toast(`The switch didn't confirm ${r.s.title.toLowerCase()}. Press Refresh Values to see what it has.`, 'error', 6000);
        setTimeout(() => { r.failed = ''; renderNote(r, known(key)); }, 8000);
    }, CONFIRM_MS[state.stack] || 12000);
    pending.set(key, { value: String(value), timer });
    showValue(r, value);
    socket().emit('update_parameter', { param: key, value });
}

function clearPending(key) {
    const p = pending.get(key);
    if (p) clearTimeout(p.timer);
    pending.delete(key);
}

// A device_config message: the switch's state, or part of it. Z2M sends the whole state with
// every message (ten a second with target reporting on), so only changes are shown.
let early = {};                // state that came in before the catalogue loaded
const last = new Map();        // key → value last heard from the switch
function fromSwitch(payload) {
    if (!catalog) {
        Object.assign(early, payload);
        return;
    }
    const keys = [];
    const present = [];
    for (const [key, value] of Object.entries(payload)) {
        if (!catalogKeys.has(key)) continue;
        present.push(key);
        const wasUnread = unread.delete(key);
        if (last.has(key) && last.get(key) === value && !pending.has(key) && !wasUnread) continue;
        last.set(key, value);
        const r = rows.get(key);
        state.settings[key] = value;
        keys.push(key);
        if (!r) continue;
        const p = pending.get(key);
        if (p && String(value) === p.value) {
            clearPending(key);
            r.saved = true;
            setTimeout(() => { r.saved = false; renderNote(r, known(key)); }, SAVED_MS);
        }
        // While a change is on its way, Z2M can still re-send the old state; keep showing the new value
        showValue(r, pending.has(key) ? pending.get(key).value : value);
    }
    if (keys.length) {
        renderCounts();
        if (changedOnly().checked) applyFilter();
    }
    if (present.length) {
        gotValues(present);
        if (!stateArrived) stateIn();
    }
}

function stateIn() {
    clearTimeout(stateTimer);
    stateArrived = true;
    if (readWhenState) {
        readWhenState = false;
        readOnOpen();
    }
}

function refused(data) {
    const key = data && data.param;
    const r = key && rows.get(key);
    if (!r || !pending.has(key)) return;
    clearPending(key);
    showValue(r, known(key));
}

function deviceChanged() {
    early = {};
    last.clear();
    clearTimeout(stateTimer);
    stateArrived = false;
    readWhenState = false;
    if (state.device) stateTimer = setTimeout(stateIn, STATE_WAIT_MS);
    for (const key of [...pending.keys()]) clearPending(key);
    requested.clear();
    unread.clear();
    reading = null;
    renderReading();
    for (const r of rows.values()) { r.saved = false; r.failed = ''; }
    if (catalog) {
        for (const r of rows.values()) r.control.querySelectorAll('option[data-extra]').forEach(o => o.remove());
        renderAll();
        if (tabOpen) readOnOpen();
    }
}

// Opening the tab asks for whatever the open groups are missing, once the switch's state
// is in: on Z2M it usually has everything already; on ZHA each setting is a radio read,
// so only open groups.
function readOnOpen() {
    if (!stateArrived) {
        readWhenState = true;
        return;
    }
    const keys = groups.filter(x => x.el.open || state.stack === 'z2m').flatMap(x => x.keys);
    readMissing(keys);
}

export function tabShown(open) {
    tabOpen = open;
    if (open && catalog) readOnOpen();
}

export async function initConfig() {
    on('device-config', fromSwitch);
    on('device', deviceChanged);
    if (state.device) deviceChanged();
    const url = document.body.dataset.catalog;
    try {
        const res = await fetch(url);
        if (!res.ok) throw new Error(res.status);
        catalog = await res.json();
        catalogKeys = new Set(catalog.settings.map(s => s.key));
    } catch (e) {
        setText($('#cfgStatus'), 'Couldn\'t load the list of settings. Reload the page to try again.');
        return;
    }
    build();
    fromSwitch(early);
    early = {};
    $('#cfgSearch').addEventListener('input', applyFilter);
    $('#cfgChanged').addEventListener('change', applyFilter);
    $('#cfgRead').addEventListener('click', readAll);
    socket().on('command_error', refused);
    socket().on('settings_unread', msg => {
        if (msg && msg.topic === state.device && Array.isArray(msg.keys)) notRead(msg.keys);
    });
    if (tabOpen) readOnOpen();
}
