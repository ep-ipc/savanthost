"""Button platform for Savant Host lighting scenes."""

from typing import TYPE_CHECKING, Any

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import SavantConnectionError
from .const import DOMAIN, LOGGER
from .coordinator import SavantConfigEntry, SavantCoordinator

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .models import SavantLightingScene

PARALLEL_UPDATES = 0
LIGHTING_SCENES_AREA = "Lighting Scenes"
_DEFAULT_AREA_APPLIED = "default_area_applied"


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

    async def async_added_to_hass(self) -> None:
        """Assign the Lighting Scenes area the first time this button is seen."""
        await super().async_added_to_hass()
        try:
            self._async_ensure_default_area()
        except Exception:  # noqa: BLE001
            LOGGER.exception(
                "Failed to assign %s to area %s",
                self.entity_id,
                LIGHTING_SCENES_AREA,
            )

    def _async_ensure_default_area(self) -> None:
        """Put an unassigned button in Lighting Scenes once."""
        entry = self.registry_entry
        if entry is None:
            return
        domain_options = entry.options.get(DOMAIN, {})
        if domain_options.get(_DEFAULT_AREA_APPLIED):
            return
        entity_registry = er.async_get(self.hass)
        if entry.area_id is None:
            area = ar.async_get(self.hass).async_get_or_create(LIGHTING_SCENES_AREA)
            self.registry_entry = entity_registry.async_update_entity(
                self.entity_id, area_id=area.id
            )
        self.registry_entry = entity_registry.async_update_entity_options(
            self.entity_id,
            DOMAIN,
            {**domain_options, _DEFAULT_AREA_APPLIED: True},
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return scene member names."""
        return {"scene_members": list(self._scene.member_names)}

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
