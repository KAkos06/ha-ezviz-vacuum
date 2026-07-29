"""Coordinator polling tests."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ezviz_vacuum.const import DEFAULT_POLL_INTERVAL, DOMAIN
from custom_components.ezviz_vacuum.coordinator import EzvizVacuumCoordinator


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
