"""Climate platform for Savant Host."""

from typing import TYPE_CHECKING, Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SavantConfigEntry, SavantCoordinator

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .models import SavantThermostat, SavantThermostatState

PARALLEL_UPDATES = 0

_SAVANT_HVAC_MODE_MAP: dict[str, HVACMode] = {
    "heat": HVACMode.HEAT,
    "cool": HVACMode.COOL,
    "auto": HVACMode.HEAT_COOL,
    "off": HVACMode.OFF,
}

_SAVANT_HVAC_ACTION_MAP: dict[str, HVACAction] = {
    "fan": HVACAction.FAN,
    "heating": HVACAction.HEATING,
    "cooling": HVACAction.COOLING,
    "idle": HVACAction.IDLE,
    "off": HVACAction.OFF,
}


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: SavantConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Savant climate entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        SavantClimateEntity(coordinator, thermostat)
        for thermostat in coordinator.data.thermostats.values()
    )


class SavantClimateEntity(CoordinatorEntity[SavantCoordinator], ClimateEntity):
    """Representation of a Savant thermostat."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_features = ClimateEntityFeature(0)

    def __init__(
        self,
        coordinator: SavantCoordinator,
        thermostat: SavantThermostat,
    ) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator)
        self._thermostat = thermostat
        configuration_id = coordinator.data.configuration.configuration_id
        self._attr_unique_id = f"{configuration_id}-{thermostat.device_id}"

        hvac_modes: list[HVACMode] = [HVACMode.OFF]
        if thermostat.heat_supported:
            hvac_modes.append(HVACMode.HEAT)
        if thermostat.cool_supported:
            hvac_modes.append(HVACMode.COOL)
        if thermostat.auto_supported:
            hvac_modes.append(HVACMode.HEAT_COOL)
        self._attr_hvac_modes = hvac_modes

        room = coordinator.data.rooms.get(thermostat.room_id)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, thermostat.device_id)},
            name=thermostat.name,
            manufacturer="Savant",
            suggested_area=room.name if room is not None else None,
            via_device=(DOMAIN, configuration_id),
        )

    def _thermostat_state(self) -> SavantThermostatState | None:
        """Return the latest polled state for this thermostat, or None."""
        return self.coordinator.data.thermostat_states.get(self._thermostat.device_id)

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement."""
        return self.coordinator.temperature_unit

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        state = self._thermostat_state()
        return state.current_temperature if state is not None else None

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return the current HVAC mode."""
        state = self._thermostat_state()
        if state is None or state.hvac_mode_raw is None:
            return None
        return _SAVANT_HVAC_MODE_MAP.get(state.hvac_mode_raw.lower())

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return the current HVAC action (what the system is actively doing)."""
        state = self._thermostat_state()
        if state is None or state.hvac_action_raw is None:
            return None
        return _SAVANT_HVAC_ACTION_MAP.get(state.hvac_action_raw.lower())

    @property
    def fan_mode(self) -> str | None:
        """Return the current fan mode."""
        state = self._thermostat_state()
        if state is None or state.fan_mode_raw is None:
            return None
        return state.fan_mode_raw.lower()

    @property
    def fan_modes(self) -> list[str]:
        """Return the list of available fan modes."""
        return ["auto", "on", "cycle"]

    @property
    def target_temperature_high(self) -> float | None:
        """Return the cooling setpoint (upper bound)."""
        state = self._thermostat_state()
        return state.cool_point if state is not None else None

    @property
    def target_temperature_low(self) -> float | None:
        """Return the heating setpoint (lower bound)."""
        state = self._thermostat_state()
        return state.heat_point if state is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        state = self._thermostat_state()
        if state is None or state.humidity_mode_raw is None:
            return {}
        return {"humidity_mode": state.humidity_mode_raw}
