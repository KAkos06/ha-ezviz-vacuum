"""Data coordinator for periodic EZVIZ cloud polling."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import EzvizVacuumApi, EzvizVacuumAuthError, EzvizVacuumError
from .const import (
    ACTIVE_POLL_INTERVAL,
    COMMAND_TRANSITION_GRACE_SECONDS,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    START_CONTROL_LOCK_SECONDS,
)
from .models import (
    VacuumData,
    normalize_task_state,
    task_state_is_active,
)

_LOGGER = logging.getLogger(__name__)


class EzvizVacuumCoordinator(DataUpdateCoordinator[dict[str, VacuumData]]):
    """Coordinate periodically refreshed EZVIZ cloud state."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: EzvizVacuumApi,
        config_entry: ConfigEntry,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=DEFAULT_POLL_INTERVAL,
        )
        self.api = api
        self._command_task_states: dict[
            str, tuple[str, bool | None, float, bool]
        ] = {}
        self._task_control_lock_until: dict[str, float] = {}
        self._task_control_lock_unsubs: dict[str, Callable[[], None]] = {}

    def task_controls_locked(self, serial: str) -> bool:
        """Return whether task commands must currently be rejected."""

        data = self.data.get(serial)
        if data and normalize_task_state(data.task_state) == "stopping":
            return True
        return self.hass.loop.time() < self._task_control_lock_until.get(serial, 0)

    def settings_locked(self, serial: str) -> bool:
        """Return whether all adjustable controls are locked while stopping."""

        data = self.data.get(serial)
        return bool(data and normalize_task_state(data.task_state) == "stopping")

    def _set_start_control_lock(self, serial: str, task_state: str) -> None:
        """Lock pause and stop briefly after a successful start command."""

        if unsub := self._task_control_lock_unsubs.pop(serial, None):
            unsub()
        self._task_control_lock_until.pop(serial, None)
        if normalize_task_state(task_state) != "cleaning":
            return

        self._task_control_lock_until[serial] = (
            self.hass.loop.time() + START_CONTROL_LOCK_SECONDS
        )
        self._task_control_lock_unsubs[serial] = async_call_later(
            self.hass,
            START_CONTROL_LOCK_SECONDS,
            lambda _now: self._release_task_control_lock(serial),
        )

    def _release_task_control_lock(self, serial: str) -> None:
        """Unlock controls and update the entity without waiting for a poll."""

        if unsub := self._task_control_lock_unsubs.pop(serial, None):
            unsub()
        self._task_control_lock_until.pop(serial, None)
        self.async_update_listeners()

    def _set_poll_interval(self, devices: dict[str, VacuumData]) -> None:
        """Poll quickly only while a robot has an active task."""

        self.update_interval = (
            ACTIVE_POLL_INTERVAL
            if self._command_task_states
            or any(task_state_is_active(data.task_state) for data in devices.values())
            else DEFAULT_POLL_INTERVAL
        )

    def async_set_task_state(
        self,
        serial: str,
        task_state: str,
        *,
        charging: bool | None = None,
        hold_until_docked: bool = False,
    ) -> None:
        """Publish a successful command immediately and schedule verification."""

        current = self.data.get(serial)
        if current is None:
            return
        devices = dict(self.data)
        devices[serial] = replace(
            current,
            task_state=task_state,
            charging=current.charging if charging is None else charging,
        )
        self._command_task_states[serial] = (
            task_state,
            charging,
            self.hass.loop.time() + COMMAND_TRANSITION_GRACE_SECONDS,
            hold_until_docked,
        )
        self._set_start_control_lock(serial, task_state)
        # Every task command gets one quick verification, including stop.
        self.update_interval = ACTIVE_POLL_INTERVAL
        self.async_set_updated_data(devices)

    def _merge_command_task_states(
        self, devices: dict[str, VacuumData]
    ) -> dict[str, VacuumData]:
        """Reconcile unreliable cloud states with the last successful command."""

        now = self.hass.loop.time()
        merged = dict(devices)
        for serial, (
            task_state,
            charging,
            transition_until,
            hold_until_docked,
        ) in tuple(
            self._command_task_states.items()
        ):
            current = merged.get(serial)
            if current is None:
                self._command_task_states.pop(serial, None)
                continue

            # Charging is the reliable indication that the task has ended.
            if current.charging is True and now >= transition_until:
                self._command_task_states.pop(serial, None)
                continue

            cloud_state = normalize_task_state(current.task_state)
            command_state = normalize_task_state(task_state)

            # Once the cloud reports a return, retain it until actual docking.
            if not hold_until_docked and cloud_state in {
                "returning",
                "goinghome",
                "docking",
            }:
                command_state = "returning"
                charging = False
                self._command_task_states[serial] = (
                    command_state,
                    charging,
                    transition_until,
                    hold_until_docked,
                )

            # Allow a physical pause/resume after stale transition data has passed.
            elif now >= transition_until:
                if command_state == "stopping" and cloud_state == "cleaning":
                    command_state = "cleaning"
                    charging = False
                    hold_until_docked = False
                    transition_until = now + COMMAND_TRANSITION_GRACE_SECONDS
                    self._command_task_states[serial] = (
                        command_state,
                        charging,
                        transition_until,
                        hold_until_docked,
                    )
                elif command_state == "cleaning" and cloud_state == "paused":
                    command_state = "paused"
                    transition_until = now + COMMAND_TRANSITION_GRACE_SECONDS
                    self._command_task_states[serial] = (
                        command_state,
                        charging,
                        transition_until,
                        hold_until_docked,
                    )
                elif command_state == "paused" and cloud_state == "cleaning":
                    command_state = "cleaning"
                    transition_until = now + COMMAND_TRANSITION_GRACE_SECONDS
                    self._command_task_states[serial] = (
                        command_state,
                        charging,
                        transition_until,
                        hold_until_docked,
                    )

            charging_matches = charging is None or current.charging is charging
            if cloud_state == command_state and charging_matches:
                continue

            merged[serial] = replace(
                current,
                task_state=command_state,
                charging=current.charging if charging is None else charging,
            )
        return merged

    async def _async_update_data(self) -> dict[str, VacuumData]:
        previous = self.data or {}
        try:
            devices = await self.hass.async_add_executor_job(self.api.refresh)
        except EzvizVacuumAuthError as err:
            raise ConfigEntryAuthFailed from err
        except EzvizVacuumError as err:
            raise UpdateFailed(str(err)) from err
        devices = self._merge_command_task_states(devices)
        for serial, data in devices.items():
            previous_data = previous.get(serial)
            if task_state_is_active(data.task_state) and (
                normalize_task_state(data.task_state) == "cleaning"
                and (
                    previous_data is None
                    or normalize_task_state(previous_data.task_state) != "cleaning"
                )
            ):
                self._set_start_control_lock(serial, "cleaning")
        self._set_poll_interval(devices)
        return devices

    async def async_shutdown(self) -> None:
        """Cancel transition timers when the config entry unloads."""

        for unsub in self._task_control_lock_unsubs.values():
            unsub()
        self._task_control_lock_unsubs.clear()
        self._task_control_lock_until.clear()
        await super().async_shutdown()
