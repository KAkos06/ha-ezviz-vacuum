"""Consumable reset and body-cleaning acknowledgement controls."""

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory

from .api import CONSUMABLES
from .entity import EzvizVacuumEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        EzvizConsumableResetButton(coordinator, serial, kind)
        for serial in coordinator.data
        for kind in CONSUMABLES
    )


class EzvizConsumableResetButton(EzvizVacuumEntity, ButtonEntity):
    """Reset one accessory's lifetime and read its counters back."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, serial: str, kind: str) -> None:
        super().__init__(coordinator, serial)
        self.kind = kind
        field, _ = CONSUMABLES[kind]
        self._attr_translation_key = f"reset_{field}"
        self._attr_unique_id = f"{serial}_reset_{field}"
        if kind == "sensor":
            self._attr_icon = "mdi:broom"

    @property
    def available(self) -> bool:
        return super().available and not self.coordinator.settings_locked(self.serial)

    async def async_press(self) -> None:
        self._ensure_settings_unlocked()
        await self._async_execute_command(
            self.coordinator.api.reset_consumable, self.serial, self.kind
        )
