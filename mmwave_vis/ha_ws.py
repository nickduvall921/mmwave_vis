"""Short requests to Home Assistant's WebSocket API, for either Zigbee stack.

The ZHA client keeps one long-lived socket for events and reads it from its own
thread, so lookups that need an answer (device and entity registry, update
entities, attribute reads) open their own short connection here instead.
"""
import json
import re
import threading
import time
import urllib.parse
import urllib.request

from websockets.sync.client import connect as ws_connect

REQUEST_TIMEOUT_S = 15
CACHE_TTL_S = 300


class HAError(RuntimeError):
    pass


def ws_url(ha_url):
    # The Supervisor proxy URL is fixed; ha_url only says whether it's TLS
    return ("wss" if (ha_url or "").startswith("https") else "ws") + "://supervisor/core/websocket"


class HAConnection:
    """`with HAConnection(token, url) as ha: ha.request('config/device_registry/list')`"""

    def __init__(self, token, url, timeout=REQUEST_TIMEOUT_S):
        self.token = token
        self.url = url
        self.timeout = timeout
        self._ws = None
        self._ctx = None
        self._msg_id = 1

    def __enter__(self):
        if not self.token:
            raise HAError("No Home Assistant token")
        try:
            # max_size=None: registry lists pass 1 MiB on big installs (issue #53)
            self._ctx = ws_connect(self.url, additional_headers={"Authorization": f"Bearer {self.token}"},
                                   max_size=None)
            self._ws = self._ctx.__enter__()
        except HAError:
            raise
        except Exception as e:
            raise HAError(f"Couldn't reach Home Assistant ({e})") from None
        try:
            msg = self._recv(time.time() + self.timeout)
            if msg.get("type") != "auth_required":
                raise HAError(f"Unexpected first message from Home Assistant: {msg.get('type')}")
            self._ws.send(json.dumps({"type": "auth", "access_token": self.token}))
            msg = self._recv(time.time() + self.timeout)
            if msg.get("type") != "auth_ok":
                raise HAError("Home Assistant rejected the addon's token")
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *exc):
        ctx, self._ctx, self._ws = self._ctx, None, None
        if ctx is not None:
            try:
                ctx.__exit__(None, None, None)
            except Exception:
                pass
        return False

    def _recv(self, deadline):
        remaining = deadline - time.time()
        if remaining <= 0:
            raise HAError("Timed out waiting for Home Assistant")
        try:
            return json.loads(self._ws.recv(timeout=remaining))
        except TimeoutError:
            raise HAError("Timed out waiting for Home Assistant") from None
        except HAError:
            raise
        except Exception as e:
            raise HAError(f"Lost the connection to Home Assistant ({e})") from None

    def request(self, type_, **fields):
        """Send one command and return its result; raises HAError on failure."""
        req_id = self._msg_id
        self._msg_id += 1
        try:
            self._ws.send(json.dumps({"id": req_id, "type": type_, **fields}))
        except Exception as e:
            raise HAError(f"Lost the connection to Home Assistant ({e})") from None
        deadline = time.time() + self.timeout
        while True:
            msg = self._recv(deadline)
            if msg.get("id") != req_id or msg.get("type") != "result":
                continue
            if not msg.get("success"):
                err = msg.get("error") or {}
                raise HAError(f"{type_} failed: {err.get('message') or err.get('code') or 'unknown error'}")
            return msg.get("result")


def rest_json(token, path, timeout=10):
    """GET http://supervisor/core/api<path> (the Supervisor's proxy to HA's REST API).

    `path` starts with / and leaves out /api, e.g. "/states". Raises on any failure.
    """
    req = urllib.request.Request("http://supervisor/core/api" + path,
                                 headers={"Authorization": f"Bearer {token}",
                                          "Content-Type": "application/json"},
                                 method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def rest_get(token, path, timeout=5):
    """rest_json(), or None if there's no token or the request fails."""
    if not token:
        return None
    try:
        return rest_json(token, path, timeout)
    except Exception:
        return None


def rest_state(token, entity_id, timeout=10):
    """One entity's state, or None."""
    if not entity_id:
        return None
    return rest_get(token, "/states/" + urllib.parse.quote(entity_id, safe="._"), timeout)


# ---------------------------------------------------------------------------
# Registry helpers (pure, so they can be tested without Home Assistant)
# ---------------------------------------------------------------------------

def ieee_digits(value):
    """'0x0c2a6ffffef6f6a7', '0c:2a:6f:ff:fe:f6:f6:a7' and 'zigbee2mqtt_0x0c2a…' → '0c2a6ffffef6f6a7'."""
    if not isinstance(value, str):
        return None
    m = re.search(r'(?:0x)?((?:[0-9a-f]{2}:){7}[0-9a-f]{2}|[0-9a-f]{16})$', value.lower())
    return m.group(1).replace(':', '') if m else None


_AREA_RE = re.compile(r'area([1-4])occupancy')


def entity_roles(entries):
    """Pick out a switch's entities by what they are, from its entity registry entries.

    ZHA unique_ids: occupancy `<ieee>-1-1030`, light `<ieee>-1`, illuminance
    `<ieee>-1-1024`. Zigbee2MQTT: `<ieee>_<property>_zigbee2mqtt`, with areas as
    `<ieee>_area1Occupancy_zigbee2mqtt`. Disabled entities are left out.
    """
    roles = {}
    for e in entries or []:
        eid = e.get("entity_id") or ""
        if not eid or e.get("disabled_by"):
            continue
        uid = (e.get("unique_id") or "").lower()
        domain = eid.split(".", 1)[0]
        role = None
        if domain == "light":
            role = "light"
        elif domain == "update":
            role = "update"
        elif domain == "binary_sensor":
            m = _AREA_RE.search(uid)
            if m:
                role = f"area{m.group(1)}"
            elif uid.endswith("-1-1030") or uid.endswith("_occupancy_zigbee2mqtt"):
                role = "occupancy"
        elif domain == "sensor":
            if uid.endswith("-1-1024") or uid.endswith("_illuminance_zigbee2mqtt"):
                role = "illuminance"
            elif uid.endswith("_linkquality_zigbee2mqtt"):
                role = "linkquality"
        if role is None and "mmwave_target_info_report" in uid.replace("mmwavetargetinforeport", "mmwave_target_info_report"):
            role = "target_report"
        if role and role not in roles:
            roles[role] = eid
    return roles


class RegistryCache:
    """Device and entity registry, fetched at most every CACHE_TTL_S seconds.

    The full lists are large on big installs, so only what the addon needs per
    switch is kept: the device entry and its entities' roles.
    """

    def __init__(self, token, url, ttl=CACHE_TTL_S):
        self.token = token
        self.url = url
        self.ttl = ttl
        self._lock = threading.Lock()
        self._fetched = 0
        self._devices = {}    # ieee digits -> {device, roles}
        self.error = None

    def lookup(self, ieee, force=False):
        """{'device': registry entry, 'roles': {...}} for a switch, or None."""
        want = ieee_digits(ieee)
        if not want or not self.token:
            return None
        with self._lock:
            stale = force or time.time() - self._fetched > self.ttl
            if stale:
                self._refresh()
            return self._devices.get(want)

    def _refresh(self):
        try:
            with HAConnection(self.token, self.url) as ha:
                devices = ha.request("config/device_registry/list") or []
                entities = ha.request("config/entity_registry/list") or []
        except HAError as e:
            self.error = str(e)
            self._fetched = time.time()   # don't hammer HA when it's down
            return
        keep = {}
        for dev in devices:
            if "inovelli" not in (dev.get("manufacturer") or "").lower():
                continue
            for pair in list(dev.get("connections") or []) + list(dev.get("identifiers") or []):
                digits = ieee_digits(str(pair[1])) if len(pair) >= 2 else None
                if digits:
                    keep[digits] = {"device": {k: dev.get(k) for k in (
                        "id", "name", "name_by_user", "sw_version", "hw_version", "model", "manufacturer")},
                        "entries": []}
                    break
        by_id = {v["device"]["id"]: v for v in keep.values()}
        for e in entities:
            slot = by_id.get(e.get("device_id"))
            if slot is not None:
                slot["entries"].append({k: e.get(k) for k in ("entity_id", "unique_id", "disabled_by")})
        self._devices = {d: {"device": v["device"], "roles": entity_roles(v["entries"])} for d, v in keep.items()}
        self._fetched = time.time()
        self.error = None
