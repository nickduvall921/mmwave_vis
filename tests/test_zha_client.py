"""
Tests for ZHAClient pure static methods.

These methods have no network/WebSocket/HA dependencies and can be called
directly without creating a ZHAClient instance.

Covered here:
  _translate_state  — converts raw HA entity state strings to frontend values
  _check_quirk_ok   — detects whether the custom ZHA quirk is installed
"""

import sys, os, types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'mmwave_vis'))

# zha_client.py imports websockets at module level, which is a runtime
# dependency not installed in the test environment.  Stub it out so the
# module loads — the methods under test don't use websockets at all.
_ws_stub = types.ModuleType("websockets")
_ws_sync  = types.ModuleType("websockets.sync")
_ws_sync_client = types.ModuleType("websockets.sync.client")
_ws_sync_client.connect = None
sys.modules.setdefault("websockets",             _ws_stub)
sys.modules.setdefault("websockets.sync",        _ws_sync)
sys.modules.setdefault("websockets.sync.client", _ws_sync_client)

from zha_client import (
    ZHAClient,
    CLUSTER_MMWAVE,
    _REVERSE_TARGET_INFO,
    _REVERSE_SENSITIVITY,
    _REVERSE_TRIGGER,
    _REVERSE_ROOM_SIZE,
    _REVERSE_WIRED_DEVICE,
)

translate    = ZHAClient._translate_state
quirk_ok     = ZHAClient._check_quirk_ok


# ===========================================================================
# _translate_state — enum params (reverse_map provided)
# ===========================================================================

class TestTranslateStateEnumIntegerInput:
    """
    ZHA number/uint8 entities report state as an integer string ("0", "1", ...).
    These should be looked up in the reverse_map and returned as display strings.
    """

    def test_target_info_disabled(self):
        assert translate("0", _REVERSE_TARGET_INFO) == "Disable (default)"

    def test_target_info_enabled(self):
        assert translate("1", _REVERSE_TARGET_INFO) == "Enable"

    def test_sensitivity_all_levels(self):
        assert translate("0", _REVERSE_SENSITIVITY) == "Low"
        assert translate("1", _REVERSE_SENSITIVITY) == "Medium"
        assert translate("2", _REVERSE_SENSITIVITY) == "High (default)"

    def test_trigger_all_speeds(self):
        assert translate("0", _REVERSE_TRIGGER) == "Fast (0.2s, default)"
        assert translate("1", _REVERSE_TRIGGER) == "Medium (1s)"
        assert translate("2", _REVERSE_TRIGGER) == "Slow (5s)"

    def test_room_size_all_presets(self):
        assert translate("0", _REVERSE_ROOM_SIZE) == "Custom"
        assert translate("1", _REVERSE_ROOM_SIZE) == "Small"
        assert translate("2", _REVERSE_ROOM_SIZE) == "Medium"
        assert translate("3", _REVERSE_ROOM_SIZE) == "Large"

    def test_float_string_accepted(self):
        # Some HA entities report "0.0" or "1.0" — int(float(...)) handles this
        assert translate("0.0", _REVERSE_TARGET_INFO) == "Disable (default)"
        assert translate("1.0", _REVERSE_TARGET_INFO) == "Enable"


class TestTranslateStateEnumDisplayStringInput:
    """
    ZHA select entities report state as the option display string directly
    (e.g. "Disable (default)", "Enable").  This is the bug that was fixed:
    the old code tried int(float(raw_state)) which raised ValueError and
    returned None, so the key was silently dropped from device_config payloads
    and the target-reporting banner never fired.

    These tests verify the fix: display strings are returned as-is.
    """

    def test_target_info_disable_string(self):
        assert translate("Disable (default)", _REVERSE_TARGET_INFO) == "Disable (default)"

    def test_target_info_enable_string(self):
        assert translate("Enable", _REVERSE_TARGET_INFO) == "Enable"

    def test_sensitivity_display_strings(self):
        assert translate("Low",            _REVERSE_SENSITIVITY) == "Low"
        assert translate("Medium",         _REVERSE_SENSITIVITY) == "Medium"
        assert translate("High (default)", _REVERSE_SENSITIVITY) == "High (default)"

    def test_trigger_display_strings(self):
        assert translate("Fast (0.2s, default)", _REVERSE_TRIGGER) == "Fast (0.2s, default)"
        assert translate("Medium (1s)",          _REVERSE_TRIGGER) == "Medium (1s)"
        assert translate("Slow (5s)",            _REVERSE_TRIGGER) == "Slow (5s)"

    def test_room_size_display_strings(self):
        assert translate("Custom", _REVERSE_ROOM_SIZE) == "Custom"
        assert translate("Small",  _REVERSE_ROOM_SIZE) == "Small"
        assert translate("Large",  _REVERSE_ROOM_SIZE) == "Large"

    def test_wired_device_display_strings(self):
        assert translate("Disabled",            _REVERSE_WIRED_DEVICE) == "Disabled"
        assert translate("Occupancy (default)", _REVERSE_WIRED_DEVICE) == "Occupancy (default)"
        assert translate("Vacancy",             _REVERSE_WIRED_DEVICE) == "Vacancy"


class TestTranslateStateEnumBadInput:
    """Unknown or unavailable states should return None gracefully."""

    def test_unknown_integer_returns_none(self):
        assert translate("99",  _REVERSE_TARGET_INFO) is None
        assert translate("-1",  _REVERSE_TARGET_INFO) is None

    def test_ha_unavailable_state(self):
        assert translate("unavailable", _REVERSE_TARGET_INFO) is None

    def test_ha_unknown_state(self):
        assert translate("unknown", _REVERSE_TARGET_INFO) is None

    def test_on_off_strings_rejected(self):
        # "on"/"off" are not valid display strings for any enum param
        assert translate("on",  _REVERSE_TARGET_INFO) is None
        assert translate("off", _REVERSE_TARGET_INFO) is None

    def test_empty_string_returns_none(self):
        assert translate("", _REVERSE_TARGET_INFO) is None

    def test_none_not_passed(self):
        # None is filtered upstream; but if it somehow reaches us, return None
        assert translate("None", _REVERSE_TARGET_INFO) is None


class TestTranslateStateNumeric:
    """Numeric params (hold time, stay life): no reverse_map, return raw int."""

    def test_integer_string(self):
        assert translate("300", None) == 300

    def test_zero(self):
        assert translate("0", None) == 0

    def test_large_value(self):
        assert translate("28800", None) == 28800

    def test_float_string_truncated(self):
        assert translate("28800.0", None) == 28800

    def test_negative(self):
        assert translate("-5", None) == -5

    def test_non_numeric_returns_none(self):
        assert translate("abc",         None) is None
        assert translate("unavailable", None) is None
        assert translate("unknown",     None) is None

    def test_empty_string_returns_none(self):
        assert translate("", None) is None


# ===========================================================================
# _check_quirk_ok — custom ZHA quirk detection
# ===========================================================================

def _dev(quirk_applied=False, endpoints=None):
    """Helper: build a minimal ZHA device dict."""
    d = {"quirk_applied": quirk_applied}
    if endpoints is not None:
        d["endpoints"] = endpoints
    return d

def _ep(*cluster_ids, key="input_cluster_ids"):
    """Helper: build an endpoint dict with the given cluster IDs."""
    return {key: list(cluster_ids)}


class TestCheckQuirkOkClusterDetection:
    """Cluster 0xFC32 presence is the strongest signal."""

    def test_mmwave_cluster_in_input_cluster_ids(self):
        dev = _dev(endpoints=[_ep(0, 3, CLUSTER_MMWAVE, key="input_cluster_ids")])
        assert quirk_ok(dev) is True

    def test_mmwave_cluster_in_in_cluster_ids(self):
        dev = _dev(endpoints=[_ep(0, 3, CLUSTER_MMWAVE, key="in_cluster_ids")])
        assert quirk_ok(dev) is True

    def test_mmwave_cluster_in_cluster_ids(self):
        dev = _dev(endpoints=[_ep(0, 3, CLUSTER_MMWAVE, key="cluster_ids")])
        assert quirk_ok(dev) is True

    def test_mmwave_cluster_in_second_endpoint(self):
        # Cluster may be on EP2, not EP1
        eps = [
            _ep(0, 3, key="input_cluster_ids"),                    # EP1: no mmWave
            _ep(0, CLUSTER_MMWAVE, key="input_cluster_ids"),       # EP2: has it
        ]
        assert quirk_ok(_dev(endpoints=eps)) is True

    def test_mmwave_cluster_absent_returns_false(self):
        dev = _dev(quirk_applied=False, endpoints=[_ep(0, 3, 6)])
        assert quirk_ok(dev) is False

    def test_wrong_cluster_id_not_enough(self):
        dev = _dev(quirk_applied=False, endpoints=[_ep(0, 3, 64561)])  # 0xFC31, not 0xFC32
        assert quirk_ok(dev) is False

    def test_empty_cluster_list(self):
        dev = _dev(quirk_applied=False, endpoints=[{"input_cluster_ids": []}])
        assert quirk_ok(dev) is False


class TestCheckQuirkOkFallback:
    """When cluster data is absent or empty, fall back to quirk_applied."""

    def test_no_endpoints_quirk_true(self):
        assert quirk_ok(_dev(quirk_applied=True)) is True

    def test_no_endpoints_quirk_false(self):
        assert quirk_ok(_dev(quirk_applied=False)) is False

    def test_empty_endpoints_list_quirk_true(self):
        assert quirk_ok(_dev(quirk_applied=True, endpoints=[])) is True

    def test_empty_endpoints_list_quirk_false(self):
        assert quirk_ok(_dev(quirk_applied=False, endpoints=[])) is False

    def test_endpoints_key_absent_quirk_true(self):
        # Device dict has no "endpoints" key at all
        assert quirk_ok({"quirk_applied": True}) is True

    def test_cluster_absent_quirk_true_is_ok(self):
        # No mmWave cluster but quirk_applied=True — some quirk is present;
        # accept it rather than show a false warning
        dev = _dev(quirk_applied=True, endpoints=[_ep(0, 3, 6)])
        assert quirk_ok(dev) is True

    def test_missing_quirk_applied_key_defaults_false(self):
        assert quirk_ok({}) is False

    def test_quirk_applied_none_treated_as_false(self):
        assert quirk_ok({"quirk_applied": None}) is False


class TestCheckQuirkOkEdgeCases:
    """Unusual but plausible ZHA response shapes."""

    def test_endpoints_is_none(self):
        # HA sometimes returns null for missing fields
        assert quirk_ok({"quirk_applied": False, "endpoints": None}) is False

    def test_endpoint_missing_cluster_key(self):
        # Endpoint exists but has no cluster ID key at all
        dev = _dev(quirk_applied=False, endpoints=[{"profile_id": 260}])
        assert quirk_ok(dev) is False

    def test_cluster_ids_is_none(self):
        dev = _dev(quirk_applied=False, endpoints=[{"input_cluster_ids": None}])
        assert quirk_ok(dev) is False

    def test_exact_cluster_id_boundary(self):
        # One below and one above CLUSTER_MMWAVE — neither should match
        assert quirk_ok(_dev(endpoints=[_ep(CLUSTER_MMWAVE - 1)])) is False
        assert quirk_ok(_dev(endpoints=[_ep(CLUSTER_MMWAVE + 1)])) is False


# ===========================================================================
# _check_quirk_ok — entity-registry marker detection (issue #46 hardening)
# ===========================================================================

def _entity(entity_id="light.some_light", unique_id="uid-1", original_name="Some light"):
    """Helper: build a minimal HA entity-registry entry."""
    return {
        "entity_id":     entity_id,
        "unique_id":     unique_id,
        "original_name": original_name,
    }

# The entry the Visualizer quirk produces on a real system
_MARKER_ENTITY = _entity(
    entity_id="switch.carpetstairs_mmwave_inovelli_switch_mmwave_target_info_report",
    unique_id="0c:2a:6f:ff:fe:aa:39:2b-1-mmwave_target_info_report",
    original_name="mmWave target info report",
)


class TestCheckQuirkOkEntityMarker:
    """
    When entity-registry entries are available, the presence of the
    Visualizer-only 'mmWave target info report' entity is decisive — in
    both directions.
    """

    def test_marker_present_wins_over_everything(self):
        # Even with quirk_applied=False and no cluster data, the marker
        # entity proves the Visualizer quirk created entities.
        dev = _dev(quirk_applied=False)
        assert quirk_ok(dev, [_MARKER_ENTITY]) is True

    def test_marker_absent_overrides_cluster_and_flag(self):
        # Issue #46 scenario: 0xFC32 is in the raw device signature and
        # quirk_applied is True (official quirk), but the Visualizer quirk
        # never loaded — must report False, not a false all-clear.
        dev = _dev(quirk_applied=True, endpoints=[_ep(0, 3, CLUSTER_MMWAVE)])
        other_entities = [
            _entity("light.master_bathroom_lights", "uid-light", "Light"),
            _entity("select.master_bathroom_lights_mmwave_sensitivity",
                    "uid-sens", "mmWave sensitivity"),
        ]
        assert quirk_ok(dev, other_entities) is False

    def test_marker_matched_by_unique_id_after_rename(self):
        # User renamed the entity_id and the display name — unique_id
        # still identifies it.
        renamed = _entity(
            entity_id="switch.stairs_radar_feed",
            unique_id="0c:2a:6f:ff:fe:aa:39:2b-1-mmwave_target_info_report",
            original_name=None,
        )
        assert quirk_ok(_dev(), [renamed]) is True

    def test_marker_matched_by_entity_id_suffix(self):
        entry = _entity(
            entity_id="switch.foo_mmwave_target_info_report",
            unique_id="",
            original_name="",
        )
        assert quirk_ok(_dev(), [entry]) is True

    def test_marker_matched_by_original_name(self):
        # original_name survives entity_id renames; spaces map to underscores
        entry = _entity(
            entity_id="switch.renamed_by_user",
            unique_id="",
            original_name="mmWave target info report",
        )
        assert quirk_ok(_dev(), [entry]) is True

    def test_none_fields_handled(self):
        entry = {"entity_id": None, "unique_id": None, "original_name": None}
        dev = _dev(quirk_applied=True, endpoints=[_ep(CLUSTER_MMWAVE)])
        # Non-empty entity list without the marker → False despite fallbacks
        assert quirk_ok(dev, [entry]) is False

    def test_non_dict_entries_skipped(self):
        assert quirk_ok(_dev(), [None, "garbage", _MARKER_ENTITY]) is True


class TestCheckQuirkOkEntityFallback:
    """
    No registry data (None or empty list) must fall back to the legacy
    cluster/quirk_applied heuristic — never a hard False from missing data.
    """

    def test_entities_none_falls_back_to_cluster(self):
        dev = _dev(quirk_applied=False, endpoints=[_ep(CLUSTER_MMWAVE)])
        assert quirk_ok(dev, None) is True

    def test_entities_none_falls_back_to_quirk_applied(self):
        assert quirk_ok(_dev(quirk_applied=True), None) is True

    def test_entities_empty_list_falls_back(self):
        # Empty list means "no data for this device", not "marker absent"
        dev = _dev(quirk_applied=True)
        assert quirk_ok(dev, []) is True

    def test_entities_none_and_nothing_else_is_false(self):
        assert quirk_ok(_dev(quirk_applied=False), None) is False
