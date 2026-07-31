"""Vacuum platform."""

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
from .api import FAN_SPEEDS
from .entity import EzvizVacuumEntity
from .models import normalize_task_state

_LOGGER = logging.getLogger(__name__)

# Values are intentionally conservative and easy to extend from real fixtures.
TASK_ACTIVITY_MAP: dict[str, VacuumActivity] = {
    "clean": VacuumActivity.CLEANING,
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
        EzvizVacuum(coordinator, serial) for serial in coordinator.data
    )


class EzvizVacuum(EzvizVacuumEntity, StateVacuumEntity):
    """An EZVIZ robot vacuum with verified controls."""

    _attr_name = None
    _attr_translation_key = "ezviz_vacuum"
    _attr_supported_features = (
        VacuumEntityFeature.START
        | VacuumEntityFeature.PAUSE
        | VacuumEntityFeature.STOP
        | VacuumEntityFeature.FAN_SPEED
    )

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
        normalized = normalize_task_state(data.task_state)
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
        return list(FAN_SPEEDS)

    async def async_start(self) -> None:
        """Start a task, or resume it when the robot is paused."""

        command = (
            self.coordinator.api.resume
            if self.activity is VacuumActivity.PAUSED
            else self.coordinator.api.start_cleaning
        )
        await self._async_execute_task_command(
            command, optimistic_state="cleaning", charging=False
        )

    async def async_pause(self) -> None:
        """Pause the current cleaning task."""

        await self._async_execute_task_command(
            self.coordinator.api.pause, optimistic_state="paused"
        )

    async def async_stop(self, **kwargs) -> None:
        """Stop the current cleaning task."""

        del kwargs
        await self._async_execute_task_command(
            self.coordinator.api.stop_cleaning,
            optimistic_state="paused",
            charging=False,
            hold_until_docked=True,
        )

    async def _async_execute_task_command(
        self,
        command,
        *,
        optimistic_state: str,
        charging: bool | None = None,
        hold_until_docked: bool = False,
    ) -> None:
        """Execute a task command and immediately reflect its expected state."""

        await self._async_execute_command(command, self.serial, refresh=False)
        self.coordinator.async_set_task_state(
            self.serial,
            optimistic_state,
            charging=charging,
            hold_until_docked=hold_until_docked,
        )

    async def async_set_fan_speed(self, fan_speed: str, **kwargs) -> None:
        del kwargs
        await self._async_execute_command(
            self.coordinator.api.set_fan_speed, self.serial, fan_speed
        )

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        data = self.vacuum_data
        if data and data.exception:
            return {"error": data.exception}
        return {}
