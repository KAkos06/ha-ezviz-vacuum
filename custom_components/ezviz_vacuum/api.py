"""Adapter around pyezvizapi's synchronous client."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pyezvizapi import EzvizClient
from pyezvizapi.exceptions import (
    EzvizAuthTokenExpired,
    HTTPError,
    InvalidHost,
    InvalidURL,
    PyEzvizError,
)
from requests.exceptions import RequestException

from .models import VacuumData, parse_vacuum_devices

ROBOT_RESOURCE = "SweepingRobot"
ROBOT_LOCAL_INDEX = "0"
IOT_ACTION_ENDPOINT = "/v3/iot-feature/action/"
IOT_FEATURE_ENDPOINT = "/v3/iot-feature/feature/"
FAN_SPEEDS = ("quiet", "normal", "strong", "super")
WATER_QUANTITIES = ("dry", "low", "middle", "high")


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

    def close(self) -> None:
        """Release local network resources without revoking the account session."""

        session = getattr(self._client, "_session", None)
        if session is not None:
            session.close()

    def start_cleaning(self, serial: str) -> None:
        """Start a new whole-home cleaning task."""

        self._clean_control(serial, "start")

    def pause(self, serial: str) -> None:
        """Pause the active cleaning task."""

        self._clean_control(serial, "pause")

    def resume(self, serial: str) -> None:
        """Resume the paused cleaning task."""

        self._clean_control(serial, "resume")

    def stop_cleaning(self, serial: str) -> None:
        """Stop the active cleaning task."""

        self._clean_control(serial, "stop")

    def _clean_control(self, serial: str, action: str) -> None:
        """Send a verified cleaning-task control command."""

        self._put_iot_value(
            IOT_ACTION_ENDPOINT,
            serial,
            "SweeperCleanTask",
            "CleanCtrl",
            {"value": {"action": action, "source": "mobile"}},
        )

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
