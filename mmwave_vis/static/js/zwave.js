// Z-Wave packet capture (diagnostic for VZW32-SN testers, #42), opened from the ⋮ menu.

import { state } from './state.js';
import { $, togglePopover } from './ui.js';

const panel = $('#zwavePanel');
const statusBox = $('#zwaveStatus');
const devices = $('#zwaveDevices');
const btnStart = $('#zwaveStart');
const btnStop = $('#zwaveStop');
const download = $('#zwaveDownload');

const duration = s => Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');

export function openZwave() {
    togglePopover($('#menuBtn'), panel, () => state.socket.emit('zwave_capture_status'));
}

function onStatus(st) {
    const running = ['starting', 'capturing', 'stopping'].includes(st.state);
    btnStart.disabled = running;
    btnStart.textContent = st.has_data ? 'Start new capture' : 'Start';
    btnStop.disabled = !['starting', 'capturing'].includes(st.state);
    download.classList.toggle('off', !st.has_data);
    $('#menuBtn').classList.toggle('capturing', running);

    const counts = `${st.lines.toLocaleString()} lines, ${st.proprietary} Manufacturer Proprietary`;
    let text;
    switch (st.state) {
        case 'starting':  text = 'Connecting to Z-Wave JS…'; break;
        case 'capturing': text = `Capturing ${duration(st.elapsed)} / ${duration(st.max_duration)} (${counts})`; break;
        case 'stopping':  text = 'Stopping…'; break;
        case 'stopped':   text = `Finished after ${duration(st.elapsed)} (${counts})`; break;
        case 'error':     text = `Error: ${st.error}` + (st.lines ? ` (${counts})` : ''); break;
        default:          text = 'Idle.';
    }
    if (st.note) text += ' ' + st.note;
    statusBox.textContent = text;
    statusBox.className = 'zwave-status' + (st.state === 'error' ? ' error' : st.state === 'capturing' ? ' live' : '');

    if (st.devices && st.devices.length) {
        devices.textContent = 'Inovelli nodes: ' + st.devices.map(d =>
            `node ${d.node_id ?? '?'} ${d.model}${d.firmware ? ' fw ' + d.firmware : ''}`).join(', ');
    } else {
        devices.textContent = st.entry_title ? 'No Inovelli devices found on this Z-Wave network.' : '';
    }
}

export function initZwave(ingress) {
    download.href = ingress + '/zwave_capture.log';
    $('#zwaveClose').addEventListener('click', () => togglePopover($('#menuBtn'), panel));
    btnStart.addEventListener('click', () => state.socket.emit('zwave_capture_start'));
    btnStop.addEventListener('click', () => state.socket.emit('zwave_capture_stop'));
    state.socket.on('zwave_capture_status', onStatus);
}
