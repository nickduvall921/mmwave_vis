"""Keeps the addon's recent console output so it can go into a diagnostics file.

The addon logs with print(), and python-socketio's logging handler holds on to
whatever sys.stderr is when it's created, so install() has to run before
SocketIO() is built. The tap forwards everything to the real stream unchanged;
it only keeps a copy of the last lines.
"""
import re
import sys
import threading
import time
from collections import deque

MAX_LINES = 2000
MAX_LINE_LENGTH = 2000

# Tokens must never reach a diagnostics file, even if a debug line prints one
_SECRET_RE = re.compile(r'(Bearer\s+)\S+|("?(?:access_token|token|password)"?\s*[:=]\s*"?)[^"\s,}]+',
                        re.IGNORECASE)


def scrub(line):
    return _SECRET_RE.sub(lambda m: (m.group(1) or m.group(2)) + '[redacted]', line)


class LineTap:
    """A file-like wrapper that writes through to `stream` and keeps whole lines."""

    def __init__(self, stream, ring, lock, label):
        self._stream = stream
        self._ring = ring
        self._lock = lock
        self._label = label
        self._partial = ''

    def write(self, s):
        try:
            result = self._stream.write(s)
        except Exception:
            result = None
        try:
            self._keep(s)
        except Exception:
            pass
        return len(s) if result is None else result

    def _keep(self, s):
        if not isinstance(s, str) or not s:
            return
        with self._lock:
            text = self._partial + s
            parts = text.split('\n')
            self._partial = parts.pop()[-MAX_LINE_LENGTH:]
            now = time.time()
            for part in parts:
                if part.strip():
                    self._ring.append((now, self._label, scrub(part[:MAX_LINE_LENGTH])))

    def flush(self):
        try:
            self._stream.flush()
        except Exception:
            pass

    def __getattr__(self, name):
        # fileno, isatty, encoding, buffer, ... come from the real stream
        return getattr(self._stream, name)


_ring = deque(maxlen=MAX_LINES)
_lock = threading.Lock()
_installed = False


def install():
    """Tee sys.stdout and sys.stderr. Safe to call more than once."""
    global _installed
    if _installed:
        return
    sys.stdout = LineTap(sys.stdout, _ring, _lock, 'out')
    sys.stderr = LineTap(sys.stderr, _ring, _lock, 'err')
    _installed = True


def lines(limit=MAX_LINES):
    """The most recent lines, oldest first, as (unix time, 'out'|'err', text)."""
    with _lock:
        return list(_ring)[-limit:]
