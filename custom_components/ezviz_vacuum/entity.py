"""Base entity for EZVIZ Vacuum."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import EzvizVacuumError
from .const import DOMAIN
from .coordinator import EzvizVacuumCoordinator
from .models import VacuumData


class EzvizVacuumEntity(CoordinatorEntity[EzvizVacuumCoordinator]):
    """Base coordinator entity tied to one robot."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EzvizVacuumCoordinator, serial: str) -> None:
        super().__init__(coordinator)
        self.serial = serial

    @property
    def vacuum_data(self) -> VacuumData | None:
        return self.coordinator.data.get(self.serial)

    @property
    def available(self) -> bool:
        data = self.vacuum_data
        return super().available and data is not None and data.available

    @property
    def device_info(self) -> DeviceInfo:
        data = self.vacuum_data
        return DeviceInfo(
            identifiers={(DOMAIN, self.serial)},
            name=data.name if data else "EZVIZ Vacuum",
            manufacturer="EZVIZ",
            model=data.model if data else None,
            sw_version=data.firmware if data else None,
        )

    async def _async_execute_command(
        self, command: Callable[..., None], *args: Any
    ) -> None:
        """Run a blocking cloud command and refresh only after success."""

        try:
            await self.coordinator.hass.async_add_executor_job(command, *args)
        except EzvizVacuumError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()
