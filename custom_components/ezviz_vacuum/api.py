"""Adapter around pyezvizapi's synchronous client."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from pyezvizapi import EzvizClient
from pyezvizapi.exceptions import (
    EzvizAuthTokenExpired,
    HTTPError,
    InvalidHost,
    InvalidURL,
    PyEzvizError,
)

from .models import MqttEvent, VacuumData, parse_mqtt_event, parse_vacuum_devices

_LOGGER = logging.getLogger(__name__)


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
        if isinstance(err, (InvalidHost, InvalidURL, HTTPError)):
            return EzvizVacuumConnectionError("Could not connect to EZVIZ")
        return EzvizVacuumError("Unexpected EZVIZ API error")

    def login(self) -> None:
        """Authenticate with EZVIZ."""

        try:
            self._client.login()
        except PyEzvizError as err:
            raise self._translate_error(err) from err

    def get_vacuums(self) -> dict[str, VacuumData]:
        """Fetch and normalize all supported vacuums."""

        try:
            return parse_vacuum_devices(self._client.get_device_infos())
        except PyEzvizError as err:
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
            self._mqtt = self._client.get_mqtt_client(_message)
            self._mqtt.connect()
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
        self._disconnect_callback = None
        self._mqtt_connected = False
        if mqtt is not None:
            try:
                mqtt.stop()
            except (PyEzvizError, OSError, ValueError, RuntimeError) as err:
                _LOGGER.debug(
                    "Could not stop EZVIZ push cleanly (%s)",
                    type(err).__name__,
                )
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
        raise NotImplementedError

    def set_fan_speed(self, serial: str, fan_speed: str) -> None:
        raise NotImplementedError
