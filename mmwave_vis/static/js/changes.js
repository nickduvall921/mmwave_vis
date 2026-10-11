// Setting changes are queued while they're adjusted and sent to the switch together
// with Apply, so a slip of the mouse or a click through a number field's arrows doesn't
// write to the switch at every step. The Detection and Config tabs share this queue.
// After Apply a change is "saving" until the switch reports the new value back, then
// "saved"; if it doesn't in time, "unconfirmed".

import { state, on, emit } from './state.js';
import { h, setText, plural, toast, confirmAction } from './ui.js';

const CONFIRM_MS = { z2m: 10000, zha: 15000 };   // ZHA reads the values back after 1.5 s, one radio read at a time

let byKey = new Map();                // the settings catalogue, once the Config tab has loaded it
export const queued = new Map();      // key → value (as Zigbee2MQTT names it) waiting for Apply
export const pending = new Map();     // key → { value, timer } sent and not confirmed yet
let unconfirmed = [];                 // keys that timed out together, for one message
let unconfirmedTimer = 0;

export function setCatalog(settings) {
    byKey = new Map(settings.map(s => [s.key, s]));
}

export const settingFor = key => byKey.get(key);

// "Hold time", or "LED 7 (top): Colour when on" where the title alone is ambiguous
export function titleOf(key) {
    const s = byKey.get(key);
    if (!s) return key;
    return s.sub ? `${s.sub}: ${s.title}` : s.title;
}

const known = key => state.settings[key];
const same = (a, b) => a !== undefined && a !== null && String(a) === String(b);

// What the controls show: the value on its way, else the queued one, else the switch's
export function shown(key) {
    if (pending.has(key)) return pending.get(key).value;
    if (queued.has(key)) return queued.get(key);
    return known(key);
}

// --- The controls both tabs use ---------------------------------------------------------

// What a control holds. On/off switches carry the switch's own values in data-on / data-off.
export const controlValue = c => (c.type === 'checkbox' ? c.dataset[c.checked ? 'on' : 'off'] : c.value);

// Show `value` in a control. `force`: also overwrite a field that has focus (putting back a
// refused value); otherwise a field being typed in is left alone.
export function showControlValue(c, value, force = false) {
    const missing = value === undefined || value === null;
    if (c.type === 'checkbox') {
        c.checked = value === c.dataset.on;
        c.indeterminate = missing;
    } else if (c.tagName === 'SELECT') {
        const v = missing ? '' : String(value);
        if (v && ![...c.options].some(o => o.value === v)) {
            // A value this page doesn't list (newer firmware?); show it rather than a blank
            c.append(h('option', { value: v, dataset: { extra: '1' } }, v));
        }
        c.value = v;
    } else if (force || document.activeElement !== c) {
        c.value = missing ? (c.type === 'range' ? c.min : '') : String(value);
    }
}

// A value the switch can take (numbers as numbers), or null after saying what's allowed
export function check(key, value) {
    const s = byKey.get(key);
    if (!s) return value;                       // the addon checks it anyway
    if (s.options) return s.options.some(o => o.value === value) ? value : null;
    const n = Number(value);
    if (value === '' || value === null || !Number.isInteger(n) || n < s.min || n > s.max) {
        toast(`${titleOf(key)} takes a whole number from ${s.min} to ${s.max}.`, 'error');
        return null;
    }
    return n;
}

// Queue a change. Setting it back to what the switch has takes it off the queue.
export function queue(key, value) {
    if (same(known(key), value)) queued.delete(key);
    else queued.set(key, value);
    emit('queue', [key]);
}

export function discard(keys = [...queued.keys()]) {
    const gone = keys.filter(k => queued.delete(k));
    if (gone.length) emit('queue', gone);
}

// Send queued changes (all, or `keys`) in one go. Settings that could stop the light
// working ask first, in one question.
export async function apply(keys = [...queued.keys()]) {
    keys = keys.filter(k => queued.has(k));
    if (!keys.length) return false;
    if (!state.device) { toast('Choose a switch first.', 'error'); return false; }
    const risky = keys.map(k => byKey.get(k))
        .filter(s => s && s.risky && (!s.riskyTo || s.riskyTo.includes(String(queued.get(s.key)))));
    if (risky.length) {
        const what = keys.length === 1 ? 'this change' : `these ${keys.length} changes`;
        if (!await confirmAction(`${risky.map(s => s.risky).join(' ')} Apply ${what}?`, { confirm: 'Apply', danger: true })) return false;
        // Another switch may have been chosen meanwhile, which empties the queue
        keys = keys.filter(k => queued.has(k));
        if (!keys.length || !state.device) return false;
    }
    const params = {};
    for (const key of keys) {
        params[key] = queued.get(key);
        queued.delete(key);
        startPending(key, params[key]);
    }
    state.socket.emit('update_parameters', { params });
    emit('queue', keys);
    return true;
}

function startPending(key, value) {
    clearPending(key);
    const device = state.device;
    const timer = setTimeout(() => {
        if (state.device !== device || !pending.has(key)) return;
        pending.delete(key);
        emit('pending', { key, result: 'unconfirmed' });
        unconfirmed.push(key);
        clearTimeout(unconfirmedTimer);
        unconfirmedTimer = setTimeout(() => {
            const what = unconfirmed.length === 1 ? `"${titleOf(unconfirmed[0])}"` : `${unconfirmed.length} changes`;
            toast(`The switch didn't confirm ${what}. Refresh Values in the Config tab shows what it has.`, 'error', 7000);
            unconfirmed = [];
        }, 300);
    }, CONFIRM_MS[state.stack] || 12000);
    pending.set(key, { value: String(value), timer });
    emit('pending', { key, result: 'saving' });
}

function clearPending(key) {
    const p = pending.get(key);
    if (p) clearTimeout(p.timer);
    pending.delete(key);
}

// The switch reported a value for `key`: settles a change on its way, and drops a queued
// change it already has (another page applied the same)
export function reported(key, value) {
    const p = pending.get(key);
    if (p && same(value, p.value)) {
        clearPending(key);
        emit('pending', { key, result: 'saved' });
    }
    if (queued.has(key) && same(value, queued.get(key))) {
        queued.delete(key);
        emit('queue', [key]);
    }
}

// The addon refused these changes (it has already said why)
export function refused(keys) {
    for (const key of keys) {
        if (!pending.has(key)) continue;
        clearPending(key);
        emit('pending', { key, result: 'refused' });
    }
}

// Another switch was chosen: nothing queued or on its way carries over
export function reset() {
    for (const key of [...pending.keys()]) clearPending(key);
    if (queued.size) {
        queued.clear();
        emit('queue', []);
    }
}

// --- Apply controls -------------------------------------------------------------------

const inScope = scope => k => !scope || scope.includes(k);

// A tab's Apply button (orange while anything in `scope`, or anything at all, waits),
// its Discard button and a line saying what's waiting
export function bindApplyBar({ button, discardButton, status, scope = null }) {
    const mine = inScope(scope);
    let saved = false;          // "Saved" for a moment once everything sent is confirmed
    let savedTimer = 0;
    const render = () => {
        const n = [...queued.keys()].filter(mine).length;
        const saving = [...pending.keys()].filter(mine).length;
        button.disabled = !n;
        button.classList.toggle('has-queue', n > 0);
        setText(button, n ? `Apply ${n}` : 'Apply');
        if (discardButton) discardButton.hidden = !n;
        if (status) {
            setText(status, n ? `${plural(n, 'change')} not applied yet. Apply sends ${n === 1 ? 'it' : 'them'} to the switch.`
                : saving ? `Sending ${plural(saving, 'change')} to the switch…` : saved ? 'Saved on the switch.' : '');
            status.dataset.tone = n ? 'queued' : !saving && saved ? 'good' : '';
        }
    };
    button.addEventListener('click', () => apply([...queued.keys()].filter(mine)));
    if (discardButton) discardButton.addEventListener('click', () => discard([...queued.keys()].filter(mine)));
    on('queue', render);
    on('pending', ({ key, result }) => {
        if (mine(key)) {
            saved = result === 'saved' || (result === 'saving' && saved);
            clearTimeout(savedTimer);
            if (saved) savedTimer = setTimeout(() => { saved = false; render(); }, 2500);
        }
        render();
    });
    render();
}

// "2 changes not applied yet  Discard  Apply" at the end of a group of settings, shown
// while any of them wait
export function applyRow(keys) {
    const text = h('span', { class: 'grow' });
    const row = h('div', { class: 'apply-row', hidden: true }, text,
        h('button', { class: 'btn link', type: 'button', onclick: () => discard(keys) }, 'Discard'),
        h('button', { class: 'btn small apply-btn has-queue', type: 'button', onclick: () => apply(keys) }, 'Apply'));
    const render = () => {
        const n = keys.filter(k => queued.has(k)).length;
        row.hidden = !n;
        setText(text, `${plural(n, 'change')} not applied yet`);
    };
    on('queue', render);
    return row;
}

export function initChanges() {
    state.socket.on('command_error', data => {
        const keys = data && (Array.isArray(data.params) ? data.params : data.param ? [data.param] : []);
        if (keys && keys.length) refused(keys);
    });
    // Leaving with changes that were never applied loses them; let the browser ask
    window.addEventListener('beforeunload', e => {
        if (!queued.size) return;
        e.preventDefault();
        e.returnValue = '';
    });
}
