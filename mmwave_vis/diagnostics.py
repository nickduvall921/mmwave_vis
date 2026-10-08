"""The "Download diagnostics" file: everything needed to look into a bug report.

People attach this to public GitHub issues, so anything secret is removed here
before it leaves the addon, whether or not the page came through HA ingress.
"""
import re
import time
from datetime import datetime, timezone

from logtap import scrub

_SECRET_KEYS = re.compile(r'password|token|secret|network_key|pan_id|ext_pan_id|api_key|access', re.IGNORECASE)
MAX_STRING = 4000


def redact(value, _depth=0):
    """A deep copy of `value` with secret-looking keys blanked and tokens scrubbed from strings."""
    if _depth > 12:
        return '…'
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if isinstance(k, str) and _SECRET_KEYS.search(k):
                out[k] = '[redacted]' if v not in (None, '') else v
            else:
                out[k] = redact(v, _depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [redact(v, _depth + 1) for v in value]
    if isinstance(value, str):
        return scrub(value[:MAX_STRING])
    return value


def z2m_bridge_summary(bridge_info):
    """Only the harmless parts of Zigbee2MQTT's bridge/info (it also holds the network key)."""
    if not isinstance(bridge_info, dict):
        return None
    coordinator = bridge_info.get('coordinator') or {}
    return {
        'version': bridge_info.get('version'),
        'commit': bridge_info.get('commit'),
        'coordinator': {
            'type': coordinator.get('type'),
            'meta': {k: (coordinator.get('meta') or {}).get(k)
                     for k in ('revision', 'majorrel', 'minorrel', 'maintrel', 'product')},
        },
        'log_level': bridge_info.get('log_level'),
    }


def _iso(t):
    try:
        return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec='milliseconds')
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def build_report(*, addon, options, driver, device, zones, settings, layout, zone_names,
                 history, packets, log_lines, stack_versions=None):
    """Assemble the diagnostics dict. Every part is redacted on the way in."""
    return redact({
        'type': 'mmwave_vis_diagnostics',
        'version': 1,
        'generated': _iso(time.time()),
        'addon': addon,
        'options': options,
        'stack_versions': stack_versions,
        'driver': driver,
        'device': device,
        'zones': zones,
        'settings': settings,
        'layout': layout,
        'zone_names': zone_names,
        'history': history,
        'packets': [{'t': _iso(t), 'data': data} for t, data in (packets or [])],
        'log': [f"{_iso(t)} {label} {text}" for t, label, text in (log_lines or [])],
    })
