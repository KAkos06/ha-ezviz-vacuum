"""Verify captured accessory requests, fresh reset readback and HA controls."""

import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.ezviz_vacuum.api import EzvizVacuumApi, EzvizVacuumError
from custom_components.ezviz_vacuum.button import EzvizConsumableResetButton
from custom_components.ezviz_vacuum.number import EzvizVolumeNumber
from custom_components.ezviz_vacuum.select import EzvizAreaUnitSelect

from .test_live import base_data

RECORDS = json.loads(
    (Path(__file__).parent / "fixtures/accessory_settings.json").read_text()
)
WRITES = [r for r in RECORDS if r["method"] == "PUT"]


@patch("custom_components.ezviz_vacuum.api.EzvizClient")
@pytest.mark.parametrize("record", WRITES)
def test_writes_match_actual_app_payloads(client_class, record):
    client = client_class.return_value
    client._request_json.return_value = record["response"]
    api = EzvizVacuumApi("unused", "unused", "eu")
    value = record["request"]["value"]
    operation = record["operation"]
    api._settings["ABC123456"] = (100, {"volume": 0})
    if operation.endswith("PromptToneVolume"):
        api.set_volume("ABC123456", value)
    elif operation.endswith("ResetConsumableWorkingTime"):
        api.reset_consumable("ABC123456", value["type"])
    elif operation.endswith("AreaUnitCfg"):
        api.set_area_unit("ABC123456", value["unit"])
    else:
        api.set_carpet_turbo("ABC123456", value["enabled"])
    endpoint = (
        "action" if operation.endswith("ResetConsumableWorkingTime") else "feature"
    )
    client._request_json.assert_called_once_with(
        "PUT",
        f"/v3/iot-feature/{endpoint}/ABC123456/SweepingRobot/{operation}",
        json_body=record["request"],
    )
    assert "ABC123456" not in api._settings


@patch("custom_components.ezviz_vacuum.api.EzvizClient")
def test_reset_readback_is_not_hidden_by_settings_cache(client_class):
    api = EzvizVacuumApi("unused", "unused", "eu")
    used = 15

    def request(method, endpoint, serial, domain, item, payload=None):
        if item.endswith("WorkingTime"):
            value = {"used": used, "rest": 150 - used}
        elif item == "PromptToneVolume":
            value = 53
        elif item == "AreaUnitCfg":
            value = {"unit": "m2"}
        else:
            value = {"enabled": True}
        return {"meta": {"code": 200}, "data": value}

    with patch.object(api, "_request_iot", side_effect=request):
        before = api._refresh_settings("ABC123456", base_data(), 100)
        assert before.hepa.used == 15
        api.reset_consumable("ABC123456", "hepa")
        used = 0
        after = api._refresh_settings("ABC123456", base_data(), 101)
        assert after.hepa.used == 0
        assert after.hepa.remaining == 150


@patch("custom_components.ezviz_vacuum.api.EzvizClient")
@pytest.mark.parametrize("value", [-1, 101, True, 53.5, "53"])
def test_invalid_volume_sends_no_request(client_class, value):
    api = EzvizVacuumApi("unused", "unused", "eu")
    with pytest.raises(EzvizVacuumError):
        api.set_volume("ABC123456", value)
    client_class.return_value._request_json.assert_not_called()


@patch("custom_components.ezviz_vacuum.api.EzvizClient")
def test_unverified_sensor_reset_sends_no_request(client_class):
    api = EzvizVacuumApi("unused", "unused", "eu")
    with pytest.raises(EzvizVacuumError):
        api.reset_consumable("ABC123456", "sensor")
    client_class.return_value._request_json.assert_not_called()


async def test_entities_expose_reported_values_and_refresh_after_commands():
    coordinator = MagicMock()
    coordinator.data = {"ABC123456": replace(base_data(), volume=53, area_unit="m2")}
    coordinator.settings_locked.return_value = False
    coordinator.hass.async_add_executor_job = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    volume = EzvizVolumeNumber(coordinator, "ABC123456")
    unit = EzvizAreaUnitSelect(coordinator, "ABC123456")
    reset = EzvizConsumableResetButton(coordinator, "ABC123456", "hepa")
    assert volume.native_value == 53
    assert unit.current_option == "m2"
    await volume.async_set_native_value(53)
    coordinator.hass.async_add_executor_job.assert_called_with(
        coordinator.api.set_volume, "ABC123456", 53
    )
    await unit.async_select_option("sq_ft")
    coordinator.hass.async_add_executor_job.assert_called_with(
        coordinator.api.set_area_unit, "ABC123456", "sq.ft"
    )
    await reset.async_press()
    coordinator.hass.async_add_executor_job.assert_called_with(
        coordinator.api.reset_consumable, "ABC123456", "hepa"
    )
    assert coordinator.async_request_refresh.await_count == 3
    coordinator.settings_locked.return_value = True
    for operation in [
        volume.async_set_native_value(42),
        unit.async_select_option("m2"),
        reset.async_press(),
    ]:
        with pytest.raises(HomeAssistantError):
            await operation
