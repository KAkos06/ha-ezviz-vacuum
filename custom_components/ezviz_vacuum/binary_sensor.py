"""Binary sensor platform for EZVIZ Vacuum."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import EzvizVacuumRuntimeData
from .entity import EzvizVacuumEntity
from .models import VacuumData


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
        EzvizMqttConnectedBinarySensor(coordinator, serial)
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


class EzvizMqttConnectedBinarySensor(EzvizVacuumEntity, BinarySensorEntity):
    _attr_translation_key = "mqtt_connected"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, serial: str) -> None:
        super().__init__(coordinator, serial)
        self._attr_unique_id = f"{serial}_mqtt_connected"

    @property
    def is_on(self) -> bool:
        return self.coordinator.mqtt_connected
