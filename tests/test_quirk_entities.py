"""The quirk's entities match Home Assistant's built-in VZM32-SN quirk, so switching between
the two keeps every entity. zha_quark/VZM32SN.py is loaded with stand-ins for zigpy and the
zha library that record what it declares; tests/fixtures/builtin_vzm32sn_entities.json lists
the built-in quirk's entities (from zha-quirks, see its "about")."""
import enum
import importlib
import json
import os
import sys
import types

import pytest

HERE = os.path.dirname(__file__)
QUIRK_DIR = os.path.join(HERE, '..', 'zha_quark')
BUILTIN = json.load(open(os.path.join(HERE, 'fixtures', 'builtin_vzm32sn_entities.json'), encoding='utf-8'))['entities']

# The Visualizer's own two, with the unique ids they've always had
OURS_ONLY = {('number', 'mmwave_stay_life'), ('switch', 'mmwave_target_info_report')}

# Entities the zha library made itself for an Inovelli switch up to zha 2.0 (Home
# Assistant before 2026.8), as (platform, unique id after "<ieee>-1-"); from zha 2.0.0's
# source, leaving out those limited to other models and relay click (not on the VZM32-SN)
ZHA_2_0_NATIVE = {
    ("number", "64561-auto_off_timer"), ("number", "64561-button_delay"),
    ("number", "64561-default_level_local"), ("number", "64561-default_level_remote"),
    ("number", "64561-dimming_speed_down_local"), ("number", "64561-dimming_speed_down_remote"),
    ("number", "64561-dimming_speed_up_local"), ("number", "64561-dimming_speed_up_remote"),
    ("number", "64561-double_tap_down_level"), ("number", "64561-double_tap_up_level"),
    ("number", "64561-led_color_when_off"), ("number", "64561-led_color_when_on"),
    ("number", "64561-led_intensity_when_off"), ("number", "64561-led_intensity_when_on"),
    ("number", "64561-load_level_indicator_timeout"), ("number", "64561-maximum_level"),
    ("number", "64561-minimum_level"), ("number", "64561-ramp_rate_off_to_on_local"),
    ("number", "64561-ramp_rate_off_to_on_remote"), ("number", "64561-ramp_rate_on_to_off_local"),
    ("number", "64561-ramp_rate_on_to_off_remote"), ("number", "64561-state_after_power_restored"),
    ("select", "64561-increased_non_neutral_output"), ("select", "64561-led_scaling_mode"),
    ("select", "64561-output_mode"),
    ("sensor", "64561"), ("sensor", "64561-overheated"),
    ("switch", "64561-aux_switch_scenes"), ("switch", "64561-binding_off_to_on_sync_level"),
    ("switch", "64561-disable_clear_notifications_double_tap"), ("switch", "64561-double_tap_down_enabled"),
    ("switch", "64561-double_tap_up_enabled"), ("switch", "64561-firmware_progress_led"),
    ("switch", "64561-invert_switch"), ("switch", "64561-local_protection"),
    ("switch", "64561-on_off_led_mode"), ("switch", "64561-smart_bulb_mode"),
}


# --- Stand-ins -----------------------------------------------------------------------

class _Value(str, enum.Enum):
    pass


EntityPlatform = _Value('EntityPlatform', {'SENSOR': 'sensor', 'SELECT': 'select', 'SWITCH': 'switch',
                                           'NUMBER': 'number'})
EntityType = _Value('EntityType', {'CONFIG': 'config', 'DIAGNOSTIC': 'diagnostic', 'STANDARD': 'standard'})


class Recorder:
    """QuirkBuilder that writes down each entity."""
    instances = []

    def __init__(self, *args, **kwargs):
        self.entities = []
        Recorder.instances.append(self)

    def _passthrough(self, *args, **kwargs):
        return self

    replaces_endpoint = replace_cluster_occurrences = device_automation_triggers = _passthrough
    add_to_registry = _passthrough

    def _add(self, platform, attribute_name, cluster_id, default_type, **kw):
        self.entities.append({
            'platform': platform.value if isinstance(platform, enum.Enum) else platform,
            'unique_id_suffix': kw.get('unique_id_suffix') or attribute_name,
            'attribute': attribute_name,
            'cluster': cluster_id,
            'entity_type': (kw.get('entity_type') or default_type).value,
            'translation_key': kw.get('translation_key'),
            'name': kw.get('fallback_name'),
            'min': kw.get('min_value'),
            'max': kw.get('max_value'),
            'options': [m.name for m in kw['enum_class']] if 'enum_class' in kw else None,
            'device_class': kw['device_class'].value if kw.get('device_class') else None,
            'unit': kw['unit'].value if kw.get('unit') else None,
        })
        return self

    def number(self, attribute_name, cluster_id, **kw):
        return self._add('number', attribute_name, cluster_id, EntityType.CONFIG, **kw)

    def switch(self, attribute_name, cluster_id, **kw):
        return self._add('switch', attribute_name, cluster_id, EntityType.CONFIG, **kw)

    def enum(self, attribute_name, enum_class, cluster_id, **kw):
        platform = kw.pop('entity_platform', EntityPlatform.SELECT)
        return self._add(platform, attribute_name, cluster_id, EntityType.CONFIG, enum_class=enum_class, **kw)

    def sensor(self, attribute_name, cluster_id, **kw):
        return self._add('sensor', attribute_name, cluster_id, EntityType.STANDARD, **kw)


def _module(name, **attrs):
    module = types.ModuleType(name)
    module.__dict__.update(attrs)
    return module


def _platform_entity(old):
    """zha's PlatformEntity: built from cluster handlers up to zha 1.3, from a cluster after."""
    class PlatformEntity:
        if old:
            def __init__(self, cluster_handlers, endpoint, device, *, entity_metadata=None):
                pass
        else:
            def __init__(self, endpoint, device, *, cluster, entity_metadata=None):
                pass
    return PlatformEntity


def load_quirk(monkeypatch, era):
    """Import zha_quark/VZM32SN.py as Home Assistant of `era` would; returns its entities.
    era 'new': zha 2.1+ (HA 2026.8+); 'native': zha 1.4-2.0; 'old': zha 1.3 and earlier."""
    zigpy_types = _module('zigpy.types', enum1=enum.IntEnum, enum8=enum.IntEnum)
    stubs = {
        'zigpy': _module('zigpy', types=zigpy_types),
        'zigpy.types': zigpy_types,
        'zigpy.profiles': _module('zigpy.profiles', zha=types.SimpleNamespace(
            DeviceType=types.SimpleNamespace(DIMMABLE_LIGHT=0x0101))),
        'zigpy.quirks': _module('zigpy.quirks'),
        'zigpy.quirks.v2': _module('zigpy.quirks.v2', QuirkBuilder=Recorder,
                                   ReportingConfig=lambda **kw: kw),
        'zigpy.quirks.v2.homeassistant': _module(
            'zigpy.quirks.v2.homeassistant', EntityPlatform=EntityPlatform, EntityType=EntityType,
            UnitOfTemperature=_Value('UnitOfTemperature', {'CELSIUS': '°C'})),
        'zigpy.quirks.v2.homeassistant.sensor': _module(
            'zigpy.quirks.v2.homeassistant.sensor',
            SensorDeviceClass=_Value('SensorDeviceClass', {'TEMPERATURE': 'temperature'}),
            SensorStateClass=_Value('SensorStateClass', {'MEASUREMENT': 'measurement'})),
        'zha': _module('zha'),
        'zha.application': _module('zha.application'),
        'zha.application.platforms': _module('zha.application.platforms',
                                             PlatformEntity=_platform_entity(era == 'old')),
        'zha.application.platforms.number': _module('zha.application.platforms.number'),
        # The package VZM32SN.py imports its clusters from
        'vzm32_quirk_under_test': _module('vzm32_quirk_under_test', __path__=[QUIRK_DIR],
                                          INOVELLI_AUTOMATION_TRIGGERS={},
                                          InovelliVZM32SNCluster=object,
                                          InovelliVZM32SNMMWaveCluster=object),
    }
    if era in ('native', 'old'):
        stubs['zha.application.platforms.number'].InovelliRemoteDimmingUpSpeed = type('Native', (), {})
    for name, module in stubs.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.delitem(sys.modules, 'vzm32_quirk_under_test.VZM32SN', raising=False)
    Recorder.instances.clear()
    importlib.import_module('vzm32_quirk_under_test.VZM32SN')
    return {(e['platform'], e['unique_id_suffix']): e for r in Recorder.instances for e in r.entities}


def builtin():
    return {(e['platform'], e['unique_id_suffix']): e for e in BUILTIN}


def test_the_entities_are_the_built_in_quirks_on_new_home_assistant(monkeypatch):
    ours, theirs = load_quirk(monkeypatch, 'new'), builtin()
    assert set(ours) - set(theirs) == OURS_ONLY
    assert set(theirs) - set(ours) == set()
    for key, expected in theirs.items():
        assert ours[key] == expected, key


def test_entities_zha_made_itself_are_left_to_it(monkeypatch):
    # Before Home Assistant 2026.8, ZHA made the shared Inovelli entities with these very
    # unique ids: declaring them too would give two entities one unique id
    ours, theirs = load_quirk(monkeypatch, 'native'), builtin()
    assert set(ours) & ZHA_2_0_NATIVE == set()
    assert set(ours) | ZHA_2_0_NATIVE == set(theirs) | OURS_ONLY
    for key in set(ours) - OURS_ONLY:
        assert ours[key] == theirs[key], key


def test_old_zha_adds_the_cluster_id_itself(monkeypatch):
    # zha 1.3 and earlier put "<cluster id>-" in a quirk entity's unique id itself
    ours, theirs = load_quirk(monkeypatch, 'old'), builtin()
    as_built = {(p, f"{e['cluster']}-{suffix}"): e for (p, suffix), e in ours.items()}
    assert set(as_built) & ZHA_2_0_NATIVE == set()
    assert set(as_built) - {(p, f'64562-{s}') for p, s in OURS_ONLY} == set(theirs) - ZHA_2_0_NATIVE


@pytest.mark.parametrize('era', ['new', 'native', 'old'])
def test_our_own_two_keep_their_unique_ids(monkeypatch, era):
    ours = load_quirk(monkeypatch, era)
    assert OURS_ONLY <= set(ours)
