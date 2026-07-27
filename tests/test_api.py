"""API adapter tests."""

from unittest.mock import MagicMock, patch

from custom_components.ezviz_vacuum.api import EzvizVacuumApi


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
