"""
Tests for ZWaveCapture (zwave_capture.py).

A scripted stand-in for the HA WebSocket API answers the same commands the
capture sends (config_entries/get, config/device_registry/list,
zwave_js/get_log_config, zwave_js/update_log_config,
zwave_js/subscribe_log_updates, unsubscribe_events) with the response and
event shapes HA uses, so the whole start → capture → stop cycle runs
without a real Home Assistant.
"""

import json
import os
import queue
import re
import sys
import time
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'mmwave_vis'))

# websockets is a runtime dependency that may not be installed for tests;
# ws_connect is replaced per test anyway.
_ws_stub = types.ModuleType("websockets")
_ws_sync = types.ModuleType("websockets.sync")
_ws_sync_client = types.ModuleType("websockets.sync.client")
_ws_sync_client.connect = None
sys.modules.setdefault("websockets",             _ws_stub)
sys.modules.setdefault("websockets.sync",        _ws_sync)
sys.modules.setdefault("websockets.sync.client", _ws_sync_client)

import zwave_capture
from zwave_capture import ZWaveCapture


ENTRY = {"entry_id": "zw1", "domain": "zwave_js", "title": "Z-Wave JS", "state": "loaded"}

DEVICES = [
    {   # the VZW32-SN on node 12
        "config_entries": ["zw1"], "manufacturer": "Inovelli", "model": "VZW32-SN",
        "sw_version": "2.4", "name": "Inovelli VZW32-SN", "name_by_user": "Kitchen mmWave",
        "identifiers": [["zwave_js", "3967862207-12"],
                        ["zwave_js", "3967862207-12-798:4:3"]],
    },
    {   # Inovelli, but on another integration
        "config_entries": ["zha1"], "manufacturer": "Inovelli", "model": "VZM32-SN",
        "identifiers": [["zha", "0c:2a:6f:ff:fe:aa:39:2b"]],
    },
    {   # same network, different maker
        "config_entries": ["zw1"], "manufacturer": "Zooz", "model": "ZEN71",
        "identifiers": [["zwave_js", "3967862207-5"]],
    },
]

LOG_EVENTS = [
    ["2026-09-27T12:00:00.000Z SERIAL « 0x011800a8000c0c91031e0101b5009e000800c8000100 (26 bytes)"],
    ["2026-09-27T12:00:00.010Z DRIVER « [Node 012] [REQ] [BridgeApplicationCommand]",
     "                                  └─[ManufacturerProprietaryCC]",
     "                                      manufacturer id: 0x031e"],
    "2026-09-27T12:00:00.020Z CNTRLR   [Node 012] TODO: no handler for application command\n",
]


class FakeHA:
    """Just enough of HA's WebSocket API; used as the ws_connect() context."""

    def __init__(self, entries=(ENTRY,), log_config=None, devices=DEVICES,
                 log_events=LOG_EVENTS, die_after_events=False):
        self.entries = list(entries)
        self.log_config = log_config or {"enabled": True, "level": "info",
                                         "log_to_file": False, "filename": "", "force_console": False}
        self.devices = devices
        self.log_events = log_events
        self.die_after_events = die_after_events
        self.sent = []
        self.inbox = queue.Queue()
        self.inbox.put({"type": "auth_required"})

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def _result(self, mid, result=None, success=True, error=None):
        msg = {"id": mid, "type": "result", "success": success, "result": result}
        if error:
            msg["error"] = error
        self.inbox.put(msg)

    def send(self, raw):
        msg = json.loads(raw)
        self.sent.append(msg)
        kind, mid = msg.get("type"), msg.get("id")
        if kind == "auth":
            self.inbox.put({"type": "auth_ok"})
        elif kind == "config_entries/get":
            self._result(mid, [e for e in self.entries if e["domain"] == msg["domain"]])
        elif kind == "config/device_registry/list":
            self._result(mid, self.devices)
        elif kind == "zwave_js/get_log_config":
            self._result(mid, dict(self.log_config))
        elif kind == "zwave_js/update_log_config":
            self.log_config.update(msg["config"])
            self._result(mid)
        elif kind == "zwave_js/subscribe_log_updates":
            self._result(mid)
            for message in self.log_events:
                self.inbox.put({"id": mid, "type": "event", "event": {
                    "type": "log_message",
                    "log_message": {"timestamp": "", "level": "debug",
                                    "primary_tags": "", "message": message},
                }})
            if self.die_after_events:
                self.inbox.put(ConnectionError("connection closed"))
        elif kind == "unsubscribe_events":
            self._result(mid)
        else:
            self._result(mid, success=False, error={"code": "unknown_command", "message": kind})

    def recv(self, timeout=None):
        try:
            item = self.inbox.get(timeout=timeout if timeout is not None else 5)
        except queue.Empty:
            raise TimeoutError from None
        if isinstance(item, Exception):
            raise item
        return json.dumps(item)

    def types_sent(self):
        return [m["type"] for m in self.sent]


class FakeSocketIO:
    def __init__(self):
        self.emits = []

    def emit(self, event, data=None, **kwargs):
        self.emits.append((event, data))


def _connect_to(monkeypatch, *fakes):
    """Each ws_connect() call hands out the next fake connection."""
    pending = list(fakes)
    monkeypatch.setattr(zwave_capture, "ws_connect", lambda *a, **k: pending.pop(0))


def _wait_for(pred, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(0.02)
    return False


def _run_capture(monkeypatch, *fakes, expect_lines=None):
    _connect_to(monkeypatch, *fakes)
    sio = FakeSocketIO()
    cap = ZWaveCapture("http://supervisor", "token", sio, addon_version="3.2.7")
    assert cap.start()
    if expect_lines is not None:
        assert _wait_for(lambda: cap.status()["lines"] >= expect_lines)
    cap.stop()
    cap._thread.join(timeout=5)
    assert not cap._thread.is_alive()
    return cap, sio


# ---------------------------------------------------------------------------
# Normal capture
# ---------------------------------------------------------------------------

def test_capture_records_lines_and_restores_log_level(monkeypatch):
    ha = FakeHA()
    cap, sio = _run_capture(monkeypatch, ha, expect_lines=5)

    st = cap.status()
    assert st["state"] == "stopped" and st["error"] is None
    assert st["lines"] == 5
    assert st["proprietary"] == 1
    assert st["has_data"] is True
    assert st["level_original"] == "info"

    updates = [m["config"] for m in ha.sent if m["type"] == "zwave_js/update_log_config"]
    assert updates == [{"level": "debug"}, {"level": "info"}]
    assert ha.log_config["level"] == "info"
    assert ha.types_sent()[-2:] == ["unsubscribe_events", "zwave_js/update_log_config"]
    assert sio.emits[-1][0] == "zwave_capture_status"
    assert sio.emits[-1][1]["state"] == "stopped"


def test_export_has_header_and_raw_lines(monkeypatch):
    cap, _ = _run_capture(monkeypatch, FakeHA(), expect_lines=5)
    text = cap.export_text()
    header, body = text.split("\n\n", 1)

    assert "# addon version: 3.2.7" in header
    assert "debug (was info, restored)" in header
    assert re.search(r"#   node 12\s+VZW32-SN\s+fw 2.4\s+Kitchen mmWave", header)
    assert "VZM32-SN" not in header          # ZHA device filtered out
    assert "ZEN71" not in header             # non-Inovelli filtered out
    assert body.splitlines() == [
        LOG_EVENTS[0][0],
        *LOG_EVENTS[1],
        LOG_EVENTS[2].rstrip("\n"),
    ]
    assert re.fullmatch(r"zwave_capture_\d{8}_\d{6}\.log", cap.export_filename())


def test_level_already_verbose_enough_is_left_alone(monkeypatch):
    ha = FakeHA(log_config={"enabled": True, "level": "silly"})
    cap, _ = _run_capture(monkeypatch, ha, expect_lines=5)
    assert "zwave_js/update_log_config" not in ha.types_sent()
    assert "unchanged" in cap.export_text()


def test_disabled_logging_is_enabled_then_restored(monkeypatch):
    ha = FakeHA(log_config={"enabled": False, "level": "debug"})
    _run_capture(monkeypatch, ha, expect_lines=5)
    updates = [m["config"] for m in ha.sent if m["type"] == "zwave_js/update_log_config"]
    assert updates == [{"enabled": True}, {"enabled": False}]


def test_start_while_running_is_refused(monkeypatch):
    _connect_to(monkeypatch, FakeHA(log_events=[]))
    cap = ZWaveCapture("http://supervisor", "token", FakeSocketIO())
    assert cap.start()
    assert _wait_for(lambda: cap.status()["state"] == "capturing")
    assert cap.start() is False
    cap.stop()
    cap._thread.join(timeout=5)
    assert cap.status()["state"] == "stopped"
    assert cap.export_text() is None         # nothing captured → nothing to download


# ---------------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------------

def test_no_zwave_integration(monkeypatch):
    ha = FakeHA(entries=())
    cap, _ = _run_capture(monkeypatch, ha)
    st = cap.status()
    assert st["state"] == "error"
    assert "No Z-Wave JS integration" in st["error"]
    assert "zwave_js/update_log_config" not in ha.types_sent()


def test_ignored_discovery_counts_as_no_integration(monkeypatch):
    # Shape of a real ignored zwave_js discovery entry from config_entries/get
    ignored = {"entry_id": "7098c75d", "domain": "zwave_js", "title": "CP2102 USB to UART Bridge",
               "source": "ignore", "state": "not_loaded"}
    cap, _ = _run_capture(monkeypatch, FakeHA(entries=(ignored,)))
    assert "No Z-Wave JS integration" in cap.status()["error"]


def test_integration_not_loaded(monkeypatch):
    ha = FakeHA(entries=({**ENTRY, "state": "not_loaded"},))
    cap, _ = _run_capture(monkeypatch, ha)
    assert "not loaded" in cap.status()["error"]


def test_connection_drop_restores_level_on_new_connection(monkeypatch):
    first = FakeHA(die_after_events=True)
    second = FakeHA()
    _connect_to(monkeypatch, first, second)
    cap = ZWaveCapture("http://supervisor", "token", FakeSocketIO())
    cap.start()
    cap._thread.join(timeout=5)

    st = cap.status()
    assert st["state"] == "error"
    assert st["lines"] == 5 and st["has_data"] is True
    assert [m["config"] for m in second.sent if m["type"] == "zwave_js/update_log_config"] \
        == [{"level": "info"}]
    assert "restored" in cap.export_text()


def test_missing_token():
    cap = ZWaveCapture("http://supervisor", "", FakeSocketIO())
    cap.start()
    cap._thread.join(timeout=5)
    assert "token" in cap.status()["error"]
