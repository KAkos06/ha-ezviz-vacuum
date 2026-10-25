"""Data coordinator for periodic EZVIZ cloud polling."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

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
    SETTING_TRANSITION_GRACE_SECONDS,
    START_CONTROL_LOCK_SECONDS,
)
from .mapdata import build_layers
from .maprender import render_svg
from .models import (
    VacuumData,
    masked_serial,
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
        self._command_task_states: dict[str, tuple[str, bool | None, float, bool]] = {}
        self._command_settings: dict[
            tuple[str, str], tuple[Any, float, int | None]
        ] = {}
        self._task_control_lock_until: dict[str, float] = {}
        self._task_control_lock_unsubs: dict[str, Callable[[], None]] = {}
        self.map_images: dict[str, bytes] = {}
        self.map_image_updated: dict[str, datetime] = {}
        self._map_cache: dict[tuple[str, int], tuple[float, dict[str, Any]]] = {}

    def task_controls_locked(self, serial: str) -> bool:
        """Return whether task commands must currently be rejected."""

        data = self.data.get(serial)
        if data and normalize_task_state(data.task_state) == "stopping":
            return True
        return self.start_controls_locked(serial)

    def start_controls_locked(self, serial: str) -> bool:
        """Return whether controls are in the brief post-start lock."""

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
            or self._command_settings
            or any(task_state_is_active(data.task_state) for data in devices.values())
            else DEFAULT_POLL_INTERVAL
        )

    def async_set_setting_state(self, serial: str, field: str, value: Any) -> None:
        """Publish an acknowledged setting while waiting briefly for cloud readback."""
        if field not in {
            "fan_speed",
            "water_quantity",
            "clean_times",
        }:
            raise ValueError("Unsupported setting field")
        current = self.data.get(serial)
        if current is None:
            return
        map_id = (
            current.map_id
            if field
            in {
                "fan_speed",
                "water_quantity",
                "clean_times",
            }
            else None
        )
        self._command_settings[(serial, field)] = (
            value,
            self.hass.loop.time() + SETTING_TRANSITION_GRACE_SECONDS,
            map_id,
        )
        devices = dict(self.data)
        devices[serial] = replace(current, **{field: value})
        self.update_interval = ACTIVE_POLL_INTERVAL
        self.async_set_updated_data(devices)

    def _merge_command_settings(
        self, devices: dict[str, VacuumData]
    ) -> dict[str, VacuumData]:
        """Bound stale-read suppression by confirmation, map and elapsed time."""
        merged = dict(devices)
        now = self.hass.loop.time()
        for (serial, field), (value, deadline, map_id) in tuple(
            self._command_settings.items()
        ):
            current = merged.get(serial)
            if (
                current is None
                or not current.available
                or current.exception
                or (map_id is not None and current.map_id != map_id)
                or now >= deadline
                or getattr(current, field) == value
            ):
                self._command_settings.pop((serial, field), None)
                continue
            merged[serial] = replace(current, **{field: value})
        return merged

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
        for serial, (task_state, charging, transition_until, hold) in tuple(
            self._command_task_states.items()
        ):
            current = merged.get(serial)
            if current is None or not current.available or current.exception:
                self._command_task_states.pop(serial, None)
                continue
            cloud_state = normalize_task_state(current.task_state)
            command_state = normalize_task_state(task_state)
            if hold and cloud_state == "returning":
                # Keep the existing stopping label only while a return is observed.
                merged[serial] = replace(current, task_state="stopping")
                continue
            charging_matches = charging is None or current.charging is charging
            if (
                cloud_state == command_state and charging_matches
            ) or now >= transition_until:
                # Do not let a command override observed state indefinitely.
                self._command_task_states.pop(serial, None)
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
        devices = self._merge_command_settings(devices)
        devices = await self._async_refresh_maps(devices)
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

    async def _async_refresh_maps(
        self, devices: dict[str, VacuumData]
    ) -> dict[str, VacuumData]:
        """Refresh optional maps and use their room IDs as a segment fallback."""
        now = self.hass.loop.time()
        for serial, data in devices.items():
            if data.map_id is None or not data.available:
                continue
            cache_key = (serial, data.map_id)
            cached = self._map_cache.get(cache_key)
            map_refresh_interval = (
                ACTIVE_POLL_INTERVAL
                if task_state_is_active(data.task_state)
                else DEFAULT_POLL_INTERVAL
            ).total_seconds()
            try:
                if cached and now - cached[0] < map_refresh_interval:
                    layers = cached[1]
                else:
                    layers = {}
                    for layer in ("map", "region", "path"):
                        layers[layer] = await self.hass.async_add_executor_job(
                            self.api.fetch_map_layer, serial, layer, data.map_id
                        )
                    image = await self.hass.async_add_executor_job(
                        render_svg,
                        build_layers(
                            layers["map"], layers["region"], layers["path"]
                        ),
                    )
                    self._map_cache[cache_key] = (now, layers)
                    if image and self.map_images.get(serial) != image:
                        self.map_images[serial] = image
                        self.map_image_updated[serial] = datetime.now(UTC)

                # Some EZVIZ accounts return room outlines in the map layer but
                # omit RegionBasicInfo from the device feature payload.
                region_rooms = layers.get("region", {}).get("room", [])
                existing_names = dict(data.rooms)
                rooms = []
                for room in region_rooms if isinstance(region_rooms, list) else []:
                    if not isinstance(room, dict):
                        continue
                    try:
                        room_id = int(room["roomID"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    name = room.get("name") or existing_names.get(room_id)
                    rooms.append((room_id, str(name or f"Room {room_id}")))
                # RegionBasicInfo is the source of IDs used by the room-clean
                # command. Map-layer room IDs are only a fallback for accounts
                # that do not report that canonical room list.
                if rooms and not data.rooms:
                    devices[serial] = replace(
                        data,
                        rooms=tuple(rooms),
                        capabilities=data.capabilities | {"rooms"},
                    )
            except EzvizVacuumError as err:
                _LOGGER.debug(
                    "Optional EZVIZ map unavailable for %s: %s",
                    masked_serial(serial),
                    err,
                )
        return devices

    async def async_shutdown(self) -> None:
        """Cancel transition timers when the config entry unloads."""

        for unsub in self._task_control_lock_unsubs.values():
            unsub()
        self._task_control_lock_unsubs.clear()
        self._task_control_lock_until.clear()
        await super().async_shutdown()
