"""Read-only vacuum platform."""

from __future__ import annotations

import logging

from homeassistant.components.vacuum import (
    StateVacuumEntity,
    VacuumActivity,
    VacuumEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import EzvizVacuumRuntimeData
from .entity import EzvizVacuumEntity

_LOGGER = logging.getLogger(__name__)

# Values are intentionally conservative and easy to extend from real fixtures.
TASK_ACTIVITY_MAP: dict[str, VacuumActivity] = {
    "cleaning": VacuumActivity.CLEANING,
    "paused": VacuumActivity.PAUSED,
    "pause": VacuumActivity.PAUSED,
    "returning": VacuumActivity.RETURNING,
    "goinghome": VacuumActivity.RETURNING,
    "docking": VacuumActivity.RETURNING,
    "docked": VacuumActivity.DOCKED,
    "idle": VacuumActivity.IDLE,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[EzvizVacuumRuntimeData],
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        EzvizReadOnlyVacuum(coordinator, serial) for serial in coordinator.data
    )


class EzvizReadOnlyVacuum(EzvizVacuumEntity, StateVacuumEntity):
    """A state-only vacuum; no unverified commands are exposed."""

    _attr_name = None
    _attr_supported_features = VacuumEntityFeature(0)

    def __init__(self, coordinator, serial: str) -> None:
        super().__init__(coordinator, serial)
        self._attr_unique_id = serial

    @property
    def activity(self) -> VacuumActivity | None:
        data = self.vacuum_data
        if not data or not data.available:
            return None
        if data.exception:
            return VacuumActivity.ERROR
        if data.charging:
            return VacuumActivity.DOCKED
        if not data.task_state:
            return VacuumActivity.IDLE
        normalized = data.task_state.strip().lower().replace("_", "").replace("-", "")
        activity = TASK_ACTIVITY_MAP.get(normalized)
        if activity is None:
            _LOGGER.debug("Unknown EZVIZ task state: %s", data.task_state)
            return VacuumActivity.IDLE
        return activity

    @property
    def fan_speed(self) -> str | None:
        data = self.vacuum_data
        return data.fan_speed if data else None

    @property
    def fan_speed_list(self) -> list[str]:
        return []

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        data = self.vacuum_data
        if data and data.exception:
            return {"error": data.exception}
        return {}
