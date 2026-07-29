"""Adapter around pyezvizapi's synchronous client."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from contextlib import suppress
from typing import Any

from pyezvizapi import EzvizClient, MQTTClient
from pyezvizapi.exceptions import (
    EzvizAuthTokenExpired,
    HTTPError,
    InvalidHost,
    InvalidURL,
    PyEzvizError,
)
from requests.exceptions import RequestException

from .models import MqttEvent, VacuumData, parse_mqtt_event, parse_vacuum_devices

_LOGGER = logging.getLogger(__name__)

ROBOT_RESOURCE = "SweepingRobot"
ROBOT_LOCAL_INDEX = "0"
IOT_ACTION_ENDPOINT = "/v3/iot-feature/action/"
IOT_FEATURE_ENDPOINT = "/v3/iot-feature/feature/"
FAN_SPEEDS = ("quiet", "normal", "strong", "super")
WATER_QUANTITIES = ("low", "middle", "high")


class EzvizVacuumError(Exception):
    """Base integration API error."""


class EzvizVacuumAuthError(EzvizVacuumError):
    """Authentication failed or expired."""


class EzvizVacuumConnectionError(EzvizVacuumError):
    """Cloud connection failed."""


class EzvizVacuumApi:
    """Stable integration-facing API around pyezvizapi internals."""

    def __init__(self, username: str, password: str, region: str) -> None:
        self._client = EzvizClient(
            account=username, password=password, url=region.lower()
        )
        self._mqtt: Any | None = None
        self._mqtt_legacy = False
        self._mqtt_connected = False
        self._disconnect_callback: Callable[[Exception | None], None] | None = None

    @staticmethod
    def _translate_error(err: Exception) -> EzvizVacuumError:
        message = str(err).lower()
        if isinstance(err, EzvizAuthTokenExpired) or any(
            marker in message
            for marker in (
                "incorrect username",
                "incorrect password",
                "user is locked",
                "login with account",
                "mfa",
                "authentication",
            )
        ):
            return EzvizVacuumAuthError("EZVIZ authentication failed")
        if isinstance(err, (InvalidHost, InvalidURL, HTTPError, RequestException)):
            return EzvizVacuumConnectionError("Could not connect to EZVIZ")
        return EzvizVacuumError("Unexpected EZVIZ API error")

    def login(self) -> None:
        """Authenticate with EZVIZ."""

        try:
            self._client.login()
        except (PyEzvizError, RequestException) as err:
            raise self._translate_error(err) from err

    def get_vacuums(self) -> dict[str, VacuumData]:
        """Fetch and normalize all supported vacuums."""

        try:
            return parse_vacuum_devices(self._client.get_device_infos())
        except (PyEzvizError, RequestException) as err:
            raise self._translate_error(err) from err

    def refresh(self) -> dict[str, VacuumData]:
        """Refresh supported vacuum state."""

        return self.get_vacuums()

    def start_mqtt(
        self,
        callback: Callable[[MqttEvent], None],
        disconnect_callback: Callable[[Exception | None], None],
    ) -> None:
        """Start EZVIZ cloud MQTT; paho owns its network thread."""

        self.stop_mqtt()
        self._disconnect_callback = disconnect_callback

        def _message(raw: dict[str, Any]) -> None:
            callback(parse_mqtt_event(raw))

        try:
            mqtt_factory = getattr(self._client, "get_mqtt_client", None)
            if callable(mqtt_factory):
                self._mqtt_legacy = False
                self._mqtt = mqtt_factory(_message)
                self._mqtt.connect()
            else:
                self._mqtt_legacy = True
                token = getattr(self._client, "_token", None)
                if not isinstance(token, dict):
                    raise EzvizVacuumError(
                        "The loaded pyezvizapi version does not expose an MQTT token"
                    )
                self._mqtt = MQTTClient(token)  # type: ignore[call-arg]

                def _legacy_message(client: Any, userdata: Any, message: Any) -> None:
                    del client, userdata
                    try:
                        decoded = json.loads(message.payload)
                        ext = decoded.get("ext")
                        if isinstance(ext, str):
                            fields = ext.split(",")
                            serial = fields[2] if len(fields) > 2 else None
                            event_type = fields[4] if len(fields) > 4 else None
                        elif isinstance(ext, dict):
                            serial = ext.get("device_serial")
                            event_type = ext.get("alert_type_code")
                        else:
                            serial = None
                            event_type = None
                    except (AttributeError, TypeError, ValueError) as err:
                        _LOGGER.debug(
                            "Could not decode legacy MQTT packet (%s)",
                            type(err).__name__,
                        )
                        return
                    _message(
                        {
                            "ext": {
                                "device_serial": serial,
                                "alert_type_code": event_type,
                            },
                            "legacy_message": True,
                        }
                    )

                # Legacy MQTTClient.start() blocks forever. run() performs
                # registration and starts paho's background network loop.
                self._mqtt.on_message = _legacy_message  # type: ignore[attr-defined]
                self._mqtt.run()  # type: ignore[attr-defined]

            paho = self._mqtt.mqtt_client
            if paho is not None:
                original_connect = paho.on_connect
                original_disconnect = paho.on_disconnect

                def _on_connect(
                    client: Any, userdata: Any, flags: Any, rc: Any, *args: Any
                ) -> None:
                    if original_connect:
                        original_connect(client, userdata, flags, rc, *args)
                    self._mqtt_connected = int(rc) == 0

                def _on_disconnect(
                    client: Any, userdata: Any, rc: Any, *args: Any
                ) -> None:
                    if original_disconnect:
                        original_disconnect(client, userdata, rc, *args)
                    self._mqtt_connected = False
                    if self._disconnect_callback:
                        self._disconnect_callback(None)

                paho.on_connect = _on_connect
                paho.on_disconnect = _on_disconnect
                self._mqtt_connected = bool(paho.is_connected())
        except (PyEzvizError, OSError, ValueError, RuntimeError) as err:
            self._mqtt_connected = False
            raise self._translate_error(err) from err

    def stop_mqtt(self) -> None:
        """Stop MQTT and its paho background thread."""

        mqtt, self._mqtt = self._mqtt, None
        legacy, self._mqtt_legacy = self._mqtt_legacy, False
        self._disconnect_callback = None
        self._mqtt_connected = False
        if mqtt is not None:
            try:
                mqtt.stop()
            except (
                PyEzvizError,
                AttributeError,
                OSError,
                ValueError,
                RuntimeError,
            ) as err:
                _LOGGER.debug(
                    "Could not stop EZVIZ push cleanly (%s)",
                    type(err).__name__,
                )
            finally:
                paho = getattr(mqtt, "mqtt_client", None)
                if legacy and paho is not None:
                    with suppress(
                        AttributeError, OSError, ValueError, RuntimeError
                    ):
                        paho.disconnect()
        self._client.mqtt_client = None

    def is_mqtt_connected(self) -> bool:
        """Return the current paho connection state."""

        if self._mqtt is not None and self._mqtt.mqtt_client is not None:
            self._mqtt_connected = bool(self._mqtt.mqtt_client.is_connected())
        return self._mqtt_connected

    def close(self) -> None:
        """Release local network resources without revoking the account session."""

        self.stop_mqtt()
        session = getattr(self._client, "_session", None)
        if session is not None:
            session.close()

    def start_cleaning(self, serial: str) -> None:
        raise NotImplementedError

    def pause(self, serial: str) -> None:
        raise NotImplementedError

    def resume(self, serial: str) -> None:
        raise NotImplementedError

    def return_to_base(self, serial: str) -> None:
        """Send the robot back to its charging dock."""

        self._put_iot_value(
            IOT_ACTION_ENDPOINT,
            serial,
            "SweeperTaskMgr",
            "RechargeCtrl",
            {"value": {"action": "start"}},
        )

    def set_fan_speed(self, serial: str, fan_speed: str) -> None:
        """Set the fan mode while preserving the rest of StdCleanCfg."""

        if fan_speed not in FAN_SPEEDS:
            raise EzvizVacuumError(f"Unsupported fan speed: {fan_speed}")
        self._set_clean_config_value(serial, "fanMode", fan_speed)

    def set_water_quantity(self, serial: str, water_quantity: str) -> None:
        """Set the mop water level while preserving the rest of StdCleanCfg."""

        if water_quantity not in WATER_QUANTITIES:
            raise EzvizVacuumError(
                f"Unsupported water quantity: {water_quantity}"
            )
        self._set_clean_config_value(serial, "waterQuantity", water_quantity)

    def set_carpet_turbo(self, serial: str, enabled: bool) -> None:
        """Enable or disable automatic carpet boost."""

        self._put_iot_value(
            IOT_FEATURE_ENDPOINT,
            serial,
            "SweeperCleanTask",
            "CarpetTurboCleanSwitch",
            {"value": {"enabled": enabled}},
        )

    def _set_clean_config_value(
        self, serial: str, key: str, value: str
    ) -> None:
        """Read, update, and write the complete standard cleaning config."""

        config = self._get_standard_clean_config(serial)
        config[key] = value
        self._put_iot_value(
            IOT_FEATURE_ENDPOINT,
            serial,
            "SweeperMapMgr",
            "StdCleanCfg",
            {"value": [config]},
        )

    def _put_iot_value(
        self,
        endpoint: str,
        serial: str,
        domain_id: str,
        item_id: str,
        payload: dict[str, Any],
    ) -> None:
        """Write an IoT value through the authenticated requests session.

        pyezvizapi's public IoT setters currently prepare requests manually and
        reuse that prepared request after reauthentication. Its regular JSON
        transport always uses the session's current authentication state.
        """

        path = (
            f"{endpoint}{serial.upper()}/{ROBOT_RESOURCE}/"
            f"{ROBOT_LOCAL_INDEX}/{domain_id}/{item_id}"
        )
        try:
            response = self._client._request_json(  # noqa: SLF001
                "PUT", path, json_body=payload
            )
        except (PyEzvizError, RequestException) as err:
            raise self._translate_error(err) from err

        if not isinstance(response, Mapping):
            raise EzvizVacuumError("EZVIZ returned an invalid command response")
        meta = response.get("meta")
        code = meta.get("code") if isinstance(meta, Mapping) else None
        if isinstance(code, (int, str)):
            try:
                if int(code) == 200:
                    return
            except ValueError:
                pass

        device_code: Any = None
        if isinstance(meta, Mapping):
            more_info = meta.get("moreInfo")
            if isinstance(more_info, Mapping):
                device_meta = more_info.get("deviceMeta")
                if isinstance(device_meta, Mapping):
                    device_code = device_meta.get("code")

        details = [f"API code {code!s}" if code is not None else "missing API code"]
        if device_code is not None:
            details.append(f"device code {device_code!s}")
        raise EzvizVacuumError(
            f"EZVIZ rejected the vacuum command ({', '.join(details)})"
        )

    def _get_standard_clean_config(self, serial: str) -> dict[str, Any]:
        """Return a mutable copy of the current StdCleanCfg object."""

        try:
            devices = self._client.get_device_infos()
        except (PyEzvizError, RequestException) as err:
            raise self._translate_error(err) from err

        if not isinstance(devices, Mapping):
            raise EzvizVacuumError("EZVIZ returned an invalid device response")

        raw_device = devices.get(serial)
        if not isinstance(raw_device, Mapping):
            raw_device = next(
                (
                    device
                    for device_serial, device in devices.items()
                    if isinstance(device_serial, str)
                    and device_serial.casefold() == serial.casefold()
                    and isinstance(device, Mapping)
                ),
                None,
            )
        if not isinstance(raw_device, Mapping):
            raise EzvizVacuumError("EZVIZ vacuum was not found")

        feature_info = raw_device.get("FEATURE_INFO")
        if not isinstance(feature_info, Mapping):
            raise EzvizVacuumError("Standard cleaning configuration is unavailable")
        channel = feature_info.get(ROBOT_LOCAL_INDEX)
        if isinstance(channel, Mapping):
            robot = channel.get(ROBOT_RESOURCE)
        else:
            robot = feature_info.get(ROBOT_RESOURCE)
        if not isinstance(robot, Mapping):
            raise EzvizVacuumError("Standard cleaning configuration is unavailable")
        map_manager = robot.get("SweeperMapMgr")
        if not isinstance(map_manager, Mapping):
            raise EzvizVacuumError("Standard cleaning configuration is unavailable")
        clean_config = map_manager.get("StdCleanCfg")
        if isinstance(clean_config, list):
            clean_config = next(
                (item for item in clean_config if isinstance(item, Mapping)),
                None,
            )
        if not isinstance(clean_config, Mapping):
            raise EzvizVacuumError("Standard cleaning configuration is unavailable")
        return dict(clean_config)
