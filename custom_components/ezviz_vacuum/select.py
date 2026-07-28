"""Select controls for EZVIZ Vacuum."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import EzvizVacuumRuntimeData
from .api import WATER_QUANTITIES
from .entity import EzvizVacuumEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[EzvizVacuumRuntimeData],
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        EzvizWaterQuantitySelect(coordinator, serial)
        for serial in coordinator.data
    )


class EzvizWaterQuantitySelect(EzvizVacuumEntity, SelectEntity):
    """Control the mop water quantity."""

    _attr_translation_key = "water_quantity_control"
    _attr_options = list(WATER_QUANTITIES)

    def __init__(self, coordinator, serial: str) -> None:
        super().__init__(coordinator, serial)
        self._attr_unique_id = f"{serial}_water_quantity_control"

    @property
    def current_option(self) -> str | None:
        data = self.vacuum_data
        if data is None or data.water_quantity not in self.options:
            return None
        return data.water_quantity

    async def async_select_option(self, option: str) -> None:
        await self._async_execute_command(
            self.coordinator.api.set_water_quantity, self.serial, option
        )
