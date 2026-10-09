"""Tests for the helpers behind firmware info, zone names, diagnostics and the log tap."""
import io
import json
import os
import queue
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

import device_info
import diagnostics
import ha_ws
import logtap
from utils import normalize_zone_names, is_fresh_target_frame, target_frame_mark

IEEE_ZHA = "0c:2a:6f:ff:fe:aa:39:2b"
IEEE_Z2M = "0x0c2a6ffffef6f6a7"


# ---------------------------------------------------------------------------
# ha_ws
# ---------------------------------------------------------------------------

class FakeHA:
    """A scripted HA websocket: answers each command type from `results`."""

    def __init__(self, results=None, auth_ok=True, noise=True):
        self.results = results or {}
        self.auth_ok = auth_ok
        self.noise = noise
        self.sent = []
        self.inbox = queue.Queue()
        self.inbox.put({"type": "auth_required"})
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.closed = True
        return False

    def send(self, raw):
        msg = json.loads(raw)
        self.sent.append(msg)
        if msg.get("type") == "auth":
            self.inbox.put({"type": "auth_ok" if self.auth_ok else "auth_invalid"})
            return
        if self.noise:   # an unrelated event and someone else's result first
            self.inbox.put({"type": "event", "id": 999, "event": {}})
            self.inbox.put({"type": "result", "id": msg["id"] + 1000, "success": True, "result": "wrong"})
        answer = self.results.get(msg["type"])
        if answer is None:
            return   # never answers: a timeout
        if isinstance(answer, Exception):
            self.inbox.put({"id": msg["id"], "type": "result", "success": False,
                            "error": {"code": "x", "message": str(answer)}})
        else:
            self.inbox.put({"id": msg["id"], "type": "result", "success": True,
                            "result": answer(msg) if callable(answer) else answer})

    def recv(self, timeout=None):
        try:
            return json.dumps(self.inbox.get(timeout=min(timeout or 1, 1)))
        except queue.Empty:
            raise TimeoutError from None


def use(monkeypatch, fake):
    seen = {}

    def connect(url, **kwargs):
        seen.update(kwargs, url=url)
        return fake
    monkeypatch.setattr(ha_ws, "ws_connect", connect)
    return seen


def test_request_returns_its_own_result(monkeypatch):
    fake = FakeHA({"zha/device": lambda m: {"ieee": m["ieee"], "lqi": 168}})
    seen = use(monkeypatch, fake)
    with ha_ws.HAConnection("tok", "ws://supervisor/core/websocket") as ha:
        assert ha.request("zha/device", ieee=IEEE_ZHA) == {"ieee": IEEE_ZHA, "lqi": 168}
    assert fake.closed
    assert seen["max_size"] is None
    assert seen["additional_headers"]["Authorization"] == "Bearer tok"


def test_failed_request_and_rejected_token(monkeypatch):
    use(monkeypatch, FakeHA({"zha/device": RuntimeError("Device not found")}))
    with ha_ws.HAConnection("tok", "ws://x") as ha:
        with pytest.raises(ha_ws.HAError, match="Device not found"):
            ha.request("zha/device", ieee="nope")
    use(monkeypatch, FakeHA(auth_ok=False))
    with pytest.raises(ha_ws.HAError, match="rejected"):
        with ha_ws.HAConnection("tok", "ws://x"):
            pass


def test_timeout_and_missing_token(monkeypatch):
    use(monkeypatch, FakeHA({}))
    with ha_ws.HAConnection("tok", "ws://x", timeout=0.3) as ha:
        with pytest.raises(ha_ws.HAError, match="Timed out"):
            ha.request("never/answered")
    with pytest.raises(ha_ws.HAError):
        with ha_ws.HAConnection("", "ws://x"):
            pass


def test_ieee_forms():
    for value in (IEEE_ZHA, "0x0c2a6ffffeaa392b", "zigbee2mqtt_0x0c2a6ffffeaa392b", "0C2A6FFFFEAA392B"):
        assert ha_ws.ieee_digits(value) == "0c2a6ffffeaa392b"
    assert ha_ws.ieee_digits("nope") is None
    assert ha_ws.ieee_digits(None) is None


def test_entity_roles_zha_and_z2m():
    zha = ha_ws.entity_roles([
        {"entity_id": "binary_sensor.stairs_occupancy", "unique_id": f"{IEEE_ZHA}-1-1030"},
        {"entity_id": "light.stairs", "unique_id": f"{IEEE_ZHA}-1"},
        {"entity_id": "sensor.stairs_illuminance", "unique_id": f"{IEEE_ZHA}-1-1024"},
        {"entity_id": "switch.stairs_mmwave_target_info_report", "unique_id": f"{IEEE_ZHA}-1-mmwave_target_info_report"},
        {"entity_id": "update.stairs_firmware", "unique_id": f"{IEEE_ZHA}-1-25-firmware_update"},
        {"entity_id": "sensor.stairs_rssi", "unique_id": f"{IEEE_ZHA}-1-0-rssi", "disabled_by": "integration"},
    ])
    assert zha == {"occupancy": "binary_sensor.stairs_occupancy", "light": "light.stairs",
                   "illuminance": "sensor.stairs_illuminance", "update": "update.stairs_firmware",
                   "target_report": "switch.stairs_mmwave_target_info_report"}
    z2m = ha_ws.entity_roles([
        {"entity_id": "binary_sensor.wash_area2occupancy", "unique_id": f"{IEEE_Z2M}_area2Occupancy_zigbee2mqtt"},
        {"entity_id": "binary_sensor.wash_occupancy", "unique_id": f"{IEEE_Z2M}_occupancy_zigbee2mqtt"},
        {"entity_id": "select.wash_mmwavetargetinforeport", "unique_id": f"{IEEE_Z2M}_mmWaveTargetInfoReport_zigbee2mqtt"},
        {"entity_id": "sensor.wash_linkquality", "unique_id": f"{IEEE_Z2M}_linkquality_zigbee2mqtt"},
    ])
    assert z2m["area2"] == "binary_sensor.wash_area2occupancy"
    assert z2m["occupancy"] == "binary_sensor.wash_occupancy"
    assert z2m["target_report"] == "select.wash_mmwavetargetinforeport"
    assert z2m["linkquality"] == "sensor.wash_linkquality"


def test_registry_cache_keeps_only_inovelli_and_caches(monkeypatch):
    calls = []
    devices = [
        {"id": "d1", "manufacturer": "Inovelli", "sw_version": "0x01030102",
         "connections": [["zigbee", IEEE_ZHA]], "identifiers": []},
        {"id": "d2", "manufacturer": "IKEA", "connections": [["zigbee", "00:00:00:00:00:00:00:02"]]},
    ]
    entities = [
        {"entity_id": "light.stairs", "unique_id": f"{IEEE_ZHA}-1", "device_id": "d1"},
        {"entity_id": "light.ikea", "unique_id": "x-1", "device_id": "d2"},
    ]

    def connect(url, **kwargs):
        calls.append(1)
        return FakeHA({"config/device_registry/list": devices, "config/entity_registry/list": entities})
    monkeypatch.setattr(ha_ws, "ws_connect", connect)
    cache = ha_ws.RegistryCache("tok", "ws://x")
    found = cache.lookup(IEEE_ZHA)
    assert found["device"]["id"] == "d1" and found["roles"] == {"light": "light.stairs"}
    assert cache.lookup("00:00:00:00:00:00:00:02") is None
    assert len(calls) == 1
    cache.lookup(IEEE_ZHA, force=True)
    assert len(calls) == 2


def test_registry_cache_without_token():
    assert ha_ws.RegistryCache("", "ws://x").lookup(IEEE_ZHA) is None


# ---------------------------------------------------------------------------
# device_info
# ---------------------------------------------------------------------------

def test_version_formatting():
    assert device_info.format_ota(16974082) == "0x01030102"
    assert device_info.format_ota("16974082") == "0x01030102"
    assert device_info.format_ota("0x01030102") == "0x01030102"
    assert device_info.format_ota(None) is None
    assert device_info.format_mmwave(100863491) == {"text": "6.3.14.3", "raw": "0x06030e03"}
    assert device_info.format_mmwave("None") is None
    assert device_info.format_mmwave("abc") == {"text": "abc", "raw": "abc"}


def test_z2m_info():
    info = device_info.z2m_info(
        IEEE_Z2M,
        {"software_build_id": "1.02", "date_code": "20250101"},
        {"mmWaveVersion": 100863491, "linkquality": 120, "last_seen": "2026-10-08T18:48:58.000Z",
         "update": {"installed_version": 16974082, "latest_version": 16974083, "state": "available"}},
        last_seen=5,
    )
    assert info["firmware"] == {"ota": "0x01030102", "build": "1.02", "date": "20250101"}
    assert info["mmwave_version"]["text"] == "6.3.14.3"
    assert info["link"] == {"lqi": 120, "rssi": None}
    assert info["update"]["available"] is True and info["update"]["latest"] == "0x01030103"
    assert info["area_trigger"] == "entity"
    assert info["last_seen"] > 1_700_000_000


def test_zha_info_and_registry():
    info = device_info.zha_info(IEEE_ZHA, {"lqi": "168", "rssi": -69, "sw_version": "0x01030102",
                                           "quirk_class": "inovelli.VZM32SN.VZM32SN",
                                           "last_seen": "2026-10-08T12:00:00"},
                                {"mmwave_version": "100863491", "sw_build_id": "None"})
    assert info["firmware"]["ota"] == "0x01030102" and info["firmware"]["build"] is None
    assert info["link"] == {"lqi": 168, "rssi": -69}
    assert info["area_trigger"] == "zha_event"
    registry = {"device": {"id": "dev1", "sw_version": "0x01030102"},
                "roles": {"occupancy": "binary_sensor.o", "update": "update.f"}}
    state = {"state": "off", "attributes": {"installed_version": "0x01030102", "latest_version": "0x01030102"}}
    device_info.apply_registry(info, registry, state)
    assert info["ha_device_id"] == "dev1"
    assert info["entities"]["occupancy"] == "binary_sensor.o"
    assert info["update"] == {"entity_id": "update.f", "installed": "0x01030102", "latest": "0x01030102",
                              "available": False, "in_progress": False}


def test_registry_sw_version_fills_in_build():
    info = device_info.empty_info("z2m")
    device_info.apply_registry(info, {"device": {"id": "d", "sw_version": "1.02"}, "roles": {}})
    assert info["firmware"]["build"] == "1.02" and info["firmware"]["ota"] is None


# ---------------------------------------------------------------------------
# Zone names and Z2M target freshness
# ---------------------------------------------------------------------------

def test_zone_names():
    names, err = normalize_zone_names({
        "mmwave_detection_areas:area2": "  Couch\n corner  ",
        "mmwave_stay_areas:area1": "B" * 60,
        "mmwave_detection_areas:area9": "nope",
        "bogus:area1": "nope",
        "mmwave_interference_areas:area3": "   ",
        "mmwave_interference_areas:area4": 5,
    })
    assert err is None
    assert names == {"mmwave_detection_areas:area2": "Couch corner", "mmwave_stay_areas:area1": "B" * 40}
    assert normalize_zone_names(None) == (None, None)
    assert normalize_zone_names({}) == (None, None)
    assert normalize_zone_names([1])[1]


def test_fresh_target_frames():
    raw = {"0": 29, "1": 47, "2": 18, "3": 5, "4": 1, "5": 0}
    assert is_fresh_target_frame(raw, None)
    # Z2M re-publishes the cached raw bytes with the next attribute change: same sequence number
    assert not is_fresh_target_frame(dict(raw, illuminance=40), target_frame_mark(raw))
    assert is_fresh_target_frame(dict(raw, **{"3": 6}), target_frame_mark(raw))
    t = [{"id": 1, "x": 0, "y": 100, "z": 0, "dop": 0}]
    assert is_fresh_target_frame({"mmwave_targets": t}, None)
    assert not is_fresh_target_frame({"mmwave_targets": list(t), "illuminance": 5}, target_frame_mark({"mmwave_targets": t}))
    assert is_fresh_target_frame({"mmwave_targets": []}, target_frame_mark({"mmwave_targets": t}))
    assert not is_fresh_target_frame({"illuminance": 5}, None)
    # Z2M 2.9 sends both; the sequence number decides
    both = dict(raw, mmwave_targets=t)
    assert not is_fresh_target_frame(dict(both, mmwave_targets=[]), target_frame_mark(both))


# ---------------------------------------------------------------------------
# Diagnostics and the log tap
# ---------------------------------------------------------------------------

def test_redaction():
    report = diagnostics.redact({
        "options": {"mqtt_password": "hunter2", "ha_token": "abc", "mqtt_username": "me", "empty_password": ""},
        "log": ["auth with Bearer eyJhbGciOiJ.secret.part ok", 'sent {"access_token": "xyz123"}'],
        "z2m": {"network_key": [1, 2, 3], "nested": [{"password": "p"}]},
    })
    assert report["options"] == {"mqtt_password": "[redacted]", "ha_token": "[redacted]",
                                 "mqtt_username": "me", "empty_password": ""}
    assert "eyJ" not in report["log"][0] and "[redacted]" in report["log"][0]
    assert "xyz123" not in report["log"][1]
    assert report["z2m"]["network_key"] == "[redacted]"
    assert report["z2m"]["nested"][0]["password"] == "[redacted]"


def test_bridge_summary_drops_network_key():
    s = diagnostics.z2m_bridge_summary({"version": "2.9.1", "config": {"advanced": {"network_key": [1]}},
                                        "coordinator": {"type": "EmberZNet", "meta": {"revision": "7.4"}}})
    assert s["version"] == "2.9.1" and "config" not in s and s["coordinator"]["type"] == "EmberZNet"


def test_build_report_shape():
    report = diagnostics.build_report(
        addon={"version": "4.1.0"}, options={"mqtt_password": "x"}, driver={}, device={}, zones={},
        settings={}, layout=None, zone_names=None, history={}, packets=[(1_800_000_000, '{"a":1}')],
        log_lines=[(1_800_000_000, "out", "hello")])
    assert report["type"] == "mmwave_vis_diagnostics"
    assert report["options"]["mqtt_password"] == "[redacted]"
    assert report["packets"][0]["data"] == '{"a":1}'
    assert report["log"][0].endswith("out hello")


def test_line_tap_keeps_whole_lines_and_passes_through():
    real = io.StringIO()
    ring = __import__("collections").deque(maxlen=3)
    tap = logtap.LineTap(real, ring, __import__("threading").Lock(), "out")
    assert tap.write("first ") == 6
    tap.write("line\nsecond\n\nthird")
    assert real.getvalue() == "first line\nsecond\n\nthird"
    assert [r[2] for r in ring] == ["first line", "second"]
    tap.write(" end\nfourth\nfifth\n")
    assert [r[2] for r in ring] == ["third end", "fourth", "fifth"]   # oldest dropped
    assert tap.getvalue() == real.getvalue()                           # attributes pass through
    tap.write("Bearer abc.def\n")
    assert ring[-1][2] == "Bearer [redacted]"


def test_line_tap_never_raises():
    class Broken:
        def write(self, s):
            raise OSError("closed")

        def flush(self):
            raise OSError("closed")
    tap = logtap.LineTap(Broken(), __import__("collections").deque(), __import__("threading").Lock(), "err")
    assert tap.write("x\n") == 2
    tap.flush()
