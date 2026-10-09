"""Tests for history.py: heat map bins, change events, replay clips and storage."""
import os
import sqlite3
import sys
import threading

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'mmwave_vis'))

import history
from history import History, HeatGrid, ClipRecorder, EventTracker, pack_frames, unpack_frames

T0 = 1_800_000_000.0   # 2027-01-15, a valid wall-clock time


class Clock:
    def __init__(self, t=T0):
        self.t = t

    def wall(self):
        return self.t

    def mono(self):
        return self.t

    def advance(self, s):
        self.t += s


def target(x, y, tid=1, z=0, dop=0):
    return {'id': tid, 'x': x, 'y': y, 'z': z, 'dop': dop}


@pytest.fixture
def clock():
    return Clock()


def make(tmp_path, clock, enabled=True, events=None):
    h = History(str(tmp_path), on_event=(lambda k, e: events.append((k, e))) if events is not None else None,
                mono=clock.mono, wall=clock.wall, start_thread=False)
    h.start()
    if enabled:
        h.set_settings(enabled=True)
    return h


def cells(result):
    return {(ix, iy): s for ix, iy, s in result['cells']}


# ---------------------------------------------------------------------------
# Off by default
# ---------------------------------------------------------------------------

def test_off_by_default_records_nothing_and_creates_no_database(tmp_path, clock):
    h = make(tmp_path, clock, enabled=False)
    h.on_targets('ieee:a', [target(0, 100)])
    clock.advance(0.5)
    h.on_targets('ieee:a', [target(0, 100)])
    h.on_state('ieee:a', {'occupancy': True})
    assert h.heatmap('ieee:a', T0 - 60, T0 + 60)['cells'] == []
    assert h.events('ieee:a', 0, 10**15) == []
    assert not (tmp_path / 'history.db').exists()
    assert h.settings()['enabled'] is False


def test_settings_persist(tmp_path, clock):
    h = make(tmp_path, clock)
    h.set_settings(days=7)
    again = History(str(tmp_path), mono=clock.mono, wall=clock.wall, start_thread=False)
    assert again.settings()['enabled'] is True
    assert again.settings()['days'] == 7
    assert h.set_settings(days=10_000)['days'] == 365


def test_wrong_clock_is_ignored(tmp_path):
    clock = Clock(1_000_000.0)   # 1970: a Pi that hasn't synced its clock yet
    h = History(str(tmp_path), mono=clock.mono, wall=clock.wall, start_thread=False)
    h.set_settings(enabled=True)
    h.on_targets('ieee:a', [target(0, 100)])
    clock.advance(0.5)
    h.on_targets('ieee:a', [target(0, 100)])
    assert h.grid._bins == {}


# ---------------------------------------------------------------------------
# Heat map
# ---------------------------------------------------------------------------

def test_first_sample_counts_zero_then_time_between_samples():
    g = HeatGrid()
    g.add('k', [target(5, 105)], 0.0, T0)
    assert g.peek('k', T0 - 60, T0 + 60) == {}
    g.add('k', [target(5, 105)], 0.1, T0 + 0.1)
    assert g.peek('k', T0 - 60, T0 + 60) == {(0, 10): pytest.approx(0.1)}


def test_long_gap_counts_at_most_one_second():
    g = HeatGrid()
    g.add('k', [target(0, 0)], 0.0, T0)
    g.add('k', [target(0, 0)], 30.0, T0 + 30)
    assert g.peek('k', T0 - 60, T0 + 60) == {(0, 0): pytest.approx(1.0)}


def test_switches_kept_apart_and_out_of_range_dropped():
    g = HeatGrid()
    for key in ('a', 'b'):
        g.add(key, [], 0.0, T0)
    g.add('a', [target(-15, 20), target(700, 20), target(0, -5), target(0, 650)], 0.5, T0 + 0.5)
    g.add('b', [target(15, 20)], 0.5, T0 + 0.5)
    assert g.peek('a', T0 - 60, T0 + 60) == {(-2, 2): pytest.approx(0.5)}
    assert g.peek('b', T0 - 60, T0 + 60) == {(1, 2): pytest.approx(0.5)}


def test_bad_targets_are_skipped():
    g = HeatGrid()
    g.add('k', [], 0.0, T0)
    g.add('k', [{'x': 'nope'}, {'y': 3}, target(float('nan'), 1), target(1, 1)], 0.2, T0 + 0.2)
    assert g.peek('k', T0 - 60, T0 + 60) == {(0, 0): pytest.approx(0.2)}


def test_heatmap_merges_unflushed_and_flushed(tmp_path, clock):
    h = make(tmp_path, clock)
    key = 'ieee:a'
    for _ in range(11):                 # 10 intervals of 0.1 s at one spot
        h.on_targets(key, [target(50, 150)])
        clock.advance(0.1)
    before = cells(h.heatmap(key, T0 - 600, clock.t))
    assert before == {(5, 15): pytest.approx(1.0)}
    h.flush_now()
    assert h.grid._bins == {}
    after = h.heatmap(key, T0 - 600, clock.t)
    assert cells(after) == {(5, 15): pytest.approx(1.0)}
    assert after['res'] == 60
    assert after['max'] == pytest.approx(1.0)
    # Data in memory again on top of the stored minute (0.1 s since the last sample, then 0.5 s)
    h.on_targets(key, [target(50, 150)])
    clock.advance(0.5)
    h.on_targets(key, [target(50, 150)])
    assert cells(h.heatmap(key, T0 - 600, clock.t)) == {(5, 15): pytest.approx(1.6)}


def test_minute_rows_cover_48h_then_hour_rows(tmp_path, clock):
    h = make(tmp_path, clock)
    key = 'ieee:a'
    h.on_targets(key, [target(0, 100)])
    clock.advance(1)
    h.on_targets(key, [target(0, 100)])
    h.flush_now()
    clock.advance(3 * 86400)            # three days later
    recent = h.heatmap(key, clock.t - 3600, clock.t)
    assert recent['cells'] == []
    week = h.heatmap(key, clock.t - 7 * 86400, clock.t)
    assert week['res'] == 3600
    assert cells(week) == {(0, 10): pytest.approx(1.0)}


def test_prune_drops_old_minute_rows_but_keeps_hours(tmp_path, clock):
    h = make(tmp_path, clock)
    key = 'ieee:a'
    h.on_targets(key, [target(0, 100)])
    clock.advance(1)
    h.on_targets(key, [target(0, 100)])
    h.flush_now()
    clock.advance(3 * 86400)
    h.prune()
    rows = dict(h.db.conn.execute('SELECT res, COUNT(*) FROM heat GROUP BY res').fetchall())
    assert rows.get(60) is None and rows.get(3600) == 1
    clock.advance(40 * 86400)           # past the 30-day retention
    h.prune()
    assert h.db.conn.execute('SELECT COUNT(*) FROM heat').fetchone()[0] == 0


def test_size_cap_drops_oldest_days(tmp_path, clock, monkeypatch):
    h = make(tmp_path, clock)
    key = 'ieee:a'
    for day in range(3):
        h.on_targets(key, [target(0, 100)])
        clock.advance(1)
        h.on_targets(key, [target(0, 100)])
        h.flush_now()
        clock.advance(86400)
    monkeypatch.setattr(history, 'MAX_DB_BYTES', 0)
    sizes = iter([10, 10, 0])
    monkeypatch.setattr(h.db, 'size', lambda: next(sizes, 0))
    h.prune()
    days_left = h.db.conn.execute('SELECT COUNT(DISTINCT t) FROM heat WHERE res=3600').fetchone()[0]
    assert days_left == 1


def test_clear_removes_one_switch(tmp_path, clock):
    h = make(tmp_path, clock)
    for key in ('ieee:a', 'ieee:b'):
        h.on_targets(key, [target(0, 100)])
    clock.advance(1)
    for key in ('ieee:a', 'ieee:b'):
        h.on_targets(key, [target(0, 100)])
    h.flush_now()
    h.clear('ieee:a')
    assert h.heatmap('ieee:a', T0 - 60, clock.t)['cells'] == []
    assert h.heatmap('ieee:b', T0 - 60, clock.t)['cells'] != []


def test_corrupt_database_is_moved_aside(tmp_path, clock):
    (tmp_path / 'history.db').write_bytes(b'this is not a database' * 100)
    h = make(tmp_path, clock)
    assert h.settings()['error'] is None
    assert any(p.name.startswith('history.db.broken-') for p in tmp_path.iterdir())
    h.on_targets('ieee:a', [target(0, 100)])
    clock.advance(1)
    h.on_targets('ieee:a', [target(0, 100)])
    h.flush_now()
    assert h.heatmap('ieee:a', T0 - 60, clock.t)['cells']


def test_concurrent_inputs(tmp_path, clock):
    h = make(tmp_path, clock)
    errors = []

    def feed(key):
        try:
            for _ in range(500):
                h.on_targets(key, [target(0, 100)])
                h.on_state(key, {'occupancy': True})
        except Exception as e:   # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=feed, args=(f'ieee:{i}',)) for i in range(4)]
    for t in threads:
        t.start()
    for _ in range(5):
        h.flush_now()
    for t in threads:
        t.join()
    h.flush_now()
    assert not errors


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

def test_tracker_ignores_repeats_and_baselines():
    t = EventTracker()
    assert t.update('k', {'occupancy': 'ON', 'area1': True}) == []      # baseline
    assert t.update('k', {'occupancy': True, 'area1': 1}) == []         # same values, other spellings
    assert t.update('k', {'occupancy': 'OFF'}) == [('occupancy', False, False)]
    assert t.update('k', {'light': None, 'area2': 'maybe'}) == []       # unknowns skipped


def test_events_recorded_and_pushed(tmp_path, clock):
    pushed = []
    h = make(tmp_path, clock, events=pushed)
    key = 'ieee:a'
    h.on_state(key, {'occupancy': False, 'area1': False, 'light': 'OFF'})
    h.on_targets(key, [target(0, 100)])
    clock.advance(1)
    h.on_targets(key, [target(0, 100)])
    h.on_state(key, {'occupancy': True, 'area1': True})
    clock.advance(2)
    h.on_state(key, {'light': 'ON'})
    clock.advance(60)
    h.on_targets(key, [])
    h.on_state(key, {'occupancy': False, 'area1': False})
    kinds = [(e['kind'], e['area'], e['value']) for _, e in pushed]
    assert kinds == [('occupancy', 0, True), ('area', 1, True), ('light', 0, True),
                     ('occupancy', 0, False), ('area', 1, False)]
    assert pushed[0][1]['ntargets'] == 1
    clear = pushed[3][1]
    assert clear['last_detect_ms'] == int((T0 + 1) * 1000)
    # Pending and flushed events read back the same way, newest first
    pending = h.events(key, 0, 10**15)
    h.flush_now()
    stored = h.events(key, 0, 10**15)
    assert pending == stored
    assert [e['kind'] for e in stored] == ['area', 'occupancy', 'light', 'area', 'occupancy']


def test_change_while_addon_was_off_is_flagged(tmp_path, clock):
    key = 'ieee:a'
    h = make(tmp_path, clock)
    h.on_state(key, {'light': 'OFF'})
    h.on_state(key, {'light': 'ON'})
    h.close()
    clock.advance(600)
    h2 = make(tmp_path, clock)
    h2.on_state(key, {'light': 'OFF'}, t_ms=int((clock.t - 120) * 1000))   # changed during the restart
    h2.on_state(key, {'light': 'OFF'})
    events = h2.events(key, 0, 10**15)
    assert events[0]['value'] is False and events[0]['offline'] is True
    assert events[0]['t_ms'] == int((clock.t - 120) * 1000)
    assert len(events) == 2


def test_same_value_after_restart_is_not_an_event(tmp_path, clock):
    key = 'ieee:a'
    h = make(tmp_path, clock)
    h.on_state(key, {'occupancy': False})
    h.on_state(key, {'occupancy': True})
    h.close()
    h2 = make(tmp_path, clock)
    h2.on_state(key, {'occupancy': True})
    assert len(h2.events(key, 0, 10**15)) == 1


# ---------------------------------------------------------------------------
# Clips
# ---------------------------------------------------------------------------

def test_clip_has_pre_roll_and_post_roll(tmp_path, clock):
    h = make(tmp_path, clock)
    key = 'ieee:a'
    h.on_state(key, {'occupancy': False})
    for i in range(40):                   # 40 s of walking, 1 frame/s
        h.on_targets(key, [target(i, 100)])
        clock.advance(1)
    event_t = int(clock.t * 1000)
    h.on_state(key, {'occupancy': True})
    for i in range(40):
        h.on_targets(key, [target(100 + i, 100)])
        clock.advance(1)
    clip = h.clip(key, event_t)
    times = [f[0] for f in clip['frames']]
    assert min(times) >= event_t - 30_000 and min(times) <= event_t - 29_000
    assert max(times) <= event_t + 30_000 and max(times) >= event_t + 29_000
    h.flush_now()
    stored = h.clip(key, event_t)
    assert stored['frames'] == clip['frames']


def test_clip_frames_downsampled_and_empty_frames_kept():
    c = ClipRecorder()
    c.trigger('k', 0)
    for t in range(0, 1000, 100):         # 10 Hz in → 4 Hz kept
        c.add('k', [target(1, 2)], t)
    c.add('k', [], 1000)
    c.tick(60_000)
    (key, t0, t1, frames), = c.done
    assert [f[0] for f in frames] == [0, 300, 600, 900]
    c2 = ClipRecorder()
    c2.trigger('k', 0)
    c2.add('k', [], 0)
    c2.tick(60_000)
    assert c2.done[0][3] == [(0, [])]


def test_overlapping_events_extend_one_clip_up_to_the_cap():
    c = ClipRecorder()
    c.trigger('k', 0)
    c.trigger('k', 20_000)
    assert c._open['k']['end'] == 50_000
    for t in range(0, 400_000, 10_000):
        c.trigger('k', t) if t <= c._open.get('k', {'end': -1})['end'] else None
    assert c._open['k']['end'] - c._open['k']['t0'] <= history.CLIP_MAX_MS


def test_clip_for_a_past_moment_takes_no_newer_frames():
    c = ClipRecorder()
    for t in range(100_000, 130_000, 1000):
        c.add('k', [target(1, 2)], t)
    c.trigger('k', 10_000)          # an event dated long before the frames in the buffer
    c.tick(200_000)
    assert c.done == []             # nothing in its window, so no clip


def test_offline_change_records_no_clip(tmp_path, clock):
    key = 'ieee:a'
    h = make(tmp_path, clock)
    h.on_state(key, {'light': 'OFF'})
    h.on_state(key, {'light': 'ON'})          # stored: light on
    h.close()
    clock.advance(3600)
    h2 = make(tmp_path, clock)
    h2.on_targets(key, [target(0, 100)])
    h2.on_state(key, {'light': 'OFF'}, t_ms=int((clock.t - 1800) * 1000))
    assert h2.events(key, 0, 10**15)[0]['offline'] is True
    assert key not in h2.clips._open


def test_pack_round_trip():
    frames = [(1000, [(1, 10, -20, 30, -5), (2, -32768, 32767, 0, 7)]), (1250, []), (1500, [(3, 1, 2, 3, 4)])]
    data = pack_frames(1000, frames)
    assert unpack_frames(1000, data) == [
        [1000, [[1, 10, -20, 30, -5], [2, -32768, 32767, 0, 7]]],
        [1250, []],
        [1500, [[3, 1, 2, 3, 4]]],
    ]


def test_reporting_changes_are_events_without_clips(tmp_path, clock):
    h = make(tmp_path, clock)
    h.on_state('ieee:a', {'reporting': 'Disable (default)'})
    h.on_state('ieee:a', {'reporting': 'Enable'})
    assert [e['kind'] for e in h.events('ieee:a', 0, 10**15)] == ['reporting']
    assert 'ieee:a' not in h.clips._open
