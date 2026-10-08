// Zone names ("Couch" for detection area 2). Display only: the addon keeps them
// per switch for every browser, and they're never sent to the switch.

import { state, emit } from './state.js';
import { toast } from './ui.js';

const MAX = 40;
let saveTimer = 0;

const clean = name => String(name || '').replace(/[\u0000-\u001f\u007f]/g, ' ').replace(/\s+/g, ' ').trim().slice(0, MAX);

// Names arrived from the addon (device change, or another browser renamed something)
export function namesFromServer(names) {
    state.zoneNames = names && typeof names === 'object' ? { ...names } : {};
    emit('names');
}

export function setName(category, area, name) {
    const key = `${category}:${area}`;
    const value = clean(name);
    if ((state.zoneNames[key] || '') === value) return;
    if (value) state.zoneNames[key] = value;
    else delete state.zoneNames[key];
    emit('names');
    scheduleSave();
}

// Several at once (backup import, undo) with one save
export function setNames(entries) {
    for (const [key, name] of Object.entries(entries)) {
        const value = clean(name);
        if (value) state.zoneNames[key] = value;
        else delete state.zoneNames[key];
    }
    emit('names');
    scheduleSave();
}

function scheduleSave() {
    clearTimeout(saveTimer);
    const topic = state.device;
    const names = { ...state.zoneNames };
    saveTimer = setTimeout(() => {
        if (!topic) return;
        state.socket.emit('save_zone_names', { topic, names: Object.keys(names).length ? names : null }, ack => {
            if (ack && ack.error) toast(`The zone name wasn't saved: ${ack.error}`, 'error', 6000);
            else if (ack && ack.warning) toast(`Zone name saved for now. ${ack.warning}`, 'error', 8000);
        });
    }, 300);
}
