"""Per-switch display settings kept in the addon's data folder: room layouts
(where each switch sits in its room) and zone names.

None of this is sent to a switch; it only changes how the page draws things.
Entries are keyed by switch (see utils.layout_key) and shared by every browser
that opens the addon.
"""
import json
import os
import tempfile
import threading

from utils import normalize_layout

MAX_LAYOUTS = 500
MAX_TOPIC_LENGTH = 256


class LayoutStore:

    def __init__(self, path, normalize=normalize_layout, label='Layouts'):
        self.path = path
        self._normalize = normalize
        self._label = label
        self._lock = threading.Lock()
        self._layouts = {}
        # Why the last write didn't reach disk (layouts are then kept in memory
        # only and lost on restart), or None when it did
        self.write_error = None
        self._load()

    def _load(self):
        try:
            with open(self.path, encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            return
        except (OSError, ValueError) as e:
            print(f"{self._label}: couldn't read {self.path} ({e}), starting with none.", flush=True)
            return
        if not isinstance(data, dict):
            return
        for topic, layout in data.items():
            clean, _ = self._normalize(layout)
            if isinstance(topic, str) and clean:
                self._layouts[topic] = clean

    def get(self, topic):
        with self._lock:
            layout = self._layouts.get(topic)
            return json.loads(json.dumps(layout)) if layout else None

    def set(self, topic, layout):
        """Store an already-normalized layout, or remove it when layout is None.

        Returns an error message for a rejected layout, or None once it is stored.
        A stored layout that couldn't be written to disk sets `write_error`.
        """
        if not isinstance(topic, str) or not topic or len(topic) > MAX_TOPIC_LENGTH:
            return "Layout needs a switch"
        with self._lock:
            if layout is None:
                self._layouts.pop(topic, None)
            else:
                if topic not in self._layouts and len(self._layouts) >= MAX_LAYOUTS:
                    return "Too many saved layouts"
                self._layouts[topic] = layout
            self._write()
        return None

    def _write(self):
        # Caller holds the lock. Write to a temp file and rename so a crash
        # mid-write never leaves a half-written layouts.json behind.
        folder = os.path.dirname(self.path) or '.'
        tmp = None
        try:
            os.makedirs(folder, exist_ok=True)
            stem = os.path.splitext(os.path.basename(self.path))[0]
            fd, tmp = tempfile.mkstemp(dir=folder, prefix=f'.{stem}-', suffix='.tmp')
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(self._layouts, f, indent=1, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())   # on disk before the rename, so a power cut can't leave an empty file
            os.replace(tmp, self.path)
            tmp = None
            self.write_error = None
        except OSError as e:
            if not self.write_error:
                print(f"{self._label}: couldn't save to {self.path} ({e}), keeping them in memory only.", flush=True)
            self.write_error = (f"Couldn't write it to {self.path} ({e.strerror or e}), "
                                "so it will be lost when the addon restarts.")
        finally:
            if tmp and os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
