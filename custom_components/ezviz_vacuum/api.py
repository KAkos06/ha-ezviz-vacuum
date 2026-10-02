"""Adapter around pyezvizapi's synchronous client."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from threading import RLock
from time import monotonic
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

from .models import (
    VacuumData,
    _consumable,
    _setting_boolean,
    active_map_settings,
    apply_live_task,
    masked_serial,
    parse_vacuum_devices,
)

_LOGGER = logging.getLogger(__name__)
METADATA_INTERVAL = 30

ROBOT_RESOURCE = "SweepingRobot"
ROBOT_LOCAL_INDEX = "0"
IOT_ACTION_ENDPOINT = "/v3/iot-feature/action/"
IOT_FEATURE_ENDPOINT = "/v3/iot-feature/feature/"
FAN_SPEEDS = ("quiet", "normal", "strong", "super")
WATER_QUANTITIES = ("dry", "low", "middle", "high")
CLEAN_TIMES = (1, 2)
AREA_UNITS = ("m2", "sq.ft", "ping")
CONSUMABLES = {
    "rotatingBrush": ("main_brush", "RotatingBrushWorkingTime"),
    "hepa": ("hepa", "HepaWorkingTime"),
    "edgeBrush": ("side_brush", "EdgeBrushWorkingTime"),
    "mop": ("mop", "MopWorkingTime"),
    "sensor": ("sensors", "SensorWorkingTime"),
}


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
        self._metadata: dict[str, VacuumData] | None = None
        self._metadata_at = 0.0
        self._battery: dict[str, tuple[float, int]] = {}
        self._session_lock = RLock()
        self._settings: dict[str, tuple[float, dict[str, Any]]] = {}

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
            with self._session_lock:
                self._client.login()
        except (PyEzvizError, RequestException) as err:
            raise self._translate_error(err) from err

    def get_vacuums(self) -> dict[str, VacuumData]:
        """Fetch and normalize all supported vacuums."""

        try:
            with self._session_lock:
                return parse_vacuum_devices(self._client.get_device_infos())
        except (PyEzvizError, RequestException) as err:
            raise self._translate_error(err) from err

    def refresh(self) -> dict[str, VacuumData]:
        """Poll live task/settings; fetch slower metadata and battery every 30s."""

        # Keep cache reads and writes ordered with commands from other threads.
        with self._session_lock:
            return self._refresh()

    def _refresh(self) -> dict[str, VacuumData]:
        """Refresh while holding the reentrant authenticated session lock."""

        now = monotonic()
        if self._metadata is None or now - self._metadata_at >= METADATA_INTERVAL:
            self._metadata = self.get_vacuums()
            self._metadata_at = now
        result = {}
        for serial, base in self._metadata.items():
            try:
                data = apply_live_task(base, self._query_current_task(serial))
            except EzvizVacuumAuthError:
                raise
            except EzvizVacuumError:
                _LOGGER.debug("Live task unavailable for %s", masked_serial(serial))
                result[serial] = replace(base, available=False)
                continue
            try:
                config = self._request_iot(
                    "GET", IOT_FEATURE_ENDPOINT, serial, "SweeperMapMgr", "StdCleanCfg"
                ).get("data")
                _, settings = active_map_settings(
                    {
                        "MapBasicProperty": {"mapID": data.map_id, "inUse": 1},
                        "StdCleanCfg": config,
                    }
                )
                data = replace(
                    data,
                    fan_speed=(
                        settings.get("fanMode")
                        if settings.get("fanMode") in FAN_SPEEDS
                        else None
                    ),
                    water_quantity=(
                        settings.get("waterQuantity")
                        if settings.get("waterQuantity") in WATER_QUANTITIES
                        else None
                    ),
                    clean_times=(
                        settings.get("cleanTimes")
                        if type(settings.get("cleanTimes")) is int
                        and settings.get("cleanTimes") in CLEAN_TIMES
                        else None
                    ),
                )
            except EzvizVacuumAuthError:
                raise
            except EzvizVacuumError:
                data = replace(
                    data, fan_speed=None, water_quantity=None, clean_times=None
                )
            cached_battery = self._battery.get(serial)
            if cached_battery is None or now - cached_battery[0] >= METADATA_INTERVAL:
                try:
                    value = self._request_iot(
                        "GET", IOT_FEATURE_ENDPOINT, serial, "PowerMgr", "SurplusPower"
                    ).get("data")
                    if type(value) is int and 0 <= value <= 100:
                        self._battery[serial] = (now, value)
                except EzvizVacuumAuthError:
                    raise
                except EzvizVacuumError:
                    pass
            if serial in self._battery:
                data = replace(data, battery_level=self._battery[serial][1])
            data = self._refresh_settings(serial, data, now)
            result[serial] = data
        return result

    def _refresh_settings(
        self, serial: str, data: VacuumData, now: float
    ) -> VacuumData:
        cached = self._settings.get(serial)
        if cached is None or now - cached[0] >= METADATA_INTERVAL:
            values: dict[str, Any] = {}
            fields = [
                ("volume", "SoundSetting", "PromptToneVolume"),
                ("area_unit", "SweeperMapMgr", "AreaUnitCfg"),
                ("carpet_turbo_enabled", "SweeperCleanTask", "CarpetTurboCleanSwitch"),
                *(
                    (field, "SweeperConsumable", item)
                    for field, item in CONSUMABLES.values()
                ),
            ]
            for field, domain, item in fields:
                try:
                    value = self._request_iot(
                        "GET", IOT_FEATURE_ENDPOINT, serial, domain, item
                    ).get("data")
                    if field == "volume":
                        value = (
                            value if type(value) is int and 0 <= value <= 100 else None
                        )
                    elif field == "area_unit":
                        value = (
                            value.get("unit") if isinstance(value, Mapping) else None
                        )
                        value = value if value in AREA_UNITS else None
                    elif field == "carpet_turbo_enabled":
                        value = _setting_boolean(value)
                    else:
                        value = _consumable(value)
                    values[field] = value
                except EzvizVacuumAuthError:
                    raise
                except EzvizVacuumError:
                    values[field] = None
            self._settings[serial] = (now, values)
            cached = self._settings[serial]
        return replace(data, **cached[1])

    def set_volume(self, serial: str, volume: int) -> None:
        """Set the prompt volume using the app's scalar percentage payload."""
        if type(volume) is not int or not 0 <= volume <= 100:
            raise EzvizVacuumError("Volume must be an integer from 0 to 100")
        self._put_iot_value(
            IOT_FEATURE_ENDPOINT,
            serial,
            "SoundSetting",
            "PromptToneVolume",
            {"value": volume},
        )
        self._settings.pop(serial, None)

    def set_area_unit(self, serial: str, unit: str) -> None:
        """Set the robot's area display preference."""
        if unit not in AREA_UNITS:
            raise EzvizVacuumError("Unsupported area unit")
        self._put_iot_value(
            IOT_FEATURE_ENDPOINT,
            serial,
            "SweeperMapMgr",
            "AreaUnitCfg",
            {"value": {"unit": unit}},
        )
        self._settings.pop(serial, None)

    def reset_consumable(self, serial: str, consumable: str) -> None:
        """Reset a counter type supported by the captured device API schema."""
        if consumable not in CONSUMABLES:
            raise EzvizVacuumError("Unsupported consumable reset")
        self._put_iot_value(
            IOT_ACTION_ENDPOINT,
            serial,
            "SweeperConsumable",
            "ResetConsumableWorkingTime",
            {"value": {"type": consumable}},
        )
        self._settings.pop(serial, None)

    def _query_current_task(self, serial: str) -> Mapping[str, Any]:
        response = self._request_iot(
            "PUT",
            IOT_ACTION_ENDPOINT,
            serial,
            "SweeperTaskMgr",
            "QueryCurrentTask",
            {
                "value": {
                    "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds")
                }
            },
        )
        task = response.get("data")
        if not isinstance(task, Mapping) or not isinstance(
            task.get("currentTask"), str
        ):
            raise EzvizVacuumError("EZVIZ returned an invalid live task")
        return task

    def close(self) -> None:
        """Release local network resources without revoking the account session."""

        session = getattr(self._client, "_session", None)
        if session is not None:
            with self._session_lock:
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

    def set_fan_speed(self, serial: str, fan_speed: str) -> None:
        """Set only the active map's fan mode, using the mobile app action."""

        if fan_speed not in FAN_SPEEDS:
            raise EzvizVacuumError(f"Unsupported fan speed: {fan_speed}")
        self._set_clean_config_value(
            serial, "SetFanModeOfStdClean", "fanMode", fan_speed
        )

    def set_water_quantity(self, serial: str, water_quantity: str) -> None:
        """Set only the active map's mop water level."""

        if water_quantity not in WATER_QUANTITIES:
            raise EzvizVacuumError(f"Unsupported water quantity: {water_quantity}")
        self._set_clean_config_value(
            serial, "SetWaterQuantityOfStdClean", "waterQuantity", water_quantity
        )

    def set_clean_times(self, serial: str, clean_times: int) -> None:
        """Set one or two passes for the active map."""

        if type(clean_times) is not int or clean_times not in CLEAN_TIMES:
            raise EzvizVacuumError(f"Unsupported cleaning count: {clean_times}")
        self._set_clean_config_value(
            serial, "SetCleanTimesOfStdClean", "cleanTimes", clean_times
        )

    def set_carpet_turbo(self, serial: str, enabled: bool) -> None:
        """Enable or disable automatic carpet boost."""

        self._put_iot_value(
            IOT_FEATURE_ENDPOINT,
            serial,
            "SweeperCleanTask",
            "CarpetTurboCleanSwitch",
            {"value": {"enabled": enabled}},
        )
        self._settings.pop(serial, None)

    def _set_clean_config_value(
        self, serial: str, action: str, key: str, value: str | int
    ) -> None:
        """Change a single setting without overwriting other map settings."""

        map_id = self._get_active_map_id(serial)
        self._put_iot_value(
            IOT_ACTION_ENDPOINT,
            serial,
            "SweeperMapMgr",
            action,
            {"value": {"mapID": map_id, key: value}},
        )

    def _put_iot_value(
        self,
        endpoint: str,
        serial: str,
        domain_id: str,
        item_id: str,
        payload: dict[str, Any],
    ) -> None:
        with self._session_lock:
            self._request_iot("PUT", endpoint, serial, domain_id, item_id, payload)
            self._settings.pop(serial, None)

    def _request_iot(
        self,
        method: str,
        endpoint: str,
        serial: str,
        domain_id: str,
        item_id: str,
        payload: dict[str, Any] | None = None,
    ) -> Mapping[str, Any]:
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
            kwargs = {"json_body": payload} if payload is not None else {}
            with self._session_lock:
                response = self._client._request_json(method, path, **kwargs)  # noqa: SLF001
        except (PyEzvizError, RequestException) as err:
            raise self._translate_error(err) from err

        if not isinstance(response, Mapping):
            raise EzvizVacuumError("EZVIZ returned an invalid command response")
        meta = response.get("meta")
        code = meta.get("code") if isinstance(meta, Mapping) else None
        device_code: Any = None
        if isinstance(meta, Mapping):
            more_info = meta.get("moreInfo")
            if isinstance(more_info, Mapping):
                device_meta = more_info.get("deviceMeta")
                if isinstance(device_meta, Mapping):
                    device_code = device_meta.get("code")

        if isinstance(code, (int, str)):
            try:
                device_success = device_code is None or int(str(device_code), 0) == 0
                if int(code) == 200 and device_success:
                    return response
            except ValueError:
                pass

        details = [f"API code {code!s}" if code is not None else "missing API code"]
        if device_code is not None:
            details.append(f"device code {device_code!s}")
        raise EzvizVacuumError(
            f"EZVIZ rejected the vacuum command ({', '.join(details)})"
        )

    def _get_active_map_id(self, serial: str) -> int:
        """Resolve the map currently in use; never write to an arbitrary map."""

        task = self._query_current_task(serial)
        map_id = task.get("currentMapID")
        if type(map_id) is not int or map_id < 0:
            raise EzvizVacuumError("Active cleaning map is unavailable")
        return map_id
