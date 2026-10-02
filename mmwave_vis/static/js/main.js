// Page entry point: socket wiring, header and status, notices, readouts,
// the targets table and tabs. The map, zones, recorder, backup, display
// settings and Z-Wave capture live in their own modules.

import { state, on, emptyZones, freshReportTimes, zoneName, ZONE_TYPES } from './state.js';
import * as prefs from './prefs.js';
import { $, $$, h, setText, num, toast, setNotice, clearNotice, bindPopover, closePopover, confirmAction, downloadBlob, fileSafe } from './ui.js';
import { Radar } from './radar.js';
import * as zones from './zones.js';
import * as recorder from './recorder.js';
import { initBackup } from './backup.js';
import * as display from './display.js';
import { initZwave, openZwave } from './zwave.js';

const ingress = document.body.dataset.ingress || '';
const socket = io({ path: ingress + '/socket.io' });
state.socket = socket;
state.stack = (document.body.className.match(/stack-(\w+)/) || [])[1] || null;

const deviceSelect = $('#deviceSelect');
const mapEl = $('#map');
const wide = window.matchMedia('(min-width: 901px)');
const HISTORY_LENGTH = 15;
let targetHistory = {};

// --- Map -------------------------------------------------------------------

const coords = $('#coords');
const radar = new Radar($('#radar'), {
    onDraft: () => zones.draftFromMap(),
    onZoneClick: (category, area) => zones.editFromMap(category, area),
    onLayout: (layout, final) => display.layoutFromMap(layout, final),
    onView: (range, final) => display.rangeFromMap(range, final),
    onPointer: s => setText(coords, s ? `x ${num(s[0])} · y ${num(s[1])} cm` : ''),
});

on('zones', () => radar.setZones(zones.displayZones(), zones.pendingKeys()));
on('draft', () => radar.draftChanged());
on('recording', () => radar.setRecording(recorder.slots, recorder.padding()));
on('recording-grew', () => radar.recordingGrew());
on('recording-padding', () => radar.setRecordingPad(recorder.padding()));
on('arrange', setArranging);

on('edit', () => {
    const editing = !!state.edit;
    const started = editing && !mapEl.classList.contains('editing');
    radar.setEdit(state.edit);
    mapEl.classList.toggle('editing', editing);
    $('#editBar').hidden = !editing;
    if (editing) setText($('#editBarName'), zoneName(state.edit.category, state.edit.area));
    // On a phone the editor is below the map; bring the map up so the zone can be dragged
    if (started && !wide.matches) mapEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
});

on('show-editor', () => {
    selectTab('tab-zones');
    if (wide.matches) requestAnimationFrame(() => $('#zoneEditor').scrollIntoView({ block: 'nearest', behavior: 'smooth' }));
});

function setArranging(arrange) {
    if (arrange && state.edit) {
        toast('Save or cancel the zone you\'re editing first.', 'error');
        return;
    }
    state.arranging = arrange;
    radar.setArranging(arrange);
    $('#arrangeBar').hidden = !arrange;
    $('#btnArrange').textContent = arrange ? 'Done' : 'Arrange on map';
    $('#btnArrange').classList.toggle('primary', arrange);
    if (arrange && !wide.matches) mapEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

$('#arrangeDone').addEventListener('click', () => setArranging(false));
$('#editBarSave').addEventListener('click', () => zones.saveEdit());
$('#editBarCancel').addEventListener('click', () => zones.cancelEdit());
$('#mapFit').addEventListener('click', () => display.fitZones());
$('#mapFull').addEventListener('click', () => display.fullRange());
$('#zoomIn').addEventListener('click', () => radar.zoomBy(1.4));
$('#zoomOut').addEventListener('click', () => radar.zoomBy(1 / 1.4));
$('#btnUseRecording').addEventListener('click', () => {
    if (recorder.applyToDraft()) {
        zones.draftFromMap();
        radar.draftChanged();
    }
});
document.addEventListener('keydown', e => {
    // ui.js marks the Escape that closed a popover; an open dialog takes its own Escape
    if (e.key === 'Escape' && state.arranging && !e.defaultPrevented && !document.querySelector('dialog[open]')) setArranging(false);
});

// --- Connection status -------------------------------------------------------

const conn = { ws: 'connecting', backend: null, error: '', wasDown: false };
let lastPacket = 0;
const clock = new Intl.DateTimeFormat([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });

function markPacket() {
    lastPacket = Date.now();
}

function packetClock() {
    const t = new Date(lastPacket);
    return clock.format(t) + '.' + String(t.getMilliseconds()).padStart(3, '0');
}

const backendName = () => state.stack === 'zha' ? 'Home Assistant' : 'MQTT broker';

function ago(seconds) {
    return seconds < 60 ? `${Math.round(seconds)} s` : `${Math.floor(seconds / 60)} min`;
}

function renderStatus() {
    let dot = '', text;
    const age = lastPacket ? (Date.now() - lastPacket) / 1000 : null;
    if (conn.ws !== 'connected') {
        dot = conn.ws === 'connecting' ? 'pending' : 'bad';
        text = conn.ws === 'connecting' ? 'Connecting…' : 'Offline';
    } else if (conn.backend === false) {
        dot = 'bad';
        text = state.stack === 'zha' ? 'HA offline' : 'MQTT offline';
    } else if (!state.device) {
        text = 'Connected';
    } else if (age === null) {
        dot = 'warn';
        text = 'Waiting for data';
    } else if (age <= 5) {
        dot = age > 2 ? 'warn' : 'ok';
        text = `Live · ${age.toFixed(1)} s`;
    } else {
        // Switches only report while something moves, so a quiet switch isn't a fault
        text = `Updated ${ago(age)} ago`;
    }
    const dotEl = $('#statusDot');
    const cls = 'dot ' + dot;
    if (dotEl.className !== cls) dotEl.className = cls;
    setText($('#statusText'), text);

    if ($('#statusPop').hidden) return;
    const serverOk = conn.ws === 'connected';
    $('#popServerDot').className = 'dot ' + (serverOk ? 'ok' : conn.ws === 'connecting' ? 'pending' : 'bad');
    setText($('#popServer'), serverOk ? 'Connected' : conn.ws === 'connecting' ? 'Connecting' : 'Disconnected');
    setText($('#popBackendLabel'), backendName());
    $('#popBackendDot').className = 'dot ' + (conn.backend === null ? '' : conn.backend ? 'ok' : 'bad');
    setText($('#popBackend'), conn.backend === null ? 'Unknown' : conn.backend ? 'Connected' : 'Disconnected' + (conn.error ? ` (${conn.error})` : ''));
    setText($('#popStack'), state.stack === 'zha' ? 'ZHA' : state.stack === 'z2m' ? 'Zigbee2MQTT' : 'Unknown');
    setText($('#popPacket'), lastPacket ? `${packetClock()} (${age.toFixed(1)} s ago)` : 'None yet');
}
setInterval(renderStatus, 200);

function applyStack(stack) {
    state.stack = stack;
    document.body.classList.remove('stack-z2m', 'stack-zha');
    if (stack) document.body.classList.add('stack-' + stack);
    renderStatus();
}

// --- Readouts and targets table --------------------------------------------

function setOccupancy(value) {
    const el = $('#occupancy');
    el.dataset.state = value === null ? 'unknown' : value ? 'on' : 'off';
    setText($('#occupancyText'), value === null ? 'Waiting for data' : value ? 'Occupied' : 'Clear');
}

function renderAreaChips() {
    $$('#areaChips .chip').forEach((chip, i) => {
        chip.classList.toggle('on', state.areaOccupied[i]);
        chip.title = `Area ${i + 1} ${state.areaOccupied[i] ? 'occupied' : 'clear'}`;
    });
    radar.setOccupied(state.areaOccupied);
}

const tableBody = $('#targetRows');
let tableKey = '';

function emptyRow(text) {
    tableKey = text;
    tableBody.replaceChildren(h('tr', null, h('td', { colspan: 5, class: 'empty' }, text)));
}

function renderTable(list) {
    const key = JSON.stringify(list);
    if (key === tableKey) return;
    tableKey = key;
    if (!list.length) { emptyRow('No one in view'); return; }
    tableBody.replaceChildren(...list.map(t => {
        let cls = 'move-still', text = 'Still';
        if (t.dop > 10) { cls = 'move-away'; text = `Moving away (${num(t.dop)})`; }
        else if (t.dop < -10) { cls = 'move-toward'; text = `Approaching (${num(t.dop)})`; }
        return h('tr', null,
            h('td', null, h('strong', null, String(t.id))),
            h('td', null, `${num(t.x)} cm`), h('td', null, `${num(t.y)} cm`), h('td', null, `${num(t.z)} cm`),
            h('td', { class: cls }, text));
    }));
}

// --- Device selection ----------------------------------------------------------

let fitAfterLayout = false;
// After a reconnect the addon has forgotten which switch this page watches. Re-subscribe once
// a device list includes it: right after an addon restart the list fills in a switch at a time.
let resubscribe = false;

function selectDevice(topic, name) {
    state.device = topic;
    state.deviceName = name || topic;
    if (topic) prefs.set('lastDevice', topic);
    socket.emit('change_device', topic);
    socket.emit('force_sync');
    resetDeviceView();
}

function resetDeviceView() {
    lastPacket = 0;
    targetHistory = {};
    state.zoneReportAt = freshReportTimes();
    state.areaOccupied = [false, false, false, false];
    state.lastCommandId = null;
    setOccupancy(null);
    setText($('#illuminance'), '–');
    setText($('#targetCount'), '0');
    renderAreaChips();
    recorder.stopRecording();
    if (state.arranging) setArranging(false);
    zones.resetZones(emptyZones());
    radar.setTargets([], {});
    emptyRow('No targets yet');
    for (const key of ['targetReport', 'quirk', 'binding', 'stayFlip']) clearNotice(key);
    fitAfterLayout = true;
    display.layoutFromServer(null);     // the addon sends this switch's layout right after change_device
    renderStatus();
}

deviceSelect.addEventListener('change', () => {
    const opt = deviceSelect.options[deviceSelect.selectedIndex];
    resubscribe = false;
    selectDevice(deviceSelect.value, opt ? opt.textContent : '');
});

$('#btnSync').addEventListener('click', () => {
    if (state.edit) zones.endEdit();
    socket.emit('request_devices');
    socket.emit('force_sync');
    toast(state.device ? 'Asking the switch for its settings and zones…' : 'Refreshing the list of switches…');
});

// --- Settings sent to the switch -----------------------------------------------

// On/off switches carry the switch's own values for each position in data-on / data-off
const paramValue = input => input.type === 'checkbox' ? input.dataset[input.checked ? 'on' : 'off'] : input.value;

function showParam(input, value) {
    if (input.type === 'checkbox') input.checked = value === input.dataset.on;
    else if (document.activeElement !== input) input.value = value;   // don't overwrite a field being typed in
}

const paramInputs = $$('[data-param]');
paramInputs.forEach(input => {
    input.addEventListener('change', () => {
        const value = paramValue(input);
        socket.emit('update_parameter', { param: input.dataset.param, value });
        if (input.dataset.param === 'mmWaveTargetInfoReport') targetReportNotice(value);
    });
});

function enableTargetReporting() {
    $('#mmWaveTargetInfoReport').checked = true;
    socket.emit('update_parameter', { param: 'mmWaveTargetInfoReport', value: 'Enable' });
    clearNotice('targetReport');
}

function targetReportNotice(value) {
    if (value === 'Enable') clearNotice('targetReport');
    else setNotice('targetReport', {
        tone: 'warning', title: 'Target reporting is off,', text: 'so people won\'t show up on the map.',
        action: { label: 'Turn on', onClick: enableTargetReporting },
    });
}

const COMMANDS = {
    1: { done: 'Scanning for interference…' },
    3: { ask: 'Clear every interference zone on the switch?', label: 'Clear', done: 'Clearing interference zones…' },
    4: { ask: 'Reset the detection areas to the switch defaults? Your detection zones will be replaced.', label: 'Reset', done: 'Resetting detection areas…' },
    5: { ask: 'Clear every stay area on the switch?', label: 'Clear', done: 'Clearing stay areas…' },
};

$$('[data-command]').forEach(btn => btn.addEventListener('click', async () => {
    const id = Number(btn.dataset.command);
    const cmd = COMMANDS[id];
    if (!state.device) { toast('Choose a switch first.', 'error'); return; }
    if (cmd.ask && !await confirmAction(cmd.ask, { confirm: cmd.label, danger: true })) return;
    socket.emit('send_command', id);
    if (id === 1 || id === 3) {
        state.lastCommandId = id;
        state.lastCommandAt = Date.now();
    }
    toast(cmd.done);
}));

// --- Tabs ------------------------------------------------------------------------

const tabs = $$('.tab');

function selectTab(id) {
    for (const tab of tabs) {
        const selected = tab.id === id;
        tab.setAttribute('aria-selected', String(selected));
        tab.tabIndex = selected ? 0 : -1;
        $('#' + tab.getAttribute('aria-controls')).hidden = !selected;
    }
    prefs.set('activeTab', id);
}

tabs.forEach((tab, i) => {
    tab.addEventListener('click', () => selectTab(tab.id));
    tab.addEventListener('keydown', e => {
        if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
        const next = tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
        selectTab(next.id);
        next.focus();
    });
});
selectTab(tabs.some(t => t.id === prefs.get('activeTab')) ? prefs.get('activeTab') : 'tab-zones');

// ⓘ buttons open a short explanation underneath (tooltips don't work on touch screens)
$$('[data-info]').forEach(btn => btn.addEventListener('click', () => {
    const panel = $('#' + btn.dataset.info);
    panel.hidden = !panel.hidden;
    btn.setAttribute('aria-expanded', String(!panel.hidden));
}));

// --- Header menus ----------------------------------------------------------------

bindPopover($('#statusBtn'), $('#statusPop'), renderStatus);
bindPopover($('#menuBtn'), $('#moreMenu'));

$('#menuZwave').addEventListener('click', e => {
    e.stopPropagation();
    openZwave();
});

$('#menuSaveImage').addEventListener('click', async e => {
    e.stopPropagation();
    closePopover();
    try {
        const bg = getComputedStyle(document.documentElement).getPropertyValue('--surface').trim() || '#1c1c1c';
        const blob = await radar.toPNG(bg);
        downloadBlob(blob, `mmwave-map-${fileSafe(state.deviceName, 'map')}-${new Date().toISOString().slice(0, 10)}.png`);
    } catch (err) {
        console.warn('Map image export failed', err);
        toast('Couldn\'t save the map image.', 'error');
    }
});

// --- Socket events -------------------------------------------------------------------

socket.on('connect', () => {
    conn.ws = 'connected';
    clearNotice('server');
    if (conn.wasDown) toast('Reconnected to the addon.', 'success');
    conn.wasDown = false;
    resubscribe = !!state.device;
    socket.emit('request_devices');
    renderStatus();
});

socket.on('disconnect', () => {
    conn.ws = 'disconnected';
    conn.wasDown = true;
    setNotice('server', { tone: 'danger', title: 'Lost the connection to the addon.', text: 'Reconnecting…' });
    renderStatus();
});

socket.on('connect_error', () => {
    conn.ws = 'disconnected';
    conn.wasDown = true;
    setNotice('server', { tone: 'danger', title: 'Can\'t reach the addon.', text: 'Retrying…' });
    renderStatus();
});

socket.on('mqtt_status', data => {
    conn.backend = !!data.connected;
    conn.error = data.error || '';
    if (data.connected) clearNotice('backend');
    else setNotice('backend', { tone: 'danger', title: `${backendName()} is disconnected.`, text: data.error || '' });
    renderStatus();
});

socket.on('stack_info', data => applyStack(data.stack));

socket.on('zha_device_info', data => {
    if (state.stack === 'zha' && data.quirk_ok === false) {
        setNotice('quirk', {
            tone: 'danger',
            title: 'The custom ZHA quirk isn\'t loaded.',
            text: 'Live targets and zone commands need the Inovelli VZM32-SN quirk. After installing it, reconfigure the device in ZHA and press Sync.',
            link: { href: 'https://github.com/nickduvall921/mmwave_vis/blob/main/ZHADOC.md', label: 'Setup guide' },
        });
    } else {
        clearNotice('quirk');
    }
});

socket.on('zha_binding_warning', data => {
    if (state.stack === 'zha' && data.show) {
        setNotice('binding', {
            tone: 'warning',
            title: 'No data from this switch yet.',
            text: 'The mmWave cluster (0xFC32) binding may be missing. In ZHA, open the device, choose Reconfigure, then press Sync.',
        });
    } else {
        clearNotice('binding');
    }
});

socket.on('command_error', data => toast((data && data.error) || 'Something went wrong.', 'error', 5000));
socket.on('command_ack', data => console.log('Command acknowledged:', data));

socket.on('device_list', devices => {
    if (!Array.isArray(devices)) return;
    const present = !!state.device && devices.some(d => d.topic === state.device);
    deviceSelect.replaceChildren(
        h('option', { value: '', disabled: true }, devices.length ? 'Choose a switch' : 'No switches found'),
        ...devices.map(d => h('option', { value: d.topic }, d.friendly_name)),
        // Keep showing the switch this page is on while the addon hasn't (re)discovered it
        state.device && !present ? h('option', { value: state.device }, `${state.deviceName} (not found)`) : null);
    deviceSelect.value = state.device;
    for (const d of devices) if (d.topic === state.device) state.deviceName = d.friendly_name;

    if (state.stack === 'zha' && devices.length === 0) {
        setNotice('zhaSetup', {
            tone: 'info',
            title: 'No switches found in ZHA yet.',
            text: 'Make sure the VZM32-SN is paired in ZHA and has been reconfigured (Device, then Reconfigure) so the mmWave binding is set up.',
        });
    } else {
        clearNotice('zhaSetup');
    }

    if (resubscribe && present) {
        resubscribe = false;
        socket.emit('change_device', state.device);
        socket.emit('force_sync');
    }

    // Pick up where this browser left off, or the only switch there is when it has no memory
    // of one. Not on ZHA with several switches: the addon watches one ZHA switch for every
    // browser, so opening the page somewhere else would take live data away from this one.
    if (!state.device && devices.length && !(state.stack === 'zha' && devices.length > 1)) {
        const last = prefs.get('lastDevice');
        const pick = devices.find(d => d.topic === last) || (!last && devices.length === 1 ? devices[0] : null);
        if (pick) {
            deviceSelect.value = pick.topic;
            selectDevice(pick.topic, pick.friendly_name);
        }
    }
});

socket.on('device_config', msg => {
    if (!msg || !msg.topic || !msg.payload || msg.topic !== state.device) return;
    const c = msg.payload;
    markPacket();
    zones.applyConfig(c);

    if ('occupancy' in c) setOccupancy(c.occupancy === true);
    if ('illuminance' in c) setText($('#illuminance'), `${c.illuminance} lx`);
    let areas = false;
    for (let i = 0; i < 4; i++) {
        const key = `mmwave_area${i + 1}_occupancy`;
        if (key in c) {
            state.areaOccupied[i] = c[key] === true || c[key] === 'ON';
            areas = true;
        }
    }
    if (areas) renderAreaChips();

    if ('mmWaveTargetInfoReport' in c) targetReportNotice(c.mmWaveTargetInfoReport);

    for (const input of paramInputs) {
        if (input.dataset.param in c) showParam(input, c[input.dataset.param]);
    }
});

// detection_zones / interference_zones / stay_zones
for (const { group, category } of ZONE_TYPES) {
    socket.on(`${group}_zones`, msg => {
        if (!msg || !msg.topic || !msg.payload || msg.topic !== state.device) return;
        zones.applyZoneList(category, msg.payload);
    });
}

socket.on('new_data', msg => {
    if (!msg || !msg.topic || !msg.payload || msg.topic !== state.device) return;
    const all = Array.isArray(msg.payload.targets) ? msg.payload.targets : [];
    markPacket();
    clearNotice('binding');

    // Targets with missing coordinates can't be drawn
    const targets = all.filter(t => !Number.isNaN(Number(t.x)) && !Number.isNaN(Number(t.y)) && !Number.isNaN(Number(t.z)));
    const ids = new Set(targets.map(t => String(t.id)));
    for (const id of Object.keys(targetHistory)) if (!ids.has(id)) delete targetHistory[id];
    for (const t of targets) {
        const trail = targetHistory[t.id] || (targetHistory[t.id] = []);
        trail.push({ x: t.x, y: t.y });
        if (trail.length > HISTORY_LENGTH) trail.shift();
    }
    recorder.record(targets);
    radar.setTargets(targets, targetHistory);
    setText($('#targetCount'), String(all.length));
    renderTable(all);
});

socket.on('layout', msg => {
    if (!msg || msg.topic !== state.device) return;
    display.layoutFromServer(msg.layout);
    if (fitAfterLayout) {
        fitAfterLayout = false;
        // The saved view is shared by every switch; if most of this one's area is off screen
        // (it sits elsewhere in its room, faces another way, or the last switch did), show it all
        if (overlap(radar.fullRange(), radar.visibleRange()) < 0.5) display.fullRange();
    }
});

// How much of box `a` lies inside box `b`, 0..1
function overlap(a, b) {
    const w = Math.min(a.xMax, b.xMax) - Math.max(a.xMin, b.xMin);
    const h = Math.min(a.yMax, b.yMax) - Math.max(a.yMin, b.yMin);
    const area = (a.xMax - a.xMin) * (a.yMax - a.yMin);
    return w > 0 && h > 0 && area > 0 ? (w * h) / area : 0;
}

// --- Start ---------------------------------------------------------------------------

zones.initZones();
recorder.initRecorder();
initBackup();
display.initDisplay(radar);
initZwave(ingress);
radar.setZones(zones.displayZones(), zones.pendingKeys());
radar.setRecording(recorder.slots, recorder.padding());
renderStatus();
