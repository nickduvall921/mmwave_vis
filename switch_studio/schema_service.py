import json
import os
import time
from copy import deepcopy


MMWAVE_PRESENCE_FIELDS = [
    "mmwaveControlWiredDevice",
    "mmWaveRoomSizePreset",
    "mmWaveHoldTime",
    "mmWaveDetectSensitivity",
    "mmWaveDetectTrigger",
    "mmWaveTargetInfoReport",
    "mmWaveStayLife",
    "mmWaveVersion",
]


class SchemaService:
    def __init__(self, definition_paths=None):
        self.definition_paths = definition_paths or []
        self.definition_path = None
        self.definition_error = None
        self.schema = None
        self.field_map = {}
        self.reload()

    def reload(self):
        model_definition = self._load_definition()
        if model_definition:
            self.schema = self._build_schema(model_definition)
        else:
            self.schema = self._fallback_schema()
        self.field_map = {field["name"]: field for field in self.schema.get("fields", []) if field.get("name")}
        return self.schema

    def get_schema(self):
        return deepcopy(self.schema)

    def validate_update(self, param, value):
        field = self.field_map.get(param)
        if not field:
            # Allow unknown fields for forward compatibility with new firmware/Z2M mappings.
            return True, None, value, True

        if not field.get("can_write", False):
            return False, f"Field '{param}' is read-only", None, False

        normalized, error = self._normalize_value(field, value)
        if error:
            return False, error, None, False
        return True, None, normalized, False

    def _load_definition(self):
        for path in self.definition_paths:
            if not path:
                continue
            normalized_path = os.path.abspath(path)
            if not os.path.exists(normalized_path):
                continue
            try:
                with open(normalized_path, encoding="utf-8") as f:
                    definition = json.load(f)
                self.definition_path = normalized_path
                self.definition_error = None
                return definition
            except Exception as load_error:
                self.definition_error = str(load_error)
        return None

    def _build_schema(self, model_definition):
        exposes = model_definition.get("exposes", []) or []
        options = model_definition.get("options", []) or []

        fields = [self._normalize_field(entry, "exposes") for entry in exposes if isinstance(entry, dict)]
        options_fields = [self._normalize_field(entry, "options") for entry in options if isinstance(entry, dict)]

        return {
            "source": "zigbee2mqtt_definition",
            "source_path": self.definition_path,
            "model": model_definition.get("model"),
            "vendor": model_definition.get("vendor"),
            "generated_at": time.time(),
            "field_count": len(fields),
            "option_count": len(options_fields),
            "fields": fields,
            "options": options_fields,
            "mmwave_presence_fields": list(MMWAVE_PRESENCE_FIELDS),
        }

    def _normalize_field(self, entry, source):
        name = entry.get("name")
        access = int(entry.get("access", 0) or 0)
        normalized_features = [self._normalize_feature(feature) for feature in (entry.get("features") or []) if isinstance(feature, dict)]

        return {
            "name": name,
            "property": entry.get("property"),
            "label": entry.get("label") or name or "Unknown",
            "description": entry.get("description", ""),
            "type": entry.get("type"),
            "category": entry.get("category") or "none",
            "source": source,
            "access": access,
            "can_read": bool(access & 1 or access & 4),
            "can_write": bool(access & 2),
            "value_min": entry.get("value_min"),
            "value_max": entry.get("value_max"),
            "value_step": entry.get("value_step"),
            "unit": entry.get("unit"),
            "values": entry.get("values", []),
            "value_on": entry.get("value_on"),
            "value_off": entry.get("value_off"),
            "presets": entry.get("presets", []),
            "item_type": self._normalize_feature(entry.get("item_type")) if isinstance(entry.get("item_type"), dict) else None,
            "features": normalized_features,
            "tab": self._infer_tab(name, entry),
            "section": self._infer_section(name, entry),
        }

    def _normalize_feature(self, feature):
        access = int(feature.get("access", 0) or 0)
        normalized_children = [self._normalize_feature(child) for child in (feature.get("features") or []) if isinstance(child, dict)]

        return {
            "name": feature.get("name"),
            "property": feature.get("property"),
            "label": feature.get("label") or feature.get("name") or "Unknown",
            "description": feature.get("description", ""),
            "type": feature.get("type"),
            "access": access,
            "can_read": bool(access & 1 or access & 4),
            "can_write": bool(access & 2),
            "value_min": feature.get("value_min"),
            "value_max": feature.get("value_max"),
            "value_step": feature.get("value_step"),
            "unit": feature.get("unit"),
            "values": feature.get("values", []),
            "value_on": feature.get("value_on"),
            "value_off": feature.get("value_off"),
            "features": normalized_children,
        }

    def _fallback_schema(self):
        fields = [
            {
                "name": "mmwaveControlWiredDevice",
                "property": "mmwaveControlWiredDevice",
                "label": "Wired Device Control",
                "description": "Controls automatic on/off behavior using presence.",
                "type": "enum",
                "category": "config",
                "source": "fallback",
                "access": 7,
                "can_read": True,
                "can_write": True,
                "value_min": None,
                "value_max": None,
                "value_step": None,
                "unit": None,
                "values": [
                    "Disabled",
                    "Occupancy (default)",
                    "Vacancy",
                    "Wasteful Occupancy",
                    "Mirrored Occupancy",
                    "Mirrored Vacancy",
                    "Mirrored Wasteful Occupancy",
                ],
                "presets": [],
                "item_type": None,
                "features": [],
                "tab": "Presence",
                "section": "Presence Controls",
            },
            {
                "name": "mmWaveRoomSizePreset",
                "property": "mmWaveRoomSizePreset",
                "label": "Room Preset",
                "description": "Predefined room dimensions for mmWave processing.",
                "type": "enum",
                "category": "config",
                "source": "fallback",
                "access": 7,
                "can_read": True,
                "can_write": True,
                "value_min": None,
                "value_max": None,
                "value_step": None,
                "unit": None,
                "values": ["Custom", "Small", "Medium", "Large"],
                "presets": [],
                "item_type": None,
                "features": [],
                "tab": "Presence",
                "section": "Presence Controls",
            },
            {
                "name": "mmWaveDetectSensitivity",
                "property": "mmWaveDetectSensitivity",
                "label": "Sensitivity",
                "description": "The sensitivity of the mmWave sensor.",
                "type": "enum",
                "category": "config",
                "source": "fallback",
                "access": 7,
                "can_read": True,
                "can_write": True,
                "value_min": None,
                "value_max": None,
                "value_step": None,
                "unit": None,
                "values": ["Low", "Medium", "High (default)"],
                "presets": [],
                "item_type": None,
                "features": [],
                "tab": "Presence",
                "section": "Presence Controls",
            },
            {
                "name": "mmWaveDetectTrigger",
                "property": "mmWaveDetectTrigger",
                "label": "Trigger Speed",
                "description": "The time from detecting a person to triggering an action.",
                "type": "enum",
                "category": "config",
                "source": "fallback",
                "access": 7,
                "can_read": True,
                "can_write": True,
                "value_min": None,
                "value_max": None,
                "value_step": None,
                "unit": None,
                "values": ["Slow (5s)", "Medium (1s)", "Fast (0.2s, default)"],
                "presets": [],
                "item_type": None,
                "features": [],
                "tab": "Presence",
                "section": "Presence Controls",
            },
            {
                "name": "mmWaveHoldTime",
                "property": "mmWaveHoldTime",
                "label": "Hold Time",
                "description": "Duration in seconds to hold occupancy after motion stops.",
                "type": "numeric",
                "category": "config",
                "source": "fallback",
                "access": 7,
                "can_read": True,
                "can_write": True,
                "value_min": 0,
                "value_max": 4294967295,
                "value_step": 1,
                "unit": "s",
                "values": [],
                "presets": [],
                "item_type": None,
                "features": [],
                "tab": "Presence",
                "section": "Presence Controls",
            },
            {
                "name": "mmWaveStayLife",
                "property": "mmWaveStayLife",
                "label": "Stay Life",
                "description": "Stationary-presence timing parameter.",
                "type": "numeric",
                "category": "config",
                "source": "fallback",
                "access": 7,
                "can_read": True,
                "can_write": True,
                "value_min": 0,
                "value_max": 4294967295,
                "value_step": 1,
                "unit": None,
                "values": [],
                "presets": [],
                "item_type": None,
                "features": [],
                "tab": "Presence",
                "section": "Presence Controls",
            },
            {
                "name": "mmWaveTargetInfoReport",
                "property": "mmWaveTargetInfoReport",
                "label": "Target Reporting",
                "description": "Enable raw target report stream when cluster binding is configured.",
                "type": "enum",
                "category": "config",
                "source": "fallback",
                "access": 7,
                "can_read": True,
                "can_write": True,
                "value_min": None,
                "value_max": None,
                "value_step": None,
                "unit": None,
                "values": ["Disable (default)", "Enable"],
                "presets": [],
                "item_type": None,
                "features": [],
                "tab": "Presence",
                "section": "Presence Controls",
            },
            {
                "name": "mmWaveVersion",
                "property": "mmWaveVersion",
                "label": "mmWave Version",
                "description": "Firmware version of the mmWave module.",
                "type": "numeric",
                "category": "none",
                "source": "fallback",
                "access": 5,
                "can_read": True,
                "can_write": False,
                "value_min": 0,
                "value_max": 4294967295,
                "value_step": 1,
                "unit": None,
                "values": [],
                "presets": [],
                "item_type": None,
                "features": [],
                "tab": "Presence",
                "section": "Presence Diagnostics",
            },
        ]
        return {
            "source": "fallback",
            "source_path": None,
            "model": "VZM32-SN",
            "vendor": "Inovelli",
            "generated_at": time.time(),
            "field_count": len(fields),
            "option_count": 0,
            "fields": fields,
            "options": [],
            "mmwave_presence_fields": list(MMWAVE_PRESENCE_FIELDS),
        }

    def _infer_tab(self, name, entry):
        if not name:
            return "Advanced"

        lname = name.lower()
        if "mmwave" in lname:
            if lname.endswith("_areas") or lname == "mmwave_control_commands":
                return "Zones"
            if lname.endswith("occupancy") or name in {"occupancy", "illuminance"}:
                return "Live"
            return "Presence"

        if lname in {"occupancy", "illuminance", "power", "voltage", "current", "energy", "action", "linkquality"}:
            return "Live"

        if any(key in lname for key in ["dimming", "ramprate", "defaultlevel", "minimumlevel", "maximumlevel", "outputmode", "quickstart"]):
            return "Load & Dimming"

        if "led" in lname or lname in {"led_effect", "individual_led_effect"}:
            return "LED & Notifications"

        if any(key in lname for key in ["tap", "button", "scene", "aux"]):
            return "Buttons & Scenes"

        if lname in {"identify", "energy_reset", "otaimagetype", "localprotection", "remoteprotection", "powertype"}:
            return "Power & Device"

        if entry.get("category") == "diagnostic":
            return "Live"

        return "Advanced"

    def _infer_section(self, name, entry):
        tab = self._infer_tab(name, entry)
        if tab == "Presence":
            if name == "mmWaveVersion":
                return "Presence Diagnostics"
            return "Presence Controls"
        if tab == "Zones":
            return "Zone Definitions"
        if tab == "Live":
            return "Live Sensors"
        if tab == "Load & Dimming":
            return "Load Behavior"
        if tab == "LED & Notifications":
            return "LED Configuration"
        if tab == "Buttons & Scenes":
            return "Button Mapping"
        if tab == "Power & Device":
            return "Device Settings"
        return "Advanced"

    def _normalize_value(self, field, value):
        field_type = field.get("type")
        if field_type == "numeric":
            return self._normalize_numeric(field, value)
        if field_type == "enum":
            return self._normalize_enum(field, value)
        if field_type == "binary":
            return self._normalize_binary(field, value)
        if field_type == "composite":
            if not isinstance(value, dict):
                return None, "Composite value must be an object"
            return value, None
        if field_type == "list":
            if not isinstance(value, list):
                return None, "List value must be an array"
            return value, None
        return value, None

    def _normalize_numeric(self, field, value):
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            return None, f"Field '{field.get('name')}' requires a numeric value"

        min_value = field.get("value_min")
        max_value = field.get("value_max")
        step_value = field.get("value_step")

        if min_value is not None and numeric_value < float(min_value):
            return None, f"Field '{field.get('name')}' is below min {min_value}"
        if max_value is not None and numeric_value > float(max_value):
            return None, f"Field '{field.get('name')}' is above max {max_value}"

        if step_value is None or float(step_value).is_integer():
            return int(round(numeric_value)), None
        return float(numeric_value), None

    def _normalize_enum(self, field, value):
        values = field.get("values") or []
        if not isinstance(value, str):
            return None, f"Field '{field.get('name')}' requires an enum string"
        if values and value not in values:
            return None, f"Field '{field.get('name')}' value '{value}' is not allowed"
        return value, None

    def _normalize_binary(self, field, value):
        if isinstance(value, bool):
            return value, None

        value_on = field.get("value_on", True)
        value_off = field.get("value_off", False)

        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "on", "yes"}:
                return value_on if isinstance(value_on, bool) else True, None
            if lowered in {"false", "0", "off", "no"}:
                return value_off if isinstance(value_off, bool) else False, None

        if value == value_on:
            return value, None
        if value == value_off:
            return value, None

        return None, f"Field '{field.get('name')}' requires a binary value"
