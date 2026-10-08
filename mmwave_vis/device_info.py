"""What the page shows about a switch: firmware, mmWave module, link quality,
firmware updates and the Home Assistant entities that belong to it.

Both stacks end up in the same shape, built from whatever each one reports.
"""
import re
from datetime import datetime


def format_ota(value):
    """An OTA file version (int, decimal string or hex string) as 0x01030102."""
    if isinstance(value, bool) or value in (None, ''):
        return None
    try:
        n = int(value, 0) if isinstance(value, str) else int(value)
    except (TypeError, ValueError):
        return str(value)
    if n < 0 or n > 0xFFFFFFFF:
        return str(value)
    return f"0x{n:08x}"


def format_mmwave(value):
    """The mmWave module version (uint32, e.g. 100863491) as {'text': '6.3.1.3', 'raw': '0x06030103'}."""
    if isinstance(value, bool) or value in (None, '', 'None'):
        return None
    try:
        n = int(value, 0) if isinstance(value, str) else int(value)
    except (TypeError, ValueError):
        return {'text': str(value), 'raw': str(value)}
    if n <= 0 or n > 0xFFFFFFFF:
        return {'text': str(value), 'raw': str(value)}
    parts = [(n >> s) & 0xFF for s in (24, 16, 8, 0)]
    return {'text': '.'.join(str(p) for p in parts), 'raw': f"0x{n:08x}"}


def _epoch(value):
    """Seconds since the epoch from a number or an ISO 8601 string."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value / 1000 if value > 1e12 else value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
        except ValueError:
            return None
    return None


def _int_or_none(value):
    if isinstance(value, bool):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def empty_info(stack, ieee=None):
    return {
        'stack': stack,
        'ieee': ieee,
        'firmware': {'ota': None, 'build': None, 'date': None},
        'mmwave_version': None,
        'link': {'lqi': None, 'rssi': None},
        'last_seen': None,
        'quirk_class': None,
        'update': None,
        'ha_device_id': None,
        'entities': {},
        'area_trigger': 'entity' if stack == 'z2m' else 'zha_event',
    }


def apply_registry(info, registry, update_state=None):
    """Add what Home Assistant knows: device id, entities, update entity state."""
    if not registry:
        return info
    device = registry.get('device') or {}
    roles = dict(registry.get('roles') or {})
    info['ha_device_id'] = device.get('id') or info['ha_device_id']
    info['entities'] = roles
    if not info['firmware']['ota'] and device.get('sw_version'):
        sw = str(device['sw_version'])
        if re.fullmatch(r'0x[0-9a-fA-F]+|\d{6,}', sw):
            info['firmware']['ota'] = format_ota(sw)
        elif not info['firmware']['build']:
            info['firmware']['build'] = sw
    if update_state and roles.get('update'):
        info['update'] = update_from_state(roles['update'], update_state)
    return info


def update_from_state(entity_id, state):
    """{'entity_id', 'installed', 'latest', 'available', 'in_progress'} from an update entity's state."""
    attrs = (state or {}).get('attributes') or {}
    installed = attrs.get('installed_version')
    latest = attrs.get('latest_version')
    return {
        'entity_id': entity_id,
        'installed': format_ota(installed) if installed is not None else None,
        'latest': format_ota(latest) if latest is not None else None,
        'available': (state or {}).get('state') == 'on',
        'in_progress': bool(attrs.get('in_progress')),
    }


def z2m_info(ieee, bridge_entry=None, state=None, last_seen=None):
    """From Zigbee2MQTT's bridge/devices entry and the switch's latest state message."""
    info = empty_info('z2m', ieee)
    bridge_entry = bridge_entry or {}
    state = state or {}
    info['firmware']['build'] = bridge_entry.get('software_build_id') or None
    info['firmware']['date'] = bridge_entry.get('date_code') or None
    update = state.get('update')
    if isinstance(update, dict):
        info['firmware']['ota'] = format_ota(update.get('installed_version'))
        latest = update.get('latest_version')
        if latest is not None:
            info['update'] = {
                'entity_id': None,
                'installed': format_ota(update.get('installed_version')),
                'latest': format_ota(latest),
                'available': update.get('state') == 'available',
                'in_progress': update.get('state') == 'updating',
            }
    info['mmwave_version'] = format_mmwave(state.get('mmWaveVersion'))
    info['link']['lqi'] = _int_or_none(state.get('linkquality'))
    info['last_seen'] = _epoch(state.get('last_seen')) or last_seen
    return info


def zha_info(ieee, zha_dev=None, attrs=None):
    """From ZHA's device info (zha/device) and attributes read from the switch."""
    info = empty_info('zha', ieee)
    zha_dev = zha_dev or {}
    attrs = attrs or {}
    info['link']['lqi'] = _int_or_none(zha_dev.get('lqi'))
    info['link']['rssi'] = _int_or_none(zha_dev.get('rssi'))
    info['last_seen'] = _epoch(zha_dev.get('last_seen'))
    info['quirk_class'] = zha_dev.get('quirk_class') or None
    if zha_dev.get('sw_version'):
        info['firmware']['ota'] = format_ota(zha_dev['sw_version'])
    build = attrs.get('sw_build_id')
    if build not in (None, '', 'None'):
        info['firmware']['build'] = str(build)
    info['mmwave_version'] = format_mmwave(attrs.get('mmwave_version'))
    return info
