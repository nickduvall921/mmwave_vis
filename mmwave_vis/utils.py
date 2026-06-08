"""
Pure utility functions shared across the mmWave Visualizer backend.

These functions have no side effects and no dependencies on Flask, MQTT, or
configuration — making them straightforward to unit test in isolation.
"""

# ---------------------------------------------------------------------------
# Parameter validation whitelist
# ---------------------------------------------------------------------------

VALID_PARAMETERS = {
    'mmWaveDetectSensitivity': {
        'type': 'enum',
        'options': ['Low', 'Medium', 'High (default)']
    },
    'mmWaveDetectTrigger': {
        'type': 'enum',
        'options': ['Fast (0.2s, default)', 'Medium (1s)', 'Slow (5s)']
    },
    'mmWaveRoomSizePreset': {
        'type': 'enum',
        'options': ['Custom', 'Small', 'Medium', 'Large']
    },
    'mmWaveTargetInfoReport': {
        'type': 'enum',
        'options': ['Disable (default)', 'Enable']
    },
    'mmwaveControlWiredDevice': {
        'type': 'enum',
        'options': [
            'Disabled', 'Occupancy (default)', 'Vacancy',
            'Wasteful Occupancy', 'Mirrored Occupancy',
            'Mirrored Vacancy', 'Mirrored Wasteful Occupancy'
        ]
    },
    'mmWaveHoldTime':  {'type': 'int', 'min': 0, 'max': 28800},
    'mmWaveStayLife':  {'type': 'int', 'min': 0, 'max': 28800},
    'mmwave_detection_areas':    {'type': 'zone_composite'},
    'mmwave_interference_areas': {'type': 'zone_composite'},
    'mmwave_stay_areas':         {'type': 'zone_composite'},
}

VALID_ZONE_KEYS  = {'width_min', 'width_max', 'depth_min', 'depth_max', 'height_min', 'height_max'}
ZONE_COORD_RANGE = (-10000, 10000)


def validate_parameter(param, value):
    """Validate a parameter name and value against the whitelist.
    Returns (is_valid: bool, error_message: str | None).
    """
    if param not in VALID_PARAMETERS:
        return False, f"Unknown parameter: {param}"

    schema = VALID_PARAMETERS[param]
    ptype  = schema['type']

    if ptype == 'enum':
        if not isinstance(value, str) or value not in schema['options']:
            return False, f"Invalid value '{value}' for {param}. Allowed: {schema['options']}"
        return True, None

    elif ptype == 'int':
        try:
            int_val = int(value)
        except (ValueError, TypeError):
            return False, f"Parameter {param} requires an integer, got: {value}"
        if int_val < schema['min'] or int_val > schema['max']:
            return False, f"Parameter {param} value {int_val} out of range [{schema['min']}, {schema['max']}]"
        return True, None

    elif ptype == 'zone_composite':
        if not isinstance(value, dict):
            return False, f"Parameter {param} expects a dict, got: {type(value).__name__}"
        for area_key, area_val in value.items():
            if not area_key.startswith('area') or not area_key[4:].isdigit():
                return False, f"Invalid area key: {area_key}"
            if int(area_key[4:]) < 1 or int(area_key[4:]) > 4:
                return False, f"Area number out of range: {area_key}"
            if not isinstance(area_val, dict):
                return False, f"Area {area_key} value must be a dict"
            unknown = set(area_val.keys()) - VALID_ZONE_KEYS
            if unknown:
                return False, f"Unknown zone keys in {area_key}: {unknown}"
            for coord_key, coord_val in area_val.items():
                try:
                    v = int(coord_val)
                except (ValueError, TypeError):
                    return False, f"Zone coordinate {coord_key} must be an integer"
                if v < ZONE_COORD_RANGE[0] or v > ZONE_COORD_RANGE[1]:
                    return False, f"Zone coordinate {coord_key}={v} out of range"
        return True, None

    return False, f"Unknown parameter type: {ptype}"


def safe_int(value, default=0):
    """Safely convert a value to int, returning default on failure."""
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (ValueError, TypeError):
        return default


def parse_signed_16(payload, idx):
    """Parse a little-endian signed 16-bit integer from a ZCL byte payload dict.

    The payload uses string keys ("0", "1", ...) where each value is a byte (0-255).
    Two consecutive bytes at idx and idx+1 are combined into a signed 16-bit integer.
    """
    try:
        low  = int(payload.get(str(idx))     or 0)
        high = int(payload.get(str(idx + 1)) or 0)
        return int.from_bytes([low, high], byteorder='little', signed=True)
    except (ValueError, TypeError, OverflowError):
        return 0


def parse_signed_8(payload, idx):
    """Parse a signed 8-bit integer from a ZCL byte payload dict.

    The payload uses string keys ("0", "1", ...) where each value is a byte (0-255).
    The single byte at idx is interpreted as a signed 8-bit integer.
    """
    try:
        byte = int(payload.get(str(idx)) or 0)
        return int.from_bytes([byte & 0xFF], byteorder='little', signed=True)
    except (ValueError, TypeError, OverflowError):
        return 0
