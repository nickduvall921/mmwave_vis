"""
Tests for room layouts: normalize_layout() checks what the page sends, and
LayoutStore keeps layouts in a JSON file in the addon's data folder.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'mmwave_vis'))

from utils import normalize_layout, layout_key
from layout_store import LayoutStore


ROOM = {'x_min': -300, 'x_max': 250, 'y_min': -20, 'y_max': 480}


# ===========================================================================
# normalize_layout
# ===========================================================================

def test_full_layout_round_trips():
    layout, error = normalize_layout({'x': 120, 'y': -15, 'rot': 90, 'room': ROOM})
    assert error is None
    assert layout == {'x': 120, 'y': -15, 'rot': 90, 'room': ROOM}


def test_missing_fields_default_to_origin_without_room():
    layout, error = normalize_layout({})
    assert error is None
    assert layout == {'x': 0, 'y': 0, 'rot': 0, 'room': None}


def test_coordinates_are_rounded_to_whole_cm():
    layout, _ = normalize_layout({'x': 10.6, 'y': -3.4, 'room': {**ROOM, 'x_min': -300.7}})
    assert layout['x'] == 11 and layout['y'] == -3
    assert layout['room']['x_min'] == -301


def test_rotation_wraps_into_0_to_360():
    assert normalize_layout({'rot': -90})[0]['rot'] == 270
    assert normalize_layout({'rot': 450})[0]['rot'] == 90
    assert normalize_layout({'rot': 12.345})[0]['rot'] == 12.3
    assert normalize_layout({'rot': 359.97})[0]['rot'] == 0


def test_unknown_keys_are_dropped():
    layout, error = normalize_layout({'x': 1, 'colour': 'red'})
    assert error is None
    assert 'colour' not in layout


def test_not_an_object_rejected():
    for bad in (None, [], 'layout', 5):
        layout, error = normalize_layout(bad)
        assert layout is None
        assert 'object' in error


def test_non_numbers_rejected():
    for bad in ('10', None, True, float('nan'), [1]):
        layout, error = normalize_layout({'x': bad})
        assert layout is None, bad
        assert 'x' in error


def test_out_of_range_rejected():
    layout, error = normalize_layout({'y': 10001})
    assert layout is None
    assert 'out of range' in error


def test_room_must_have_min_below_max():
    layout, error = normalize_layout({'room': {**ROOM, 'x_min': 300}})
    assert layout is None
    assert 'below' in error


def test_room_missing_a_side_rejected():
    room = dict(ROOM)
    del room['y_max']
    layout, error = normalize_layout({'room': room})
    assert layout is None
    assert 'room.y_max' in error


def test_room_must_be_object_or_null():
    assert normalize_layout({'room': None})[0]['room'] is None
    layout, error = normalize_layout({'room': [1, 2, 3, 4]})
    assert layout is None
    assert 'room' in error


# ===========================================================================
# LayoutStore
# ===========================================================================

def _layout(**kw):
    layout, error = normalize_layout(kw)
    assert error is None
    return layout


def test_set_get_and_persist(tmp_path):
    path = tmp_path / 'layouts.json'
    store = LayoutStore(str(path))
    assert store.get('zha/aa') is None

    assert store.set('zha/aa', _layout(x=50, rot=180, room=ROOM)) is None
    assert store.get('zha/aa')['x'] == 50

    # A fresh store reads the same file back
    again = LayoutStore(str(path))
    assert again.get('zha/aa') == _layout(x=50, rot=180, room=ROOM)


def test_get_returns_a_copy(tmp_path):
    store = LayoutStore(str(tmp_path / 'layouts.json'))
    store.set('t', _layout(room=ROOM))
    store.get('t')['room']['x_min'] = 0
    assert store.get('t')['room']['x_min'] == ROOM['x_min']


def test_none_removes_layout(tmp_path):
    path = tmp_path / 'layouts.json'
    store = LayoutStore(str(path))
    store.set('t', _layout(x=1))
    assert store.set('t', None) is None
    assert store.get('t') is None
    assert json.loads(path.read_text()) == {}


def test_bad_topic_rejected(tmp_path):
    store = LayoutStore(str(tmp_path / 'layouts.json'))
    assert store.set('', _layout()) is not None
    assert store.set(None, _layout()) is not None
    assert store.set('x' * 300, _layout()) is not None


def test_creates_missing_data_folder(tmp_path):
    path = tmp_path / 'nested' / 'data' / 'layouts.json'
    store = LayoutStore(str(path))
    store.set('t', _layout(x=5))
    assert path.exists()


def test_corrupt_file_starts_empty(tmp_path):
    path = tmp_path / 'layouts.json'
    path.write_text('{not json')
    store = LayoutStore(str(path))
    assert store.get('t') is None
    store.set('t', _layout(x=2))
    assert LayoutStore(str(path)).get('t')['x'] == 2


def test_invalid_entries_in_file_are_skipped(tmp_path):
    path = tmp_path / 'layouts.json'
    path.write_text(json.dumps({'good': {'x': 1}, 'bad': {'x': 'nope'}, 'worse': 4}))
    store = LayoutStore(str(path))
    assert store.get('good')['x'] == 1
    assert store.get('bad') is None
    assert store.get('worse') is None


def test_unwritable_folder_keeps_layouts_in_memory_and_says_so(tmp_path):
    blocker = tmp_path / 'blocker'
    blocker.write_text('a file where the data folder should be')
    store = LayoutStore(str(blocker / 'layouts.json'))
    assert store.set('t', _layout(x=9)) is None
    assert store.get('t')['x'] == 9
    assert store.write_error and 'lost when the addon restarts' in store.write_error


def test_write_error_clears_after_a_good_write(tmp_path):
    store = LayoutStore(str(tmp_path / 'layouts.json'))
    store.write_error = 'stale'
    store.set('t', _layout(x=1))
    assert store.write_error is None


# ===========================================================================
# layout_key
# ===========================================================================

def test_layout_key_prefers_ieee():
    assert layout_key('zigbee2mqtt/Hall Switch', '0x0C2A6FFFFEAA392B') == 'ieee:0x0c2a6ffffeaa392b'


def test_layout_key_falls_back_to_topic():
    assert layout_key('zigbee2mqtt/Hall Switch', None) == 'zigbee2mqtt/Hall Switch'
    assert layout_key('zigbee2mqtt/Hall Switch', '') == 'zigbee2mqtt/Hall Switch'


def test_no_temp_files_left_behind(tmp_path):
    store = LayoutStore(str(tmp_path / 'layouts.json'))
    for i in range(5):
        store.set('t', _layout(x=i))
    assert [p.name for p in tmp_path.iterdir()] == ['layouts.json']
