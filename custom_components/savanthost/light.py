"""Light platform for Savant Host."""

from typing import TYPE_CHECKING, Any

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.util.scaling import scale_ranged_value_to_int_range

from .api import SavantConnectionError
from .entity import SavantEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .coordinator import SavantConfigEntry, SavantCoordinator
    from .models import SavantLoad

PARALLEL_UPDATES = 0


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: SavantConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Savant lights."""
    coordinator = entry.runtime_data
    async_add_entities(
        SavantLightEntity(coordinator, load) for load in coordinator.data.loads.values()
    )


class SavantLightEntity(SavantEntity, LightEntity):
    """Representation of a Savant lighting load."""

    def __init__(self, coordinator: SavantCoordinator, savant_load: SavantLoad) -> None:
        """Initialize the light."""
        super().__init__(coordinator, savant_load)
        if savant_load.supports_brightness:
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
            self._attr_color_mode = ColorMode.BRIGHTNESS
        else:
            self._attr_supported_color_modes = {ColorMode.ONOFF}
            self._attr_color_mode = ColorMode.ONOFF

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success

    @property
    def is_on(self) -> bool | None:
        """Return true if light is on."""
        level = self.coordinator.data.get_load_level(self.savant_load.load_id)
        if level is None:
            return None
        return level > 0

    @property
    def brightness(self) -> int | None:
        """Return the brightness of the light."""
        if not self.savant_load.supports_brightness:
            return None
        level = self.coordinator.data.get_load_level(self.savant_load.load_id)
        if level is None:
            return None
        return scale_ranged_value_to_int_range((0, 100), (0, 255), level)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        brightness = kwargs.get("brightness")
        try:
            await self.coordinator.async_turn_on_load(
                self.savant_load.load_id, brightness
            )
        except SavantConnectionError:
            self.coordinator.logger.exception("Failed to turn on %s", self.entity_id)
            raise

    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Turn the light off."""
        try:
            await self.coordinator.async_turn_off_load(self.savant_load.load_id)
        except SavantConnectionError:
            self.coordinator.logger.exception("Failed to turn off %s", self.entity_id)
            raise
