"""Replay the captured mobile session through live polling and HA entities."""

import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.vacuum import VacuumActivity

from custom_components.ezviz_vacuum.api import (
    EzvizVacuumApi,
    EzvizVacuumAuthError,
    EzvizVacuumError,
)
from custom_components.ezviz_vacuum.models import apply_live_task, parse_vacuum_devices
from custom_components.ezviz_vacuum.sensor import SENSORS
from custom_components.ezviz_vacuum.vacuum import EzvizVacuum

FIXTURES = Path(__file__).parent / "fixtures"
SESSION = json.loads((FIXTURES / "active_session.json").read_text())


def base_data():
    return parse_vacuum_devices(
        json.loads((FIXTURES / "docked.json").read_text(encoding="utf-8"))
    )["ABC123456"]


def test_entire_recorded_state_sequence_and_activity():
    states = []
    phases = []
    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.start_controls_locked.return_value = False
    coordinator.settings_locked.return_value = False
    entity = EzvizVacuum(coordinator, "ABC123456")
    for record in SESSION["states"]:
        data = apply_live_task(base_data(), record["data"])
        coordinator.data = {"ABC123456": data}
        pair = (data.task_state, entity.activity)
        if not states or states[-1] != pair:
            states.append(pair)
        if not phases or phases[-1] != data.task_phase:
            phases.append(data.task_phase)
        assert data.task_id == record["data"]["taskID"]
        assert data.task_duration == record["data"]["taskDuration"]
        assert data.exception is None
    assert states == [
        ("docked", VacuumActivity.DOCKED),
        ("cleaning", VacuumActivity.CLEANING),
        ("paused", VacuumActivity.PAUSED),
        ("cleaning", VacuumActivity.CLEANING),
        ("returning", VacuumActivity.RETURNING),
        ("docked", VacuumActivity.DOCKED),
    ]
    assert phases == [
        "charging",
        "clean",
        "relocation",
        "clean",
        "pause",
        "clean",
        "backBase",
        "charging",
    ]


def test_active_metrics_do_not_leak_into_returning_or_docked_state():
    paused = next(
        r["data"]
        for r in SESSION["states"]
        if r["data"].get("cleanTaskInfo", {}).get("status") == "pause"
    )
    data = apply_live_task(replace(base_data(), clean_times=2), paused)
    assert data.clean_times == 2  # Configured next task versus running task.
    assert data.clean_pass_total == 1
    assert data.clean_pass_current == 1
    assert data.cleaned_area == pytest.approx(5.05)
    assert data.task_duration == 133
    sensors = {s.key: s.value_fn(data) for s in SENSORS}
    assert sensors["task_phase"] == "pause"
    assert sensors["clean_pass_total"] == 1
    assert data.on_base_station is False
    docked = apply_live_task(data, SESSION["states"][-1]["data"])
    assert docked.cleaned_area is None
    assert docked.clean_pass_current is None
    assert docked.clean_pass_total is None
    assert docked.on_base_station is True


@patch("custom_components.ezviz_vacuum.api.EzvizClient")
def test_refresh_uses_live_task_and_config_over_stale_pagelist(client_class):
    client = client_class.return_value
    client.get_device_infos.return_value = json.loads(
        (FIXTURES / "docked.json").read_text(encoding="utf-8")
    )
    paused = next(
        r["data"]
        for r in SESSION["states"]
        if r["data"].get("cleanTaskInfo", {}).get("status") == "pause"
    )
    paths = []

    def request(method, path, **kwargs):
        paths.append(path)
        if path.endswith("QueryCurrentTask"):
            assert method == "PUT"
            assert set(kwargs["json_body"]["value"]) == {"timestamp"}
            data = paused
        elif path.endswith("StdCleanCfg"):
            assert method == "GET"
            data = [
                {
                    "mapID": 4,
                    "fanMode": "quiet",
                    "waterQuantity": "dry",
                    "cleanTimes": 2,
                }
            ]
        elif path.endswith("SurplusPower"):
            data = 98
        elif path.endswith("PromptToneVolume"):
            data = 53
        elif path.endswith("AreaUnitCfg"):
            data = {"unit": "m2"}
        elif path.endswith("CarpetTurboCleanSwitch"):
            data = {"enabled": 1}
        elif path.endswith("WorkingTime"):
            data = {"rest": 150, "used": 0}
        else:
            raise AssertionError(path)
        return {"meta": {"code": 200}, "data": data}

    client._request_json.side_effect = request
    api = EzvizVacuumApi("user", "password", "eu")
    with patch("custom_components.ezviz_vacuum.api.monotonic", return_value=100):
        data = api.refresh()["ABC123456"]
        api.refresh()
    assert data.task_state == "paused"
    assert data.charging is False
    assert data.map_id == 4
    assert data.map_name is None  # Never label map 4 using map 3's cached name.
    assert data.fan_speed == "quiet"
    assert data.water_quantity == "dry"
    assert data.clean_times == 2
    assert data.battery_level == 98
    assert data.volume == 53
    assert data.area_unit == "m2"
    assert data.carpet_turbo_enabled is True
    assert data.hepa.used == 0
    client.get_device_infos.assert_called_once()
    assert sum(p.endswith("QueryCurrentTask") for p in paths) == 2
    assert sum(p.endswith("StdCleanCfg") for p in paths) == 2
    assert sum(p.endswith("SurplusPower") for p in paths) == 1
    assert sum(p.endswith("PromptToneVolume") for p in paths) == 1


@patch("custom_components.ezviz_vacuum.api.EzvizClient")
def test_live_failure_never_exposes_cached_online_state(client_class):
    api = EzvizVacuumApi("user", "password", "eu")
    with (
        patch.object(api, "get_vacuums", return_value={"ABC123456": base_data()}),
        patch.object(api, "_query_current_task", side_effect=EzvizVacuumError),
    ):
        assert api.refresh()["ABC123456"].available is False
    with (
        patch.object(api, "_query_current_task", side_effect=EzvizVacuumAuthError),
        pytest.raises(EzvizVacuumAuthError),
    ):
        api.refresh()


@patch("custom_components.ezviz_vacuum.api.EzvizClient")
def test_optional_setting_failure_does_not_hide_live_task(client_class):
    api = EzvizVacuumApi("user", "password", "eu")
    task = SESSION["states"][-1]["data"]
    with (
        patch.object(api, "get_vacuums", return_value={"ABC123456": base_data()}),
        patch.object(api, "_query_current_task", return_value=task),
        patch.object(api, "_request_iot", side_effect=EzvizVacuumError),
    ):
        data = api.refresh()["ABC123456"]
    assert data.available
    assert data.task_state == "docked"
    assert data.fan_speed is None
    assert data.water_quantity is None
    assert data.clean_times is None


def test_live_error_and_unknown_task_are_not_reported_as_idle():
    coordinator = MagicMock()
    coordinator.last_update_success = True
    entity = EzvizVacuum(coordinator, "ABC123456")
    data = apply_live_task(
        base_data(),
        {
            "currentTask": "newTask",
            "exceptionCode": "",
            "inCharging": 0,
        },
    )
    coordinator.data = {"ABC123456": data}
    assert entity.activity is None
    coordinator.data["ABC123456"] = apply_live_task(
        data,
        {
            "currentTask": "clean",
            "exceptionCode": "TEST_ERROR",
            "inCharging": 0,
        },
    )
    assert entity.activity is VacuumActivity.ERROR
    assert entity.extra_state_attributes == {"error": "TEST_ERROR"}


@patch("custom_components.ezviz_vacuum.api.EzvizClient")
@pytest.mark.parametrize("record", SESSION["commands"])
def test_active_controls_match_captured_requests(client_class, record):
    client = client_class.return_value
    api = EzvizVacuumApi("user", "password", "eu")
    client._request_json.return_value = record["response"]
    value = record["request"]["value"]
    with patch.object(api, "_query_current_task", return_value={"currentMapID": 4}):
        if "action" in value:
            method = {
                "start": "start_cleaning",
                "pause": "pause",
                "resume": "resume",
                "stop": "stop_cleaning",
            }[value["action"]]
            getattr(api, method)("ABC123456")
        else:
            field, method = next(
                (f, m)
                for f, m in [
                    ("fanMode", "set_fan_speed"),
                    ("waterQuantity", "set_water_quantity"),
                    ("cleanTimes", "set_clean_times"),
                ]
                if f in value
            )
            getattr(api, method)("ABC123456", value[field])
    client._request_json.assert_called_once_with(
        "PUT",
        "/v3/iot-feature/action/ABC123456/SweepingRobot/" + record["operation"],
        json_body=record["request"],
    )
