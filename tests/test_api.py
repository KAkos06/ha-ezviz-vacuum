"""API adapter tests."""

import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest
from pyezvizapi.exceptions import HTTPError
from requests.exceptions import ConnectionError as RequestsConnectionError

from custom_components.ezviz_vacuum.api import (
    EzvizVacuumApi,
    EzvizVacuumConnectionError,
    EzvizVacuumError,
)


def _raw_device(clean_config=None):
    return {
        "FEATURE_INFO": {
            "0": {
                "SweepingRobot": {
                    "SweeperMapMgr": {
                        "StdCleanCfg": [
                            clean_config
                            or {
                                "fanMode": "normal",
                                "waterQuantity": "middle",
                                "cleanTimes": 1,
                                "cleanConfigType": "universal",
                                "mapID": 3,
                                "futureField": {"preserve": True},
                            }
                        ]
                    }
                }
            }
        }
    }


@patch("custom_components.ezviz_vacuum.api.EzvizClient")
def test_login_and_refresh_use_real_library_surface(client_class) -> None:
    client = client_class.return_value
    client.get_device_infos.return_value = {}
    api = EzvizVacuumApi("user@example.com", "secret", "eu")
    api.login()
    assert api.refresh() == {}
    client.login.assert_called_once_with()
    client.get_device_infos.assert_called_once_with()
    client_class.assert_called_once_with(
        account="user@example.com", password="secret", url="eu"
    )


@patch("custom_components.ezviz_vacuum.api.EzvizClient")
@pytest.mark.parametrize(
    ("method_name", "action"),
    [
        ("start_cleaning", "start"),
        ("pause", "pause"),
        ("resume", "resume"),
        ("stop_cleaning", "stop"),
    ],
)
def test_clean_controls_use_verified_action_and_wrapper(
    client_class, method_name: str, action: str
) -> None:
    client = client_class.return_value
    client._request_json.return_value = {"meta": {"code": 200}}
    api = EzvizVacuumApi("user@example.com", "secret", "eu")

    getattr(api, method_name)("abc123456")

    client._request_json.assert_called_once_with(
        "PUT",
        "/v3/iot-feature/action/ABC123456/SweepingRobot/0/SweeperCleanTask/CleanCtrl",
        json_body={"value": {"action": action, "source": "mobile"}},
    )


@patch("custom_components.ezviz_vacuum.api.EzvizClient")
@pytest.mark.parametrize(
    ("method_name", "action", "field", "new_value"),
    [
        ("set_fan_speed", "SetFanModeOfStdClean", "fanMode", "super"),
        ("set_water_quantity", "SetWaterQuantityOfStdClean", "waterQuantity", "high"),
        ("set_clean_times", "SetCleanTimesOfStdClean", "cleanTimes", 2),
    ],
)
def test_clean_config_controls_only_change_the_requested_setting(
    client_class, method_name, action, field, new_value
) -> None:
    client = client_class.return_value
    original = _raw_device()
    original_config = deepcopy(
        original["FEATURE_INFO"]["0"]["SweepingRobot"]["SweeperMapMgr"]["StdCleanCfg"][
            0
        ]
    )
    client.get_device_infos.return_value = {"ABC123456": original}
    client._request_json.side_effect = [
        {"meta": {"code": 200}, "data": {"currentTask": "charging", "currentMapID": 3}},
        {"meta": {"code": 200}},
    ]
    api = EzvizVacuumApi("user@example.com", "secret", "eu")

    getattr(api, method_name)("ABC123456", new_value)

    client._request_json.assert_called_with(
        "PUT",
        f"/v3/iot-feature/action/ABC123456/SweepingRobot/0/SweeperMapMgr/{action}",
        json_body={"value": {"mapID": 3, field: new_value}},
    )
    client.set_iot_feature.assert_not_called()
    assert (
        original["FEATURE_INFO"]["0"]["SweepingRobot"]["SweeperMapMgr"]["StdCleanCfg"][
            0
        ]
        == original_config
    )


CAPTURED_SETTINGS = json.loads(
    (Path(__file__).parent / "fixtures/docked_setting_commands.json").read_text()
)


@patch("custom_components.ezviz_vacuum.api.EzvizClient")
@pytest.mark.parametrize("capture", CAPTURED_SETTINGS)
def test_setting_commands_match_docked_mobile_capture(client_class, capture) -> None:
    client = client_class.return_value
    device = _raw_device()
    map_manager = device["FEATURE_INFO"]["0"]["SweepingRobot"]["SweeperMapMgr"]
    map_manager["MapBasicProperty"] = [
        {"mapID": 3, "inUse": 0},
        {"mapID": 4, "inUse": 1},
    ]
    client.get_device_infos.return_value = {"ABC123456": device}
    client._request_json.side_effect = [
        {"meta": {"code": 200}, "data": {"currentTask": "charging", "currentMapID": 4}},
        capture["response"],
    ]
    api = EzvizVacuumApi("user@example.com", "secret", "eu")
    action = capture["action"]
    method, field = {
        "SetFanModeOfStdClean": (api.set_fan_speed, "fanMode"),
        "SetWaterQuantityOfStdClean": (api.set_water_quantity, "waterQuantity"),
        "SetCleanTimesOfStdClean": (api.set_clean_times, "cleanTimes"),
    }[action]

    method("abc123456", capture["request"]["value"][field])

    client._request_json.assert_called_with(
        "PUT",
        f"/v3/iot-feature/action/ABC123456/SweepingRobot/0/SweeperMapMgr/{action}",
        json_body=capture["request"],
    )


@patch("custom_components.ezviz_vacuum.api.EzvizClient")
def test_missing_live_map_does_not_send_a_setting(client_class) -> None:
    client = client_class.return_value
    device = _raw_device()
    device["FEATURE_INFO"]["0"]["SweepingRobot"]["SweeperMapMgr"][
        "MapBasicProperty"
    ] = [{"mapID": 3}, {"mapID": 4}]
    client.get_device_infos.return_value = {"ABC123456": device}
    client._request_json.return_value = {
        "meta": {"code": 200},
        "data": {"currentTask": "charging"},
    }
    api = EzvizVacuumApi("user@example.com", "secret", "eu")

    with pytest.raises(EzvizVacuumError, match="Active cleaning map"):
        api.set_clean_times("ABC123456", 2)

    assert client._request_json.call_count == 1
    assert client._request_json.call_args.args[1].endswith("QueryCurrentTask")


@patch("custom_components.ezviz_vacuum.api.EzvizClient")
@pytest.mark.parametrize("count", [0, 3, True, "2", 1.5])
def test_invalid_clean_times_does_not_read_or_write(client_class, count) -> None:
    client = client_class.return_value
    api = EzvizVacuumApi("user@example.com", "secret", "eu")
    with pytest.raises(EzvizVacuumError):
        api.set_clean_times("ABC123456", count)
    client.get_device_infos.assert_not_called()
    client._request_json.assert_not_called()


@patch("custom_components.ezviz_vacuum.api.EzvizClient")
@pytest.mark.parametrize("enabled", [True, False])
def test_carpet_turbo_uses_verified_feature_and_wrapper(
    client_class, enabled: bool
) -> None:
    client = client_class.return_value
    client._request_json.return_value = {"meta": {"code": 200}}
    api = EzvizVacuumApi("user@example.com", "secret", "eu")

    api.set_carpet_turbo("ABC123456", enabled)

    client._request_json.assert_called_once_with(
        "PUT",
        "/v3/iot-feature/feature/ABC123456/SweepingRobot/0/"
        "SweeperCleanTask/CarpetTurboCleanSwitch",
        json_body={"value": {"enabled": enabled}},
    )
    client.set_iot_feature.assert_not_called()


@patch("custom_components.ezviz_vacuum.api.EzvizClient")
def test_invalid_setting_does_not_read_or_write(client_class) -> None:
    client = client_class.return_value
    api = EzvizVacuumApi("user@example.com", "secret", "eu")

    with pytest.raises(EzvizVacuumError):
        api.set_fan_speed("ABC123456", "turbo-plus")
    with pytest.raises(EzvizVacuumError):
        api.set_water_quantity("ABC123456", "maximum")

    client.get_device_infos.assert_not_called()
    client._request_json.assert_not_called()


@patch("custom_components.ezviz_vacuum.api.EzvizClient")
def test_invalid_live_task_does_not_write(client_class) -> None:
    client = client_class.return_value
    client.get_device_infos.return_value = {"ABC123456": {}}
    client._request_json.return_value = {"meta": {"code": 200}, "data": None}
    api = EzvizVacuumApi("user@example.com", "secret", "eu")

    with pytest.raises(EzvizVacuumError):
        api.set_fan_speed("ABC123456", "normal")

    assert client._request_json.call_count == 1
    assert client._request_json.call_args.args[1].endswith("QueryCurrentTask")


@patch("custom_components.ezviz_vacuum.api.EzvizClient")
def test_command_errors_are_translated(client_class) -> None:
    client = client_class.return_value
    client._request_json.side_effect = HTTPError
    api = EzvizVacuumApi("user@example.com", "secret", "eu")

    with pytest.raises(EzvizVacuumConnectionError):
        api.pause("ABC123456")


@patch("custom_components.ezviz_vacuum.api.EzvizClient")
def test_requests_connection_errors_are_translated(client_class) -> None:
    client = client_class.return_value
    client._request_json.side_effect = RequestsConnectionError
    api = EzvizVacuumApi("user@example.com", "secret", "eu")

    with pytest.raises(EzvizVacuumConnectionError):
        api.pause("ABC123456")


@patch("custom_components.ezviz_vacuum.api.EzvizClient")
def test_rejected_command_exposes_only_safe_error_codes(client_class) -> None:
    client = client_class.return_value
    client._request_json.return_value = {
        "meta": {
            "code": 500,
            "moreInfo": {"deviceMeta": {"code": "DEVICE_BUSY"}},
        }
    }
    api = EzvizVacuumApi("user@example.com", "secret", "eu")

    with pytest.raises(
        EzvizVacuumError,
        match=r"API code 500, device code DEVICE_BUSY",
    ):
        api.pause("ABC123456")


@patch("custom_components.ezviz_vacuum.api.EzvizClient")
def test_cloud_success_does_not_hide_a_device_rejection(client_class) -> None:
    client = client_class.return_value
    client._request_json.return_value = {
        "meta": {"code": 200, "moreInfo": {"deviceMeta": {"code": "0x00000001"}}}
    }
    api = EzvizVacuumApi("user@example.com", "secret", "eu")

    with pytest.raises(EzvizVacuumError, match="device code 0x00000001"):
        api.pause("ABC123456")
