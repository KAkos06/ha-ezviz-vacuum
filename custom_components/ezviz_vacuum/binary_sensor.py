"""Binary sensor platform for EZVIZ Vacuum."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from . import EzvizVacuumRuntimeData
from .entity import EzvizVacuumEntity
from .models import VacuumData, rest_mode_is_active


@dataclass(frozen=True, kw_only=True)
class EzvizBinaryDescription(BinarySensorEntityDescription):
    value_fn: Callable[[VacuumData], bool | None]


BINARY_SENSORS = (
    EzvizBinaryDescription(
        key="charging",
        translation_key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda data: data.charging,
    ),
    EzvizBinaryDescription(
        key="online",
        translation_key="online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda data: data.available,
    ),
    EzvizBinaryDescription(
        key="carpet_turbo_enabled",
        translation_key="carpet_turbo_enabled",
        value_fn=lambda data: data.carpet_turbo_enabled,
    ),
    EzvizBinaryDescription(
        key="rest_mode_enabled",
        translation_key="rest_mode_enabled",
        value_fn=lambda data: data.rest_mode_enabled,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[EzvizVacuumRuntimeData],
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    entities: list[BinarySensorEntity] = [
        EzvizVacuumBinarySensor(coordinator, serial, description)
        for serial in coordinator.data
        for description in BINARY_SENSORS
    ]
    entities.extend(
        EzvizRestModeActiveBinarySensor(coordinator, serial)
        for serial in coordinator.data
    )
    async_add_entities(entities)


class EzvizVacuumBinarySensor(EzvizVacuumEntity, BinarySensorEntity):
    entity_description: EzvizBinaryDescription

    def __init__(self, coordinator, serial, description) -> None:
        super().__init__(coordinator, serial)
        self.entity_description = description
        self._attr_unique_id = f"{serial}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        data = self.vacuum_data
        return self.entity_description.value_fn(data) if data else None


class EzvizRestModeActiveBinarySensor(EzvizVacuumEntity, BinarySensorEntity):
    """Show whether the configured device-local rest period is active now."""

    _attr_translation_key = "rest_mode_active"

    def __init__(self, coordinator, serial: str) -> None:
        super().__init__(coordinator, serial)
        self._attr_unique_id = f"{serial}_rest_mode_active"
        self._last_active: bool | None = None

    @property
    def is_on(self) -> bool | None:
        data = self.vacuum_data
        if data is None:
            return None
        return rest_mode_is_active(data, dt_util.now().time())

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._last_active = self.is_on
        self.async_on_remove(
            async_track_time_interval(
                self.hass,
                self._handle_time_update,
                timedelta(minutes=1),
            )
        )

    def _handle_time_update(self, now: datetime) -> None:
        del now
        active = self.is_on
        if active == self._last_active:
            return
        self._last_active = active
        self.async_write_ha_state()

    def _handle_coordinator_update(self) -> None:
        self._last_active = self.is_on
        super()._handle_coordinator_update()
