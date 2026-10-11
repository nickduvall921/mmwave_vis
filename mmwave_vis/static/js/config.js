// Config tab: every setting the switch has, grouped, each with an ⓘ explaining it.
// It's built from the settings catalogue (assets/settings.json), which the addon also
// checks every write against. Values are the ones Zigbee2MQTT uses; on ZHA the addon
// converts them. Changes are queued (orange dot) and sent with Apply (changes.js);
// a change counts as saved when the switch reports the new value back.

import { state, on } from './state.js';
import * as prefs from './prefs.js';
import { $, h, setText, duration, infoButton } from './ui.js';
import * as changes from './changes.js';

const SAVED_MS = 2500;
const UNCONFIRMED_MS = 8000;
const READ_GIVE_UP_MS = 30000;   // Zigbee2MQTT says nothing about a setting it couldn't read
const STATE_WAIT_MS = 5000;      // how long to wait for the switch's state before asking for settings

let catalog = null;
let loadError = '';
let tabOpen = false;
const rows = new Map();          // key → { s, row, info, infoBtn, control, note, mark, swatch, text, flash }
const groups = [];               // { g, el, count, queuedCount, keys }
const requested = new Set();     // settings asked from this switch since it was selected
const unread = new Set();        // settings the switch didn't answer
const giveUps = new Set();       // give-up timers for those reads
let reading = null;              // { left: Set, total } while "Refresh Values" runs on ZHA
let waitingForState = false;     // a switch was selected and its state isn't in yet
let stateWait = 0;
let unsupported = new Set();     // settings the switch's ZHA quirk doesn't define

// Groups the person has open, kept here too so a page without storage still remembers
const savedOpen = prefs.get('configOpen');
const openSet = new Set(savedOpen === null ? ['presence'] : savedOpen.split(',').filter(Boolean));

const socket = () => state.socket;
const known = key => state.settings[key];
const has = key => known(key) !== undefined && known(key) !== null;
const usable = s => !(state.stack === 'zha' && s.zha === false);
const optionsFor = s => (s.options || []).filter(o => !(o.zhaOnly && state.stack !== 'zha'));
const isDefault = (s, value) => s.default === undefined || String(value) === String(s.default);
// The switch's value isn't the default (the blue dot)
const isChanged = (s, value) => !s.readOnly && value !== undefined && value !== null && !isDefault(s, value);

// Why a setting can't be changed here, or '' if it can
function unavailable(s) {
    if (s.readOnly) return '';
    if (unsupported.has(s.key)) return 'The ZHA quirk running this switch can\'t change this';
    if (s.needsRadar && !state.radarReports) return 'Needs the Visualizer\'s ZHA quirk';
    return '';
}

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

// --- Building the tab -----------------------------------------------------------------------

function makeControl(s, id, label) {
    if (s.readOnly) return h('span', { id, class: 'cfg-readonly' }, '–');
    if (s.control === 'toggle') {
        const off = s.options.find(o => o.value !== s.on);
        return h('input', { type: 'checkbox', role: 'switch', class: 'switch', id, 'aria-label': label, dataset: { on: s.on, off: off.value } });
    }
    if (s.control === 'select') {
        return h('select', { id, 'aria-label': label },
            h('option', { value: '', disabled: true }, '–'),
            optionsFor(s).map(o => h('option', { value: o.value }, o.label || o.value)));
    }
    if (s.format === 'hue' || s.format === 'ledHue') {
        return h('input', { type: 'range', id, min: s.min, max: s.max, step: 1, class: 'hue-range', 'aria-label': label });
    }
    return h('input', { type: 'number', id, min: s.min, max: s.max, step: 1, inputmode: 'numeric', placeholder: '–', 'aria-label': label });
}

function buildRow(s) {
    const id = `cfg-${s.key}`;
    const infoId = `${id}-info`;
    const label = changes.titleOf(s.key);
    const control = makeControl(s, id, label);
    const note = h('span', { class: 'cfg-note' });
    const mark = h('span', { class: 'cfg-mark', 'aria-hidden': 'true' });
    const swatch = (s.format === 'hue' || s.format === 'ledHue') ? h('span', { class: 'cfg-swatch', 'aria-hidden': 'true' }) : null;
    const infoBtn = infoButton(infoId, `About ${label}`);
    const title = s.readOnly ? h('span', null, s.title) : h('label', { for: id }, s.title);
    const row = h('div', { class: 'cfg-row' },
        h('span', { class: 'label-info' }, mark, title, infoBtn),
        h('span', { class: 'cfg-value' }, h('span', { class: 'cfg-control' }, swatch, control), note));
    const reset = !s.readOnly && s.default !== undefined
        ? h('button', { class: 'btn link', type: 'button', onclick: () => edit(r, s.default) }, 'Reset to default')
        : null;
    const meta = [];
    if (!s.readOnly && s.default !== undefined) meta.push(`Default: ${describe(s, s.default) || s.default}${s.options ? '' : ` (${s.default})`}.`);
    if (s.control === 'number' && !s.readOnly) meta.push(`Range ${s.min} to ${s.max}.`);
    meta.push(`Parameter ${s.param}, ${s.key}.`);
    const info = h('div', { class: 'info-panel', id: infoId, hidden: true },
        s.help.split('\n\n').map(p => h('p', null, p)),
        s.quirkUpdate ? h('p', { class: 'zha-only' }, 'With the Visualizer\'s ZHA quirk this needs version 4.2 or later of it; ZHA\'s built-in quirk has it.') : null,
        h('p', { class: 'cfg-meta' }, meta.join(' '), reset ? ' ' : null, reset));
    const r = { s, row, info, infoBtn, control, note, mark, swatch, flash: null,
        text: `${s.title} ${s.sub || ''} ${s.help} ${s.key}`.toLowerCase() };

    if (control.type === 'range') {
        control.addEventListener('input', () => renderNote(r, Number(control.value)));
    }
    if (!s.readOnly) control.addEventListener('change', () => edit(r, controlValue(r)));
    rows.set(s.key, r);
    return [row, info];
}

function buildGroup(g) {
    const settings = catalog.settings.filter(s => s.group === g.id && usable(s));
    if (!settings.length) return null;
    const keys = settings.map(s => s.key);
    const count = h('span', { class: 'count' });
    const queuedCount = h('span', { class: 'count queued-count' });
    const body = [];
    let sub = null;
    for (const s of settings) {
        if (s.sub && s.sub !== sub) body.push(h('h3', { class: 'cfg-sub' }, s.sub));
        sub = s.sub;
        body.push(...buildRow(s));
    }
    const el = h('details', { class: 'section cfg-group' },
        h('summary', null, h('span', null, g.title, count, queuedCount)),
        g.help ? h('p', { class: 'cfg-group-help' }, g.help) : null,
        body, changes.applyRow(keys));
    el.open = openSet.has(g.id);
    el.addEventListener('toggle', () => {
        // Remember what the person opened, not what the search opened
        if (!filtering()) {
            if (el.open) openSet.add(g.id); else openSet.delete(g.id);
            prefs.set('configOpen', [...openSet].join(','));
        }
        if (el.open && tabOpen) readOnOpen();
    });
    groups.push({ g, el, count, queuedCount, keys });
    return el;
}

function build() {
    rows.clear();
    groups.length = 0;
    $('#cfgGroups').replaceChildren(...catalog.groups.map(buildGroup).filter(Boolean));
    renderAll();
}

// --- Showing values ---------------------------------------------------------------------------

function controlValue(r) {
    const c = r.control;
    if (c.type === 'checkbox') return c.dataset[c.checked ? 'on' : 'off'];
    return c.value;
}

// `force`: also overwrite a field that has focus (putting back a refused value)
function showValue(r, value, force = false) {
    const c = r.control;
    const missing = value === undefined || value === null;
    if (r.s.readOnly) {
        setText(c, missing ? '–' : describe(r.s, value) || String(value));
    } else if (c.type === 'checkbox') {
        c.checked = value === c.dataset.on;
        c.indeterminate = missing;
    } else if (c.tagName === 'SELECT') {
        const v = missing ? '' : String(value);
        if (v && ![...c.options].some(o => o.value === v)) {
            // A value this page doesn't know (newer firmware?); show it rather than a blank
            c.append(h('option', { value: v, dataset: { extra: '1' } }, v));
        }
        c.value = v;
    } else if (force || document.activeElement !== c) {
        c.value = missing ? (c.type === 'range' ? c.min : '') : String(value);
    }
}

function renderNote(r, value) {
    const s = r.s;
    const key = s.key;
    const why = unavailable(s);
    const queued = changes.queued.has(key);
    let text = '';
    let tone = '';
    if (why) text = why;
    else if (changes.pending.has(key)) { text = 'Saving…'; tone = 'busy'; }
    else if (r.flash) ({ text, tone } = r.flash);
    else if (queued) {
        const d = !s.options && s.format ? describe(s, value) : '';
        text = d ? `${d} · not applied` : 'Not applied yet';
        tone = 'queued';
    } else if (value === undefined || value === null) {
        text = unread.has(key) ? 'Couldn\'t read' : (requested.has(key) ? 'Reading…' : '');
        tone = unread.has(key) ? 'bad' : '';
    } else if (!s.options && s.format && !s.readOnly) text = describe(s, value);
    setText(r.note, text);
    r.note.dataset.tone = tone;
    if (r.swatch) {
        const n = Number(value);
        const follows = s.format === 'ledHue' && n === 255;
        r.swatch.style.background = Number.isFinite(n) && value !== undefined && value !== null && !follows ? hueColor(n) : 'transparent';
        r.swatch.classList.toggle('follows', follows);
    }
    const changed = isChanged(s, known(key));
    r.mark.classList.toggle('queued', queued);
    r.mark.classList.toggle('on', !queued && changed);
    r.mark.title = queued ? 'Changed here, not applied yet' : changed ? 'Not at its default' : '';
}

function render(r, force = false) {
    const value = changes.shown(r.s.key);
    showValue(r, value, force);
    const off = !!unavailable(r.s);
    if (!r.s.readOnly) r.control.disabled = off;
    r.row.classList.toggle('cfg-off', off);
    renderNote(r, value);
}

function renderAll() {
    for (const r of rows.values()) render(r);
    renderCounts();
    applyFilter();
}

function renderCounts() {
    for (const { el, count, queuedCount, keys } of groups) {
        const changed = keys.filter(k => isChanged(rows.get(k).s, known(k))).length;
        const q = keys.filter(k => changes.queued.has(k)).length;
        setText(count, changed ? `${changed} changed` : '');
        setText(queuedCount, q ? `${q} not applied` : '');
        el.classList.toggle('queued', q > 0);
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
    for (const { g, el, keys } of groups) {
        let any = false;
        for (const key of keys) {
            const r = rows.get(key);
            const match = (!q || q.split(/\s+/).every(w => matchesWord(r, w))) &&
                (!onlyChanged || isChanged(r.s, known(key)) || changes.queued.has(key));
            r.row.hidden = !match;
            if (!match && !r.info.hidden) {
                r.info.hidden = true;
                r.infoBtn.setAttribute('aria-expanded', 'false');
            }
            any = any || match;
        }
        for (const subhead of el.querySelectorAll('.cfg-sub')) {
            // A subheading shows while any of its rows do
            let n = subhead.nextElementSibling, visible = false;
            while (n && !n.classList.contains('cfg-sub')) { if (n.classList.contains('cfg-row') && !n.hidden) visible = true; n = n.nextElementSibling; }
            subhead.hidden = !visible;
        }
        el.hidden = !any;
        el.open = filtering() ? any : openSet.has(g.id);
    }
    const shown = [...rows.values()].filter(r => !r.row.hidden).length;
    setText($('#cfgEmpty'), filtering() && !shown ? 'No settings match.' : '');
    // Groups the search opens are read by their toggle event
}

// --- Reading from the switch --------------------------------------------------------------------

function readMissing(keys) {
    if (!state.device || !catalog) return;
    const want = keys.filter(k => !has(k) && !requested.has(k));
    if (!want.length) return;
    want.forEach(k => requested.add(k));
    socket().emit('read_settings', { keys: want });
    for (const k of want) renderNote(rows.get(k), known(k));
    giveUpLater(want);
}

function giveUpLater(keys) {
    const timer = setTimeout(() => {
        giveUps.delete(timer);
        const missing = keys.filter(k => !has(k) && !unread.has(k));
        if (missing.length) notRead(missing);
    }, state.stack === 'zha' ? READ_GIVE_UP_MS + keys.length * 1000 : READ_GIVE_UP_MS);
    giveUps.add(timer);
}

function notRead(keys) {
    for (const key of keys) {
        unread.add(key);
        const r = rows.get(key);
        if (r) renderNote(r, changes.shown(key));
    }
    gotValues(keys);
}

function readAll() {
    if (!state.device) return;
    const keys = [...rows.keys()];
    keys.forEach(k => { requested.add(k); unread.delete(k); });
    for (const k of keys) renderNote(rows.get(k), changes.shown(k));
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
    // One read of everything at a time: a second would only wait for the first
    $('#cfgRead').disabled = !!(reading && reading.left.size);
    let text = loadError;
    if (!text && reading) {
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

// Opening the tab (or a group) asks for whatever the open groups are missing, once the
// switch's state is in: on Z2M it usually has everything already; on ZHA each setting
// is a radio read, so only open groups.
function readOnOpen() {
    if (waitingForState || !catalog) return;
    readMissing(groups.filter(x => x.el.open || state.stack === 'z2m').flatMap(x => x.keys));
}

// `late`: nothing came in time. Zigbee2MQTT then has nothing for the switch (it's
// offline, or new), so asking it to read every setting would only queue up timeouts;
// Refresh Values still can. ZHA has no state to send without the Visualizer's quirk.
function stateArrived(late = false) {
    clearTimeout(stateWait);
    waitingForState = false;
    if (tabOpen && !(late && state.stack === 'z2m')) readOnOpen();
}

// --- Changing a setting ----------------------------------------------------------------------------

// The person changed a control: queue it (or put the control back if it can't take that)
function edit(r, value) {
    const key = r.s.key;
    if (!state.device || unavailable(r.s)) { render(r, true); return; }
    const v = changes.check(key, value);
    if (v === null) { render(r, true); return; }
    changes.queue(key, v);
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
    const present = [];
    let changed = false;
    for (const [key, value] of Object.entries(payload)) {
        const r = rows.get(key);
        if (!r) continue;
        present.push(key);
        state.settings[key] = value;
        changes.reported(key, value);
        const wasUnread = unread.delete(key);
        if (last.has(key) && last.get(key) === value && !wasUnread) continue;
        last.set(key, value);
        changed = true;
        render(r);
    }
    if (changed) {
        renderCounts();
        if (changedOnly().checked) applyFilter();
    }
    if (present.length) {
        gotValues(present);
        if (waitingForState) stateArrived();
    }
}

function flash(r, text, tone, ms) {
    r.flash = { text, tone };
    clearTimeout(r.flashTimer);
    r.flashTimer = setTimeout(() => { r.flash = null; renderNote(r, changes.shown(r.s.key)); }, ms);
}

function onPending({ key, result }) {
    const r = rows.get(key);
    if (!r) return;
    if (result === 'saved') flash(r, 'Saved', 'good', SAVED_MS);
    else if (result === 'unconfirmed') flash(r, 'Not confirmed', 'bad', UNCONFIRMED_MS);
    render(r, result !== 'saving');
}

function onQueue(keys) {
    for (const key of keys.length ? keys : rows.keys()) {
        const r = rows.get(key);
        if (r) render(r, true);
    }
    renderCounts();
    if (changedOnly().checked) applyFilter();
}

function deviceChanged() {
    early = {};
    last.clear();
    for (const t of giveUps) clearTimeout(t);
    giveUps.clear();
    clearTimeout(stateWait);
    waitingForState = !!state.device;
    if (waitingForState) stateWait = setTimeout(() => stateArrived(true), STATE_WAIT_MS);
    requested.clear();
    unread.clear();
    unsupported = new Set();
    reading = null;
    renderReading();
    if (catalog) {
        for (const r of rows.values()) {
            r.flash = null;
            r.control.querySelectorAll('option[data-extra]').forEach(o => o.remove());
        }
        renderAll();
    }
}

function deviceInfo() {
    const info = state.deviceInfo;
    unsupported = new Set(info && info.topic === state.device ? info.unsupported_settings || [] : []);
    if (catalog) renderAll();
}

export function tabShown(open) {
    tabOpen = open;
    if (open) readOnOpen();
}

export async function initConfig() {
    on('device-config', fromSwitch);
    on('device', deviceChanged);
    on('queue', keys => catalog && onQueue(keys));
    on('pending', p => catalog && onPending(p));
    on('device-info', deviceInfo);
    on('radar-reports', () => catalog && renderAll());
    if (state.device) deviceChanged();
    try {
        const res = await fetch(document.body.dataset.catalog);
        if (!res.ok) throw new Error(res.status);
        catalog = await res.json();
    } catch (e) {
        loadError = 'Couldn\'t load the list of settings. Reload the page to try again.';
        renderReading();
        return;
    }
    changes.setCatalog(catalog.settings);
    build();
    fromSwitch(early);
    early = {};
    deviceInfo();
    $('#cfgSearch').addEventListener('input', applyFilter);
    $('#cfgChanged').addEventListener('change', applyFilter);
    $('#cfgRead').addEventListener('click', readAll);
    changes.bindApplyBar({ button: $('#cfgApply'), discardButton: $('#cfgDiscard'), status: $('#cfgQueued') });
    socket().on('settings_unread', msg => {
        if (msg && msg.topic === state.device && Array.isArray(msg.keys)) notRead(msg.keys);
    });
    if (tabOpen) readOnOpen();
}
