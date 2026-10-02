"""Verify body-cleaning support against captured vendor schemas and counters."""

import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import jsonschema
from homeassistant.const import UnitOfTime

from custom_components.ezviz_vacuum.api import CONSUMABLES, EzvizVacuumApi
from custom_components.ezviz_vacuum.button import EzvizConsumableResetButton
from custom_components.ezviz_vacuum.models import ConsumableData
from custom_components.ezviz_vacuum.sensor import SENSORS, EzvizVacuumSensor

from .test_live import base_data

SCHEMA = json.loads(
    (Path(__file__).parent / "fixtures/consumable_schema.json").read_text()
)


@patch("custom_components.ezviz_vacuum.api.EzvizClient")
def test_sensor_reset_payload_matches_device_schema(client_class):
    value = {"type": "sensor"}
    jsonschema.validate(value, SCHEMA["ResetConsumableWorkingTime"]["input"]["schema"])
    client = client_class.return_value
    client._request_json.return_value = {"meta": {"code": 200}}
    api = EzvizVacuumApi("unused", "unused", "eu")
    api._settings["ABC123456"] = (100, {"sensors": ConsumableData(164, 16)})
    api.reset_consumable("ABC123456", "sensor")
    client._request_json.assert_called_once_with(
        "PUT",
        "/v3/iot-feature/action/ABC123456/SweepingRobot/0/"
        "SweeperConsumable/ResetConsumableWorkingTime",
        json_body={"value": value},
    )
    assert "ABC123456" not in api._settings


def test_counter_units_match_captured_schema_and_16_plus_164_is_180():
    for _, item in CONSUMABLES.values():
        fields = SCHEMA[item]["schema"]["properties"]
        assert fields["used"]["unit"] == fields["rest"]["unit"] == "\u5c0f\u65f6"
    descriptions = {description.key: description for description in SENSORS}
    assert all(
        d.native_unit_of_measurement == UnitOfTime.HOURS
        for d in SENSORS
        if d.raw_counter
    )
    coordinator = MagicMock()
    coordinator.data = {
        "ABC123456": replace(base_data(), sensors=ConsumableData(164, 16))
    }
    remaining = EzvizVacuumSensor(
        coordinator, "ABC123456", descriptions["sensor_cleaning_remaining"]
    )
    used = EzvizVacuumSensor(
        coordinator, "ABC123456", descriptions["sensor_cleaning_used"]
    )
    assert remaining.native_value == 164
    assert used.native_value == 16
    assert remaining.extra_state_attributes["total_hours"] == 180
    assert used.extra_state_attributes["source_field"] == "used"


async def test_body_cleaned_button_runs_sensor_reset_then_refreshes():
    coordinator = MagicMock()
    coordinator.settings_locked.return_value = False
    coordinator.hass.async_add_executor_job = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    button = EzvizConsumableResetButton(coordinator, "ABC123456", "sensor")
    assert button.translation_key == "reset_sensors"
    assert button.icon == "mdi:broom"
    await button.async_press()
    coordinator.hass.async_add_executor_job.assert_awaited_once_with(
        coordinator.api.reset_consumable,
        "ABC123456",
        "sensor",
    )
    coordinator.async_request_refresh.assert_awaited_once_with()
