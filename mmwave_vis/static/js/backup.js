// Zone backup and restore (#52): save a switch's zones to a file and put them back.

import { state, emit, ZONE_KEYS, ZONE_TYPES, AREAS } from './state.js';
import { $, toast, confirmAction, plural, downloadBlob, fileSafe } from './ui.js';
import { EMPTY_AREA, zoneToDevicePayload, endEdit, sameZone, isMirroredX, clearPending, renderZoneList, SWITCH_ROUNDING_CM as ROUNDING } from './zones.js';

const BACKUP_TYPE = 'mmwave_vis_zone_backup';
const GROUPS = Object.fromEntries(ZONE_TYPES.map(t => [t.group, t.category]));   // file key → category
const GROUP_NAMES = Object.fromEntries(ZONE_TYPES.map(t => [t.category, t.group]));
const RESTORE_GAP_MS = 600;   // space out writes so a slow Zigbee network keeps up
const RESTORE_PASSES = 3;     // send, then up to twice more for what didn't land
const APPLY_MS = 12000;       // after this long, a steady report that still doesn't match is the answer

const btnExport = $('#btnExportZones');
const btnImport = $('#btnImportZones');
const fileInput = $('#importZonesFile');
const statusLine = $('#zoneBackupStatus');
const sleep = ms => new Promise(r => setTimeout(r, ms));

function setBusy(busy) {
    btnExport.disabled = btnImport.disabled = busy;
}

// Ask the switch to report all three zone types and wait for each to come back.
// Resolves with the zone types that didn't report in time (empty when all did).
async function readZonesFromSwitch(timeoutMs = 12000) {
    const since = Date.now();
    state.socket.emit('send_command', 2);   // query_areas
    await sleep(3000);                      // Z2M republishes cached state on unrelated updates; give the real reports time
    while (Date.now() - since < timeoutMs) {
        if (Object.values(state.zoneReportAt).every(t => t > since)) {
            await sleep(1500);              // let the last report of the batch land
            return [];
        }
        await sleep(250);
    }
    return Object.keys(state.zoneReportAt).filter(c => state.zoneReportAt[c] <= since);
}

async function exportZones() {
    if (!state.device) { toast('Choose a switch first.', 'error'); return; }
    const topic = state.device;
    setBusy(true);
    statusLine.textContent = 'Reading zones from the switch…';
    const missing = await readZonesFromSwitch();
    setBusy(false);
    if (state.device !== topic) { statusLine.textContent = ''; return; }
    if (missing.length) {
        const names = missing.map(c => GROUP_NAMES[c]).join(', ');
        statusLine.textContent = '';
        toast(`The switch didn't report its ${names} zones, so nothing was saved. Try again in a moment.`, 'error', 6000);
        return;
    }

    const zones = {};
    let count = 0;
    for (const [group, category] of Object.entries(GROUPS)) {
        zones[group] = {};
        for (const area of AREAS) {
            const a = state.zones[category][area];
            zones[group][area] = a ? Object.fromEntries(ZONE_KEYS.map(k => [k, Math.round(Number(a[k]) || 0)])) : null;
            if (a) count++;
        }
    }

    const name = state.deviceName;
    const backup = { type: BACKUP_TYPE, version: 1, exported: new Date().toISOString(), device: name, stack: state.stack, zones };
    downloadBlob(new Blob([JSON.stringify(backup, null, 2)], { type: 'application/json' }),
        `mmwave-zones-${fileSafe(name, 'switch')}-${backup.exported.slice(0, 10)}.json`);
    statusLine.textContent = `Exported ${plural(count, 'zone')} from ${name}.`;
}

// Validate a backup file and turn it into an ordered list of area writes.
// A zone type missing from the file is left alone on the switch (listed in `skipped`).
export function parseZoneBackup(text) {
    let data;
    try { data = JSON.parse(text); } catch (e) { throw new Error('That file isn\'t valid JSON.'); }
    if (!data || data.type !== BACKUP_TYPE || !data.zones || typeof data.zones !== 'object' || Array.isArray(data.zones)) {
        throw new Error('That file isn\'t a zone backup from this addon.');
    }
    if (data.version !== 1) throw new Error(`Unsupported zone backup version: ${data.version}`);

    const writes = [], skipped = [];
    for (const [group, category] of Object.entries(GROUPS)) {
        const areas = data.zones[group];
        if (areas == null) { skipped.push(group); continue; }
        if (typeof areas !== 'object' || Array.isArray(areas)) throw new Error(`The ${group} zones in that file are malformed.`);
        for (let i = 1; i <= 4; i++) {
            const area = areas[`area${i}`];
            if (area == null) {
                // Detection area 1 holds the room limits; never wipe it
                if (group === 'detection' && i === 1) continue;
                writes.push({ category, area: `area${i}`, zone: null });
                continue;
            }
            const zone = {};
            for (const k of ZONE_KEYS) {
                const v = Number(area[k]);
                if (!Number.isInteger(v) || Math.abs(v) > 10000) throw new Error(`Bad ${k} in ${group} area ${i}.`);
                zone[k] = v;
            }
            writes.push({ category, area: `area${i}`, zone });
        }
    }
    if (!writes.length) throw new Error('That backup has no zones in it.');
    return { data, writes, skipped };
}

async function onFileChosen() {
    const file = fileInput.files[0];
    fileInput.value = '';   // so picking the same file again still fires
    if (!file) return;
    if (!state.device) { toast('Choose a switch first.', 'error'); return; }

    let parsed;
    try { parsed = parseZoneBackup(await file.text()); }
    catch (e) { toast(e.message, 'error', 6000); return; }

    const { data, writes, skipped } = parsed;
    const source = data.device ? `"${data.device}"` : 'this backup';
    const saved = data.exported ? ` (saved ${new Date(data.exported).toLocaleString()})` : '';
    const zoneCount = writes.filter(w => w.zone).length;
    const clearCount = writes.length - zoneCount;
    let msg = `Restore zones from ${source}${saved} onto "${state.deviceName}"?\n\n` +
              `${plural(zoneCount, 'zone')} will be written`;
    if (clearCount) msg += ` and ${plural(clearCount, 'empty slot')} cleared`;
    msg += '.';
    if (skipped.length) msg += `\n\nNot in the backup, left as they are: ${skipped.join(', ')} zones.`;
    if (!await confirmAction(msg, { confirm: 'Restore' })) return;
    restoreZones(writes);
}

async function restoreZones(writes) {
    endEdit();
    // Every slot is about to be rewritten; earlier unconfirmed saves would only fight the restore
    clearPending();
    renderZoneList();
    emit('zones');
    setBusy(true);
    const topic = state.device;
    const name = state.deviceName;
    const errors = [];
    const onError = d => errors.push((d && d.error) || 'Unknown error');
    state.socket.on('command_error', onError);

    const finish = (text, ok) => {
        statusLine.textContent = text;
        toast(text, ok ? 'success' : 'error', ok ? 5000 : 8000);
    };
    // Send one area at a time; returns why it had to stop, or null
    const send = async (list, label) => {
        for (let i = 0; i < list.length; i++) {
            if (state.device !== topic) return 'a different switch was selected';
            if (!state.socket.connected) return 'the connection to the addon dropped';
            if (errors.length) return `the switch rejected a write (${errors[0]})`;
            const w = list[i];
            state.socket.emit('update_parameter', { param: w.category, value: { [w.area]: w.payload } });
            statusLine.textContent = `${label} ${i + 1}/${list.length}`;
            await sleep(RESTORE_GAP_MS);
        }
        return errors.length ? `the switch rejected a write (${errors[0]})` : null;
    };
    const slotName = w => `${GROUP_NAMES[w.category]} area ${w.area.slice(4)}`;
    const current = w => state.zones[w.category][w.area];
    const matches = w => sameZone(current(w), w.zone, ROUNDING);
    const isStayMirror = w => w.category === 'mmwave_stay_areas' && !!w.zone && isMirroredX(current(w), w.zone, ROUNDING);
    const started = Date.now();

    const landed = w => matches(w) || isStayMirror(w);

    // Re-read the switch until every slot in `list` has held the same value on two reads in a row
    // and has landed, or (after APPLY_MS) has stayed put without landing, or time runs out.
    // Returns the zone types that never reported. Firmware 1.02 takes ~6 s to apply a zone write,
    // and after a stay write it briefly reports the raw value before the mirrored one, so a single
    // read can be misleading.
    const settle = async (list, timeoutMs = 45000) => {
        const sentAt = Date.now();
        const deadline = sentAt + timeoutMs;
        let prev = null;
        await sleep(3000);
        while (true) {
            statusLine.textContent = `Checking the switch… (${Math.round((Date.now() - started) / 1000)} s)`;
            const missing = await readZonesFromSwitch();
            if (state.device !== topic) return [];
            const snap = list.map(w => JSON.stringify(current(w)));
            const steady = prev !== null && snap.every((v, i) => v === prev[i]);
            if (!missing.length && steady && (list.every(landed) || Date.now() - sentAt > APPLY_MS)) return [];
            if (Date.now() > deadline) return missing;
            prev = snap;
        }
    };
    const flipX = p => ({ ...p, width_min: -p.width_max, width_max: -p.width_min });

    try {
        let todo = writes.map(w => ({ ...w, payload: w.zone ? zoneToDevicePayload(w.category, w.zone) : EMPTY_AREA }));
        let missing = [];
        let flipped = false;
        for (let pass = 1; pass <= RESTORE_PASSES && todo.length; pass++) {
            const stopped = await send(todo, pass === 1 ? 'Restoring zones…' : 'Sending again what didn\'t land…');
            if (stopped) return finish(`Restore stopped because ${stopped}. Some zones may not have been written.`, false);
            missing = await settle(todo);
            if (missing.length || state.device !== topic) break;
            // Stay zones stored mirrored (the firmware bug) go again flipped; anything the switch
            // dropped goes again as it was
            todo = todo.filter(w => !matches(w)).map(w => {
                if (!isStayMirror(w)) return w;
                flipped = true;
                return { ...w, payload: flipX(w.payload) };
            });
        }

        if (state.device !== topic) return finish('Restore stopped because a different switch was selected.', false);
        if (missing.length) {
            const names = missing.map(c => GROUP_NAMES[c]).join(', ');
            return finish(`Zones were sent, but the switch didn't report its ${names} zones back, so the restore couldn't be checked. Press Sync to look.`, false);
        }
        const wrong = writes.filter(w => !matches(w));
        if (wrong.length) return finish(`Restore finished, but ${plural(wrong.length, 'slot')} ${wrong.length === 1 ? 'doesn\'t' : 'don\'t'} match the backup: ${wrong.map(slotName).join(', ')}.`, false);

        let text = `Restored and checked ${writes.length} zone slots on ${name}.`;
        if (flipped) text += ' This switch mirrors stay zones, so they were re-sent flipped. Turning on "Correct mirrored stay zones" makes manual edits land right too.';
        finish(text, true);
    } finally {
        state.socket.off('command_error', onError);
        setBusy(false);
    }
}

export function initBackup() {
    btnExport.addEventListener('click', exportZones);
    btnImport.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', onFileChosen);
}
