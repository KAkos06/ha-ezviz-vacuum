"""Switch controls for EZVIZ Vacuum."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
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
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        EzvizCarpetTurboSwitch(coordinator, serial)
        for serial in coordinator.data
    )


class EzvizCarpetTurboSwitch(EzvizVacuumEntity, SwitchEntity):
    """Control automatic carpet boost."""

    _attr_translation_key = "carpet_turbo_control"

    def __init__(self, coordinator, serial: str) -> None:
        super().__init__(coordinator, serial)
        self._attr_unique_id = f"{serial}_carpet_turbo_control"

    @property
    def is_on(self) -> bool | None:
        data = self.vacuum_data
        return data.carpet_turbo_enabled if data else None

    @property
    def available(self) -> bool:
        return super().available and not self.coordinator.settings_locked(self.serial)

    async def async_turn_on(self, **kwargs: Any) -> None:
        del kwargs
        await self._async_set_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        del kwargs
        await self._async_set_enabled(False)

    async def _async_set_enabled(self, enabled: bool) -> None:
        self._ensure_settings_unlocked()
        await self._async_execute_command(
            self.coordinator.api.set_carpet_turbo, self.serial, enabled
        )
