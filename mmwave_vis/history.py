"""History: where people spent time (heat map) and when each switch's occupancy
and light changed (timeline), with a short replay of the radar around each change.

Off by default. Nothing is recorded, and no database file is created, until
it's turned on from the History tab. Everything stays in the addon's /data
folder on the Home Assistant host.

Sizes are kept small on purpose (HA often runs from an SD card):
  * heat: seconds spent per 10 cm cell, per minute for the last 48 h and per
    hour after that, written in one transaction every few minutes;
  * events: one row per change, never repeats;
  * clips: ±30 s of target positions around each change, packed into a blob,
    at most 4 frames a second, kept 7 days.

Thread safety: the drivers call on_targets()/on_state() from their own threads.
In-memory state is guarded by one lock and the database by another; a single
writer thread does the periodic flushing and pruning.
"""
import json
import math
import os
import struct
import tempfile
import threading
import time
from collections import deque

try:
    import sqlite3
except ImportError:   # pragma: no cover - the image ships it, but fail soft
    sqlite3 = None

CELL_CM = 10
X_LIMIT = 600            # cm either side of the switch
Y_LIMIT = 600            # cm in front of it
MAX_DT_S = 1.0           # a sample never counts for more than a second
MINUTE = 60
HOUR = 3600
MINUTE_KEEP_S = 48 * HOUR
CLIP_PRE_MS = 30_000
CLIP_POST_MS = 30_000
CLIP_MAX_MS = 5 * 60_000
CLIP_FRAME_MS = 250      # at most 4 frames a second
CLIP_KEEP_S = 7 * 86400
FLUSH_EVERY_S = 300
PRUNE_EVERY_S = HOUR
TICK_S = 5
MAX_DB_BYTES = 64 * 1024 * 1024
MIN_VALID_EPOCH = 1735689600   # 2025-01-01: a Pi without an RTC boots in 1970
DEFAULT_DAYS = 30
KEEP_DAYS_RANGE = (1, 365)
SCHEMA_VERSION = 1

# One target in a clip: time since the clip started (10 ms units), x, y, z, dop, id.
# A frame with no targets is stored as one record with id -128.
FRAME = struct.Struct('<Hhhhhb')
EMPTY_ID = -128

STATE_FIELDS = ('occupancy', 'area1', 'area2', 'area3', 'area4', 'light', 'reporting')


def _kind_area(field):
    if field.startswith('area'):
        return 'area', int(field[4:])
    return field, 0


def _field(kind, area):
    return f"area{area}" if kind == 'area' else kind


def _clamp(v, lo, hi):
    try:
        v = int(round(float(v)))
    except (TypeError, ValueError):
        return 0
    return lo if v < lo else hi if v > hi else v


def as_bool(value):
    """True/False from the many ways switches report on/off; None if unknown."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ('on', 'true', '1', 'enable', 'enabled', 'occupied', 'detected'):
            return True
        if v in ('off', 'false', '0', 'disable', 'disable (default)', 'disabled', 'clear'):
            return False
    return None


# ---------------------------------------------------------------------------
# In-memory parts (pure, with injectable clocks so they can be tested)
# ---------------------------------------------------------------------------

class HeatGrid:
    """Seconds spent per cell, per switch, per minute, until they're flushed."""

    def __init__(self):
        self._last = {}    # key -> monotonic time of that switch's last sample
        self._bins = {}    # (key, minute start) -> {(ix, iy): seconds}

    def add(self, key, targets, mono, wall):
        last = self._last.get(key)
        self._last[key] = mono
        if last is None:
            return
        dt = min(max(mono - last, 0.0), MAX_DT_S)
        if dt <= 0 or not targets:
            return
        minute = int(wall // MINUTE) * MINUTE
        cells = None
        for t in targets:
            try:
                x, y = float(t['x']), float(t['y'])
            except (KeyError, TypeError, ValueError):
                continue
            if not (math.isfinite(x) and math.isfinite(y)) or abs(x) > X_LIMIT or y < 0 or y > Y_LIMIT:
                continue
            if cells is None:
                cells = self._bins.setdefault((key, minute), {})
            cell = (int(x // CELL_CM), int(y // CELL_CM))
            cells[cell] = cells.get(cell, 0.0) + dt

    def take(self):
        bins, self._bins = self._bins, {}
        return bins

    def peek(self, key, t0, t1):
        """Unflushed seconds per cell for one switch between two times (s)."""
        out = {}
        for (k, minute), cells in self._bins.items():
            if k == key and t0 <= minute + MINUTE and minute < t1:
                for cell, secs in cells.items():
                    out[cell] = out.get(cell, 0.0) + secs
        return out

    def forget(self, key):
        self._last.pop(key, None)
        for k in [k for k in self._bins if k[0] == key]:
            del self._bins[k]


class ClipRecorder:
    """Keeps the last 30 s of frames per switch and records clips around events."""

    def __init__(self):
        self._ring = {}      # key -> deque of (t_ms, targets)
        self._open = {}      # key -> {'t0', 'end', 'frames'}
        self.done = []       # finished clips waiting to be written: (key, t0, t1, frames)

    def add(self, key, targets, t_ms):
        ring = self._ring.setdefault(key, deque())
        if ring and t_ms - ring[-1][0] < CLIP_FRAME_MS:
            return
        frame = (t_ms, [(t.get('id', 0), t.get('x', 0), t.get('y', 0), t.get('z', 0), t.get('dop', 0))
                        for t in targets or [] if isinstance(t, dict)])
        ring.append(frame)
        while ring and ring[0][0] < t_ms - CLIP_PRE_MS:
            ring.popleft()
        clip = self._open.get(key)
        if clip is not None:
            if t_ms <= clip['end']:
                clip['frames'].append(frame)
            else:
                self._close(key)

    def trigger(self, key, t_ms):
        """An event happened: record from 30 s before it to 30 s after."""
        clip = self._open.get(key)
        if clip is not None:
            if t_ms <= clip['end']:
                clip['end'] = min(max(clip['end'], t_ms + CLIP_POST_MS), clip['t0'] + CLIP_MAX_MS)
                return
            self._close(key)
        t0 = t_ms - CLIP_PRE_MS
        frames = [f for f in self._ring.get(key, ()) if f[0] >= t0]
        self._open[key] = {'t0': t0, 'end': t_ms + CLIP_POST_MS, 'frames': frames}

    def tick(self, now_ms):
        for key in [k for k, c in self._open.items() if now_ms > c['end']]:
            self._close(key)

    def close_all(self):
        for key in list(self._open):
            self._close(key)

    def _close(self, key):
        clip = self._open.pop(key)
        if clip['frames']:
            self.done.append((key, clip['t0'], clip['end'], clip['frames']))

    def open_clip(self, key, t_ms):
        clip = self._open.get(key)
        if clip and clip['t0'] <= t_ms <= clip['end']:
            return clip['t0'], clip['end'], list(clip['frames'])
        for k, t0, t1, frames in self.done:
            if k == key and t0 <= t_ms <= t1:
                return t0, t1, list(frames)
        return None

    def forget(self, key):
        self._ring.pop(key, None)
        self._open.pop(key, None)
        self.done = [c for c in self.done if c[0] != key]


def pack_frames(t0, frames):
    out = bytearray()
    for t_ms, targets in frames:
        dt = _clamp((t_ms - t0) / 10, 0, 65535)
        if not targets:
            out += FRAME.pack(dt, 0, 0, 0, 0, EMPTY_ID)
            continue
        for tid, x, y, z, dop in targets:
            out += FRAME.pack(dt, _clamp(x, -32768, 32767), _clamp(y, -32768, 32767),
                              _clamp(z, -32768, 32767), _clamp(dop, -32768, 32767),
                              _clamp(tid, -127, 127))
    return bytes(out)


def unpack_frames(t0, data):
    """[[t_ms, [[id, x, y, z, dop], ...]], ...] in time order."""
    frames = []
    for dt, x, y, z, dop, tid in FRAME.iter_unpack(data[:len(data) - len(data) % FRAME.size]):
        t_ms = t0 + dt * 10
        if not frames or frames[-1][0] != t_ms:
            frames.append([t_ms, []])
        if tid != EMPTY_ID:
            frames[-1][1].append([tid, x, y, z, dop])
    return frames


class EventTracker:
    """Turns state reports into change events, ignoring repeats."""

    def __init__(self):
        self._state = {}   # key -> {field: bool}

    def known(self, key):
        return key in self._state

    def seed(self, key, values):
        """The last stored value of each field, so changes while the addon was off show up."""
        self._state[key] = dict(values)
        self._state[key]['_seeded'] = set(values)

    def update(self, key, state):
        """(field, value, was_offline_change) for each field that changed."""
        current = self._state.setdefault(key, {'_seeded': set()})
        seeded = current['_seeded']
        changes = []
        for field in STATE_FIELDS:
            if field not in state:
                continue
            value = as_bool(state[field])
            if value is None:
                continue
            old = current.get(field)
            first = field in seeded
            if first:
                seeded.discard(field)
            current[field] = value
            if old is None:
                continue          # first sighting with nothing stored: a baseline
            if old != value:
                changes.append((field, value, first))
        return changes

    def forget(self, key):
        self._state.pop(key, None)


# ---------------------------------------------------------------------------
# Settings file
# ---------------------------------------------------------------------------

def load_settings(path):
    settings = {'enabled': False, 'days': DEFAULT_DAYS}
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        h = data.get('history') if isinstance(data, dict) else None
        if isinstance(h, dict):
            settings['enabled'] = h.get('enabled') is True
            if isinstance(h.get('days'), int) and not isinstance(h.get('days'), bool):
                settings['days'] = _clamp(h['days'], *KEEP_DAYS_RANGE)
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as e:
        print(f"History: couldn't read {path} ({e}), history stays off.", flush=True)
    return settings


def save_settings(path, settings):
    """Write atomically; returns an error message or None."""
    folder = os.path.dirname(path) or '.'
    tmp = None
    try:
        data = {}
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict):
                data = {}
        except (OSError, ValueError):
            data = {}
        data['history'] = {'enabled': bool(settings['enabled']), 'days': int(settings['days'])}
        os.makedirs(folder, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=folder, prefix='.settings-', suffix='.tmp')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=1, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        tmp = None
        return None
    except OSError as e:
        return f"Couldn't save the setting ({e.strerror or e})"
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

class HistoryDB:
    """One sqlite connection, used under one lock from any thread."""

    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        self.conn = None
        self._dev_ids = {}

    def open(self):
        if sqlite3 is None:
            raise RuntimeError("This Python has no sqlite3 module")
        if self.path != ':memory:':
            os.makedirs(os.path.dirname(self.path) or '.', exist_ok=True)
        try:
            self._connect()
        except sqlite3.DatabaseError as e:
            if self.path == ':memory:':
                raise
            broken = f"{self.path}.broken-{int(time.time())}"
            print(f"History: {self.path} is damaged ({e}); moved it to {broken} and starting a new one.",
                  flush=True)
            self._close_quietly()
            for suffix in ('', '-wal', '-shm'):
                if os.path.exists(self.path + suffix):
                    try:
                        os.replace(self.path + suffix, broken + suffix)
                    except OSError:
                        pass
            self._connect()

    def _connect(self):
        self.conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        c = self.conn
        c.execute('PRAGMA auto_vacuum=INCREMENTAL')    # only takes effect before the first table
        c.execute('PRAGMA journal_mode=WAL')
        c.execute('PRAGMA synchronous=NORMAL')
        c.execute('PRAGMA cache_size=-1024')
        c.execute('PRAGMA busy_timeout=5000')
        c.execute('PRAGMA journal_size_limit=4194304')
        c.execute('PRAGMA quick_check(1)').fetchone()
        c.executescript('''
            CREATE TABLE IF NOT EXISTS devices(id INTEGER PRIMARY KEY, key TEXT UNIQUE NOT NULL);
            CREATE TABLE IF NOT EXISTS heat(
                dev INTEGER NOT NULL, res INTEGER NOT NULL, t INTEGER NOT NULL,
                ix INTEGER NOT NULL, iy INTEGER NOT NULL, secs REAL NOT NULL,
                PRIMARY KEY(dev, res, t, ix, iy)) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS events(
                id INTEGER PRIMARY KEY, dev INTEGER NOT NULL, t_ms INTEGER NOT NULL,
                kind TEXT NOT NULL, area INTEGER NOT NULL, value INTEGER NOT NULL,
                offline INTEGER NOT NULL DEFAULT 0, last_detect_ms INTEGER, ntargets INTEGER);
            CREATE INDEX IF NOT EXISTS events_dev_t ON events(dev, t_ms);
            CREATE TABLE IF NOT EXISTS clips(
                id INTEGER PRIMARY KEY, dev INTEGER NOT NULL, t0 INTEGER NOT NULL,
                t1 INTEGER NOT NULL, data BLOB NOT NULL);
            CREATE INDEX IF NOT EXISTS clips_dev_t ON clips(dev, t0);
        ''')
        c.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
        self._dev_ids = {k: i for i, k in c.execute('SELECT id, key FROM devices')}

    def _close_quietly(self):
        if self.conn is not None:
            try:
                self.conn.close()
            except Exception:
                pass
        self.conn = None

    def close(self):
        with self.lock:
            self._close_quietly()

    # Callers hold self.lock for everything below.

    def dev_id(self, key, create=True):
        dev = self._dev_ids.get(key)
        if dev is None and create:
            cur = self.conn.execute('INSERT OR IGNORE INTO devices(key) VALUES (?)', (key,))
            dev = cur.lastrowid if cur.rowcount else self.conn.execute(
                'SELECT id FROM devices WHERE key=?', (key,)).fetchone()[0]
            self._dev_ids[key] = dev
        return dev

    def size(self):
        pages = self.conn.execute('PRAGMA page_count').fetchone()[0]
        free = self.conn.execute('PRAGMA freelist_count').fetchone()[0]
        page_size = self.conn.execute('PRAGMA page_size').fetchone()[0]
        return (pages - free) * page_size

    def last_states(self, key):
        dev = self.dev_id(key, create=False)
        if dev is None:
            return {}
        rows = self.conn.execute(
            'SELECT kind, area, value FROM events e WHERE dev=? AND t_ms = '
            '(SELECT MAX(t_ms) FROM events WHERE dev=e.dev AND kind=e.kind AND area=e.area)', (dev,))
        return {_field(kind, area): bool(value) for kind, area, value in rows}


# ---------------------------------------------------------------------------
# Facade used by app.py
# ---------------------------------------------------------------------------

class History:

    def __init__(self, data_dir, on_event=None, db_name='history.db',
                 mono=time.monotonic, wall=time.time, start_thread=True):
        self.data_dir = data_dir
        self.settings_path = os.path.join(data_dir, 'settings.json')
        self.db = HistoryDB(':memory:' if db_name == ':memory:' else os.path.join(data_dir, db_name))
        self.on_event = on_event
        self._mono = mono
        self._wall = wall
        self._start_thread = start_thread
        self._lock = threading.Lock()
        self.grid = HeatGrid()
        self.clips = ClipRecorder()
        self.tracker = EventTracker()
        self._pending_events = []        # (key, event) not yet written
        self._last_detect = {}           # key -> t_ms a target was last seen
        self._last_count = {}            # key -> (t_ms, number of targets)
        self._settings = load_settings(self.settings_path)
        self.error = None if sqlite3 is not None else "This addon's Python has no sqlite3, so history is unavailable."
        self._opened = False
        self._stop = threading.Event()
        self._thread = None
        self._last_flush = mono()
        self._last_prune = 0.0

    # --- lifecycle ---

    def start(self):
        if self._settings['enabled']:
            self._ensure_open()

    def _ensure_open(self):
        if self._opened:
            return True
        if sqlite3 is None:
            return False
        try:
            with self.db.lock:
                self.db.open()
            self._opened = True
            self.error = None
        except Exception as e:
            self.error = f"Couldn't open the history database ({e})."
            print(f"History: {self.error}", flush=True)
            return False
        if self._start_thread and (self._thread is None or not self._thread.is_alive()):
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name='history-writer', daemon=True)
            self._thread.start()
        return True

    def close(self):
        """Write out everything still in memory (called on shutdown)."""
        self._stop.set()
        if self._opened:
            with self._lock:
                self.clips.close_all()
            self.flush_now()
            self.db.close()
            self._opened = False

    @property
    def enabled(self):
        return self._settings['enabled'] and self._opened

    def settings(self):
        return {'enabled': self._settings['enabled'], 'days': self._settings['days'],
                'available': sqlite3 is not None, 'error': self.error}

    def set_settings(self, enabled=None, days=None):
        new = dict(self._settings)
        if enabled is not None:
            new['enabled'] = bool(enabled)
        if days is not None:
            new['days'] = _clamp(days, *KEEP_DAYS_RANGE)
        error = save_settings(self.settings_path, new)
        if error:
            return dict(self.settings(), error=error)
        was = self._settings['enabled']
        self._settings = new
        if new['enabled'] and not was:
            self._ensure_open()
        elif was and not new['enabled'] and self._opened:
            with self._lock:
                self.clips.close_all()
            self.flush_now()
        return self.settings()

    # --- inputs (never raise) ---

    def on_targets(self, key, targets):
        if not key or not self.enabled:
            return
        try:
            wall = self._wall()
            if wall < MIN_VALID_EPOCH:
                return
            t_ms = int(wall * 1000)
            targets = [t for t in (targets or []) if isinstance(t, dict)]
            with self._lock:
                self.grid.add(key, targets, self._mono(), wall)
                self.clips.add(key, targets, t_ms)
                self._last_count[key] = (t_ms, len(targets))
                if targets:
                    self._last_detect[key] = t_ms
        except Exception as e:
            print(f"History: couldn't record targets ({e})", flush=True)

    def on_state(self, key, state, t_ms=None):
        """state: any of occupancy, area1..area4, light, reporting (bool-ish values).

        t_ms is when the change happened if the source knows (HA's last_changed),
        otherwise now. A change found by comparing with the stored value after a
        restart is flagged offline: it happened while the addon wasn't running.
        """
        if not key or not self.enabled or not isinstance(state, dict):
            return
        try:
            wall = self._wall()
            if wall < MIN_VALID_EPOCH:
                return
            now_ms = int(wall * 1000)
            if not isinstance(t_ms, (int, float)) or t_ms < MIN_VALID_EPOCH * 1000 or t_ms > now_ms + 60_000:
                t_ms = now_ms
            t_ms = int(t_ms)
            if not self.tracker.known(key):
                with self.db.lock:
                    stored = self.db.last_states(key) if self.db.conn else {}
                with self._lock:
                    if not self.tracker.known(key):
                        self.tracker.seed(key, stored)
            new_events = []
            with self._lock:
                for field, value, offline in self.tracker.update(key, state):
                    kind, area = _kind_area(field)
                    last_seen = self._last_count.get(key)
                    event = {
                        't_ms': t_ms, 'kind': kind, 'area': area, 'value': value,
                        'offline': offline,
                        'ntargets': last_seen[1] if last_seen and now_ms - last_seen[0] < 3000 else 0,
                        'last_detect_ms': None if value else self._last_detect.get(key),
                    }
                    self._pending_events.append((key, event))
                    if kind != 'reporting':
                        self.clips.trigger(key, event['t_ms'])
                    new_events.append(event)
            if self.on_event:
                for event in new_events:
                    try:
                        self.on_event(key, event)
                    except Exception:
                        pass
        except Exception as e:
            print(f"History: couldn't record a state change ({e})", flush=True)

    # --- writer ---

    def _run(self):
        while not self._stop.wait(TICK_S):
            try:
                now = self._mono()
                with self._lock:
                    self.clips.tick(int(self._wall() * 1000))
                if now - self._last_flush >= FLUSH_EVERY_S:
                    self.flush_now()
                if now - self._last_prune >= PRUNE_EVERY_S:
                    self.prune()
            except Exception as e:
                print(f"History: writer error ({e})", flush=True)

    def flush_now(self):
        if not self._opened:
            return
        with self._lock:
            bins = self.grid.take()
            events, self._pending_events = self._pending_events, []
            clips, self.clips.done = self.clips.done, []
        self._last_flush = self._mono()
        if not (bins or events or clips):
            return
        try:
            with self.db.lock:
                c = self.db.conn
                c.execute('BEGIN')
                try:
                    for (key, minute), cells in bins.items():
                        dev = self.db.dev_id(key)
                        hour = minute // HOUR * HOUR
                        rows_m = [(dev, MINUTE, minute, ix, iy, secs) for (ix, iy), secs in cells.items()]
                        rows_h = [(dev, HOUR, hour, ix, iy, secs) for (ix, iy), secs in cells.items()]
                        c.executemany('INSERT INTO heat VALUES (?,?,?,?,?,?) ON CONFLICT(dev,res,t,ix,iy) '
                                      'DO UPDATE SET secs = secs + excluded.secs', rows_m + rows_h)
                    for key, e in events:
                        c.execute('INSERT INTO events(dev, t_ms, kind, area, value, offline, last_detect_ms, '
                                  'ntargets) VALUES (?,?,?,?,?,?,?,?)',
                                  (self.db.dev_id(key), e['t_ms'], e['kind'], e['area'], int(e['value']),
                                   int(e['offline']), e['last_detect_ms'], e['ntargets']))
                    for key, t0, t1, frames in clips:
                        c.execute('INSERT INTO clips(dev, t0, t1, data) VALUES (?,?,?,?)',
                                  (self.db.dev_id(key), t0, t1, pack_frames(t0, frames)))
                    c.execute('COMMIT')
                except Exception:
                    c.execute('ROLLBACK')
                    raise
        except Exception as e:
            self.error = f"Couldn't save history ({e})."
            print(f"History: {self.error}", flush=True)

    def prune(self):
        self._last_prune = self._mono()
        if not self._opened:
            return
        now = self._wall()
        days = self._settings['days']
        try:
            with self.db.lock:
                c = self.db.conn
                c.execute('DELETE FROM heat WHERE res=? AND t < ?', (MINUTE, int(now - MINUTE_KEEP_S)))
                c.execute('DELETE FROM heat WHERE res=? AND t < ?', (HOUR, int(now - days * 86400)))
                c.execute('DELETE FROM events WHERE t_ms < ?', (int((now - days * 86400) * 1000),))
                c.execute('DELETE FROM clips WHERE t1 < ?', (int((now - min(days * 86400, CLIP_KEEP_S)) * 1000),))
                # Hard cap: drop the oldest day at a time until the file fits
                for _ in range(400):
                    if self.db.size() <= MAX_DB_BYTES:
                        break
                    oldest = c.execute('SELECT MIN(t) FROM heat WHERE res=?', (HOUR,)).fetchone()[0]
                    if oldest is None:
                        c.execute('DELETE FROM clips WHERE id IN (SELECT id FROM clips ORDER BY t0 LIMIT 100)')
                        c.execute('DELETE FROM events WHERE id IN (SELECT id FROM events ORDER BY t_ms LIMIT 1000)')
                        if not c.execute('SELECT 1 FROM clips LIMIT 1').fetchone() and \
                                not c.execute('SELECT 1 FROM events LIMIT 1').fetchone():
                            break
                        continue
                    cutoff = oldest + 86400
                    c.execute('DELETE FROM heat WHERE t < ?', (cutoff,))
                    c.execute('DELETE FROM events WHERE t_ms < ?', (cutoff * 1000,))
                    c.execute('DELETE FROM clips WHERE t1 < ?', (cutoff * 1000,))
                c.execute('PRAGMA incremental_vacuum')
        except Exception as e:
            print(f"History: couldn't prune ({e})", flush=True)

    # --- queries (socket handlers) ---

    def heatmap(self, key, t0, t1):
        """Seconds spent per cell between two times (unix seconds)."""
        out = {'cell': CELL_CM, 'res': MINUTE, 'from': t0, 'to': t1, 'cells': [], 'max': 0, 'total': 0}
        if not self._opened or not key:
            return out
        now = self._wall()
        t1 = min(t1, now + MINUTE)
        res = MINUTE if now - t0 <= MINUTE_KEEP_S + MINUTE else HOUR
        start = int(t0 // res * res)
        cells = {}
        with self.db.lock:
            dev = self.db.dev_id(key, create=False)
            if dev is not None:
                rows = self.db.conn.execute(
                    'SELECT ix, iy, SUM(secs) FROM heat WHERE dev=? AND res=? AND t>=? AND t<? GROUP BY ix, iy',
                    (dev, res, start, int(t1)))
                cells = {(ix, iy): secs for ix, iy, secs in rows}
        with self._lock:
            for cell, secs in self.grid.peek(key, start, t1).items():
                cells[cell] = cells.get(cell, 0.0) + secs
        out.update({
            'res': res, 'from': start, 'to': t1,
            'cells': [[ix, iy, round(s, 2)] for (ix, iy), s in cells.items() if s > 0],
            'max': round(max(cells.values()), 2) if cells else 0,
            'total': round(sum(cells.values()), 1),
        })
        return out

    def events(self, key, t0_ms, t1_ms, limit=500):
        out = []
        if self._opened and key:
            with self.db.lock:
                dev = self.db.dev_id(key, create=False)
                if dev is not None:
                    rows = self.db.conn.execute(
                        'SELECT t_ms, kind, area, value, offline, last_detect_ms, ntargets FROM events '
                        'WHERE dev=? AND t_ms>=? AND t_ms<? ORDER BY t_ms DESC, id DESC LIMIT ?',
                        (dev, int(t0_ms), int(t1_ms), int(limit)))
                    out = [{'t_ms': r[0], 'kind': r[1], 'area': r[2], 'value': bool(r[3]),
                            'offline': bool(r[4]), 'last_detect_ms': r[5], 'ntargets': r[6]} for r in rows]
            with self._lock:
                pending = [dict(e) for k, e in reversed(self._pending_events)
                           if k == key and t0_ms <= e['t_ms'] < t1_ms]
            # Newest first; for equal times the later one first (sort is stable)
            out = sorted(pending + out, key=lambda e: e['t_ms'], reverse=True)[:limit]
        return out

    def clip(self, key, t_ms):
        """The recorded frames around a moment, or None."""
        if not self._opened or not key:
            return None
        with self._lock:
            found = self.clips.open_clip(key, t_ms)
        if found:
            t0, t1, frames = found
            return {'t0': t0, 't1': t1, 'frames': [[t, [list(x) for x in targets]] for t, targets in frames]}
        with self.db.lock:
            dev = self.db.dev_id(key, create=False)
            if dev is None:
                return None
            row = self.db.conn.execute(
                'SELECT t0, t1, data FROM clips WHERE dev=? AND t0<=? AND t1>=? ORDER BY t0 DESC LIMIT 1',
                (dev, int(t_ms), int(t_ms))).fetchone()
        if not row:
            return None
        return {'t0': row[0], 't1': row[1], 'frames': unpack_frames(row[0], row[2])}

    def stats(self, key):
        out = dict(self.settings(), first_t=None, events=0, bytes=None)
        if not self._opened:
            return out
        with self.db.lock:
            out['bytes'] = self.db.size()
            dev = self.db.dev_id(key, create=False) if key else None
            if dev is not None:
                # Minute rows give the real start; once those are pruned (48 h) only whole hours are left
                first_m, first_h = self.db.conn.execute(
                    'SELECT (SELECT MIN(t) FROM heat WHERE dev=? AND res=60), '
                    '(SELECT MIN(t) FROM heat WHERE dev=? AND res=3600)', (dev, dev)).fetchone()
                if first_m is not None and (first_h is None or first_h >= first_m // HOUR * HOUR):
                    out['first_t'] = first_m
                else:
                    out['first_t'] = first_h
                out['events'] = self.db.conn.execute('SELECT COUNT(*) FROM events WHERE dev=?', (dev,)).fetchone()[0]
        with self._lock:
            if out['first_t'] is None and any(k == key for k, _ in self.grid._bins):
                out['first_t'] = min(m for k, m in self.grid._bins if k == key)
        return out

    def clear(self, key):
        if not key:
            return
        with self._lock:
            self.grid.forget(key)
            self.clips.forget(key)
            self.tracker.forget(key)
            self._pending_events = [(k, e) for k, e in self._pending_events if k != key]
            self._last_detect.pop(key, None)
            self._last_count.pop(key, None)
        if self._opened:
            with self.db.lock:
                dev = self.db.dev_id(key, create=False)
                if dev is not None:
                    c = self.db.conn
                    for table in ('heat', 'events', 'clips'):
                        c.execute(f'DELETE FROM {table} WHERE dev=?', (dev,))
                    c.execute('PRAGMA incremental_vacuum')
