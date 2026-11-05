"""Tests for Savant Host models."""

from custom_components.savanthost.const import (
    ARG_COOL_POINT,
    ARG_HEAT_POINT,
    ARG_THERMOSTAT_ADDRESS,
    CMD_SET_COOL_POINT,
    CMD_SET_HEAT_POINT,
    CMD_SET_HVAC_MODE_HEAT,
)
from custom_components.savanthost.models import (
    SavantConfiguration,
    SavantHostData,
    SavantLightingScene,
    SavantLoad,
    SavantThermostat,
    SavantThermostatState,
    apply_state_updates,
    build_hvac_service_command,
    compute_load_hex_address,
    match_hvac_services,
    merge_thermostat_state,
    parse_avc_state_update,
    parse_lighting_scenes,
    parse_load_level_value,
    parse_module_get_response,
    parse_module_level_at_offset,
    parse_service_request,
    state_patch_for_command,
)


def _make_load(
    load_id: str,
    device_address: str,
    offset: int,
    name: str = "Test Load",
) -> SavantLoad:
    """Build a SavantLoad with computed addresses."""
    return SavantLoad(
        load_id=load_id,
        device_id="device-1",
        room_id="room-1",
        name=name,
        offset=offset,
        device_address=device_address,
        hex_address=compute_load_hex_address(device_address, offset),
    )


def test_compute_load_hex_address() -> None:
    """Test load hex address calculation."""
    assert compute_load_hex_address("005", 0) == "50000"
    assert compute_load_hex_address("005", 1) == "50001"
    assert compute_load_hex_address("002", 0) == "20000"


def test_parse_module_level_at_offset() -> None:
    """Test parsing module level strings."""
    assert parse_module_level_at_offset("50,100,X,-1", 0) == 50
    assert parse_module_level_at_offset("50,100,X,-1", 1) == 100
    assert parse_module_level_at_offset("50,100,X,-1", 2) is None
    assert parse_module_level_at_offset("50,100,X,-1", 3) is None


def test_parse_load_level_value() -> None:
    """Test parsing load level values."""
    assert parse_load_level_value("75%") == 75
    assert parse_load_level_value("0%.1") == 0
    assert parse_load_level_value("X") is None


def test_parse_avc_state_update_load() -> None:
    """Test parsing AVC load state updates."""
    loads = {"load-1": _make_load("load-1", "005", 0, "Kitchen Downlights")}
    updates = parse_avc_state_update(
        {
            "URI": "state/update",
            "messages": [{"state": "load.50000", "value": "75%"}],
        },
        loads,
    )
    assert updates == {"load-1": 75}


def test_parse_avc_state_update_module() -> None:
    """Test parsing AVC module state updates using raw device address."""
    loads = {
        "load-1": _make_load("load-1", "002", 0, "Load 1"),
        "load-2": _make_load("load-2", "002", 1, "Load 2"),
    }
    updates = parse_avc_state_update(
        {
            "URI": "state/update",
            "messages": [
                {
                    "state": "module.002",
                    "value": "100,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1",
                }
            ],
        },
        loads,
    )
    assert updates == {"load-1": 100}


def test_parse_module_get_response_uses_raw_address() -> None:
    """Test that module/get responses are matched on the raw device address."""
    loads = {
        "load-1": _make_load("load-1", "002", 0, "Kitchen Cabinet Lights"),
        "load-2": _make_load("load-2", "002", 1, "Kitchen Downlights"),
    }
    updates = parse_module_get_response(
        {
            "URI": "state/module/002/get",
            "messages": [{"value": "80,60,X,-1"}],
        },
        loads,
    )
    assert updates == {"load-1": 80, "load-2": 60}


def test_parse_lighting_scenes() -> None:
    """Test parsing lighting scenes and skipping incomplete entries."""
    scenes = parse_lighting_scenes(
        [
            {
                "lightingSceneID": "scene-1",
                "name": "Exterior Lights",
                "type": 0,
                "members": [{"loadID": "load-1"}],
            },
            {
                "lightingSceneID": "scene-2",
                "name": "All Off",
            },
            {"name": "Missing Id"},
            {"lightingSceneID": "scene-3"},
            {"lightingSceneID": "", "name": "Empty Id"},
            {"lightingSceneID": "scene-4", "name": ""},
        ]
    )
    assert set(scenes) == {"scene-1", "scene-2"}
    assert scenes["scene-1"] == SavantLightingScene(
        lighting_scene_id="scene-1", name="Exterior Lights"
    )
    assert scenes["scene-2"].name == "All Off"


def test_apply_state_updates_keeps_lighting_scenes() -> None:
    """Test that light state updates preserve lighting scenes."""
    scene = SavantLightingScene(lighting_scene_id="scene-1", name="Exterior Lights")
    data = SavantHostData(
        configuration=SavantConfiguration(configuration_id="cfg-1", name="Host"),
        rooms={},
        loads={},
        lighting_scenes={"scene-1": scene},
    )
    updated = apply_state_updates(data, {"load-1": 50})
    assert updated.lighting_scenes == {"scene-1": scene}
    assert updated.states == {"load-1": 50}


def test_parse_service_request() -> None:
    """Test parsing a documented serviceRequest string."""
    binding = parse_service_request(
        "Library-1st Floor Guest Thermostat-HVAC_controller-1-SVC_ENV_HVAC"
    )
    assert binding.zone == "Library"
    assert binding.component == "1st Floor Guest Thermostat"
    assert binding.logical_component == "HVAC_controller"
    assert binding.service_variant_id == "1"
    assert binding.service_type == "SVC_ENV_HVAC"


def test_parse_service_request_component_with_dashes() -> None:
    """Test parsing when the component name contains dashes."""
    binding = parse_service_request(
        "Library-1st-Floor-Guest-Thermostat-HVAC_controller-1-SVC_ENV_HVAC"
    )
    assert binding.component == "1st-Floor-Guest-Thermostat"


def test_match_hvac_services() -> None:
    """Test matching HVAC services to thermostats by alias."""
    thermostats = {
        "dev-1": SavantThermostat(
            device_id="dev-1",
            room_id="room-1",
            name="Guest Thermostat",
            thermostat_address="1",
            current_temp_state_name=None,
            hvac_mode_state_name=None,
            fan_mode_state_name=None,
            cool_point_state_name=None,
            heat_point_state_name=None,
            hvac_action_state_name=None,
            humidity_mode_state_name=None,
            heat_supported=True,
            cool_supported=True,
            auto_supported=True,
        ),
    }
    services = [
        {
            "name": "SVC_ENV_HVAC",
            "alias": "Guest Thermostat",
            "serviceRequest": "Library-Guest Thermostat-HVAC_controller-1-SVC_ENV_HVAC",
        },
        {
            "name": "SVC_ENV_LIGHTING",
            "alias": "Kitchen Lights",
            "serviceRequest": "Kitchen-Kitchen Lights-Light-1-SVC_ENV_LIGHTING",
        },
    ]
    bindings = match_hvac_services(services, thermostats)
    assert "dev-1" in bindings
    assert bindings["dev-1"].component == "Guest Thermostat"


def test_match_hvac_services_uses_first_match() -> None:
    """Test that the first matching service is used when alias appears in many zones."""
    thermostats = {
        "kitchen": SavantThermostat(
            device_id="kitchen",
            room_id="room-kitchen",
            name="Kitchen Thermostat",
            thermostat_address="1",
            current_temp_state_name=None,
            hvac_mode_state_name=None,
            fan_mode_state_name=None,
            cool_point_state_name=None,
            heat_point_state_name=None,
            hvac_action_state_name=None,
            humidity_mode_state_name=None,
            heat_supported=True,
            cool_supported=True,
            auto_supported=True,
        ),
    }
    services = [
        {
            "name": "SVC_ENV_HVAC",
            "alias": "Kitchen Thermostat",
            "serviceRequest": (
                "Hallways-Kitchen Thermostat-HVAC_controller-1-SVC_ENV_HVAC"
            ),
        },
        {
            "name": "SVC_ENV_HVAC",
            "alias": "Kitchen Thermostat",
            "serviceRequest": (
                "Kitchen-Kitchen Thermostat-HVAC_controller-1-SVC_ENV_HVAC"
            ),
        },
    ]
    bindings = match_hvac_services(services, thermostats)
    assert bindings["kitchen"].zone == "Hallways"


def test_build_hvac_service_command() -> None:
    """Test building a POST body for /config/v1/services."""
    binding = parse_service_request(
        "Library-1st Floor Guest Thermostat-HVAC_controller-1-SVC_ENV_HVAC"
    )
    body = build_hvac_service_command(
        binding,
        "1",
        CMD_SET_HVAC_MODE_HEAT,
    )
    assert body == {
        "command": CMD_SET_HVAC_MODE_HEAT,
        "component": "1st Floor Guest Thermostat",
        "logicalComponent": "HVAC_controller",
        "serviceVariantID": "1",
        "type": "SVC_ENV_HVAC",
        "zone": "Library",
        "arguments": {ARG_THERMOSTAT_ADDRESS: "1"},
    }


def test_build_hvac_service_command_with_temperature() -> None:
    """Test building setpoint commands with extra arguments."""
    binding = parse_service_request(
        "Library-1st Floor Guest Thermostat-HVAC_controller-1-SVC_ENV_HVAC"
    )
    heat_body = build_hvac_service_command(
        binding,
        "2",
        CMD_SET_HEAT_POINT,
        {ARG_HEAT_POINT: "72"},
    )
    assert heat_body["arguments"] == {
        ARG_THERMOSTAT_ADDRESS: "2",
        ARG_HEAT_POINT: "72",
    }
    cool_body = build_hvac_service_command(
        binding,
        "2",
        CMD_SET_COOL_POINT,
        {ARG_COOL_POINT: "74"},
    )
    assert cool_body["arguments"][ARG_COOL_POINT] == "74"


def test_merge_thermostat_state() -> None:
    """Test merging optimistic patches into existing thermostat state."""
    existing = SavantThermostatState(
        current_temperature=72.0,
        hvac_mode_raw="off",
        cool_point=77.0,
    )
    merged = merge_thermostat_state(
        existing,
        SavantThermostatState(hvac_mode_raw="cool", heat_point=74.0),
    )
    assert merged.current_temperature == 72.0
    assert merged.hvac_mode_raw == "cool"
    assert merged.cool_point == 77.0
    assert merged.heat_point == 74.0


def test_state_patch_for_command() -> None:
    """Test building optimistic state patches from Savant commands."""
    assert state_patch_for_command(CMD_SET_HVAC_MODE_HEAT) == SavantThermostatState(
        hvac_mode_raw="heat"
    )
    assert state_patch_for_command(
        CMD_SET_COOL_POINT, {ARG_COOL_POINT: "78"}
    ) == SavantThermostatState(cool_point=78.0)
