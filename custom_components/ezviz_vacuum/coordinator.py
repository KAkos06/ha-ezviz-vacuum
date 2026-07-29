"""Data coordinator for periodic EZVIZ cloud polling."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import EzvizVacuumApi, EzvizVacuumAuthError, EzvizVacuumError
from .const import DEFAULT_POLL_INTERVAL, DOMAIN
from .models import VacuumData

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

    async def _async_update_data(self) -> dict[str, VacuumData]:
        try:
            devices = await self.hass.async_add_executor_job(self.api.refresh)
        except EzvizVacuumAuthError as err:
            raise ConfigEntryAuthFailed from err
        except EzvizVacuumError as err:
            raise UpdateFailed(str(err)) from err
        return devices
