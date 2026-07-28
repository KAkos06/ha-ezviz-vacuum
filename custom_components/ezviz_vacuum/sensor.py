"""Sensor platform for EZVIZ Vacuum."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import EzvizVacuumRuntimeData
from .entity import EzvizVacuumEntity
from .models import VacuumData


@dataclass(frozen=True, kw_only=True)
class EzvizSensorDescription(SensorEntityDescription):
    value_fn: Callable[[VacuumData], Any]
    raw_counter: bool = False


SENSORS: tuple[EzvizSensorDescription, ...] = (
    EzvizSensorDescription(
        key="battery",
        translation_key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.battery_level,
    ),
    EzvizSensorDescription(
        key="task_state",
        translation_key="task_state",
        value_fn=lambda data: data.task_state,
    ),
    EzvizSensorDescription(
        key="fan_speed",
        translation_key="fan_speed",
        value_fn=lambda data: data.fan_speed,
    ),
    EzvizSensorDescription(
        key="water_quantity",
        translation_key="water_quantity",
        value_fn=lambda data: data.water_quantity,
    ),
    EzvizSensorDescription(
        key="map_name",
        translation_key="map_name",
        value_fn=lambda data: data.map_name,
    ),
    EzvizSensorDescription(
        key="hepa_remaining",
        translation_key="hepa_remaining",
        entity_category=EntityCategory.DIAGNOSTIC,
        raw_counter=True,
        value_fn=lambda data: data.hepa.remaining if data.hepa else None,
    ),
    EzvizSensorDescription(
        key="main_brush_remaining",
        translation_key="main_brush_remaining",
        entity_category=EntityCategory.DIAGNOSTIC,
        raw_counter=True,
        value_fn=lambda data: data.main_brush.remaining if data.main_brush else None,
    ),
    EzvizSensorDescription(
        key="side_brush_remaining",
        translation_key="side_brush_remaining",
        entity_category=EntityCategory.DIAGNOSTIC,
        raw_counter=True,
        value_fn=lambda data: data.side_brush.remaining if data.side_brush else None,
    ),
    EzvizSensorDescription(
        key="mop_remaining",
        translation_key="mop_remaining",
        entity_category=EntityCategory.DIAGNOSTIC,
        raw_counter=True,
        value_fn=lambda data: data.mop.remaining if data.mop else None,
    ),
    EzvizSensorDescription(
        key="sensor_cleaning_remaining",
        translation_key="sensor_cleaning_remaining",
        entity_category=EntityCategory.DIAGNOSTIC,
        raw_counter=True,
        value_fn=lambda data: data.sensors.remaining if data.sensors else None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[EzvizVacuumRuntimeData],
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    entities: list[SensorEntity] = [
        EzvizVacuumSensor(coordinator, serial, description)
        for serial in coordinator.data
        for description in SENSORS
    ]
    async_add_entities(entities)


class EzvizVacuumSensor(EzvizVacuumEntity, SensorEntity):
    entity_description: EzvizSensorDescription

    def __init__(self, coordinator, serial, description) -> None:
        super().__init__(coordinator, serial)
        self.entity_description = description
        self._attr_unique_id = f"{serial}_{description.key}"

    @property
    def native_value(self) -> Any:
        data = self.vacuum_data
        return self.entity_description.value_fn(data) if data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.raw_counter:
            return {"source_field": "rest", "unit_documented": False}
        return None
