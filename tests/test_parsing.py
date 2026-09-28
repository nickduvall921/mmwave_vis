"""
Tests for parse_signed_16() — the function that decodes little-endian signed
16-bit integers from raw ZCL byte packets sent by the mmWave sensor.

Background: the device sends raw Zigbee Cluster Library (ZCL) frames.
Each byte arrives as a separate key in a dict: {"0": 29, "1": 47, ...}.
Two consecutive bytes form a signed 16-bit integer (little-endian).
Range: -32768 to 32767.  Used for X/Y/Z coordinates (in millimetres).
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'mmwave_vis'))

from utils import parse_signed_16, parse_signed_8, decode_raw_targets, decode_raw_zones


def _payload(*bytes_):
    """Build a payload dict from a sequence of byte values, starting at key "0"."""
    return {str(i): b for i, b in enumerate(bytes_)}


# --- Positive values ---

def test_zero():
    p = _payload(0x00, 0x00)
    assert parse_signed_16(p, 0) == 0

def test_one():
    p = _payload(0x01, 0x00)
    assert parse_signed_16(p, 0) == 1

def test_255():
    # 0x00FF little-endian: low=255, high=0
    p = _payload(0xFF, 0x00)
    assert parse_signed_16(p, 0) == 255

def test_256():
    # 0x0100 little-endian: low=0, high=1
    p = _payload(0x00, 0x01)
    assert parse_signed_16(p, 0) == 256

def test_max_positive():
    # 32767 = 0x7FFF: low=0xFF, high=0x7F
    p = _payload(0xFF, 0x7F)
    assert parse_signed_16(p, 0) == 32767

def test_typical_x_coord():
    # 500 mm = 0x01F4: low=0xF4, high=0x01
    p = _payload(0xF4, 0x01)
    assert parse_signed_16(p, 0) == 500


# --- Negative values (two's complement) ---

def test_negative_one():
    # -1 = 0xFFFF little-endian: low=0xFF, high=0xFF
    p = _payload(0xFF, 0xFF)
    assert parse_signed_16(p, 0) == -1

def test_min_negative():
    # -32768 = 0x8000 little-endian: low=0x00, high=0x80
    p = _payload(0x00, 0x80)
    assert parse_signed_16(p, 0) == -32768

def test_negative_500():
    # -500 = 0xFE0C little-endian: low=0x0C, high=0xFE
    p = _payload(0x0C, 0xFE)
    assert parse_signed_16(p, 0) == -500


# --- Offset into payload ---

def test_reads_from_correct_offset():
    # Real packets have many bytes before the coordinate.
    # Build a payload where bytes 6 and 7 encode 1000.
    # 1000 = 0x03E8: low=0xE8, high=0x03
    p = _payload(0, 0, 0, 0, 0, 0, 0xE8, 0x03)
    assert parse_signed_16(p, 6) == 1000

def test_does_not_read_adjacent_bytes():
    # If offset=2 encodes -1 (0xFFFF) and offset=0 encodes 0, ensure only
    # the right pair is read.
    p = _payload(0x00, 0x00, 0xFF, 0xFF)
    assert parse_signed_16(p, 0) == 0
    assert parse_signed_16(p, 2) == -1


# --- Fault tolerance ---

def test_missing_key_returns_zero():
    # If the payload is shorter than expected, should not crash.
    p = {}
    assert parse_signed_16(p, 0) == 0

def test_partial_payload_returns_zero():
    p = {"0": 0xFF}  # only the low byte; high byte missing
    assert parse_signed_16(p, 0) == 255  # high defaults to 0 → unsigned 255

def test_none_value_treated_as_zero():
    p = {"0": None, "1": 0x01}
    assert parse_signed_16(p, 0) == 256  # None → 0, high=1 → 256

def test_string_bytes_accepted():
    # Bytes might arrive as strings from JSON parsing edge cases
    p = {"0": "0xF4", "1": "0x01"}  # "0xF4" → 244 (0xF4) → 500
    # int("0xF4") raises ValueError, so parse_signed_16 should return 0
    assert parse_signed_16(p, 0) == 0


# --- parse_signed_8: the mmWave target `id` field (1 byte, signed) ---
#
# Per Inovelli's corrected FC32 docs (and herdsman-converters PR #12284), each
# reportTargetInfo record is 9 bytes: x/y/z/dop as int16 + id as a signed int8.

def test_s8_zero():
    assert parse_signed_8(_payload(0x00), 0) == 0

def test_s8_one():
    assert parse_signed_8(_payload(0x01), 0) == 1

def test_s8_max_positive():
    # 127 = 0x7F is the largest positive signed int8
    assert parse_signed_8(_payload(0x7F), 0) == 127

def test_s8_negative_one():
    # 0xFF = -1 in two's complement
    assert parse_signed_8(_payload(0xFF), 0) == -1

def test_s8_min_negative():
    # 0x80 = -128, the most negative signed int8
    assert parse_signed_8(_payload(0x80), 0) == -128

def test_s8_reads_from_correct_offset():
    # id sits at offset+8 of a 9-byte record starting at offset 6 → key "14"
    p = _payload(*([0] * 14), 0x80)
    assert parse_signed_8(p, 14) == -128

def test_s8_missing_key_returns_zero():
    assert parse_signed_8({}, 0) == 0


# --- decode_raw_targets: legacy Z2M raw reportTargetInfo frames ---
#
# Frame captured from a live VZM32-SN (fw 0x01030102):
#   1d 2f 12 38 01 | 01 | b5 00 9e 00 08 00 c8 00 01
#   ZCL header      | n  | x=181 y=158 z=8 dop=200 id=1   (9-byte record)

LIVE_FRAME = _payload(0x1D, 0x2F, 0x12, 0x38, 0x01,
                      0x01,
                      0xB5, 0x00, 0x9E, 0x00, 0x08, 0x00, 0xC8, 0x00, 0x01)

def test_raw_targets_live_frame():
    assert decode_raw_targets(LIVE_FRAME) == [
        {"x": 181, "y": 158, "z": 8, "dop": 200, "id": 1},
    ]

def test_raw_targets_second_target_uses_9_byte_stride():
    # Two records back to back: the second starts at byte 15, not 16.
    p = _payload(0x1D, 0x2F, 0x12, 0x38, 0x01,
                 0x02,
                 0xB5, 0x00, 0x9E, 0x00, 0x08, 0x00, 0xC8, 0x00, 0x01,
                 0x38, 0xFF, 0x2C, 0x01, 0xF6, 0xFF, 0x00, 0x00, 0x02)
    assert decode_raw_targets(p) == [
        {"x": 181,  "y": 158, "z": 8,   "dop": 200, "id": 1},
        {"x": -200, "y": 300, "z": -10, "dop": 0,   "id": 2},
    ]

def test_raw_targets_truncated_frame_keeps_complete_records():
    # target_num says 2 but only one full record is present.
    p = dict(LIVE_FRAME)
    p["5"] = 2
    p["15"] = 0x38
    assert len(decode_raw_targets(p)) == 1

def test_raw_targets_zero_targets():
    assert decode_raw_targets(_payload(0x1D, 0x2F, 0x12, 0x38, 0x01, 0x00)) == []

def test_raw_targets_out_of_range_count_rejected():
    assert decode_raw_targets(_payload(0x1D, 0x2F, 0x12, 0x38, 0x01, 0xFF)) is None


# --- decode_raw_zones: legacy Z2M raw area reports (cmd 2/3/4) ---
#
# Four 12-byte areas follow the count byte; each is x/y/z min/max as int16.

def _area_bytes(x0, x1, y0, y1, z0, z1):
    out = []
    for v in (x0, x1, y0, y1, z0, z1):
        out += list((v & 0xFFFF).to_bytes(2, "little"))
    return out

def _area_report(count, *areas):
    return _payload(0x1D, 0x2F, 0x12, 0x39, 0x02, count, *[b for a in areas for b in _area_bytes(*a)])

EMPTY_AREA = (0, 0, 0, 0, -600, 600)   # firmware's unused-slot sentinel

def test_raw_zones_keep_slot_positions():
    # Area 2 is empty: area 3 must stay in slot 3, not move up to slot 2.
    p = _area_report(2, (-100, 100, 0, 300, -300, 300), EMPTY_AREA,
                        (50, 150, 200, 400, 0, 250), EMPTY_AREA)
    assert decode_raw_zones(p) == [
        {"x_min": -100, "x_max": 100, "y_min": 0, "y_max": 300, "z_min": -300, "z_max": 300},
        None,
        {"x_min": 50, "x_max": 150, "y_min": 200, "y_max": 400, "z_min": 0, "z_max": 250},
        None,
    ]

def test_raw_zones_ignore_count():
    # A count of 1 still reads all four slots, like Z2M's converter.
    p = _area_report(1, EMPTY_AREA, (10, 20, 30, 40, 50, 60), EMPTY_AREA, EMPTY_AREA)
    assert decode_raw_zones(p)[1] == {"x_min": 10, "x_max": 20, "y_min": 30, "y_max": 40, "z_min": 50, "z_max": 60}

def test_raw_zones_all_empty():
    assert decode_raw_zones(_area_report(4, EMPTY_AREA, EMPTY_AREA, EMPTY_AREA, EMPTY_AREA)) == [None] * 4

def test_raw_zones_truncated_payload():
    p = _area_report(4, (1, 2, 3, 4, 5, 6))
    assert decode_raw_zones(p) == [{"x_min": 1, "x_max": 2, "y_min": 3, "y_max": 4, "z_min": 5, "z_max": 6}]


def test_raw_zones_reject_out_of_range_count():
    # Live switches always send count 4; anything past 4 is not an area report
    assert decode_raw_zones(_area_report(0xFF, (1, 2, 3, 4, 5, 6))) is None
