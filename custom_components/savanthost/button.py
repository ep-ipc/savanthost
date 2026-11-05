"""Button platform for Savant Host lighting scenes."""

from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import SavantConnectionError
from .const import DOMAIN
from .coordinator import SavantConfigEntry, SavantCoordinator

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .models import SavantLightingScene

PARALLEL_UPDATES = 0


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: SavantConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Savant lighting scene buttons."""
    coordinator = entry.runtime_data
    async_add_entities(
        SavantLightingSceneButton(coordinator, scene)
        for scene in coordinator.data.lighting_scenes.values()
    )


class SavantLightingSceneButton(CoordinatorEntity[SavantCoordinator], ButtonEntity):
    """Button that applies a Savant lighting scene."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SavantCoordinator,
        scene: SavantLightingScene,
    ) -> None:
        """Initialize the scene button."""
        super().__init__(coordinator)
        self._scene = scene
        configuration_id = coordinator.data.configuration.configuration_id
        self._attr_unique_id = f"{configuration_id}-scene-{scene.lighting_scene_id}"
        self._attr_name = scene.name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, configuration_id)},
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success

    async def async_press(self) -> None:
        """Apply the lighting scene."""
        try:
            await self.coordinator.async_apply_lighting_scene(
                self._scene.lighting_scene_id
            )
        except SavantConnectionError:
            self.coordinator.logger.exception(
                "Failed to apply lighting scene %s", self.entity_id
            )
            raise
