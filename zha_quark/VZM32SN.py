"""VZM32-SN mmWave Switch/Dimmer Module.

The entities are the ones ZHA's built-in quirk for this switch creates (zhaquirks
VZM32SN, Home Assistant 2026.8 and later): the same platforms, unique ids, names and
options. So switching between the two quirks, either way, keeps every entity with its
entity id, history and the automations that use it. This quirk adds two entities of
its own, the mmWave target info report switch and the mmWave stay life number, and
passes the radar's reports on as zha_events (see __init__.py).

Unique ids are "<ieee>-1-<cluster id>-<attribute>", as ZHA itself made them for
Inovelli switches before the built-in quirks took over. How to get there depends on
the zha library Home Assistant runs:

- zha 2.1 and later (Home Assistant 2026.8+): a quirk entity's unique id is
  "<ieee>-1-<suffix>", so the suffix carries the cluster id, as the built-in quirk does.
- zha 1.4 to 2.0: the same, but ZHA still makes the entities shared by every Inovelli
  switch itself, with exactly these unique ids. Declaring them again would clash, so
  this quirk leaves them to ZHA and adds only the VZM32-SN's own.
- zha 1.3 and earlier: ZHA puts the cluster id in a quirk entity's unique id itself,
  so the suffix is the bare attribute name. ZHA makes the shared entities here too.
"""
import inspect

import zigpy.types as t
from zigpy.profiles import zha
from zigpy.quirks.v2 import QuirkBuilder, ReportingConfig
from zigpy.quirks.v2.homeassistant import EntityPlatform, EntityType, UnitOfTemperature
from zigpy.quirks.v2.homeassistant.sensor import SensorDeviceClass, SensorStateClass

from . import (
    INOVELLI_AUTOMATION_TRIGGERS,
    InovelliVZM32SNCluster,
    InovelliVZM32SNMMWaveCluster,
)

VZM32SN_CLUSTER_ID = 0xFC31   # 64561
MMWAVE_CLUSTER_ID = 0xFC32    # 64562


def _zha_makes_shared_entities() -> bool:
    """Whether this Home Assistant's ZHA makes the shared Inovelli entities itself
    (zha 2.0 and earlier). If it can't be told, assume it does: a missing entity is
    better than two entities with one unique id."""
    try:
        from zha.application.platforms import number as zha_number
    except Exception:  # noqa: BLE001
        return True
    return hasattr(zha_number, "InovelliRemoteDimmingUpSpeed")


def _zha_adds_cluster_id() -> bool:
    """Whether ZHA puts the cluster id in a quirk entity's unique id itself (zha 1.3
    and earlier, where entities are built from cluster handlers)."""
    try:
        from zha.application.platforms import PlatformEntity
        return "cluster_handlers" in inspect.signature(PlatformEntity.__init__).parameters
    except Exception:  # noqa: BLE001
        return False


ZHA_MAKES_SHARED_ENTITIES = _zha_makes_shared_entities()
ZHA_ADDS_CLUSTER_ID = _zha_adds_cluster_id()


def _suffix(attribute_name, cluster_id=VZM32SN_CLUSTER_ID):
    """The unique_id suffix that gives "<ieee>-1-<cluster id>[-<attribute>]"."""
    if ZHA_ADDS_CLUSTER_ID:
        return attribute_name
    return f"{cluster_id}" if attribute_name is None else f"{cluster_id}-{attribute_name}"


# --- Options of the select entities, named as in the built-in quirk --------------------

class InovelliOutputMode(t.enum1):
    """Inovelli output mode."""

    Dimmer = 0x00
    OnOff = 0x01


class InovelliLedScalingMode(t.enum1):
    """Inovelli led mode."""

    VZM31SN = 0x00
    LZW31SN = 0x01


class InovelliNonNeutralOutput(t.enum1):
    """Inovelli non neutral output selection."""

    Low = 0x00
    High = 0x01


class InovelliOverheatedState(t.enum8):
    """Inovelli overheat protection state."""

    Normal = 0x00
    Overheated = 0x01


class InovelliVZM32SwitchType(t.enum8):
    """Inovelli VZM32-SN switch type."""

    Single_Pole = 0x00
    Three_Way_AUX = 0x01


class InovelliLightOnPresenceBehavior(t.enum8):
    """Inovelli light on presence behavior."""

    Disabled = 0x00
    On_When_Occupied_Off_When_Unoccupied = 0x01
    Off_When_Vacant = 0x02
    On_When_Occupied = 0x03
    On_When_Vacant_Off_When_Occupied = 0x04
    On_When_Vacant = 0x05
    Off_When_Occupied = 0x06


class InovelliMmwaveRoomSizePreset(t.enum8):
    """Inovelli mmWave room size preset."""

    Custom = 0x00
    X_Small = 0x01
    Small = 0x02
    Medium = 0x03
    Large = 0x04
    X_Large = 0x05


class InovelliMmwaveSensitivity(t.enum8):
    """Inovelli mmWave detection sensitivity."""

    Low = 0x00
    Medium = 0x01
    High = 0x02


class InovelliMmwaveTargetSpeed(t.enum8):
    """Inovelli mmWave target speed."""

    Low = 0x00
    Medium = 0x01
    Fast = 0x02


# --- Entity helpers, made as the built-in quirk's InovelliQuirkBuilder makes them -------

def _number(builder, attribute_name, min_value, max_value, fallback_name, cluster_id=VZM32SN_CLUSTER_ID):
    return builder.number(
        attribute_name=attribute_name,
        cluster_id=cluster_id,
        endpoint_id=1,
        min_value=min_value,
        max_value=max_value,
        unique_id_suffix=_suffix(attribute_name, cluster_id),
        translation_key=attribute_name,
        fallback_name=fallback_name,
    )


def _switch(builder, attribute_name, fallback_name, translation_key=None, cluster_id=VZM32SN_CLUSTER_ID):
    return builder.switch(
        attribute_name=attribute_name,
        cluster_id=cluster_id,
        endpoint_id=1,
        unique_id_suffix=_suffix(attribute_name, cluster_id),
        translation_key=translation_key or attribute_name,
        fallback_name=fallback_name,
    )


def _select(builder, attribute_name, enum_class, fallback_name, cluster_id=VZM32SN_CLUSTER_ID):
    return builder.enum(
        attribute_name=attribute_name,
        enum_class=enum_class,
        cluster_id=cluster_id,
        endpoint_id=1,
        unique_id_suffix=_suffix(attribute_name, cluster_id),
        translation_key=attribute_name,
        fallback_name=fallback_name,
    )


# Entities every Inovelli switch shares on 0xFC31. ZHA made these itself before
# Home Assistant 2026.8, with the same unique ids.
SHARED_NUMBERS = (
    ("dimming_speed_up_remote", 0, 126, "Remote dimming up speed"),
    ("dimming_speed_up_local", 0, 127, "Local dimming up speed"),
    ("dimming_speed_down_remote", 0, 127, "Remote dimming down speed"),
    ("dimming_speed_down_local", 0, 127, "Local dimming down speed"),
    ("ramp_rate_off_to_on_remote", 0, 127, "Remote ramp rate off to on"),
    ("ramp_rate_off_to_on_local", 0, 127, "Local ramp rate off to on"),
    ("ramp_rate_on_to_off_remote", 0, 127, "Remote ramp rate on to off"),
    ("ramp_rate_on_to_off_local", 0, 127, "Local ramp rate on to off"),
    ("button_delay", 0, 9, "Button delay"),
    ("minimum_level", 1, 254, "Minimum load dimming level"),
    ("maximum_level", 2, 255, "Maximum load dimming level"),
    ("auto_off_timer", 0, 32767, "Automatic switch shutoff timer"),
    ("default_level_local", 0, 255, "Local default dimming level"),
    ("default_level_remote", 0, 255, "Remote default dimming level"),
    ("state_after_power_restored", 0, 255, "Start-up default dimming level"),
    ("load_level_indicator_timeout", 0, 11, "Load level indicator timeout"),
    ("led_color_when_on", 0, 255, "Default all LED on color"),
    ("led_color_when_off", 0, 255, "Default all LED off color"),
    ("led_intensity_when_on", 0, 100, "Default all LED on intensity"),
    ("led_intensity_when_off", 0, 100, "Default all LED off intensity"),
    ("double_tap_up_level", 2, 254, "Double tap up level"),
    ("double_tap_down_level", 0, 254, "Double tap down level"),
)
SHARED_SWITCHES = (
    ("invert_switch", "Invert switch", None),
    ("smart_bulb_mode", "Smart bulb mode", None),
    ("double_tap_up_enabled", "Double tap up enabled", None),
    ("double_tap_down_enabled", "Double tap down enabled", None),
    ("aux_switch_scenes", "Aux switch scenes", None),
    ("binding_off_to_on_sync_level", "Binding off to on sync level", None),
    ("local_protection", "Local protection", None),
    ("on_off_led_mode", "Only 1 LED mode", "one_led_mode"),
    ("firmware_progress_led", "Firmware progress LED", None),
    ("disable_clear_notifications_double_tap", "Disable config 2x tap to clear notifications", None),
)
SHARED_SELECTS = (
    ("output_mode", InovelliOutputMode, "Output mode"),
    ("led_scaling_mode", InovelliLedScalingMode, "LED scaling mode"),
    ("increased_non_neutral_output", InovelliNonNeutralOutput, "Increased non-neutral output"),
)
MMWAVE_NUMBERS = (
    ("mmwave_height_minimum_floor", -600, 600, "mmWave height minimum (floor)"),
    ("mmwave_height_maximum_ceiling", -600, 600, "mmWave height maximum (ceiling)"),
    ("mmwave_width_minimum_left", -600, 600, "mmWave width minimum (left)"),
    ("mmwave_width_maximum_right", -600, 600, "mmWave width maximum (right)"),
    ("mmwave_depth_minimum_near", 0, 600, "mmWave depth minimum (near)"),
    ("mmwave_depth_maximum_far", 0, 600, "mmWave depth maximum (far)"),
    ("mmwave_hold_time", 0, 4294967295, "mmWave hold time"),
)


builder = (
    QuirkBuilder("Inovelli", "VZM32-SN")
    .replaces_endpoint(1, device_type=zha.DeviceType.DIMMABLE_LIGHT)
    .replace_cluster_occurrences(InovelliVZM32SNMMWaveCluster)
    .replace_cluster_occurrences(InovelliVZM32SNCluster)
    .device_automation_triggers(INOVELLI_AUTOMATION_TRIGGERS)
)

if not ZHA_MAKES_SHARED_ENTITIES:
    for name, low, high, label in SHARED_NUMBERS:
        builder = _number(builder, name, low, high, label)
    for name, label, key in SHARED_SWITCHES:
        builder = _switch(builder, name, label, translation_key=key)
    for name, enum_class, label in SHARED_SELECTS:
        builder = _select(builder, name, enum_class, label)
    builder = builder.sensor(
        attribute_name="internal_temp_monitor",
        cluster_id=VZM32SN_CLUSTER_ID,
        endpoint_id=1,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        unit=UnitOfTemperature.CELSIUS,
        entity_type=EntityType.DIAGNOSTIC,
        unique_id_suffix=_suffix(None),
        translation_key="internal_temp_monitor",
        fallback_name="Internal temperature",
    )
    builder = builder.enum(
        attribute_name="overheated",
        enum_class=InovelliOverheatedState,
        cluster_id=VZM32SN_CLUSTER_ID,
        endpoint_id=1,
        entity_platform=EntityPlatform.SENSOR,
        entity_type=EntityType.DIAGNOSTIC,
        unique_id_suffix=_suffix("overheated"),
        translation_key="overheated",
        fallback_name="Overheat protection",
    )

# The VZM32-SN's own settings on 0xFC31
builder = _switch(builder, "remote_protection", "Remote protection")
builder = _select(builder, "switch_type", InovelliVZM32SwitchType, "Switch type")
builder = _select(builder, "light_on_presence_behavior", InovelliLightOnPresenceBehavior,
                  "Light on presence behavior")
builder = _select(builder, "mmwave_room_size_preset", InovelliMmwaveRoomSizePreset, "mmWave room size preset")

# The mmWave cluster (0xFC32)
for name, low, high, label in MMWAVE_NUMBERS:
    builder = _number(builder, name, low, high, label, cluster_id=MMWAVE_CLUSTER_ID)
builder = _select(builder, "mmwave_detect_sensitivity", InovelliMmwaveSensitivity, "mmWave sensitivity",
                  cluster_id=MMWAVE_CLUSTER_ID)
builder = _select(builder, "mmwave_detect_trigger", InovelliMmwaveTargetSpeed, "mmWave target speed",
                  cluster_id=MMWAVE_CLUSTER_ID)

# This quirk's own two. Their unique ids stay as they've always been
# ("<ieee>-1-mmwave_stay_life"), so the Visualizer and existing automations keep them.
VZM32SN = (
    builder
    .number(
        "mmwave_stay_life",
        MMWAVE_CLUSTER_ID,
        min_value=0,
        max_value=4294967295,
        step=1,
        entity_type=EntityType.CONFIG,
        translation_key="mmwave_stay_life",
        fallback_name="mmWave stay life",
    )
    # Live target position/area reports from the mmWave sensor (up to 1 s interval).
    # reporting_config makes ZHA treat this cluster as reportable, which forces
    # ClusterHandler.BIND = True and so a ZDP Bind_req during reconfigure.
    .switch(
        "mmwave_target_info_report",
        MMWAVE_CLUSTER_ID,
        off_value=0,
        on_value=1,
        entity_type=EntityType.CONFIG,
        translation_key="mmwave_target_info_report",
        fallback_name="mmWave target info report",
        reporting_config=ReportingConfig(
            min_interval=0,
            max_interval=900,
            reportable_change=1,
        ),
    )
    .add_to_registry()
)
