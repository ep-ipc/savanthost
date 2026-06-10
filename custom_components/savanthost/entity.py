"""Base entity for Savant Host."""

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SavantCoordinator

if TYPE_CHECKING:
    from .models import SavantLoad


class SavantEntity(CoordinatorEntity[SavantCoordinator]):
    """Base class for Savant entities."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, coordinator: SavantCoordinator, savant_load: SavantLoad) -> None:
        """Initialize the Savant entity."""
        super().__init__(coordinator)
        self.savant_load = savant_load
        configuration_id = coordinator.data.configuration.configuration_id
        self._attr_unique_id = f"{configuration_id}-{savant_load.load_id}"
        room = coordinator.data.rooms.get(savant_load.room_id)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, savant_load.load_id)},
            name=savant_load.name,
            manufacturer="Savant",
            suggested_area=room.name if room is not None else None,
            via_device=(DOMAIN, configuration_id),
        )
