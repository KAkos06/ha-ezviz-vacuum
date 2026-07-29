"""Entity tests for verified EZVIZ controls."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.ezviz_vacuum.api import EzvizVacuumError
from custom_components.ezviz_vacuum.models import VacuumData
from custom_components.ezviz_vacuum.select import (
    EzvizFanSpeedSelect,
    EzvizWaterQuantitySelect,
)
from custom_components.ezviz_vacuum.switch import EzvizCarpetTurboSwitch
from custom_components.ezviz_vacuum.vacuum import EzvizVacuum


def _data() -> VacuumData:
    return VacuumData(
        serial="ABC123456",
        name="Vacuum",
        model="CS-RE5P-TWT",
        firmware="1",
        available=True,
        battery_level=100,
        charging=True,
        task_state="docked",
        task_id=None,
        exception=None,
        fan_speed="normal",
        water_quantity="middle",
        map_id=3,
        map_name="Home",
        hepa=None,
        main_brush=None,
        side_brush=None,
        mop=None,
        sensors=None,
        carpet_turbo_enabled=True,
        rest_mode_enabled=False,
        rest_mode_start=None,
        rest_mode_end=None,
    )


def _coordinator():
    coordinator = MagicMock()
    coordinator.data = {"ABC123456": _data()}
    coordinator.last_update_success = True
    coordinator.async_request_refresh = AsyncMock()

    async def execute(command, *args):
        return command(*args)

    coordinator.hass.async_add_executor_job = AsyncMock(side_effect=execute)
    return coordinator


@pytest.mark.asyncio
async def test_vacuum_controls_run_in_executor_and_refresh() -> None:
    coordinator = _coordinator()
    entity = EzvizVacuum(coordinator, "ABC123456")

    await entity.async_return_to_base()
    coordinator.api.return_to_base.assert_called_once_with("ABC123456")
    coordinator.async_request_refresh.assert_awaited_once_with()

    coordinator.async_request_refresh.reset_mock()
    await entity.async_set_fan_speed("super")
    coordinator.api.set_fan_speed.assert_called_once_with("ABC123456", "super")
    coordinator.async_request_refresh.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_water_select_exposes_state_and_controls() -> None:
    coordinator = _coordinator()
    entity = EzvizWaterQuantitySelect(coordinator, "ABC123456")

    assert entity.current_option == "middle"
    assert entity.options == ["dry", "low", "middle", "high"]
    await entity.async_select_option("dry")

    coordinator.api.set_water_quantity.assert_called_once_with(
        "ABC123456", "dry"
    )
    coordinator.async_request_refresh.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_fan_select_exposes_state_and_controls() -> None:
    coordinator = _coordinator()
    entity = EzvizFanSpeedSelect(coordinator, "ABC123456")

    assert entity.translation_key == "fan_speed_control"
    assert entity.current_option == "normal"
    assert entity.options == ["quiet", "normal", "strong", "super"]
    await entity.async_select_option("strong")

    coordinator.api.set_fan_speed.assert_called_once_with(
        "ABC123456", "strong"
    )
    coordinator.async_request_refresh.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_carpet_turbo_switch_exposes_state_and_controls() -> None:
    coordinator = _coordinator()
    entity = EzvizCarpetTurboSwitch(coordinator, "ABC123456")

    assert entity.is_on is True
    await entity.async_turn_off()

    coordinator.api.set_carpet_turbo.assert_called_once_with(
        "ABC123456", False
    )
    coordinator.async_request_refresh.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_failed_command_is_exposed_and_does_not_refresh() -> None:
    coordinator = _coordinator()
    coordinator.api.return_to_base.side_effect = EzvizVacuumError("failed")
    entity = EzvizVacuum(coordinator, "ABC123456")

    with pytest.raises(HomeAssistantError, match="failed"):
        await entity.async_return_to_base()

    coordinator.async_request_refresh.assert_not_awaited()
