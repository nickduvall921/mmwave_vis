// History tab: the heat map (where people spent time), the timeline of occupancy
// and light changes, and replaying what the radar saw around one of them.
// The addon records it in the background (off until turned on here).

import { state, on, emit, zoneName } from './state.js';
import * as prefs from './prefs.js';
import { $, $$, h, setText, toast, confirmAction, plural, clockTime, dayLabel, shortDateTime, duration } from './ui.js';

const RANGES = { '10m': 600, '1h': 3600, '6h': 6 * 3600, '24h': 86400, '7d': 7 * 86400 };
const LIVE_REFRESH_MS = 30000;
const TRAIL_MS = 4000;
const SPEEDS = [1, 4];

let radar = null;
let tabOpen = false;
let settings = { enabled: false, days: 30, available: true, error: null };
let stats = null;
let range = prefs.get('historyRange') in RANGES || prefs.get('historyRange') === 'custom' ? prefs.get('historyRange') : '1h';
let filter = 'on';
let events = [];
let heatTimer = 0;
let loadSeq = 0;
let replay = null;     // { clip, eventT, t, playing, speed, frame, last }

const socket = () => state.socket;

// --- Range ---------------------------------------------------------------------

function toLocalInput(ms) {
    const d = new Date(ms);
    const pad = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// The selected time range in unix seconds, or null if the custom one is unusable
function rangeTimes() {
    const now = Date.now() / 1000;
    if (range !== 'custom') return { from: now - RANGES[range], to: now };
    const from = Date.parse($('#heatFrom').value) / 1000;
    const to = Date.parse($('#heatTo').value) / 1000;
    if (!(from < to)) return null;
    return { from, to };
}

function renderRangeButtons() {
    $$('#heatRanges button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.range === range)));
    $('#heatCustom').hidden = range !== 'custom';
}

function setRange(next) {
    range = next;
    prefs.set('historyRange', next);
    if (next === 'custom' && !$('#heatFrom').value) {
        const now = Date.now();
        $('#heatFrom').value = toLocalInput(now - 86400000);
        $('#heatTo').value = toLocalInput(now);
    }
    renderRangeButtons();
    load();
}

// --- Loading ---------------------------------------------------------------------

const heatWanted = () => (tabOpen || prefs.getBool('heatAlways', false)) && !!state.device;

function load() {
    clearTimeout(heatTimer);
    const topic = state.device;
    if (!topic) { radar.setHeat(null); return; }
    const seq = ++loadSeq;
    socket().emit('history_stats', topic, ack => {
        if (seq !== loadSeq || topic !== state.device) return;
        stats = ack || null;
        renderStatus();
        const hasData = stats && (stats.first_t || stats.events);
        if (!hasData && !settings.enabled) {
            radar.setHeat(null);
            events = [];
            renderEvents();
            setText($('#heatSummary'), '');
            return;
        }
        const times = rangeTimes();
        if (!times) { setText($('#heatSummary'), 'Pick a start time before the end time.'); return; }
        if (heatWanted()) loadHeat(topic, times, seq);
        else radar.setHeat(null);
        if (tabOpen) loadEvents(topic, times, seq);
        if (range === '10m' || range === '1h') heatTimer = setTimeout(load, LIVE_REFRESH_MS);
    });
}

function loadHeat(topic, times, seq) {
    socket().emit('get_heatmap', { topic, from: times.from, to: times.to }, ack => {
        if (seq !== loadSeq || topic !== state.device) return;
        if (!ack || ack.error) {
            radar.setHeat(null);
            setText($('#heatSummary'), ack && ack.error ? ack.error : '');
            return;
        }
        radar.setHeat(heatWanted() ? ack : null);
        if (!ack.cells.length) {
            setText($('#heatSummary'), 'Nobody was seen in this range.');
        } else {
            const coarse = ack.res === 3600 ? ' Ranges reaching back more than two days are counted in whole hours.' : '';
            setText($('#heatSummary'), `${duration(ack.total)} of presence recorded, most in one spot ${duration(ack.max)}.${coarse}`);
        }
    });
}

function loadEvents(topic, times, seq) {
    socket().emit('get_events', { topic, from: times.from * 1000, to: times.to * 1000 + 60000 }, ack => {
        if (seq !== loadSeq || topic !== state.device) return;
        events = (ack && Array.isArray(ack.events)) ? ack.events : [];
        renderEvents();
    });
}

// --- Settings and status ------------------------------------------------------------

function renderSettings() {
    const box = $('#historyEnabled');
    box.checked = !!settings.enabled;
    box.disabled = settings.available === false;
    $('#historyDays').value = String(settings.days);
    $('#historyKeepRow').hidden = !settings.enabled;
    $('#historyView').classList.toggle('muted', !settings.enabled && !(stats && stats.first_t));
}

function renderStatus() {
    let text = '';
    if (settings.available === false || settings.error) {
        text = settings.error || 'History isn\'t available in this addon build.';
    } else if (!settings.enabled) {
        text = stats && (stats.first_t || stats.events) ? 'Recording is off. What was recorded before is still shown.' : '';
    } else if (state.device && stats && stats.has_ieee === false) {
        text = 'Waiting for Zigbee2MQTT to report this switch\'s IEEE address before recording it.';
    } else if (state.settings.mmWaveTargetInfoReport && state.settings.mmWaveTargetInfoReport !== 'Enable') {
        text = 'Target reporting is off on this switch, so occupancy changes are recorded but positions aren\'t. Turn it on in Switch settings for the heat map and replays.';
    } else if (stats && stats.first_t) {
        text = `Recording since ${shortDateTime(stats.first_t * 1000)}.`;
    } else if (settings.enabled) {
        text = 'Recording. The heat map fills in as people move around.';
    }
    if (stats && stats.bytes) text += ` History uses ${(stats.bytes / 1048576).toFixed(1)} MB.`;
    setText($('#historyStatus'), text.trim());
}

function applySettings(next) {
    if (!next || typeof next !== 'object') return;
    settings = { ...settings, ...next };
    renderSettings();
    renderStatus();
}

function saveSettings(change) {
    socket().emit('set_history_settings', change, ack => {
        if (!ack || ack.error) toast((ack && ack.error) || 'Couldn\'t change the history setting.', 'error', 6000);
        applySettings(ack);
        load();
    });
}

// --- Timeline --------------------------------------------------------------------------

function describe(e) {
    let title = '', detail = '';
    switch (e.kind) {
        case 'occupancy':
            title = e.value ? 'Occupied' : 'Clear';
            if (e.value && e.ntargets) detail = plural(e.ntargets, 'target');
            if (!e.value && e.last_detect_ms) detail = `${duration((e.t_ms - e.last_detect_ms) / 1000)} after the last target`;
            break;
        case 'area':
            title = `${zoneName('mmwave_detection_areas', `area${e.area}`)} ${e.value ? 'occupied' : 'clear'}`;
            break;
        case 'light':
            title = e.value ? 'Light on' : 'Light off';
            break;
        case 'reporting':
            title = e.value ? 'Target reporting on' : 'Target reporting off';
            break;
        default:
            title = e.kind;
    }
    if (e.offline) detail = (detail ? detail + ' · ' : '') + 'while the addon was off';
    return { title, detail };
}

const isTrigger = e => e.value && (e.kind === 'occupancy' || e.kind === 'light');

function renderEvents() {
    const root = $('#eventList');
    $$('#eventFilter button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.filter === filter)));
    const shown = events.filter(e => filter === 'all' || isTrigger(e));
    if (!shown.length) {
        root.replaceChildren(h('div', { class: 'empty-line' },
            events.length ? 'Nothing turned on in this range. Choose All to see every change.' : 'No changes recorded in this range.'));
        return;
    }
    const nodes = [];
    let day = '';
    for (const e of shown.slice(0, 300)) {
        const d = dayLabel(e.t_ms);
        if (d !== day) {
            day = d;
            nodes.push(h('div', { class: 'event-day' }, d));
        }
        const { title, detail } = describe(e);
        const playable = e.kind !== 'reporting';
        nodes.push(h(playable ? 'button' : 'div', {
            class: `event-row kind-${e.kind}${e.value ? ' on' : ''}${replay && replay.eventT === e.t_ms ? ' active' : ''}`,
            type: playable ? 'button' : null,
            title: playable ? 'Replay what the radar saw around this' : null,
            onclick: playable ? () => startReplay(e) : null,
        },
            h('span', { class: 'event-time num' }, clockTime(e.t_ms)),
            h('span', { class: 'event-text' }, h('span', null, title), detail ? h('span', { class: 'event-detail' }, detail) : null),
            playable ? h('span', { class: 'go' }, 'Replay') : null));
    }
    if (shown.length > 300) nodes.push(h('div', { class: 'empty-line' }, `Showing the latest 300 of ${shown.length}. Pick a shorter range to see the rest.`));
    root.replaceChildren(...nodes);
}

function onLiveEvent(msg) {
    if (!msg || msg.topic !== state.device || !msg.event) return;
    if (range === 'custom') return;
    events.unshift(msg.event);
    if (tabOpen) renderEvents();
}

// --- Replay ------------------------------------------------------------------------------

function frameIndexAt(frames, t) {
    let lo = 0, hi = frames.length - 1, best = -1;
    while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        if (frames[mid][0] <= t) { best = mid; lo = mid + 1; } else hi = mid - 1;
    }
    return best;
}

function drawReplay() {
    const r = replay;
    const frames = r.clip.frames;
    const i = frameIndexAt(frames, r.t);
    // A frame more than 2 s old means nobody was reported since
    const live = i >= 0 && r.t - frames[i][0] <= 2000 ? frames[i][1] : [];
    const targets = live.map(([id, x, y, z, dop]) => ({ id, x, y, z, dop }));
    const trails = {};
    for (let j = Math.max(0, i - 40); j <= i && j >= 0; j++) {
        if (r.t - frames[j][0] > TRAIL_MS) continue;
        for (const [id, x, y] of frames[j][1]) (trails[id] || (trails[id] = [])).push({ x, y });
    }
    radar.setTargets(targets, trails);
    emit('replay-targets', targets);
    const rel = (r.t - r.eventT) / 1000;
    setText($('#replayTime'), `${clockTime(r.t)} · ${rel >= 0 ? '+' : '−'}${Math.abs(rel).toFixed(0)} s`);
    const slider = $('#replaySlider');
    if (document.activeElement !== slider) slider.value = String(Math.round(r.t - r.clip.t0));
}

function tick(now) {
    const r = replay;
    if (!r || !r.playing) return;
    const dt = r.last ? now - r.last : 0;
    r.last = now;
    r.t = Math.min(r.clip.t1, r.t + dt * r.speed);
    drawReplay();
    if (r.t >= r.clip.t1) { setPlaying(false); return; }
    r.frame = requestAnimationFrame(tick);
}

function setPlaying(playing) {
    const r = replay;
    if (!r) return;
    if (playing && r.t >= r.clip.t1) r.t = r.clip.t0;
    r.playing = playing;
    r.last = 0;
    cancelAnimationFrame(r.frame);
    $('#replayPlay').setAttribute('aria-label', playing ? 'Pause' : 'Play');
    $('#replayPlay').classList.toggle('playing', playing);
    if (playing) r.frame = requestAnimationFrame(tick);
}

function startReplay(e) {
    if (state.edit) { toast('Save or cancel the zone you\'re editing first.', 'error'); return; }
    const topic = state.device;
    socket().emit('get_clip', { topic, t: e.t_ms }, ack => {
        if (topic !== state.device) return;
        const clip = ack && ack.clip;
        if (!clip || !clip.frames || !clip.frames.length) {
            toast('No positions were recorded around then. Target reporting was probably off.', 'error', 6000);
            return;
        }
        if (state.arranging) emit('arrange', false);
        stopReplay(false);
        replay = { clip, eventT: e.t_ms, t: Math.max(clip.t0, e.t_ms - 5000), playing: false, speed: 1, frame: 0, last: 0 };
        state.replay = replay;
        const slider = $('#replaySlider');
        slider.max = String(clip.t1 - clip.t0);
        slider.value = String(replay.t - clip.t0);
        setText($('#replayWhat'), describe(e).title);
        $('#replaySpeed').textContent = '1×';
        $('#replayBar').hidden = false;
        $('#map').classList.add('replaying');
        drawReplay();
        setPlaying(true);
        renderEvents();
        if (!window.matchMedia('(min-width: 901px)').matches) $('#map').scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
}

export function stopReplay(render = true) {
    if (!replay) return;
    cancelAnimationFrame(replay.frame);
    replay = null;
    state.replay = null;
    $('#replayBar').hidden = true;
    $('#map').classList.remove('replaying');
    radar.setTargets([], {});
    emit('replay-end');
    if (render) renderEvents();
}

// --- Setup ---------------------------------------------------------------------------------

export function tabShown(open) {
    tabOpen = open;
    load();
}

export function deviceChanged() {
    stopReplay(false);
    events = [];
    stats = null;
    renderEvents();
    renderStatus();
    load();
}

export function initHistory(radarInstance) {
    radar = radarInstance;
    radar.setHeatOpacity(prefs.getInt('heatOpacity', 85) / 100);

    $('#historyEnabled').addEventListener('change', e => saveSettings({ enabled: e.target.checked }));
    $('#historyDays').addEventListener('change', e => saveSettings({ days: parseInt(e.target.value, 10) }));
    $$('#heatRanges button').forEach(b => b.addEventListener('click', () => setRange(b.dataset.range)));
    for (const id of ['heatFrom', 'heatTo']) $('#' + id).addEventListener('change', () => { if (range === 'custom') load(); });
    $$('#eventFilter button').forEach(b => b.addEventListener('click', () => { filter = b.dataset.filter; renderEvents(); }));

    const opacity = $('#heatOpacity');
    opacity.value = String(prefs.getInt('heatOpacity', 85));
    opacity.addEventListener('input', () => {
        radar.setHeatOpacity(Number(opacity.value) / 100);
        prefs.set('heatOpacity', Number(opacity.value));
    });

    // The same setting in two places: here and in the Display tab
    const always = [$('#heatAlways'), $('#vizToggleHeat')];
    for (const box of always) {
        box.checked = prefs.getBool('heatAlways', false);
        box.addEventListener('change', () => {
            prefs.set('heatAlways', box.checked);
            for (const other of always) other.checked = box.checked;
            load();
        });
    }

    $('#btnClearHistory').addEventListener('click', async () => {
        if (!state.device) { toast('Choose a switch first.', 'error'); return; }
        if (!await confirmAction(`Delete all recorded history for "${state.deviceName}"? The heat map and timeline for this switch start over.`, { confirm: 'Delete', danger: true })) return;
        socket().emit('clear_history', state.device, ack => {
            if (ack && ack.error) toast(ack.error, 'error');
            else toast('History cleared.', 'success');
            load();
        });
    });

    $('#replayPlay').addEventListener('click', () => setPlaying(!(replay && replay.playing)));
    $('#replaySpeed').addEventListener('click', () => {
        if (!replay) return;
        replay.speed = SPEEDS[(SPEEDS.indexOf(replay.speed) + 1) % SPEEDS.length];
        $('#replaySpeed').textContent = `${replay.speed}×`;
    });
    $('#replaySlider').addEventListener('input', e => {
        if (!replay) return;
        replay.t = replay.clip.t0 + Number(e.target.value);
        drawReplay();
    });
    $('#replayLive').addEventListener('click', () => stopReplay());
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape' && replay && !e.defaultPrevented && !document.querySelector('dialog[open]')) stopReplay();
    });

    on('edit', () => { if (state.edit && replay) stopReplay(); });
    on('arrange', arranging => { if (arranging && replay) stopReplay(); });
    on('device-settings', () => renderStatus());

    socket().on('history_settings', applySettings);
    socket().on('history_event', onLiveEvent);
    const fetchSettings = () => socket().emit('get_history_settings', null, applySettings);
    socket().on('connect', fetchSettings);
    if (socket().connected) fetchSettings();

    renderRangeButtons();
    renderSettings();
    renderEvents();
}
