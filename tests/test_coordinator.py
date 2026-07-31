"""Coordinator polling tests."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock

from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ezviz_vacuum.const import (
    ACTIVE_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
)
from custom_components.ezviz_vacuum.coordinator import EzvizVacuumCoordinator
from custom_components.ezviz_vacuum.models import parse_vacuum_devices

FIXTURES = Path(__file__).parent / "fixtures"


def _devices(name: str):
    return parse_vacuum_devices(
        json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    )


def _coordinator(hass, api) -> EzvizVacuumCoordinator:
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
    return EzvizVacuumCoordinator(hass, api, entry)


async def test_first_refresh(hass) -> None:
    api = MagicMock()
    api.refresh.return_value = {}
    coordinator = _coordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()
    assert coordinator.data == {}
    assert coordinator.last_update_success
    assert coordinator.update_interval == timedelta(seconds=15)
    assert coordinator.update_interval == DEFAULT_POLL_INTERVAL
    api.refresh.assert_called_once_with()


async def test_active_task_uses_fast_polling(hass) -> None:
    api = MagicMock()
    api.refresh.return_value = _devices("cleaning.json")
    coordinator = _coordinator(hass, api)

    await coordinator.async_config_entry_first_refresh()

    assert coordinator.update_interval == timedelta(seconds=3)
    assert coordinator.update_interval == ACTIVE_POLL_INTERVAL
    coordinator._release_task_control_lock("ABC123456")


async def test_command_state_is_immediate_and_survives_stale_cloud_data(
    hass,
) -> None:
    api = MagicMock()
    api.refresh.return_value = _devices("docked.json")
    coordinator = _coordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()

    coordinator.async_set_task_state(
        "ABC123456", "cleaning", charging=False
    )

    assert coordinator.data["ABC123456"].task_state == "cleaning"
    assert coordinator.data["ABC123456"].charging is False
    assert coordinator.update_interval == ACTIVE_POLL_INTERVAL
    assert coordinator.task_controls_locked("ABC123456") is True

    coordinator._release_task_control_lock("ABC123456")
    assert coordinator.task_controls_locked("ABC123456") is False

    await coordinator.async_refresh()

    assert coordinator.data["ABC123456"].task_state == "cleaning"
    assert coordinator.data["ABC123456"].charging is False
    assert coordinator.update_interval == ACTIVE_POLL_INTERVAL


async def test_stop_stays_stopping_until_charging_confirms_docking(hass) -> None:
    api = MagicMock()
    api.refresh.return_value = _devices("cleaning.json")
    coordinator = _coordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()

    coordinator.async_set_task_state(
        "ABC123456",
        "stopping",
        charging=False,
        hold_until_docked=True,
    )
    api.refresh.return_value = {
        "ABC123456": replace(
            api.refresh.return_value["ABC123456"],
            task_state="returning",
            charging=False,
        )
    }

    await coordinator.async_refresh()

    assert coordinator.data["ABC123456"].task_state == "stopping"

    task_state, charging, _, hold = coordinator._command_task_states[
        "ABC123456"
    ]
    coordinator._command_task_states["ABC123456"] = (
        task_state,
        charging,
        0,
        hold,
    )
    api.refresh.return_value = _devices("docked.json")

    await coordinator.async_refresh()

    assert coordinator.data["ABC123456"].task_state == "docked"
    assert "ABC123456" not in coordinator._command_task_states


async def test_remote_pause_overrides_started_state_after_transition(hass) -> None:
    api = MagicMock()
    api.refresh.return_value = _devices("cleaning.json")
    coordinator = _coordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()
    coordinator._release_task_control_lock("ABC123456")
    coordinator.async_set_task_state("ABC123456", "cleaning", charging=False)
    coordinator._release_task_control_lock("ABC123456")
    coordinator._command_task_states["ABC123456"] = (
        "cleaning",
        False,
        0,
        False,
    )
    api.refresh.return_value = {
        "ABC123456": replace(
            api.refresh.return_value["ABC123456"], task_state="paused"
        )
    }

    await coordinator.async_refresh()

    assert coordinator.data["ABC123456"].task_state == "paused"
    assert coordinator.task_controls_locked("ABC123456") is False


async def test_remote_start_overrides_stopping_and_relocks_controls(hass) -> None:
    api = MagicMock()
    api.refresh.return_value = _devices("cleaning.json")
    coordinator = _coordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()
    coordinator._release_task_control_lock("ABC123456")
    coordinator.async_set_task_state(
        "ABC123456",
        "stopping",
        charging=False,
        hold_until_docked=True,
    )
    coordinator._command_task_states["ABC123456"] = (
        "stopping",
        False,
        0,
        True,
    )

    await coordinator.async_refresh()

    assert coordinator.data["ABC123456"].task_state == "cleaning"
    assert coordinator.task_controls_locked("ABC123456") is True
    coordinator._release_task_control_lock("ABC123456")
