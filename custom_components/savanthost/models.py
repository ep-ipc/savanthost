"""Data models for the Savant Host integration."""

from dataclasses import dataclass, field
from typing import Any

from .const import ARG_THERMOSTAT_ADDRESS, HVAC_SERVICE_TYPES

WS_URI_DEVICE_RECOGNIZED = "session/deviceRecognized"
WS_URI_STATE_UPDATE = "state/update"
MIN_SERVICE_REQUEST_PARTS = 5

# Savant exposes the same thermostat alias in every zone; avoid these when possible.
# NOTE: This is VERY installation specific - we should avoid this.
GENERIC_HVAC_ZONES = frozenset(
    {
        "Hallways",
        "Library",
        "Cabana",
        "Exterior",
        "Elevator Housing",
        "Pool",
        "2nd Floor Master Bath",
        "Living Room",
        "Garage",
        "Master Bathroom",
    }
)

# Thermostat name hints that do not exactly match a Savant zone name.
ZONE_HINT_OVERRIDES: dict[str, str] = {
    "2nd FL Master Bed": "2nd Floor Master Bed",
    "1st Floor Guest": "Guest Room Downstairs",
    "2nd Floor Guest": "Guest Room Upstairs",
}


@dataclass(slots=True)
class SavantConfiguration:
    """Active Savant configuration."""

    configuration_id: str
    name: str


@dataclass(slots=True)
class SavantRoom:
    """Savant room metadata."""

    room_id: str
    name: str


@dataclass(slots=True)
class SavantLightingDevice:
    """Savant lighting hardware device."""

    device_id: str
    room_id: str
    name: str
    address: str
    dimmer_is_switch: bool


@dataclass(slots=True)
class SavantLoad:
    """Savant lighting load."""

    load_id: str
    device_id: str
    room_id: str
    name: str
    offset: int
    device_address: str
    hex_address: str
    supports_brightness: bool = True


@dataclass(slots=True)
class SavantThermostatState:
    """Polled runtime state for a single Savant thermostat."""

    current_temperature: float | None = None
    hvac_mode_raw: str | None = None
    fan_mode_raw: str | None = None
    cool_point: float | None = None
    heat_point: float | None = None
    hvac_action_raw: str | None = None
    humidity_mode_raw: str | None = None


@dataclass(slots=True)
class SavantHvacServiceBinding:
    """Parsed HVAC service routing fields for POST /config/v1/services."""

    zone: str
    component: str
    logical_component: str
    service_variant_id: str
    service_type: str


@dataclass(slots=True)
class SavantThermostat:
    """Savant HVAC thermostat component."""

    device_id: str
    room_id: str
    name: str
    thermostat_address: str
    current_temp_state_name: str | None
    hvac_mode_state_name: str | None
    fan_mode_state_name: str | None
    cool_point_state_name: str | None
    heat_point_state_name: str | None
    hvac_action_state_name: str | None
    humidity_mode_state_name: str | None
    heat_supported: bool
    cool_supported: bool
    auto_supported: bool
    service: SavantHvacServiceBinding | None = None


@dataclass(slots=True)
class SavantHostData:
    """Coordinator data for a Savant host."""

    configuration: SavantConfiguration
    rooms: dict[str, SavantRoom]
    loads: dict[str, SavantLoad]
    states: dict[str, int] = field(default_factory=dict)
    thermostats: dict[str, SavantThermostat] = field(default_factory=dict)
    thermostat_states: dict[str, SavantThermostatState] = field(default_factory=dict)

    def get_load_level(self, load_id: str) -> int | None:
        """Return the Savant load level (0-100) for a load."""
        return self.states.get(load_id)


def compute_load_hex_address(device_address: str, offset: int) -> str:
    """Compute the AVC load hex address for a device address and offset."""
    base = int(device_address, 16) << 16
    return f"{(base | (offset & 0x3FF)):x}"


def parse_load_level_value(value: str) -> int | None:
    """Parse an AVC load level value such as 75% or 0%.1."""
    normalized = value.strip().rstrip("%")
    if not normalized or normalized.upper() == "X":
        return None
    level_part = normalized.split(".", maxsplit=1)[0].rstrip("%")
    try:
        return max(0, min(100, int(level_part)))
    except ValueError:
        return None


def parse_module_level_at_offset(levels: str, offset: int) -> int | None:
    """Parse one load level from a module update string."""
    parts = levels.split(",")
    if offset >= len(parts):
        return None
    part = parts[offset].strip()
    if part.upper() == "X" or part == "-1":
        return None
    try:
        return max(0, min(100, int(part)))
    except ValueError:
        return None


def parse_configuration(data: dict[str, Any]) -> SavantConfiguration:
    """Parse active configuration response."""
    return SavantConfiguration(
        configuration_id=data["configurationID"],
        name=data["name"],
    )


def parse_lighting_devices(
    lighting_data: dict[str, Any],
) -> dict[str, SavantLightingDevice]:
    """Build a device_id to lighting device map from lighting config."""
    devices: dict[str, SavantLightingDevice] = {}
    for room in lighting_data.get("rooms", []):
        room_id = room["roomID"]
        for device in room.get("lightingDevices", []):
            devices[device["deviceID"]] = SavantLightingDevice(
                device_id=device["deviceID"],
                room_id=room_id,
                name=device["name"],
                address=device["address"],
                dimmer_is_switch=bool(device.get("dimmerIsSwitch")),
            )
    return devices


def parse_rooms(lighting_data: dict[str, Any]) -> dict[str, SavantRoom]:
    """Build a room_id to room map from lighting config."""
    return {
        room["roomID"]: SavantRoom(room_id=room["roomID"], name=room["name"])
        for room in lighting_data.get("rooms", [])
    }


def parse_loads(
    loads_data: list[dict[str, Any]],
    devices: dict[str, SavantLightingDevice],
) -> dict[str, SavantLoad]:
    """Parse and filter lighting loads."""
    loads: dict[str, SavantLoad] = {}
    for load_data in loads_data:
        load_id = load_data["loadID"]
        if load_id in loads:
            continue
        device_id = load_data["deviceID"]
        device = devices.get(device_id)
        if device is None or device.dimmer_is_switch:
            continue
        offset = int(load_data.get("offset", 0))
        loads[load_id] = SavantLoad(
            load_id=load_id,
            device_id=device_id,
            room_id=load_data["roomID"],
            name=load_data["name"],
            offset=offset,
            device_address=device.address,
            hex_address=compute_load_hex_address(device.address, offset),
            supports_brightness=load_data.get("max", 100) != load_data.get("min", 0),
        )
    return loads


def parse_avc_state_update(
    message: dict[str, Any],
    loads: dict[str, SavantLoad],
) -> dict[str, int]:
    """Parse an AVC state/update message into load_id to level updates."""
    uri = message.get("URI") or message.get("uri")
    if uri != WS_URI_STATE_UPDATE:
        return {}

    by_hex = {load.hex_address.lower(): load.load_id for load in loads.values()}
    by_device: dict[str, dict[int, str]] = {}
    for load in loads.values():
        by_device.setdefault(load.device_address.lower(), {})[load.offset] = (
            load.load_id
        )

    updates: dict[str, int] = {}
    for item in message.get("messages", []):
        if not isinstance(item, dict):
            continue
        state = item.get("state")
        if not isinstance(state, str):
            continue
        value = str(item.get("value", ""))
        if state.startswith("load."):
            hex_address = state[5:].lower()
            if (load_id := by_hex.get(hex_address)) and (
                level := parse_load_level_value(value)
            ) is not None:
                updates[load_id] = level
            continue
        if not state.startswith("module."):
            continue
        device_addr = state[7:].lower()
        offset_map = by_device.get(device_addr, {})
        for offset, load_id in offset_map.items():
            if (level := parse_module_level_at_offset(value, offset)) is not None:
                updates[load_id] = level
    return updates


def parse_module_get_response(
    message: dict[str, Any],
    loads: dict[str, SavantLoad],
) -> dict[str, int]:
    """Parse an AVC state/module/<addr>/get response into load updates."""
    uri = message.get("URI") or message.get("uri") or ""
    prefix = "state/module/"
    suffix = "/get"
    if not uri.startswith(prefix) or not uri.endswith(suffix):
        return {}

    addr_in_uri = uri[len(prefix) : -len(suffix)].lower()
    updates: dict[str, int] = {}
    for item in message.get("messages", []):
        if not isinstance(item, dict):
            continue
        value = item.get("value")
        if not isinstance(value, str):
            continue
        for load in loads.values():
            if load.device_address.lower() != addr_in_uri:
                continue
            if (level := parse_module_level_at_offset(value, load.offset)) is not None:
                updates[load.load_id] = level
    return updates


def _resolve_state_name(
    state_names: list[str], base_suffix: str, address1: str
) -> str | None:
    """
    Resolve a Savant state name from the feedback list.

    The feedback API returns bare base names (e.g. "...ThermostatMode"). The state
    endpoint requires the ThermostatAddress appended (e.g. "...ThermostatMode_1").
    endswith() is used instead of substring matching to avoid false matches on names
    that share a common prefix (e.g. ThermostatMode vs ThermostatModelNumber) or a
    common suffix (e.g. ThermostatCurrentCoolPoint vs TempThermostatCurrentCoolPoint).
    """
    suffixed = next(
        (s for s in state_names if s.endswith(f".{base_suffix}_{address1}")), None
    )
    if suffixed is not None:
        return suffixed
    base = next((s for s in state_names if s.endswith(f".{base_suffix}")), None)
    if base is not None:
        return f"{base}_{address1}"
    return None


def parse_service_request(service_request: str) -> SavantHvacServiceBinding:
    """
    Parse a dash-separated serviceRequest string.

    Format: zone-component-logicalComponent-variant-type
    Component names may contain dashes; fixed tail fields are parsed from the right.
    """
    parts = service_request.split("-")
    if len(parts) < MIN_SERVICE_REQUEST_PARTS:
        msg = f"Invalid serviceRequest: {service_request!r}"
        raise ValueError(msg)
    return SavantHvacServiceBinding(
        zone=parts[0],
        component="-".join(parts[1:-3]),
        logical_component=parts[-3],
        service_variant_id=parts[-2],
        service_type=parts[-1],
    )


def _score_hvac_service_zone(zone: str, thermostat_name: str) -> int:
    """Score how well a service zone matches a thermostat's physical location."""
    hint = thermostat_name.removesuffix(" Thermostat")
    if zone == hint:
        return 100
    mapped = ZONE_HINT_OVERRIDES.get(hint)
    if mapped is not None and zone == mapped:
        return 95
    hint_norm = hint.replace(" ", "").lower()
    zone_norm = zone.replace(" ", "").lower()
    if hint_norm in zone_norm or zone_norm in hint_norm:
        return 70
    if zone in GENERIC_HVAC_ZONES:
        return 10
    return 50


def match_hvac_services(
    services_data: list[dict[str, Any]],
    thermostats: dict[str, SavantThermostat],
) -> dict[str, SavantHvacServiceBinding]:
    """Match HVAC services to thermostats by alias and best zone."""
    bindings: dict[str, SavantHvacServiceBinding] = {}
    scores: dict[str, int] = {}

    for device_id, thermostat in thermostats.items():
        best_score = -1
        best_binding: SavantHvacServiceBinding | None = None

        for service in services_data:
            if service.get("name") not in HVAC_SERVICE_TYPES:
                continue
            if service.get("alias") != thermostat.name:
                continue
            service_request = service.get("serviceRequest")
            if not isinstance(service_request, str):
                continue
            try:
                binding = parse_service_request(service_request)
            except ValueError:
                continue
            score = _score_hvac_service_zone(binding.zone, thermostat.name)
            if score > best_score:
                best_score = score
                best_binding = binding

        if best_binding is not None:
            bindings[device_id] = best_binding
            scores[device_id] = best_score

    return bindings


def build_hvac_service_command(
    binding: SavantHvacServiceBinding,
    thermostat_address: str,
    command: str,
    extra_arguments: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build the POST body for /config/v1/services."""
    arguments: dict[str, str] = {ARG_THERMOSTAT_ADDRESS: thermostat_address}
    if extra_arguments:
        arguments.update(extra_arguments)
    return {
        "command": command,
        "component": binding.component,
        "logicalComponent": binding.logical_component,
        "serviceVariantID": binding.service_variant_id,
        "type": binding.service_type,
        "zone": binding.zone,
        "arguments": arguments,
    }


def parse_hvac_components(
    components_data: list[dict[str, Any]],
    state_names_by_device: dict[str, list[str]],
    service_bindings: dict[str, SavantHvacServiceBinding] | None = None,
) -> dict[str, SavantThermostat]:
    """Parse HVAC component data into SavantThermostat objects."""
    bindings = service_bindings or {}
    thermostats: dict[str, SavantThermostat] = {}
    for component in components_data:
        device_id = component["deviceID"]
        address1 = str(component.get("address1", "1"))
        names = state_names_by_device.get(device_id, [])
        thermostats[device_id] = SavantThermostat(
            device_id=device_id,
            room_id=component["roomID"],
            name=component["name"],
            thermostat_address=address1,
            current_temp_state_name=_resolve_state_name(
                names, "ThermostatCurrentTemperature", address1
            ),
            hvac_mode_state_name=_resolve_state_name(names, "ThermostatMode", address1),
            fan_mode_state_name=_resolve_state_name(
                names, "ThermostatFanMode", address1
            ),
            cool_point_state_name=_resolve_state_name(
                names, "ThermostatCurrentCoolPoint", address1
            ),
            heat_point_state_name=_resolve_state_name(
                names, "ThermostatCurrentHeatPoint", address1
            ),
            hvac_action_state_name=_resolve_state_name(
                names, "ThermostatHVACState", address1
            ),
            humidity_mode_state_name=_resolve_state_name(
                names, "ThermostatHumidityMode", address1
            ),
            heat_supported=bool(component.get("heatControlSupported")),
            cool_supported=bool(component.get("coolControlSupported")),
            auto_supported=bool(component.get("autoControlSupported")),
            service=bindings.get(device_id),
        )
    return thermostats


def apply_state_updates(
    data: SavantHostData, updates: dict[str, int]
) -> SavantHostData:
    """Return coordinator data with merged light state updates."""
    if not updates:
        return data
    return SavantHostData(
        configuration=data.configuration,
        rooms=data.rooms,
        loads=data.loads,
        states={**data.states, **updates},
        thermostats=data.thermostats,
        thermostat_states=data.thermostat_states,
    )


def apply_thermostat_state_updates(
    data: SavantHostData, updates: dict[str, SavantThermostatState]
) -> SavantHostData:
    """Return coordinator data with merged thermostat state updates."""
    if not updates:
        return data
    return SavantHostData(
        configuration=data.configuration,
        rooms=data.rooms,
        loads=data.loads,
        states=data.states,
        thermostats=data.thermostats,
        thermostat_states={**data.thermostat_states, **updates},
    )
