"""The switch's settings: what each one is, which values it takes and where ZHA keeps it.

static/settings.json is the catalogue. The page builds the Config tab from the same
file. Values are the ones Zigbee2MQTT uses (enum labels such as "Fast (0.2s, default)",
plain numbers otherwise), so Z2M takes them as they are; ZHA reads and writes the raw
attribute values, converted here.
"""
import json
import os
import re

CATALOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'settings.json')

CLUSTERS = {'fc31': 0xFC31, 'fc32': 0xFC32}
MANUFACTURER = 0x122F     # Inovelli; both clusters are manufacturer specific


def load(path=CATALOG_PATH):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


CATALOG = load()
SETTINGS = {s['key']: s for s in CATALOG['settings']}


def setting(key):
    return SETTINGS.get(key) if isinstance(key, str) else None


def _option(s, value=None, raw=None):
    for o in s.get('options') or ():
        if (value is not None and o['value'] == value) or (raw is not None and o['raw'] == raw):
            return o
    return None


def _as_int(value):
    """An integer from an int or a string of digits; None for anything else (bools, floats, '3.5')."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r'-?\d+', value.strip()):
        return int(value.strip())
    return None


def validate(key, value):
    """(ok, error) for writing `value` (as Zigbee2MQTT names it) to setting `key`."""
    s = setting(key)
    if s is None:
        return False, f"Unknown parameter: {key}"
    if s.get('readOnly'):
        return False, f"{s['title']} can't be changed; the switch only reports it"
    if s.get('options'):
        if not isinstance(value, str) or _option(s, value=value) is None:
            allowed = [o['value'] for o in s['options']]
            return False, f"Invalid value '{value}' for {key}. Allowed: {allowed}"
        return True, None
    n = _as_int(value)
    if n is None:
        return False, f"Parameter {key} requires an integer, got: {value}"
    if n < s['min'] or n > s['max']:
        return False, f"Parameter {key} value {n} out of range [{s['min']}, {s['max']}]"
    return True, None


def to_raw(key, value):
    """The attribute value ZHA writes for a (validated) Zigbee2MQTT value."""
    s = SETTINGS[key]
    if s.get('options'):
        return _option(s, value=value)['raw']
    return _as_int(value)


def from_raw(key, raw):
    """The Zigbee2MQTT-style value for an attribute value read through ZHA, or None."""
    s = setting(key)
    n = parse_zha_value(raw)
    if s is None or n is None:
        return None
    if s.get('options'):
        o = _option(s, raw=n)
        return o['value'] if o else None
    return n


# ZHA's attribute read returns str(value): "12", "-3", "True", "<Bool.true: 1>", "Bool.false",
# or "None" when the switch didn't answer
_BOOL_TEXT = {'true': 1, 'false': 0}


def parse_zha_value(raw):
    if isinstance(raw, bool):
        return int(raw)
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float) and raw.is_integer():
        return int(raw)
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    n = _as_int(text)
    if n is not None:
        return n
    m = re.search(r':\s*(-?\d+)>$', text)          # <Bool.true: 1>, <enum8.x: 3>
    if m:
        return int(m.group(1))
    word = text.rsplit('.', 1)[-1].lower()           # Bool.true, True
    return _BOOL_TEXT.get(word)


def zha_address(key):
    """(cluster id, attribute id) of a setting on ZHA, or None if ZHA can't reach it."""
    s = setting(key)
    if s is None or s.get('zha') is False:
        return None
    return CLUSTERS[s['cluster']], s['attr']


def zha_keys(keys=None):
    """The settings (all of them, or those of `keys`) that ZHA can read, in catalogue order."""
    wanted = None if keys is None else set(keys)
    return [s['key'] for s in CATALOG['settings']
            if s.get('zha') is not False and (wanted is None or s['key'] in wanted)]


GIVE_UP_AFTER = 3   # reads in a row that fail: the switch isn't answering, so stop asking


def read_zha(request, ieee, keys, on_value=None, on_failed=None):
    """Read settings from a switch through ZHA, one attribute per request.

    `request(type, **fields)` is an ha_ws.HAConnection.request. Each value read is
    passed to on_value(key, value) as it arrives (so a page can fill in while the rest
    is read), and each key that couldn't be to on_failed(key). After GIVE_UP_AFTER
    failed requests in a row the rest count as failed without asking: each one would
    wait for ZHA's timeout. Returns ({key: value}, [keys that couldn't be read]).
    """
    values, failed = {}, []
    in_a_row = 0

    def fail(key):
        failed.append(key)
        if on_failed:
            on_failed(key)

    for key in zha_keys(keys):
        if in_a_row >= GIVE_UP_AFTER:
            fail(key)
            continue
        cluster, attr = zha_address(key)
        try:
            raw = request('zha/devices/clusters/attributes/value', ieee=ieee, endpoint_id=1,
                          cluster_id=cluster, cluster_type='in', attribute=attr,
                          manufacturer=MANUFACTURER)
        except Exception:
            in_a_row += 1
            fail(key)
            continue
        in_a_row = 0
        value = from_raw(key, raw)
        if value is None:
            fail(key)
            continue
        values[key] = value
        if on_value:
            on_value(key, value)
    return values, failed
