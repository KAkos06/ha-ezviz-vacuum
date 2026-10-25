"""Optional cloud map images."""

from __future__ import annotations

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import EzvizVacuumRuntimeData
from .entity import EzvizVacuumEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[EzvizVacuumRuntimeData],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the map image only when the robot reports an active map."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        EzvizMapImage(coordinator, serial)
        for serial, data in coordinator.data.items()
        if data.map_id is not None
    )


class EzvizMapImage(EzvizVacuumEntity, ImageEntity):
    """SVG map assembled from the cloud map layers."""

    _attr_translation_key = "map"
    _attr_content_type = "image/svg+xml"

    def __init__(self, coordinator, serial: str) -> None:
        ImageEntity.__init__(self, coordinator.hass)
        EzvizVacuumEntity.__init__(self, coordinator, serial)
        self._attr_unique_id = f"{serial}_map"

    @property
    def image_last_updated(self):
        return self.coordinator.map_image_updated.get(self.serial)

    async def async_image(self) -> bytes | None:
        return self.coordinator.map_images.get(self.serial)

    @property
    def available(self) -> bool:
        return super().available and self.serial in self.coordinator.map_images
