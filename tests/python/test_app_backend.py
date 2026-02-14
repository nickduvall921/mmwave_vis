import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ["SWITCH_STUDIO_TEST_MODE"] = "1"

from switch_studio import app as app_module  # noqa: E402


def _make_device(name, topic):
    return {
        "friendly_name": name,
        "topic": topic,
        "interference_zones": [],
        "detection_zones": [],
        "stay_zones": [],
        "zone_config": {"x_min": -400, "x_max": 400, "y_min": 0, "y_max": 600},
        "last_config": {},
        "last_update": 0,
        "last_seen": 0,
    }


def _int16_to_le_bytes(value):
    raw = int(value).to_bytes(2, byteorder="little", signed=True)
    return raw[0], raw[1]


class AppBackendTests(unittest.TestCase):
    def setUp(self):
        with app_module.device_list_lock:
            app_module.device_list.clear()
        with app_module.session_topics_lock:
            app_module.session_topics.clear()
        with app_module.session_reporting_auto_off_lock:
            app_module.session_reporting_auto_off.clear()
        self.clients = []

    def tearDown(self):
        for client in self.clients:
            try:
                client.disconnect()
            except Exception:
                pass

    def _client(self):
        client = app_module.socketio.test_client(app_module.app)
        self.clients.append(client)
        return client

    def test_as_int_or_none_parsing(self):
        self.assertEqual(app_module._as_int_or_none(10), 10)
        self.assertEqual(app_module._as_int_or_none(10.9), 10)
        self.assertEqual(app_module._as_int_or_none(" 55 "), 55)
        self.assertEqual(app_module._as_int_or_none("12.7"), 12)
        self.assertIsNone(app_module._as_int_or_none(""))
        self.assertIsNone(app_module._as_int_or_none("nan-value"))

    def test_build_force_sync_payload_uses_readable_schema_fields(self):
        fake_schema = {
            "fields": [
                {"name": "occupancy", "can_read": True},
                {"name": "mmWaveVersion", "can_read": True},
                {"name": "write_only_field", "can_read": False},
                {"name": None, "can_read": True},
                "invalid",
            ]
        }
        with patch.object(app_module.schema_service, "get_schema", return_value=fake_schema):
            payload = app_module.build_force_sync_payload()
        self.assertEqual(payload, {"occupancy": "", "mmWaveVersion": "", "state": "", "brightness": ""})

    def test_resolve_target_reporting_value_uses_schema_enum(self):
        fake_schema = {
            "fields": [
                {
                    "name": "mmWaveTargetInfoReport",
                    "values": ["Disable (default)", "Enable"],
                }
            ]
        }
        with patch.object(app_module.schema_service, "get_schema", return_value=fake_schema):
            self.assertEqual(app_module.resolve_target_reporting_value(False), "Disable (default)")
            self.assertEqual(app_module.resolve_target_reporting_value(True), "Enable")

    def test_update_parameter_routes_to_each_sessions_selected_topic(self):
        published = []

        def fake_publish(topic, payload, origin, sid=None):
            published.append({"topic": topic, "payload": payload, "origin": origin, "sid": sid})
            return True, 0

        client_a = self._client()
        client_b = self._client()

        client_a.get_received()
        client_b.get_received()

        with patch.object(app_module, "publish_json", side_effect=fake_publish):
            client_a.emit("change_device", "zigbee2mqtt/device_a")
            client_b.emit("change_device", "zigbee2mqtt/device_b")
            client_a.get_received()
            client_b.get_received()

            client_a.emit("update_parameter", {"param": "mmWaveHoldTime", "value": 30, "request_id": "req-a"})
            client_b.emit("update_parameter", {"param": "mmWaveHoldTime", "value": 45, "request_id": "req-b"})

        self.assertEqual(len(published), 2)
        self.assertEqual(published[0]["topic"], "zigbee2mqtt/device_a/set")
        self.assertEqual(published[0]["payload"], {"mmWaveHoldTime": 30})
        self.assertEqual(published[1]["topic"], "zigbee2mqtt/device_b/set")
        self.assertEqual(published[1]["payload"], {"mmWaveHoldTime": 45})

        results_a = [event["args"][0] for event in client_a.get_received() if event["name"] == "command_result"]
        results_b = [event["args"][0] for event in client_b.get_received() if event["name"] == "command_result"]

        self.assertTrue(results_a)
        self.assertTrue(results_b)
        self.assertEqual(results_a[-1]["status"], "sent")
        self.assertEqual(results_a[-1]["topic"], "zigbee2mqtt/device_a")
        self.assertEqual(results_b[-1]["status"], "sent")
        self.assertEqual(results_b[-1]["topic"], "zigbee2mqtt/device_b")

    def test_update_parameter_without_selected_device_returns_error(self):
        client = self._client()
        client.get_received()
        client.emit("update_parameter", {"param": "mmWaveHoldTime", "value": 30, "request_id": "req-no-device"})
        results = [event["args"][0] for event in client.get_received() if event["name"] == "command_result"]
        self.assertTrue(results)
        self.assertEqual(results[-1]["status"], "error")
        self.assertEqual(results[-1]["message"], "No device selected")

    def test_set_target_reporting_publishes_immediately(self):
        published = []

        def fake_publish(topic, payload, origin, sid=None):
            published.append({"topic": topic, "payload": payload, "origin": origin, "sid": sid})
            return True, 0

        client = self._client()
        client.get_received()

        with patch.object(app_module, "publish_json", side_effect=fake_publish):
            client.emit("change_device", "zigbee2mqtt/device_a")
            client.get_received()
            client.emit("set_target_reporting", {"enabled": True, "request_id": "report-on"})

        self.assertEqual(len(published), 1)
        self.assertEqual(published[0]["topic"], "zigbee2mqtt/device_a/set")
        self.assertEqual(published[0]["origin"], "set_target_reporting")
        self.assertIn("mmWaveTargetInfoReport", published[0]["payload"])

        results = [event["args"][0] for event in client.get_received() if event["name"] == "command_result"]
        matching = [result for result in results if result.get("action") == "set_target_reporting"]
        self.assertTrue(matching)
        self.assertEqual(matching[-1]["status"], "sent")
        self.assertEqual(matching[-1]["payload"]["enabled"], True)

    def test_set_basic_control_publishes_state_and_brightness(self):
        published = []

        def fake_publish(topic, payload, origin, sid=None):
            published.append({"topic": topic, "payload": payload, "origin": origin, "sid": sid})
            return True, 0

        client = self._client()
        client.get_received()

        with patch.object(app_module, "publish_json", side_effect=fake_publish):
            client.emit("change_device", "zigbee2mqtt/device_a")
            client.get_received()
            client.emit(
                "set_basic_control",
                {"state": "ON", "brightness": 130, "request_id": "basic-1"},
            )

        self.assertEqual(len(published), 1)
        self.assertEqual(published[0]["topic"], "zigbee2mqtt/device_a/set")
        self.assertEqual(published[0]["origin"], "set_basic_control")
        self.assertEqual(published[0]["payload"], {"state": "ON", "brightness": 130})

        results = [event["args"][0] for event in client.get_received() if event["name"] == "command_result"]
        matching = [result for result in results if result.get("action") == "set_basic_control"]
        self.assertTrue(matching)
        self.assertEqual(matching[-1]["status"], "sent")
        self.assertEqual(matching[-1]["payload"], {"state": "ON", "brightness": 130})

    def test_set_basic_control_clamps_brightness(self):
        published = []

        def fake_publish(topic, payload, origin, sid=None):
            published.append({"topic": topic, "payload": payload, "origin": origin, "sid": sid})
            return True, 0

        client = self._client()
        client.get_received()

        with patch.object(app_module, "publish_json", side_effect=fake_publish):
            client.emit("change_device", "zigbee2mqtt/device_a")
            client.get_received()
            client.emit("set_basic_control", {"brightness": 999, "request_id": "basic-2"})

        self.assertEqual(len(published), 1)
        self.assertEqual(published[0]["payload"], {"brightness": 254})

        results = [event["args"][0] for event in client.get_received() if event["name"] == "command_result"]
        matching = [result for result in results if result.get("action") == "set_basic_control"]
        self.assertTrue(matching)
        self.assertEqual(matching[-1]["status"], "sent")
        self.assertEqual(matching[-1]["payload"], {"brightness": 254})

    def test_set_basic_control_without_selected_device_returns_error(self):
        client = self._client()
        client.get_received()
        client.emit("set_basic_control", {"state": "ON", "request_id": "basic-no-device"})
        results = [event["args"][0] for event in client.get_received() if event["name"] == "command_result"]
        self.assertTrue(results)
        self.assertEqual(results[-1]["status"], "error")
        self.assertEqual(results[-1]["message"], "No device selected")

    def test_auto_off_disconnect_only_when_last_session_on_topic(self):
        published = []

        def fake_publish(topic, payload, origin, sid=None):
            published.append({"topic": topic, "payload": payload, "origin": origin, "sid": sid})
            return True, 0

        client_a = self._client()
        client_b = self._client()
        client_a.get_received()
        client_b.get_received()

        with patch.object(app_module, "publish_json", side_effect=fake_publish):
            client_a.emit("change_device", "zigbee2mqtt/device_shared")
            client_b.emit("change_device", "zigbee2mqtt/device_shared")
            client_a.emit("set_reporting_auto_off", {"enabled": True})
            client_b.emit("set_reporting_auto_off", {"enabled": True})
            client_a.get_received()
            client_b.get_received()

            client_a.disconnect()
            self.assertEqual(len(published), 0)

            client_b.disconnect()
            self.assertEqual(len(published), 1)
            self.assertEqual(published[0]["topic"], "zigbee2mqtt/device_shared/set")
            self.assertEqual(published[0]["origin"], "auto_disable_target_reporting")
            self.assertIn("mmWaveTargetInfoReport", published[0]["payload"])

    def test_index_renders_feature_flag_value(self):
        original_value = app_module.SWITCH_STUDIO_UI
        try:
            app_module.SWITCH_STUDIO_UI = False
            with app_module.app.test_client() as client:
                response = client.get("/")
            self.assertEqual(response.status_code, 200)
            body = response.get_data(as_text=True)
            self.assertIn("const SWITCH_STUDIO_UI_ENABLED = false;", body)
        finally:
            app_module.SWITCH_STUDIO_UI = original_value

    def test_on_message_ignores_get_topic_for_state_update(self):
        topic = "zigbee2mqtt/Bedroom Light Control"
        with app_module.device_list_lock:
            app_module.device_list["Bedroom Light Control"] = _make_device("Bedroom Light Control", topic)
        before_zone = dict(app_module.device_list["Bedroom Light Control"]["zone_config"])

        payload = {
            "mmWaveWidthMin": "",
            "mmWaveWidthMax": "",
            "mmWaveDepthMin": "",
            "mmWaveDepthMax": "",
        }
        msg = SimpleNamespace(topic=f"{topic}/get", payload=json.dumps(payload).encode("utf-8"))
        app_module.on_message(None, None, msg)

        with app_module.device_list_lock:
            after_zone = dict(app_module.device_list["Bedroom Light Control"]["zone_config"])
        self.assertEqual(after_zone, before_zone)

    def test_on_message_updates_zone_config_for_exact_device_topic(self):
        topic = "zigbee2mqtt/Bedroom Light Control"
        with app_module.device_list_lock:
            app_module.device_list["Bedroom Light Control"] = _make_device("Bedroom Light Control", topic)

        payload = {
            "mmWaveWidthMin": "20",
            "mmWaveWidthMax": "100",
            "mmWaveDepthMin": "10",
            "mmWaveDepthMax": "220",
        }
        msg = SimpleNamespace(topic=topic, payload=json.dumps(payload).encode("utf-8"))
        app_module.on_message(None, None, msg)

        with app_module.device_list_lock:
            zone = dict(app_module.device_list["Bedroom Light Control"]["zone_config"])
        self.assertEqual(zone, {"x_min": 20, "x_max": 100, "y_min": 10, "y_max": 220})

    def test_on_message_parses_detection_zone_raw_packet(self):
        topic = "zigbee2mqtt/Bedroom Light Control"
        with app_module.device_list_lock:
            app_module.device_list["Bedroom Light Control"] = _make_device("Bedroom Light Control", topic)

        zone_values = {
            "x_min": 20,
            "x_max": 111,
            "y_min": 0,
            "y_max": 107,
            "z_min": -11,
            "z_max": 300,
        }

        payload = {
            "0": 29,
            "1": 47,
            "2": 18,
            "3": 1,
            "4": 3,
            "5": 1,
        }
        ordered = ["x_min", "x_max", "y_min", "y_max", "z_min", "z_max"]
        offset = 6
        for key in ordered:
            low, high = _int16_to_le_bytes(zone_values[key])
            payload[str(offset)] = low
            payload[str(offset + 1)] = high
            offset += 2

        msg = SimpleNamespace(topic=topic, payload=json.dumps(payload).encode("utf-8"))
        app_module.on_message(None, None, msg)

        with app_module.device_list_lock:
            zones = list(app_module.device_list["Bedroom Light Control"]["detection_zones"])

        self.assertEqual(len(zones), 1)
        self.assertEqual(zones[0], zone_values)


if __name__ == "__main__":
    unittest.main()
