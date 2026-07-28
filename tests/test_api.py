"""API adapter tests."""

from copy import deepcopy
from unittest.mock import MagicMock, patch

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
def test_modern_mqtt_callback_is_normalized(client_class) -> None:
    paho = MagicMock()
    paho.is_connected.return_value = True
    mqtt = client_class.return_value.get_mqtt_client.return_value
    mqtt.mqtt_client = paho
    events = []
    api = EzvizVacuumApi("user@example.com", "secret", "eu")
    api.start_mqtt(events.append, lambda error: None)
    callback = client_class.return_value.get_mqtt_client.call_args.args[0]
    callback({"ext": {"device_serial": "ABC123456", "alert_type_code": 7}})
    assert events[0].serial == "ABC123456"
    assert events[0].event_type == "7"
    mqtt.connect.assert_called_once_with()


@patch("custom_components.ezviz_vacuum.api.MQTTClient")
@patch("custom_components.ezviz_vacuum.api.EzvizClient")
def test_legacy_mqtt_callback_is_normalized(client_class, mqtt_class) -> None:
    client = client_class.return_value
    client.get_mqtt_client = None
    client._token = {"username": "internal-user"}
    mqtt = mqtt_class.return_value
    paho = MagicMock()
    paho.is_connected.return_value = True
    mqtt.mqtt_client = paho
    events = []

    api = EzvizVacuumApi("user@example.com", "secret", "eu")
    api.start_mqtt(events.append, lambda error: None)

    mqtt.run.assert_called_once_with()
    message = MagicMock()
    message.payload = b'{"ext":"unused,now,ABC123456,unused,vacuum_state"}'
    mqtt.on_message(None, None, message)
    assert events[0].serial == "ABC123456"
    assert events[0].event_type == "vacuum_state"


@patch("custom_components.ezviz_vacuum.api.EzvizClient")
def test_return_to_base_uses_verified_action_and_wrapper(client_class) -> None:
    client = client_class.return_value
    client._request_json.return_value = {"meta": {"code": 200}}
    api = EzvizVacuumApi("user@example.com", "secret", "eu")

    api.return_to_base("ABC123456")

    client._request_json.assert_called_once_with(
        "PUT",
        "/v3/iot-feature/action/ABC123456/SweepingRobot/0/"
        "SweeperTaskMgr/RechargeCtrl",
        json_body={"value": {"action": "start"}},
    )
    client.set_iot_action.assert_not_called()


@patch("custom_components.ezviz_vacuum.api.EzvizClient")
@pytest.mark.parametrize(
    ("method_name", "field", "new_value"),
    [
        ("set_fan_speed", "fanMode", "super"),
        ("set_water_quantity", "waterQuantity", "high"),
    ],
)
def test_clean_config_controls_preserve_all_other_fields(
    client_class, method_name, field, new_value
) -> None:
    client = client_class.return_value
    original = _raw_device()
    original_config = deepcopy(
        original["FEATURE_INFO"]["0"]["SweepingRobot"]["SweeperMapMgr"][
            "StdCleanCfg"
        ][0]
    )
    client.get_device_infos.return_value = {"ABC123456": original}
    client._request_json.return_value = {"meta": {"code": 200}}
    api = EzvizVacuumApi("user@example.com", "secret", "eu")

    getattr(api, method_name)("ABC123456", new_value)

    expected = deepcopy(original_config)
    expected[field] = new_value
    client._request_json.assert_called_once_with(
        "PUT",
        "/v3/iot-feature/feature/ABC123456/SweepingRobot/0/"
        "SweeperMapMgr/StdCleanCfg",
        json_body={"value": [expected]},
    )
    client.set_iot_feature.assert_not_called()
    assert original["FEATURE_INFO"]["0"]["SweepingRobot"]["SweeperMapMgr"][
        "StdCleanCfg"
    ][0] == original_config


@patch("custom_components.ezviz_vacuum.api.EzvizClient")
def test_carpet_turbo_uses_verified_feature_and_wrapper(client_class) -> None:
    client = client_class.return_value
    client._request_json.return_value = {"meta": {"code": 200}}
    api = EzvizVacuumApi("user@example.com", "secret", "eu")

    api.set_carpet_turbo("ABC123456", True)

    client._request_json.assert_called_once_with(
        "PUT",
        "/v3/iot-feature/feature/ABC123456/SweepingRobot/0/"
        "SweeperCleanTask/CarpetTurboCleanSwitch",
        json_body={"value": {"enabled": 1}},
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
def test_missing_clean_config_does_not_write(client_class) -> None:
    client = client_class.return_value
    client.get_device_infos.return_value = {"ABC123456": {}}
    api = EzvizVacuumApi("user@example.com", "secret", "eu")

    with pytest.raises(EzvizVacuumError):
        api.set_fan_speed("ABC123456", "normal")

    client._request_json.assert_not_called()


@patch("custom_components.ezviz_vacuum.api.EzvizClient")
def test_command_errors_are_translated(client_class) -> None:
    client = client_class.return_value
    client._request_json.side_effect = HTTPError
    api = EzvizVacuumApi("user@example.com", "secret", "eu")

    with pytest.raises(EzvizVacuumConnectionError):
        api.return_to_base("ABC123456")


@patch("custom_components.ezviz_vacuum.api.EzvizClient")
def test_requests_connection_errors_are_translated(client_class) -> None:
    client = client_class.return_value
    client._request_json.side_effect = RequestsConnectionError
    api = EzvizVacuumApi("user@example.com", "secret", "eu")

    with pytest.raises(EzvizVacuumConnectionError):
        api.return_to_base("ABC123456")


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
        api.return_to_base("ABC123456")
