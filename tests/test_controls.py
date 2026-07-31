"""Entity tests for verified EZVIZ controls."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from homeassistant.components.vacuum import VacuumEntityFeature
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
    coordinator.task_controls_locked.return_value = False
    coordinator.settings_locked.return_value = False
    coordinator.async_request_refresh = AsyncMock()

    async def execute(command, *args):
        return command(*args)

    coordinator.hass.async_add_executor_job = AsyncMock(side_effect=execute)
    return coordinator


@pytest.mark.asyncio
async def test_vacuum_controls_run_in_executor_and_refresh() -> None:
    coordinator = _coordinator()
    entity = EzvizVacuum(coordinator, "ABC123456")

    await entity.async_set_fan_speed("super")
    coordinator.api.set_fan_speed.assert_called_once_with("ABC123456", "super")
    coordinator.async_request_refresh.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_cleaning_controls_run_in_executor_and_refresh() -> None:
    coordinator = _coordinator()
    entity = EzvizVacuum(coordinator, "ABC123456")

    await entity.async_start()
    coordinator.api.start_cleaning.assert_called_once_with("ABC123456")

    await entity.async_pause()
    coordinator.api.pause.assert_called_once_with("ABC123456")

    await entity.async_stop()
    coordinator.api.stop_cleaning.assert_called_once_with("ABC123456")

    assert coordinator.hass.async_add_executor_job.await_count == 3
    assert coordinator.async_set_task_state.call_args_list == [
        call(
            "ABC123456",
            "cleaning",
            charging=False,
            hold_until_docked=False,
        ),
        call(
            "ABC123456",
            "paused",
            charging=None,
            hold_until_docked=False,
        ),
        call(
            "ABC123456",
            "stopping",
            charging=False,
            hold_until_docked=True,
        ),
    ]
    coordinator.async_request_refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_start_resumes_when_paused() -> None:
    coordinator = _coordinator()
    coordinator.data["ABC123456"] = replace(
        coordinator.data["ABC123456"], task_state="paused", charging=False
    )
    entity = EzvizVacuum(coordinator, "ABC123456")

    await entity.async_start()

    coordinator.api.resume.assert_called_once_with("ABC123456")
    coordinator.api.start_cleaning.assert_not_called()
    coordinator.async_set_task_state.assert_called_once_with(
        "ABC123456",
        "cleaning",
        charging=False,
        hold_until_docked=False,
    )
    coordinator.async_request_refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_task_commands_are_rejected_while_transition_is_locked() -> None:
    coordinator = _coordinator()
    coordinator.task_controls_locked.return_value = True
    entity = EzvizVacuum(coordinator, "ABC123456")

    assert entity.supported_features == VacuumEntityFeature.FAN_SPEED
    with pytest.raises(HomeAssistantError, match="temporarily locked"):
        await entity.async_pause()
    with pytest.raises(HomeAssistantError, match="temporarily locked"):
        await entity.async_stop()

    coordinator.api.pause.assert_not_called()
    coordinator.api.stop_cleaning.assert_not_called()


@pytest.mark.asyncio
async def test_all_controls_are_disabled_while_stopping() -> None:
    coordinator = _coordinator()
    coordinator.settings_locked.return_value = True
    coordinator.task_controls_locked.return_value = True
    vacuum = EzvizVacuum(coordinator, "ABC123456")
    water = EzvizWaterQuantitySelect(coordinator, "ABC123456")
    carpet = EzvizCarpetTurboSwitch(coordinator, "ABC123456")

    assert vacuum.supported_features == VacuumEntityFeature(0)
    assert water.available is False
    assert carpet.available is False
    with pytest.raises(HomeAssistantError, match="locked while stopping"):
        await vacuum.async_set_fan_speed("normal")
    with pytest.raises(HomeAssistantError, match="locked while stopping"):
        await water.async_select_option("low")
    with pytest.raises(HomeAssistantError, match="locked while stopping"):
        await carpet.async_turn_off()


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
    coordinator.api.pause.side_effect = EzvizVacuumError("failed")
    entity = EzvizVacuum(coordinator, "ABC123456")

    with pytest.raises(HomeAssistantError, match="failed"):
        await entity.async_pause()

    coordinator.async_request_refresh.assert_not_awaited()
    coordinator.async_set_task_state.assert_not_called()
