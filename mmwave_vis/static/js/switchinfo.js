// The selected switch's firmware, mmWave module version, Zigbee signal and
// firmware updates (top of the Switch settings tab, and a line in the status popover).

import { state, emit } from './state.js';
import { $, h, setText, toast, copyText, shortDateTime } from './ui.js';

const WEAK_LQI = 80;

export function deviceInfoFromServer(info) {
    if (!info || info.topic !== state.device) return;
    state.deviceInfo = info;
    render();
    emit('device-info');
}

export function clearDeviceInfo() {
    state.deviceInfo = null;
    render();
}

function firmwareText(info) {
    const fw = info.firmware || {};
    if (fw.build && fw.ota) return `${fw.build} (${fw.ota})`;
    return fw.build || fw.ota || 'Not reported';
}

function signalText(info) {
    const { lqi, rssi } = info.link || {};
    if (lqi == null && rssi == null) return null;
    const parts = [];
    if (lqi != null) parts.push(`LQI ${lqi}`);
    if (rssi != null) parts.push(`RSSI ${rssi} dBm`);
    return parts.join(' · ');
}

function row(label, value, extra = null) {
    return [h('dt', null, label), h('dd', null, value, extra)];
}

function render() {
    const root = $('#switchInfo');
    const info = state.deviceInfo && state.deviceInfo.topic === state.device ? state.deviceInfo : null;
    setText($('#popFirmware'), info ? firmwareText(info) : '–');
    if (!state.device) { root.replaceChildren(h('p', { class: 'hint' }, 'Choose a switch.')); return; }
    if (!info) { root.replaceChildren(h('p', { class: 'hint' }, 'Reading the switch\'s details…')); return; }

    const items = [];
    items.push(...row('Firmware', firmwareText(info)));
    if (info.mmwave_version) {
        items.push(...row('mmWave module', h('span', { title: info.mmwave_version.raw }, info.mmwave_version.text)));
    }
    const signal = signalText(info);
    if (signal) {
        const weak = info.link.lqi != null && info.link.lqi < WEAK_LQI;
        items.push(...row('Signal', h('span', { class: weak ? 'warn-text' : null }, signal)));
    }
    if (info.last_seen) items.push(...row('Last seen', shortDateTime(info.last_seen * 1000)));
    const up = info.update;
    if (up && up.latest) {
        items.push(...row('Update', up.in_progress ? 'Installing…'
            : up.available ? h('strong', { class: 'warn-text' }, `${up.latest} available`) : 'Up to date'));
    }
    const occ = info.entities && info.entities.occupancy;
    if (occ) {
        items.push(...row('Occupancy entity', h('code', null, occ),
            h('button', { class: 'btn link', type: 'button', onclick: async () => {
                if (await copyText(occ)) toast(`Copied ${occ}.`, 'success', 2500);
            } }, 'Copy')));
    }

    const notes = [];
    if (info.link && info.link.lqi != null && info.link.lqi < WEAK_LQI) {
        notes.push(h('p', { class: 'hint' }, 'The Zigbee signal is weak, which can make tracking choppy. A mains-powered Zigbee device between the switch and your coordinator helps.'));
    }
    if (!info.ha_available) {
        notes.push(h('p', { class: 'hint' }, 'Running without Home Assistant, so update and entity details aren\'t available.'));
    } else if (info.ha_error) {
        notes.push(h('p', { class: 'hint' }, `Couldn't read Home Assistant's device list: ${info.ha_error}`));
    }

    const links = [];
    if (info.ha_device_id) {
        links.push(h('a', { class: 'btn small', href: `/config/devices/device/${encodeURIComponent(info.ha_device_id)}`, target: '_top' }, 'Open in Home Assistant'));
    }
    links.push(h('button', { class: 'btn small ghost', type: 'button', onclick: refresh }, 'Refresh'));

    root.replaceChildren(h('dl', { class: 'facts' }, ...items), ...notes, h('div', { class: 'button-row' }, ...links));
}

function refresh() {
    if (!state.device) return;
    state.socket.emit('refresh_device_info', state.device);
    toast('Reading the switch\'s details again…', 'info', 2500);
}

export function initSwitchInfo() {
    render();
}
