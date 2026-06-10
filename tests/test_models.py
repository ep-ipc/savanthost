"""Tests for Savant Host models."""

from custom_components.savanthost.models import (
    SavantLoad,
    compute_load_hex_address,
    parse_avc_state_update,
    parse_load_level_value,
    parse_module_get_response,
    parse_module_level_at_offset,
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
