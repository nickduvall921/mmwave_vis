// Undo for zone changes: a save or delete, a maintenance command (clear, reset,
// auto-detect) or a backup import. Each switch keeps its own short list, in this
// page only. Undoing sends the zones back as they were before the change.

import { state, on, AREAS, zoneName } from './state.js';
import { $, toast, confirmAction } from './ui.js';
import { writeZone, sameZone, isMirroredX, displayZones, SWITCH_ROUNDING_CM } from './zones.js';
import { restoreZones, isRestoring } from './backup.js';
import { setNames } from './names.js';

const MAX = 10;
const stacks = new Map();   // topic → entries, newest last

const bar = $('#undoBar');
const label = $('#undoLabel');

function stack() {
    if (!stacks.has(state.device)) stacks.set(state.device, []);
    return stacks.get(state.device);
}

// entry: { label, writes: [{ category, area, zone (before), after? }], names?: {key: name} }
// `after` is what the change left in the slot, when known; undo checks it's still there.
// The entry object itself is kept, so a toast can later ask to undo exactly that change.
function push(entry) {
    if (!state.device || !entry || !entry.writes || !entry.writes.length) return null;
    const list = stack();
    entry.topic = state.device;
    entry.at = Date.now();
    list.push(entry);
    while (list.length > MAX) list.shift();
    render();
    return entry;
}

// Take an entry back off the list without undoing it (the change never happened)
export function drop(entry) {
    const list = stacks.get(entry && entry.topic) || [];
    const i = list.indexOf(entry);
    if (i >= 0) {
        list.splice(i, 1);
        render();
    }
}

// The zone types a maintenance command or import is about to change, as they are now.
// Only types the switch has reported since it was selected and that have no unconfirmed
// writes, so undo never puts back something the page only guessed at.
export function snapshot(categories) {
    const writes = [];
    const skipped = [];
    for (const category of categories) {
        const pending = Object.values(state.pending).some(p => p.category === category);
        if (!state.zoneReportAt[category] || pending) { skipped.push(category); continue; }
        for (const area of AREAS) {
            const zone = state.zones[category][area];
            // Detection area 1 holds the room limits; never clear it
            if (!zone && category === 'mmwave_detection_areas' && area === 'area1') continue;
            writes.push({ category, area, zone: zone ? { ...zone } : null });
        }
    }
    return { writes, skipped };
}

// The names of the snapshotted slots, so undo brings them back with their zones (a name
// is dropped when the switch reports its slot empty)
function namesOf(writes) {
    const names = {};
    for (const w of writes) names[`${w.category}:${w.area}`] = (state.zoneNames || {})[`${w.category}:${w.area}`] || '';
    return names;
}

// The pushed entry, or null when there was nothing to snapshot
export function pushSnapshot(labelText, categories) {
    const { writes } = snapshot(categories);
    return writes.length ? push({ label: labelText, writes, names: namesOf(writes) }) : null;
}

function render() {
    const list = stacks.get(state.device) || [];
    const last = list[list.length - 1];
    bar.hidden = !last;
    if (last) label.textContent = last.label;
}

// The slot no longer holds what the change left there (a stay zone the firmware stored
// mirrored still counts as unchanged)
function changedSince(w) {
    if (w.after === undefined) return false;
    const now = displayZones()[w.category][w.area];
    if (sameZone(now, w.after, SWITCH_ROUNDING_CM)) return false;
    return !(w.category === 'mmwave_stay_areas' && isMirroredX(now, w.after, SWITCH_ROUNDING_CM));
}

// Undo the newest change, or `target` (from a toast) only while it still is the newest:
// undoing an older change under a newer one would leave the zones in a mix of both
export async function undo(target = null) {
    const list = stacks.get(state.device) || [];
    const entry = list[list.length - 1];
    if (target && entry !== target) {
        toast(list.includes(target)
            ? 'You\'ve changed zones since then. Use the Undo bar to take back the newest change first.'
            : 'That change can\'t be undone any more.', 'error', 6000);
        return;
    }
    if (!entry) { toast('Nothing to undo.', 'info', 2500); return; }
    if (isRestoring()) { toast('Wait for the zones being sent now to finish.', 'error'); return; }
    if (state.edit) { toast('Save or cancel the zone you\'re editing first.', 'error'); return; }
    const changed = entry.writes.filter(changedSince);
    if (changed.length) {
        const names = changed.map(w => zoneName(w.category, w.area)).join(', ');
        if (!await confirmAction(`${names} changed again since "${entry.label}". Undo anyway?`, { confirm: 'Undo' })) return;
    }
    if (list[list.length - 1] !== entry || state.device !== entry.topic) return;
    list.pop();
    render();
    if (entry.names) setNames(entry.names);
    if (entry.writes.length === 1) {
        const w = entry.writes[0];
        writeZone(w.category, w.area, w.zone, { message: `Undoing: ${entry.label.charAt(0).toLowerCase()}${entry.label.slice(1)}…` });
        return;
    }
    restoreZones(entry.writes.map(w => ({ category: w.category, area: w.area, zone: w.zone })),
        { label: `Undo of "${entry.label}"` });
}

// For a toast that offers to take back one particular change
export const undoActionFor = entry => ({ label: 'Undo', onClick: () => undo(entry) });

export function initUndo() {
    on('undoable', push);
    on('undo-snapshot', ({ label: text, categories, names }) => {
        const { writes } = snapshot(categories);
        if (writes.length) push({ label: text, writes, names });
    });
    on('undo', target => undo(target || null));
    on('device', render);
    $('#btnUndo').addEventListener('click', () => undo());
    document.addEventListener('keydown', e => {
        if (!(e.ctrlKey || e.metaKey) || e.shiftKey || e.altKey || e.key.toLowerCase() !== 'z') return;
        const t = e.target;
        if (t && (t.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(t.tagName))) return;
        if (document.querySelector('dialog[open]')) return;
        e.preventDefault();
        undo();
    });
    render();
}
