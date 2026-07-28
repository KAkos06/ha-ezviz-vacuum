"""Data coordinator and MQTT lifecycle management."""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import EzvizVacuumApi, EzvizVacuumAuthError, EzvizVacuumError
from .const import (
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    MQTT_RECONNECT_INITIAL_SECONDS,
    MQTT_RECONNECT_MAX_SECONDS,
    MQTT_REFRESH_DEBOUNCE_SECONDS,
    MQTT_UNROUTED_REFRESH_MIN_SECONDS,
)
from .models import MqttEvent, VacuumData, masked_serial

_LOGGER = logging.getLogger(__name__)


class EzvizVacuumCoordinator(DataUpdateCoordinator[dict[str, VacuumData]]):
    """Coordinate REST state with MQTT-triggered refreshes."""

    def __init__(self, hass: HomeAssistant, api: EzvizVacuumApi) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_POLL_INTERVAL,
        )
        self.api = api
        self.mqtt_connected = False
        self.last_mqtt_event: datetime | None = None
        self._known_serials: set[str] = set()
        self._last_unrouted_refresh: datetime | None = None
        self._debounce_task: asyncio.Task[None] | None = None
        self._reconnect_task: asyncio.Task[None] | None = None
        self._mqtt_started = False
        self._stopping = False

    async def _async_update_data(self) -> dict[str, VacuumData]:
        try:
            devices = await self.hass.async_add_executor_job(self.api.refresh)
        except EzvizVacuumAuthError as err:
            raise ConfigEntryAuthFailed from err
        except EzvizVacuumError as err:
            raise UpdateFailed(str(err)) from err
        self._known_serials.update(devices)
        self.mqtt_connected = self.api.is_mqtt_connected()
        self.update_interval = DEFAULT_POLL_INTERVAL
        if self._mqtt_started and not self.mqtt_connected:
            self._schedule_reconnect()
        return devices

    async def async_start_mqtt(self) -> None:
        """Start MQTT without blocking Home Assistant's event loop."""

        self._stopping = False
        self._mqtt_started = True

        def _event(event: MqttEvent) -> None:
            self.hass.loop.call_soon_threadsafe(self.async_handle_mqtt_event, event)

        def _disconnect(error: Exception | None) -> None:
            self.hass.loop.call_soon_threadsafe(self._handle_disconnect, error)

        try:
            await self.hass.async_add_executor_job(
                self.api.start_mqtt, _event, _disconnect
            )
        except EzvizVacuumError as err:
            _LOGGER.warning("EZVIZ MQTT connection failed: %s", err)
            self.mqtt_connected = False
            self.update_interval = DEFAULT_POLL_INTERVAL
            self._schedule_reconnect()
            return
        except Exception as err:  # MQTT is optional; REST setup must still succeed.
            _LOGGER.warning(
                "EZVIZ MQTT is unavailable with the loaded library (%s); "
                "continuing with REST polling",
                type(err).__name__,
            )
            self._mqtt_started = False
            self.mqtt_connected = False
            self.update_interval = DEFAULT_POLL_INTERVAL
            return
        self.mqtt_connected = self.api.is_mqtt_connected()
        self.update_interval = DEFAULT_POLL_INTERVAL
        if not self.mqtt_connected:
            self._schedule_reconnect()

    def async_handle_mqtt_event(self, event: MqttEvent) -> None:
        """Filter and debounce an event already transferred to the HA loop."""

        if self._stopping:
            return
        if event.serial and event.serial not in self._known_serials:
            _LOGGER.debug("Ignoring MQTT event for %s", masked_serial(event.serial))
            return
        self.mqtt_connected = True
        self.update_interval = DEFAULT_POLL_INTERVAL
        self.last_mqtt_event = event.received_at
        if not event.serial:
            if (
                self._last_unrouted_refresh is not None
                and (
                    event.received_at - self._last_unrouted_refresh
                ).total_seconds()
                < MQTT_UNROUTED_REFRESH_MIN_SECONDS
            ):
                _LOGGER.debug("Rate-limiting MQTT event without a device serial")
                return
            self._last_unrouted_refresh = event.received_at
        _LOGGER.debug(
            "MQTT packet received: type=%s serial=%s keys=%s",
            event.event_type,
            masked_serial(event.serial),
            event.payload_keys,
        )
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()
        self._debounce_task = self.hass.async_create_task(
            self._async_debounced_refresh(), eager_start=False
        )

    async def _async_debounced_refresh(self) -> None:
        try:
            await asyncio.sleep(MQTT_REFRESH_DEBOUNCE_SECONDS)
            _LOGGER.debug("Starting MQTT-triggered REST refresh")
            await self.async_request_refresh()
        except asyncio.CancelledError:
            return

    def _handle_disconnect(self, error: Exception | None) -> None:
        if self._stopping:
            return
        self.mqtt_connected = False
        self.update_interval = DEFAULT_POLL_INTERVAL
        _LOGGER.debug("EZVIZ MQTT disconnected: %s", error or "connection lost")
        # Paho reconnects automatically. A delayed health check restarts the
        # registration only if that built-in reconnect does not recover.
        self._schedule_reconnect()

    def _schedule_reconnect(self) -> None:
        if self._stopping or (self._reconnect_task and not self._reconnect_task.done()):
            return
        self._reconnect_task = self.hass.async_create_task(
            self._async_reconnect(), eager_start=False
        )

    async def _async_reconnect(self) -> None:
        delay = MQTT_RECONNECT_INITIAL_SECONDS
        try:
            while not self._stopping:
                await asyncio.sleep(delay + random.uniform(0, delay * 0.2))
                if self.api.is_mqtt_connected():
                    self.mqtt_connected = True
                    self.update_interval = DEFAULT_POLL_INTERVAL
                    return
                _LOGGER.debug("Restarting EZVIZ MQTT registration")
                await self.async_start_mqtt()
                if self.api.is_mqtt_connected():
                    return
                delay = min(delay * 2, MQTT_RECONNECT_MAX_SECONDS)
        except asyncio.CancelledError:
            return

    async def async_shutdown(self) -> None:
        """Cancel tasks and stop paho before unloading."""

        self._stopping = True
        self._mqtt_started = False
        for task in (self._debounce_task, self._reconnect_task):
            if task and not task.done():
                task.cancel()
        await asyncio.gather(
            *(
                task
                for task in (self._debounce_task, self._reconnect_task)
                if task is not None
            ),
            return_exceptions=True,
        )
        await self.hass.async_add_executor_job(self.api.stop_mqtt)
