"""ZHAClient with several switches: every switch is recorded, only the one a page
is watching is sent to the page, and the switches' own entities are followed."""
import os
import sys
import types
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'mmwave_vis'))

_ws_stub = types.ModuleType("websockets")
_ws_sync = types.ModuleType("websockets.sync")
_ws_sync_client = types.ModuleType("websockets.sync.client")
_ws_sync_client.connect = None
sys.modules.setdefault("websockets", _ws_stub)
sys.modules.setdefault("websockets.sync", _ws_sync)
sys.modules.setdefault("websockets.sync.client", _ws_sync_client)

from zha_client import ZHAClient

A = "0c:2a:6f:ff:fe:aa:39:2b"
B = "0c:2a:6f:ff:fe:00:00:01"


def client_with_two(watch=A):
    c = ZHAClient("http://supervisor", "token", MagicMock(), history=MagicMock())
    c.device_list = {
        ieee: {"topic": f"zha/{ieee}", "ieee": ieee, "interference_zones": [], "detection_zones": [],
               "stay_zones": []}
        for ieee in (A, B)
    }
    c._ieee, c._topic = watch, f"zha/{watch}"
    c._clear_binding_warning = MagicMock()
    return c


def zha_event(ieee, command, args):
    return {"type": "event", "id": 1, "event": {"data": {"device_ieee": ieee, "command": command, "args": args}}}


def emitted(c, event):
    return [call.args[1] for call in c.socketio.emit.call_args_list if call.args[0] == event]


def target_args(tid, x, index=0, num=1):
    return {"id": tid, "x": x, "y": 100, "z": 0, "dop": 0, "target_index": index, "target_num": num}


def test_other_switch_targets_are_recorded_but_not_sent():
    c = client_with_two()
    c._handle_message(zha_event(B, "mmwave_target_info", target_args(1, 10)))
    c.history.on_targets.assert_called_once()
    assert c.history.on_targets.call_args.args[0] == f"ieee:{B}"
    assert emitted(c, "new_data") == []
    c._handle_message(zha_event(A, "mmwave_target_info", target_args(2, 20)))
    (sent,) = emitted(c, "new_data")
    assert sent["topic"] == f"zha/{A}" and sent["payload"]["targets"][0]["id"] == 2


def test_history_key_callback_is_used():
    # app.py passes its own history_key, which also remembers the topic for live timeline events
    seen = []
    c = ZHAClient("http://supervisor", "token", MagicMock(), history=MagicMock(),
                  history_key=lambda topic, ieee: seen.append((topic, ieee)) or f"key:{ieee}")
    c.device_list = {A: {"topic": f"zha/{A}", "ieee": A}}
    c._ieee, c._topic = A, f"zha/{A}"
    c._clear_binding_warning = MagicMock()
    c._handle_message(zha_event(A, "mmwave_target_info", target_args(1, 10)))
    assert c.history.on_targets.call_args.args[0] == f"key:{A}"
    assert seen == [(f"zha/{A}", A)]


def test_frame_flushes_on_its_last_target():
    c = client_with_two()
    c._handle_message(zha_event(A, "mmwave_target_info", target_args(1, 10, index=0, num=2)))
    assert emitted(c, "new_data") == []
    c._handle_message(zha_event(A, "mmwave_target_info", target_args(2, 20, index=1, num=2)))
    (sent,) = emitted(c, "new_data")
    assert sorted(t["id"] for t in sent["payload"]["targets"]) == [1, 2]
    c._accum_for(A).clear()


def test_batch_for_a_switch_no_longer_watched_is_not_sent():
    c = client_with_two()
    c._ieee, c._topic = B, f"zha/{B}"
    c._on_targets_ready(A, [{"id": 1, "x": 0, "y": 0, "z": 0, "dop": 0}])
    assert emitted(c, "new_data") == []
    c.history.on_targets.assert_called_once()


def test_other_switch_zone_report_is_cached_not_sent():
    c = client_with_two()
    area = {"width_min": 10, "width_max": 20, "depth_min": 30, "depth_max": 40, "height_min": 0, "height_max": 9}
    c._handle_message(zha_event(B, "mmwave_report_detection_area", {"count": 1, "area1": area}))
    assert c.device_list[B]["detection_zones"][0]["x_min"] == 10
    assert c.device_list[A]["detection_zones"] == []
    assert emitted(c, "detection_zones") == []


def test_binding_warning_only_cleared_by_the_watched_switch():
    c = client_with_two()
    c._handle_message(zha_event(B, "mmwave_anyone_in_area", {"area1": 0}))
    c._clear_binding_warning.assert_not_called()
    c._handle_message(zha_event(A, "mmwave_anyone_in_area", {"area1": 0}))
    c._clear_binding_warning.assert_called_once()


def test_unknown_device_events_are_ignored():
    c = client_with_two()
    c._handle_message(zha_event("aa:bb", "mmwave_target_info", target_args(1, 1)))
    c.history.on_targets.assert_not_called()


def test_area_events_stand_in_for_occupancy_without_an_entity():
    c = client_with_two()
    c._handle_message(zha_event(A, "mmwave_anyone_in_area", {"area1": 0, "area2": 1}))
    (payload,) = [p["payload"] for p in emitted(c, "device_config")]
    assert payload["occupancy"] is True and payload["mmwave_area2_occupancy"] is True
    state = c.history.on_state.call_args.args[1]
    assert state == {"area1": False, "area2": True, "occupancy": True}


def test_real_occupancy_entity_replaces_the_stand_in():
    c = client_with_two()
    c._entity_index = {"binary_sensor.a_occupancy": (A, "occupancy")}
    c._handle_message(zha_event(A, "mmwave_anyone_in_area", {"area1": 0, "area2": 1}))
    (payload,) = [p["payload"] for p in emitted(c, "device_config")]
    assert "occupancy" not in payload
    assert "occupancy" not in c.history.on_state.call_args.args[1]


def test_packets_are_kept_per_switch():
    c = client_with_two()
    for _ in range(200):
        c._handle_message(zha_event(B, "mmwave_anyone_in_area", {"area1": 0}))
    assert len(c.packets[B]) == 150 and A not in c.packets


# ---------------------------------------------------------------------------
# subscribe_entities
# ---------------------------------------------------------------------------

def entity_client():
    c = client_with_two()
    c._sub_ent = 9
    c._entity_index = {
        "binary_sensor.a_occupancy": (A, "occupancy"),
        "sensor.a_illuminance": (A, "illuminance"),
        "light.a": (A, "light"),
        "switch.a_mmwave_target_info_report": (A, "target_report"),
        "binary_sensor.b_occupancy": (B, "occupancy"),
        "sensor.b_illuminance": (B, "illuminance"),
    }
    return c


def entities_event(payload):
    return {"type": "event", "id": 9, "event": payload}


def test_initial_states_reach_the_page_and_history():
    c = entity_client()
    c._handle_message(entities_event({"a": {
        "binary_sensor.a_occupancy": {"s": "on", "a": {}, "c": "x", "lc": 1_800_000_000.5},
        "sensor.a_illuminance": {"s": "39.4", "a": {}, "c": "x", "lc": 1_800_000_000.0},
        "sensor.b_illuminance": {"s": "12", "a": {}, "c": "x", "lc": 1_800_000_000.0},
        "light.a": {"s": "unavailable", "a": {}, "c": "x", "lc": 1_800_000_000.0},
    }}))
    payloads = [p["payload"] for p in emitted(c, "device_config")]
    assert {"occupancy": True} in payloads and {"illuminance": 39} in payloads
    assert all(p != {"illuminance": 12} for p in payloads)     # B isn't watched
    calls = [call.args for call in c.history.on_state.call_args_list]
    assert (f"ieee:{A}", {"occupancy": "on"}, 1_800_000_000_500) in calls
    assert not any(args[1].get("light") for args in calls)   # unavailable skipped


def test_changes_and_attribute_only_updates():
    c = entity_client()
    c._handle_message(entities_event({"c": {
        "light.a": {"+": {"s": "on", "lc": 1_800_000_100.0, "c": "y"}},
        "sensor.a_illuminance": {"+": {"a": {"friendly_name": "x"}, "lu": 1.0}},
        "switch.a_mmwave_target_info_report": {"+": {"s": "off", "lu": 1_800_000_200.0}},
    }}))
    calls = [call.args for call in c.history.on_state.call_args_list]
    assert (f"ieee:{A}", {"light": "on"}, 1_800_000_100_000) in calls
    assert (f"ieee:{A}", {"reporting": "off"}, 1_800_000_200_000) in calls
    payloads = [p["payload"] for p in emitted(c, "device_config")]
    assert {"mmWaveTargetInfoReport": "Disable (default)"} in payloads
    assert not any("illuminance" in p for p in payloads)


def test_selecting_a_switch_sends_its_latest_entity_states():
    c = entity_client()
    c._handle_message(entities_event({"a": {"sensor.b_illuminance": {"s": "12", "lc": 1.0}}}))
    c.socketio.emit.reset_mock()
    c.query_areas = MagicMock()
    c._start_binding_timer = MagicMock()
    c.set_device(B, f"zha/{B}")
    assert {"illuminance": 12} in [p["payload"] for p in emitted(c, "device_config")]


def test_failed_subscription_is_logged(capsys):
    c = entity_client()
    c._handle_message({"type": "result", "id": 9, "success": False, "error": {"message": "nope"}})
    assert "subscription failed" in capsys.readouterr().out
