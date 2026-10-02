"""Prompt volume control."""

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.exceptions import HomeAssistantError

from .entity import EzvizVacuumEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        EzvizVolumeNumber(coordinator, serial) for serial in coordinator.data
    )


class EzvizVolumeNumber(EzvizVacuumEntity, NumberEntity):
    """Control the robot's prompt volume from zero to one hundred percent."""

    _attr_translation_key = "volume"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator, serial: str) -> None:
        super().__init__(coordinator, serial)
        self._attr_unique_id = f"{serial}_volume"

    @property
    def native_value(self) -> int | None:
        data = self.vacuum_data
        return data.volume if data else None

    @property
    def available(self) -> bool:
        return super().available and not self.coordinator.settings_locked(self.serial)

    async def async_set_native_value(self, value: float) -> None:
        self._ensure_settings_unlocked()
        if not 0 <= value <= 100 or int(value) != value:
            raise HomeAssistantError("Volume must be an integer from 0 to 100")
        await self._async_execute_command(
            self.coordinator.api.set_volume, self.serial, int(value)
        )
