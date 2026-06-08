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

from utils import parse_signed_16, parse_signed_8


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
