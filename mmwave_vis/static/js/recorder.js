// Movement recorder: three slots of recorded target positions that can be
// turned into a zone while editing.

import { state, emit } from './state.js';
import { $, h, toast, setText } from './ui.js';

const MAX_POINTS = 5000;

export const slots = [0, 1, 2].map(() => ({ points: [], bounds: null }));
let selected = 0;
let recording = false;

const button = $('#btnRecord');
const status = $('#recStatus');
const padInput = $('#recordingPadding');

export function padding() {
    return parseInt(padInput.value, 10) || 0;
}

function renderSlots() {
    $('#recSlots').replaceChildren(...slots.map((slot, i) => h('button', {
        type: 'button',
        'aria-pressed': String(i === selected),
        disabled: recording && i !== selected,
        onclick: () => { selected = i; renderSlots(); },
    }, String(i + 1), slot.points.length ? h('span', { class: 'count' }, slot.points.length) : null)));

    const parts = slots.map((s, i) => s.points.length ? `Slot ${i + 1}: ${s.points.length} pts` : null).filter(Boolean);
    setText($('#recSummary'), parts.length ? parts.join(' · ') : 'No recordings yet.');
}

function start() {
    recording = true;
    slots[selected] = { points: [], bounds: null };
    button.textContent = 'Stop recording';
    button.classList.add('recording');
    setText(status, '0 pts');
    renderSlots();
    emit('recording');
}

function stop() {
    recording = false;
    button.textContent = 'Record';
    button.classList.remove('recording');
    const n = slots[selected].points.length;
    setText(status, n ? `Slot ${selected + 1}: ${n} pts` : 'Nothing recorded');
    renderSlots();
}

export function stopRecording() {
    if (recording) stop();
}

// Called for every target packet
export function record(targets) {
    if (!recording) return;
    const slot = slots[selected];
    if (slot.points.length >= MAX_POINTS) return;
    for (const t of targets) {
        if (slot.points.length >= MAX_POINTS) break;
        slot.points.push({ x: t.x, y: t.y, z: t.z });
        const b = slot.bounds;
        if (!b) {
            slot.bounds = { x_min: t.x, x_max: t.x, y_min: t.y, y_max: t.y, z_min: t.z, z_max: t.z };
        } else {
            if (t.x < b.x_min) b.x_min = t.x;
            if (t.x > b.x_max) b.x_max = t.x;
            if (t.y < b.y_min) b.y_min = t.y;
            if (t.y > b.y_max) b.y_max = t.y;
            if (t.z < b.z_min) b.z_min = t.z;
            if (t.z > b.z_max) b.z_max = t.z;
        }
    }
    const n = slot.points.length;
    setText(status, `${n} pts${n >= MAX_POINTS ? ' (full)' : ''}`);
    emit('recording-grew');
}

// Fit the zone being edited around the selected slot, plus padding
export function applyToDraft() {
    const slot = slots[selected];
    if (!slot.bounds) {
        toast(`Slot ${selected + 1} has nothing recorded yet.`, 'error');
        return false;
    }
    if (!state.edit) {
        toast('Start editing a zone first, then use the recording.', 'error');
        return false;
    }
    const pad = padding();
    const b = slot.bounds;
    Object.assign(state.edit.draft, {
        x_min: b.x_min - pad, x_max: b.x_max + pad,
        y_min: b.y_min - pad, y_max: b.y_max + pad,
        z_min: b.z_min - pad, z_max: b.z_max + pad,
    });
    return true;
}

function clearSlot() {
    if (recording) return;
    slots[selected] = { points: [], bounds: null };
    setText(status, '');
    renderSlots();
    emit('recording');
}

export function initRecorder() {
    button.addEventListener('click', () => recording ? stop() : start());
    $('#btnClearSlot').addEventListener('click', clearSlot);
    padInput.addEventListener('input', () => emit('recording-padding'));   // only the outlines move
    renderSlots();
}
