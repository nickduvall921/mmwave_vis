"""The settings catalogue behind the Config tab: its contents, value checks, and the
conversions between Zigbee2MQTT's values and ZHA's raw attribute values."""
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'mmwave_vis'))

_ws_stub = types.ModuleType("websockets")
_ws_sync = types.ModuleType("websockets.sync")
_ws_sync_client = types.ModuleType("websockets.sync.client")
_ws_sync_client.connect = None
sys.modules.setdefault("websockets", _ws_stub)
sys.modules.setdefault("websockets.sync", _ws_sync)
sys.modules.setdefault("websockets.sync.client", _ws_sync_client)

import settings_catalog as sc
from settings_catalog import CATALOG, SETTINGS
from utils import validate_parameter
from zha_client import ZHAClient

QUIRK = os.path.join(os.path.dirname(__file__), '..', 'zha_quark', '__init__.py')


# ---------------------------------------------------------------------------
# The catalogue itself
# ---------------------------------------------------------------------------

def test_every_setting_is_complete():
    groups = {g['id'] for g in CATALOG['groups']}
    assert len(SETTINGS) == len(CATALOG['settings']), 'duplicate keys'
    for s in CATALOG['settings']:
        assert s['group'] in groups, s['key']
        assert s['title'] and s['help'], s['key']
        assert s['cluster'] in sc.CLUSTERS, s['key']
        assert s['attr'] == s['param'], s['key']      # Inovelli parameter numbers are the attribute ids
        assert s['control'] in ('select', 'toggle', 'number'), s['key']
        if not s.get('readOnly'):
            assert 'default' in s, s['key']
            ok, err = sc.validate(s['key'], s['default'])
            assert ok, (s['key'], err)


def test_every_group_has_settings():
    used = {s['group'] for s in CATALOG['settings']}
    assert used == {g['id'] for g in CATALOG['groups']}


def test_options_are_unique_and_toggles_have_two():
    for s in CATALOG['settings']:
        if 'options' not in s:
            assert s['min'] <= s['max'], s['key']
            continue
        values = [o['value'] for o in s['options']]
        raws = [o['raw'] for o in s['options']]
        assert len(set(values)) == len(values) and len(set(raws)) == len(raws), s['key']
        if s['control'] == 'toggle':
            assert len(s['options']) == 2 and s['on'] in values, s['key']


def test_risky_settings_explain_themselves():
    risky = {s['key'] for s in CATALOG['settings'] if s.get('risky')}
    assert {'switchType', 'outputMode', 'smartBulbMode', 'higherOutputInNonNeutral', 'localProtection'} <= risky
    # riskyTo: the values that need a confirmation (turning a lock off again never does)
    for s in CATALOG['settings']:
        for value in s.get('riskyTo', []):
            assert s.get('risky') and value in [o['value'] for o in s['options']], s['key']
    assert SETTINGS['outputMode']['riskyTo'] == ['Dimmer']       # dimming a non-dimmable load is the danger
    assert SETTINGS['localProtection']['riskyTo'] == ['Enabled']


def test_the_quirk_defines_every_attribute_zha_uses():
    """ZHA can only read or write attributes the quirk declares on its clusters."""
    quirk = open(QUIRK, encoding='utf-8').read()
    vzm32 = quirk[quirk.index('class InovelliVZM32SNCluster'):]
    for key in sc.zha_keys():
        s = SETTINGS[key]
        assert f"id=0x{s['attr']:04X}" in quirk, key
        if s['cluster'] == 'fc31' and s['attr'] in (0x17, 0x18):
            assert f"id=0x{s['attr']:04X}" in vzm32[:vzm32.index('class InovelliVZM32SNMMWaveCluster')], key


def test_the_detection_tab_and_the_catalogue_agree():
    """The Detection tab's mmWave controls send values the catalogue accepts, under the
    same labels the Config tab shows for them."""
    html = open(os.path.join(os.path.dirname(__file__), '..', 'mmwave_vis', 'templates', 'index.html'), encoding='utf-8').read()
    import re
    for key in ('mmWaveDetectSensitivity', 'mmWaveDetectTrigger', 'mmWaveRoomSizePreset', 'mmwaveControlWiredDevice'):
        block = re.search(rf'<select id="{key}" data-param="{key}">(.*?)</select>', html, re.S).group(1)
        labels = {o['value']: o.get('label', o['value']) for o in SETTINGS[key]['options']}
        options = re.findall(r'<option value="([^"]+)"( class="zha-only")?>([^<]*)</option>', block)
        for value, zha_only, label in options:
            assert sc.validate(key, value)[0], (key, value)
            assert label == labels[value], (key, value, label)
            # Options Zigbee2MQTT doesn't know are hidden there
            assert bool(zha_only) == bool(SETTINGS[key]['options'][[o['value'] for o in SETTINGS[key]['options']].index(value)].get('zhaOnly')), (key, value)
        # Every value the switch can report has an option
        assert {v for v, _, _ in options} == set(labels), key


# ---------------------------------------------------------------------------
# Checking values
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('key,value,ok', [
    ('dimmingSpeedUpRemote', 25, True),
    ('dimmingSpeedUpRemote', '25', True),
    ('dimmingSpeedUpRemote', 127, False),     # P1 has nothing to follow, so 127 isn't allowed
    ('dimmingSpeedUpLocal', 127, True),
    ('ledIntensityWhenOn', 101, False),
    ('defaultLed3IntensityWhenOn', 101, True),
    ('minimumLevel', 0, False),
    ('autoTimerOff', 32767, True),
    ('autoTimerOff', 32768, False),
    ('ledColorWhenOn', 2.5, False),
    ('ledColorWhenOn', True, False),
    ('switchType', 'Aux Switch', True),
    ('switchType', '3-Way Dumb Switch', False),   # not on the VZM32
    ('fanControlMode', 'Toggle', False),
    ('outputMode', 1, False),                  # enums take Z2M's labels
    ('invertSwitch', 'Yes', True),
    ('mmWaveStayLife', 36000, True),           # Inovelli's bedroom suggestion
    ('internalTemperature', 40, False),        # read-only
    ('powerType', 'Neutral', False),
    ('fanLedLevelType', 0, False),             # a fan switch setting, left out
])
def test_validate(key, value, ok):
    assert sc.validate(key, value)[0] is ok
    assert validate_parameter(key, value)[0] is ok


def test_read_only_message_names_the_setting():
    ok, err = sc.validate('overheat', 'No Alert')
    assert not ok and 'Overheated' in err


# ---------------------------------------------------------------------------
# Z2M value ↔ ZHA raw value
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('key,value,raw', [
    ('mmWaveDetectTrigger', 'Slow (5s)', 0),
    ('mmWaveDetectTrigger', 'Fast (0.2s, default)', 2),
    ('doubleTapClearNotifications', 'Disabled', 1),     # 1 turns the feature off
    ('invertSwitch', 'Yes', 1),
    ('outputMode', 'On/Off', 1),
    ('mmWaveRoomSizePreset', 'Preset 5', 5),
    ('ledColorWhenOn', 170, 170),
    ('ledColorWhenOn', '85', 85),
])
def test_to_raw(key, value, raw):
    assert sc.to_raw(key, value) == raw


@pytest.mark.parametrize('key,raw,value', [
    ('invertSwitch', '<Bool.true: 1>', 'Yes'),
    ('invertSwitch', 'Bool.false', 'No'),
    ('smartBulbMode', 'True', 'Smart Bulb Mode'),
    ('mmWaveDetectSensitivity', '1', 'Medium'),
    ('loadLevelIndicatorTimeout', '11', 'Stay On'),
    ('internalTemperature', '-3', -3),
    ('periodicPowerAndEnergyReports', '3600', 3600),
    ('mmWaveVersion', 100863491, 100863491),
    ('outputMode', 'None', None),                # the switch didn't answer
    ('buttonDelay', '42', None),                 # not one of its options
    ('notASetting', '1', None),
])
def test_from_raw(key, raw, value):
    assert sc.from_raw(key, raw) == value


def test_zha_reaches_everything_but_the_z2m_only_settings():
    assert sc.zha_address('ledColorWhenOn') == (0xFC31, 0x5F)
    assert sc.zha_address('mmWaveHoldTime') == (0xFC32, 0x72)
    assert sc.zha_address('otaImageType') is None
    assert sc.zha_address('mmwave_detection_areas') is None
    assert 'otaImageType' not in sc.zha_keys()
    assert sc.zha_keys(['otaImageType', 'invertSwitch', 'nope']) == ['invertSwitch']


def test_read_zha_reads_each_attribute_and_reports_failures():
    calls = []
    answers = {0x0B: '<Bool.true: 1>', 0x70: '2', 0x5F: 'None'}

    def request(kind, **kw):
        calls.append((kind, kw))
        if kw['attribute'] == 0x32:
            raise RuntimeError('unknown attribute')
        return answers[kw['attribute']]

    seen = []
    values, failed = sc.read_zha(request, 'aa:bb', ['invertSwitch', 'mmWaveDetectSensitivity', 'ledColorWhenOn', 'buttonDelay'],
                                 on_value=lambda k, v: seen.append(k))
    assert values == {'invertSwitch': 'Yes', 'mmWaveDetectSensitivity': 'High (default)'}
    assert sorted(failed) == ['buttonDelay', 'ledColorWhenOn']
    assert seen == ['mmWaveDetectSensitivity', 'invertSwitch']     # catalogue order
    kind, kw = next(c for c in calls if c[1]['attribute'] == 0x0B)
    assert kind == 'zha/devices/clusters/attributes/value'
    assert kw == {'ieee': 'aa:bb', 'endpoint_id': 1, 'cluster_id': 0xFC31, 'cluster_type': 'in',
                  'attribute': 0x0B, 'manufacturer': 0x122F}


def test_zha_only_values_are_refused_on_zigbee2mqtt():
    assert sc.validate('mmWaveRoomSizePreset', 'Preset 4')[0]
    assert sc.validate('mmWaveRoomSizePreset', 'Preset 4', stack='zha')[0]
    ok, error = sc.validate('mmWaveRoomSizePreset', 'Preset 4', stack='z2m')
    assert not ok and 'Zigbee2MQTT' in error
    assert sc.validate('mmWaveRoomSizePreset', 'Large', stack='z2m')[0]


def test_write_zha_sends_the_raw_value_and_waits():
    calls = []
    sc.write_zha(lambda kind, **kw: calls.append((kind, kw)), 'aa:bb', 'mmWaveDetectSensitivity', 'Medium')
    kind, kw = calls[0]
    assert kind == 'call_service'
    assert kw['domain'] == 'zha' and kw['service'] == 'set_zigbee_cluster_attribute'
    cluster, attr = sc.zha_address('mmWaveDetectSensitivity')
    assert kw['service_data'] == {'ieee': 'aa:bb', 'endpoint_id': 1, 'cluster_id': cluster, 'cluster_type': 'in',
                                  'attribute': attr, 'value': 1, 'manufacturer': 0x122F}


def test_read_zha_stops_asking_a_switch_that_doesnt_answer():
    calls = []

    def request(kind, **kw):
        calls.append(kw['attribute'])
        raise TimeoutError('no answer')

    keys = sc.zha_keys()[:10]
    reported = []
    values, failed = sc.read_zha(request, 'aa:bb', keys, on_failed=reported.append)
    assert values == {}
    assert len(calls) == sc.GIVE_UP_AFTER
    assert failed == keys and reported == keys


def test_read_zha_keeps_going_past_a_few_unknown_attributes():
    # "None" (an attribute the switch doesn't have) isn't the switch going quiet
    keys = sc.zha_keys()[:6]
    values, failed = sc.read_zha(lambda kind, **kw: 'None', 'aa:bb', keys)
    assert failed == keys


# ---------------------------------------------------------------------------
# ZHA writes go through the catalogue
# ---------------------------------------------------------------------------

class _Socket:
    def emit(self, *a, **kw):
        pass


def _client():
    client = ZHAClient('http://supervisor/core', 'token', _Socket())
    client._ieee = 'aa:bb:cc'
    sent = []
    client._send = sent.append
    return client, sent


@pytest.mark.parametrize('key,value,cluster,attr,raw', [
    ('mmWaveDetectTrigger', 'Fast (0.2s, default)', 0xFC32, 0x71, 2),
    ('mmwaveControlWiredDevice', 'Vacancy', 0xFC31, 0x6E, 2),
    ('ledIntensityWhenOff', '5', 0xFC31, 0x62, 5),
    ('doubleTapClearNotifications', 'Disabled', 0xFC31, 0x106, 1),
    ('quickStartTime', 30, 0xFC31, 0x17, 30),
])
def test_zha_write_sends_the_raw_value(key, value, cluster, attr, raw):
    client, sent = _client()
    assert client.update_parameter(key, value) is True
    (msg,) = sent
    assert msg['type'] == 'call_service' and msg['service'] == 'set_zigbee_cluster_attribute'
    data = msg['service_data']
    assert (data['cluster_id'], data['attribute'], data['value'], data['manufacturer']) == (cluster, attr, raw, 0x122F)
    assert data['ieee'] == 'aa:bb:cc' and data['endpoint_id'] == 1


def test_zha_refuses_what_it_cant_reach():
    client, sent = _client()
    assert client.update_parameter('otaImageType', 'mmWave (260)') is False
    assert client.update_parameter('notASetting', 1) is False
    assert sent == []
