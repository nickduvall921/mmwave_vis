// Tests for the detection settings, run live against the switch:
//  * hold time: after everyone leaves, how long until the switch reports clear,
//    compared with the hold time it's set to;
//  * sit still: whether someone sitting still stays detected, with a one-click
//    stay area where they sat if they don't.

import { state, on } from './state.js';
import { $, h, setText, duration } from './ui.js';
import { startNewZone } from './zones.js';

const STILL_DOP = 10;          // |doppler| at or under this is "still"
const LOST_AFTER_MS = 3000;    // gone this long counts as lost
const SETTLE_S = 10;           // time to get into position for the sit-still test
const STILL_TEST_S = 60;
const STUCK_EXTRA_S = 120;     // give up this long after the hold time has passed
export const STAY_LIFE_STEP_S = 0.05;   // stay life counts in 50 ms steps (300 = 15 s)

let test = null;
let ticker = 0;

const overlay = $('#testerOverlay');
const status = $('#testerStatus');
const actions = $('#testerActions');

const reporting = () => state.settings.mmWaveTargetInfoReport === 'Enable';
const anyArea = () => state.areaOccupied.some(Boolean);
const someoneSeen = () => anyArea() || (reporting() && state.targetCount > 0);
const holdTime = () => {
    const v = Number(state.settings.mmWaveHoldTime);
    return Number.isFinite(v) && v >= 0 ? v : null;
};
const elapsed = since => (Date.now() - since) / 1000;

function say(text, tone = '') {
    setText(status, text);
    status.dataset.tone = tone;
}

function showOverlay(big, small) {
    overlay.hidden = false;
    overlay.replaceChildren(h('strong', { class: 'num' }, big), small ? h('span', null, small) : null);
}

function renderButtons() {
    $('#btnTestHold').textContent = test && test.kind === 'hold' ? 'Stop test' : 'Test hold time';
    $('#btnTestStill').textContent = test && test.kind === 'still' ? 'Stop test' : 'Sit still test';
    $('#btnTestHold').disabled = !!test && test.kind !== 'hold';
    $('#btnTestStill').disabled = !!test && test.kind !== 'still';
}

function stop(message = null, tone = '') {
    test = null;
    clearInterval(ticker);
    ticker = 0;
    overlay.hidden = true;
    renderButtons();
    if (message !== null) say(message, tone);
}

function start(kind) {
    if (!state.device) { say('Choose a switch first.', 'bad'); return; }
    actions.replaceChildren();
    test = { kind, phase: 'start', since: Date.now() };
    clearInterval(ticker);
    ticker = setInterval(step, 250);
    renderButtons();
    step();
}

// --- Hold time ------------------------------------------------------------------

function holdStep() {
    const t = test;
    const hold = holdTime();
    if (t.phase === 'start') {
        if (state.stack === 'zha' && state.deviceInfo && state.deviceInfo.topic === state.device &&
                state.deviceInfo.ha_available && !(state.deviceInfo.entities || {}).occupancy) {
            stop('Home Assistant has no occupancy entity for this switch, so the time it clears can\'t be measured.', 'bad');
            return;
        }
        // Time only from a room the test has seen someone leave: started while the room
        // is already empty (but still held occupied), it would time from the click
        t.phase = state.occupied && someoneSeen() ? 'present' : 'waiting';
    }
    if (t.phase === 'waiting') {
        say('Walk in front of the switch until it shows Occupied and sees you.');
        showOverlay('Walk in', 'waiting to see you');
        if (state.occupied && someoneSeen()) t.phase = 'present';
        return;
    }
    if (t.phase === 'present') {
        say(reporting()
            ? 'Now leave the room, or step out of view. The countdown starts once nobody is seen.'
            : 'Now leave the room. The countdown starts once no area sees anyone (turn on target reporting to time it from the last person seen).');
        showOverlay('Leave', 'the countdown starts when nobody is seen');
        if (!someoneSeen()) {
            t.phase = 'countdown';
            t.emptyAt = Date.now();
        }
        if (state.occupied === false) stop('The switch reported clear while someone was still being seen. Try again and wait in view until it shows Occupied.', 'bad');
        return;
    }
    if (t.phase === 'countdown') {
        const gone = elapsed(t.emptyAt);
        if (someoneSeen()) {
            t.phase = 'present';
            say('Someone was seen again, so the countdown starts over.');
            return;
        }
        if (state.occupied === false) {
            report(gone, hold);
            return;
        }
        if (hold !== null) {
            say('Nobody is seen now. Stay out of view until the switch reports clear.');
            const left = hold - gone;
            showOverlay(left >= 0 ? `${Math.ceil(left)} s` : `+${Math.floor(-left)} s`,
                left >= 0 ? 'until it should clear' : 'past the hold time, still occupied');
            if (-left > STUCK_EXTRA_S) {
                stop(`Still occupied ${duration(gone)} after the room emptied. Something keeps it occupied that isn't shown as a target or area: a fan, curtain or vent nearby. Try an interference area, lower sensitivity, or "Detect automatically" under Zone tools.`, 'bad');
            }
        } else {
            showOverlay(`${Math.floor(gone)} s`, 'since the room emptied');
            say('Counting. The switch hasn\'t reported its hold time, so press Sync to compare it.');
        }
    }
}

function report(gone, hold) {
    if (hold === null) {
        stop(`Cleared ${duration(gone)} after the room emptied.`, 'good');
        return;
    }
    const slack = Math.max(5, hold * 0.2);
    if (Math.abs(gone - hold) <= slack) {
        stop(`Cleared ${duration(gone)} after the room emptied. The hold time is ${duration(hold)}, so that's as expected.`, 'good');
    } else if (gone > hold) {
        stop(`Cleared ${duration(gone)} after the room emptied, ${duration(gone - hold)} longer than the hold time (${duration(hold)}). The switch kept sensing something faint for a while: look for a fan, curtain or vent, and try an interference area or a lower sensitivity.`, 'warn');
    } else {
        stop(`Cleared after ${duration(gone)}, sooner than the hold time (${duration(hold)}). The switch probably lost sight of you before you left, so the hold time ran from then.`, 'warn');
    }
}

// --- Sit still ----------------------------------------------------------------------

function stillStep() {
    const t = test;
    if (t.phase === 'start') {
        t.phase = 'settle';
        t.settleUntil = Date.now() + SETTLE_S * 1000;
    }
    if (t.phase === 'settle') {
        const left = Math.ceil((t.settleUntil - Date.now()) / 1000);
        say(`Sit or lie down where you want to be detected and keep still. Starting in ${left} s.`);
        showOverlay(`${left} s`, 'get into position');
        if (left <= 0) {
            Object.assign(t, { phase: 'run', runFrom: Date.now(), lostSince: null, lostAt: null, sum: [0, 0, 0], n: 0 });
        }
        return;
    }
    if (t.phase !== 'run') return;
    const now = Date.now();
    // With positions, judge by them (occupancy is held for the hold time, which would hide a
    // loss); without them, the areas and occupancy are all there is
    const seen = reporting() ? someoneSeen() : anyArea() || state.occupied === true;
    if (seen) t.lostSince = null;
    else if (t.lostSince === null) t.lostSince = now;
    if (t.lostSince !== null && now - t.lostSince >= LOST_AFTER_MS && t.lostAt === null) t.lostAt = t.lostSince;
    const left = STILL_TEST_S - elapsed(t.runFrom);
    showOverlay(`${Math.max(0, Math.ceil(left))} s`, seen ? 'detected · keep still' : 'not detected');
    say(seen ? 'Keep still. You\'re being detected.' : 'The switch isn\'t seeing you right now.');
    if (t.lostAt !== null || left <= 0) stillReport();
}

function trackStill(targets) {
    if (!test || test.kind !== 'still' || test.phase !== 'run') return;
    for (const p of targets) {
        if (Math.abs(Number(p.dop) || 0) > STILL_DOP) continue;
        test.sum[0] += Number(p.x);
        test.sum[1] += Number(p.y);
        test.sum[2] += Number(p.z);
        test.n++;
    }
}

function stillReport() {
    const t = test;
    const where = t.n ? { x: t.sum[0] / t.n, y: t.sum[1] / t.n, z: t.sum[2] / t.n } : null;
    const stayLife = Number(state.settings.mmWaveStayLife) * STAY_LIFE_STEP_S;
    let message, tone;
    if (t.lostAt === null) {
        message = `You stayed detected for the whole ${duration(STILL_TEST_S)} of sitting still.`;
        tone = 'good';
    } else {
        message = `The switch lost you after ${duration((t.lostAt - t.runFrom) / 1000)} of sitting still.`;
        message += ' A stay area where you sat helps it keep tracking someone who barely moves';
        message += Number.isFinite(stayLife) ? ` (for up to the stay life, now ${duration(stayLife)}).` : '.';
        message += ' Raising the sensitivity helps too.';
        tone = 'warn';
    }
    stop(message, tone);
    if (where && (tone === 'warn' || !coveredByStay(where))) {
        actions.replaceChildren(h('button', {
            class: 'btn small', type: 'button',
            onclick: () => {
                const r = 60;
                startNewZone('mmwave_stay_areas', {
                    x_min: Math.round(where.x - r), x_max: Math.round(where.x + r),
                    y_min: Math.max(0, Math.round(where.y - r)), y_max: Math.round(where.y + r),
                    z_min: -300, z_max: 300,
                });
                actions.replaceChildren();
            },
        }, 'Add a stay area where you sat'));
    }
}

function coveredByStay(p) {
    return Object.values(state.zones.mmwave_stay_areas).some(z => z &&
        p.x >= z.x_min && p.x <= z.x_max && p.y >= z.y_min && p.y <= z.y_max);
}

// --- Setup ----------------------------------------------------------------------------

function step() {
    if (!test) return;
    if (test.kind === 'hold') holdStep();
    else stillStep();
}

export function stopTests() {
    if (test) stop('');
    actions.replaceChildren();
}

export function initTester() {
    $('#btnTestHold').addEventListener('click', () => test ? stop('Test stopped.') : start('hold'));
    $('#btnTestStill').addEventListener('click', () => test ? stop('Test stopped.') : start('still'));
    on('targets', trackStill);
    on('occupancy', step);
    on('areas', step);
    renderButtons();
}

