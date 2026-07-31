"""Typed models and defensive parsers for EZVIZ vacuum data."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any

from .const import SUPPORTED_CATEGORY

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ConsumableData:
    """Raw consumable counters (the unit is not documented)."""

    remaining: int | None
    used: int | None


@dataclass(frozen=True, slots=True)
class VacuumData:
    """Normalized vacuum state used by Home Assistant."""

    serial: str
    name: str
    model: str | None
    firmware: str | None
    available: bool
    battery_level: int | None
    charging: bool | None
    task_state: str | None
    task_id: int | None
    exception: str | None
    fan_speed: str | None
    water_quantity: str | None
    map_id: int | None
    map_name: str | None
    hepa: ConsumableData | None
    main_brush: ConsumableData | None
    side_brush: ConsumableData | None
    mop: ConsumableData | None
    sensors: ConsumableData | None
    carpet_turbo_enabled: bool | None
    rest_mode_enabled: bool | None
    rest_mode_start: str | None
    rest_mode_end: str | None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _boolean(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in (0, "0"):
        return False
    if value in (1, "1"):
        return True
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "on", "yes", "online"}:
            return True
        if normalized in {"false", "off", "no", "offline"}:
            return False
    return None


def _setting_boolean(value: Any) -> bool | None:
    """Parse either a direct switch value or an EZVIZ setting object."""

    data = _mapping(value)
    if data:
        for key in ("enabled", "enable", "status", "switch"):
            if key in data:
                return _boolean(data[key])
        return None
    return _boolean(value)


def _text(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


def _clock_time(value: Any) -> time | None:
    text = _text(value)
    if text is None:
        return None
    try:
        return time.fromisoformat(text)
    except ValueError:
        return None


def rest_mode_window(
    data: VacuumData, current_datetime: datetime
) -> tuple[datetime, datetime] | None:
    """Return the current or next device-local rest period as datetimes."""

    start = _clock_time(data.rest_mode_start)
    end = _clock_time(data.rest_mode_end)
    if start is None or end is None:
        return None

    current_time = current_datetime.time()
    today = current_datetime.date()
    if start < end:
        start_date = today if current_time < end else today + timedelta(days=1)
    elif start > end:
        start_date = today - timedelta(days=1) if current_time < end else today
    else:
        start_date = (
            today if current_time >= start else today - timedelta(days=1)
        )

    end_date = start_date if start < end else start_date + timedelta(days=1)
    timezone = current_datetime.tzinfo
    return (
        datetime.combine(start_date, start, tzinfo=timezone),
        datetime.combine(end_date, end, tzinfo=timezone),
    )


def rest_mode_is_active(data: VacuumData, current_time: time) -> bool | None:
    """Return whether the configured rest period is active at the given time."""

    if data.rest_mode_enabled is False:
        return False
    if data.rest_mode_enabled is None:
        return None

    start = _clock_time(data.rest_mode_start)
    end = _clock_time(data.rest_mode_end)
    if start is None or end is None:
        return None

    current = (current_time.hour, current_time.minute, current_time.second)
    start_value = (start.hour, start.minute, start.second)
    end_value = (end.hour, end.minute, end.second)
    if start_value == end_value:
        return True
    if start_value < end_value:
        return start_value <= current < end_value
    return current >= start_value or current < end_value


def _consumable(value: Any) -> ConsumableData | None:
    data = _mapping(value)
    if not data:
        return None
    return ConsumableData(_integer(data.get("rest")), _integer(data.get("used")))


def _first_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, list):
        return next((item for item in value if isinstance(item, Mapping)), {})
    return _mapping(value)


def _robot_data(raw_device: Mapping[str, Any]) -> Mapping[str, Any]:
    feature_info = _mapping(raw_device.get("FEATURE_INFO"))
    channel_zero = _mapping(feature_info.get("0"))
    robot = _mapping(channel_zero.get(SUPPORTED_CATEGORY))
    if robot:
        return robot
    # Some API variants omit the channel wrapper.
    return _mapping(feature_info.get(SUPPORTED_CATEGORY))


def _available(raw_device: Mapping[str, Any], info: Mapping[str, Any]) -> bool:
    status = _mapping(raw_device.get("STATUS"))
    status_options = _mapping(status.get("optionals"))
    connection = _mapping(raw_device.get("CONNECTION"))

    # Sweeping robots can report STATUS.globalStatus=0 while they are online.
    # Prefer the explicit online flags returned by the device information API.
    for value in (
        status_options.get("OnlineStatus"),
        connection.get("localStatus"),
        connection.get("status"),
        info.get("status"),
        raw_device.get("status"),
        status.get("status"),
        status.get("globalStatus"),
    ):
        parsed = _boolean(value)
        if parsed is not None:
            return parsed
        numeric = _integer(value)
        if numeric is not None:
            return numeric > 0
    return True


def parse_single_vacuum(
    serial: str, raw_device: Mapping[str, Any]
) -> VacuumData | None:
    """Parse one raw device, returning None for non-vacuums."""

    info = _mapping(raw_device.get("deviceInfos"))
    category = info.get("deviceCategory") or raw_device.get("deviceCategory")
    if category != SUPPORTED_CATEGORY:
        return None

    robot = _robot_data(raw_device)
    power = _mapping(robot.get("PowerMgr"))
    current = _mapping(_mapping(robot.get("SweeperTaskMgr")).get("CurrentTask"))
    map_mgr = _mapping(robot.get("SweeperMapMgr"))
    map_data = _first_mapping(map_mgr.get("MapBasicProperty"))
    clean_cfg = _first_mapping(map_mgr.get("StdCleanCfg"))
    consumables = _mapping(robot.get("SweeperConsumable"))
    sweeper_mgr = _mapping(robot.get("SweeperMgr"))
    rest_mode = _mapping(sweeper_mgr.get("RestMode"))
    clean_task = _mapping(robot.get("SweeperCleanTask"))

    battery = _integer(power.get("SurplusPower"))
    if battery is not None:
        battery = max(0, min(100, battery))
    charging = _boolean(current.get("inCharging"))
    task_state = _text(current.get("taskState"))
    if task_state == "clean":
        task_state = "cleaning"
    if not task_state and charging is not None:
        task_state = "docked" if charging else "idle"

    return VacuumData(
        serial=serial,
        name=_text(info.get("name")) or "EZVIZ Vacuum",
        model=_text(info.get("deviceType") or info.get("model")),
        firmware=_text(info.get("version") or info.get("firmwareVersion")),
        available=_available(raw_device, info),
        battery_level=battery,
        charging=charging,
        task_state=task_state,
        task_id=_integer(current.get("ID")),
        exception=_text(current.get("exception")),
        fan_speed=_text(clean_cfg.get("fanMode")),
        water_quantity=_text(clean_cfg.get("waterQuantity")),
        map_id=_integer(map_data.get("mapID")),
        map_name=_text(map_data.get("mapName")),
        hepa=_consumable(consumables.get("HepaWorkingTime")),
        main_brush=_consumable(consumables.get("RotatingBrushWorkingTime")),
        side_brush=_consumable(consumables.get("EdgeBrushWorkingTime")),
        mop=_consumable(consumables.get("MopWorkingTime")),
        sensors=_consumable(consumables.get("SensorWorkingTime")),
        carpet_turbo_enabled=_setting_boolean(
            clean_task.get("CarpetTurboCleanSwitch")
        ),
        rest_mode_enabled=_setting_boolean(sweeper_mgr.get("RestMode")),
        rest_mode_start=_text(rest_mode.get("startTime")),
        rest_mode_end=_text(rest_mode.get("endTime")),
    )


def parse_vacuum_devices(response: Any) -> dict[str, VacuumData]:
    """Parse all SweepingRobot devices from get_device_infos()."""

    if not isinstance(response, Mapping):
        return {}
    result: dict[str, VacuumData] = {}
    for serial, raw in response.items():
        if not isinstance(serial, str) or not isinstance(raw, Mapping):
            continue
        parsed = parse_single_vacuum(serial, raw)
        if parsed is not None:
            result[serial] = parsed
    return result


def masked_serial(serial: str | None) -> str:
    """Mask a serial for safe debug logging."""

    if not serial:
        return "unknown"
    if len(serial) <= 6:
        return "***"
    return f"{serial[:3]}***{serial[-3:]}"
