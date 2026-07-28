"""Coordinator polling and MQTT debounce tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ezviz_vacuum.const import DEFAULT_POLL_INTERVAL, DOMAIN
from custom_components.ezviz_vacuum.coordinator import EzvizVacuumCoordinator
from custom_components.ezviz_vacuum.models import MqttEvent


def _coordinator(hass, api) -> EzvizVacuumCoordinator:
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
    return EzvizVacuumCoordinator(hass, api, entry)


async def test_first_refresh(hass) -> None:
    api = MagicMock()
    api.refresh.return_value = {}
    api.is_mqtt_connected.return_value = False
    coordinator = _coordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()
    assert coordinator.data == {}
    assert coordinator.last_update_success
    assert coordinator.update_interval == timedelta(seconds=60)
    api.refresh.assert_called_once_with()


async def test_mqtt_event_is_debounced(hass) -> None:
    api = MagicMock()
    api.refresh.return_value = {}
    api.is_mqtt_connected.return_value = False
    coordinator = _coordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()
    event = MqttEvent(
        serial=None,
        event_type="state",
        payload_keys=("ext",),
        received_at=datetime.now(UTC),
    )
    with patch(
        "custom_components.ezviz_vacuum.coordinator.MQTT_REFRESH_DEBOUNCE_SECONDS",
        0,
    ):
        coordinator.async_handle_mqtt_event(event)
        coordinator.async_handle_mqtt_event(event)
        await hass.async_block_till_done()
    assert api.refresh.call_count == 2
    assert coordinator.last_mqtt_event == event.received_at
    await coordinator.async_shutdown()


async def test_connected_mqtt_keeps_sixty_second_polling(hass) -> None:
    api = MagicMock()
    api.refresh.return_value = {}
    api.is_mqtt_connected.return_value = True
    coordinator = _coordinator(hass, api)

    await coordinator.async_config_entry_first_refresh()

    assert coordinator.mqtt_connected is True
    assert coordinator.update_interval == DEFAULT_POLL_INTERVAL


async def test_unrouted_mqtt_events_are_rate_limited(hass) -> None:
    api = MagicMock()
    api.refresh.return_value = {}
    api.is_mqtt_connected.return_value = False
    coordinator = _coordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()
    first = MqttEvent(None, "state", ("ext",), datetime.now(UTC))
    second = MqttEvent(
        None,
        "state",
        ("ext",),
        first.received_at + timedelta(seconds=10),
    )

    with patch(
        "custom_components.ezviz_vacuum.coordinator.MQTT_REFRESH_DEBOUNCE_SECONDS",
        0,
    ):
        coordinator.async_handle_mqtt_event(first)
        await hass.async_block_till_done()
        coordinator.async_handle_mqtt_event(second)
        await hass.async_block_till_done()

    assert api.refresh.call_count == 2
    assert coordinator.last_mqtt_event == second.received_at
    await coordinator.async_shutdown()


async def test_unsupported_mqtt_does_not_fail_setup(hass) -> None:
    api = MagicMock()
    api.start_mqtt.side_effect = AttributeError("legacy API")
    coordinator = _coordinator(hass, api)

    await coordinator.async_start_mqtt()

    assert coordinator.mqtt_connected is False
    assert coordinator._reconnect_task is None
