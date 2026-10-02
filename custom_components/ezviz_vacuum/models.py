"""Typed models and defensive parsers for EZVIZ vacuum data."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, time, timedelta
from typing import Any

from .const import SUPPORTED_CATEGORY

_LOGGER = logging.getLogger(__name__)

ACTIVE_TASK_STATES = frozenset(
    {
        "clean",
        "cleaning",
        "pause",
        "paused",
        "cleanpause",
        "stopping",
        "returning",
        "goinghome",
        "docking",
    }
)


@dataclass(frozen=True, slots=True)
class ConsumableData:
    """Consumable counters in hours, as documented by the device API schema."""

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
    hepa: ConsumableData | None
    main_brush: ConsumableData | None
    side_brush: ConsumableData | None
    mop: ConsumableData | None
    sensors: ConsumableData | None
    carpet_turbo_enabled: bool | None
    rest_mode_enabled: bool | None
    rest_mode_start: str | None
    rest_mode_end: str | None
    clean_times: int | None = None
    task_phase: str | None = None
    task_duration: int | None = None
    on_base_station: bool | None = None
    picked_up: bool | None = None
    in_dnd_mode: bool | None = None
    volume: int | None = None
    area_unit: str | None = None


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


def normalize_task_state(value: str | None) -> str | None:
    """Normalize a cloud task state for comparisons and HA mapping."""

    if value is None:
        return None
    normalized = value.strip().lower().replace("_", "").replace("-", "")
    return {
        "clean": "cleaning",
        "cleanpause": "paused",
        "pause": "paused",
    }.get(normalized, normalized)


def task_state_is_active(value: str | None) -> bool:
    """Return whether a task benefits from fast state polling."""

    return normalize_task_state(value) in ACTIVE_TASK_STATES


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
        start_date = today if current_time >= start else today - timedelta(days=1)

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


def _mapping_items(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, Mapping)]
    return [value] if isinstance(value, Mapping) else []


def active_map_settings(
    map_manager: Mapping[str, Any],
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Match standard settings to the map marked in use, regardless of order."""

    maps = _mapping_items(map_manager.get("MapBasicProperty"))
    active_maps = [item for item in maps if _boolean(item.get("inUse")) is True]
    if len(active_maps) == 1:
        active_map = active_maps[0]
    elif len(maps) == 1:
        active_map = maps[0]
    else:
        active_map = {}

    configs = _mapping_items(map_manager.get("StdCleanCfg"))
    map_id = _integer(active_map.get("mapID"))
    if map_id is not None:
        config = next(
            (item for item in configs if _integer(item.get("mapID")) == map_id), {}
        )
        return active_map, config
    if not maps and len(configs) == 1:
        return {"mapID": configs[0].get("mapID")}, configs[0]
    return active_map, {}


def _robot_data(raw_device: Mapping[str, Any]) -> Mapping[str, Any]:
    feature_info = _mapping(raw_device.get("FEATURE_INFO"))
    channel_zero = _mapping(feature_info.get("0"))
    robot = _mapping(channel_zero.get(SUPPORTED_CATEGORY))
    if robot:
        return robot
    # Some API variants omit the channel wrapper.
    return _mapping(feature_info.get(SUPPORTED_CATEGORY))


def _available(
    raw_device: Mapping[str, Any],
    info: Mapping[str, Any],
    robot: Mapping[str, Any],
) -> bool:
    # The pagelist API can keep returning cached device metadata and an online
    # flag after a robot and its dock have lost power.  Do not treat that stale
    # shell as available when the robot-specific feature data is absent.
    if not robot:
        return False

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
    map_data, clean_cfg = active_map_settings(map_mgr)
    consumables = _mapping(robot.get("SweeperConsumable"))
    sweeper_mgr = _mapping(robot.get("SweeperMgr"))
    rest_mode = _mapping(sweeper_mgr.get("RestMode"))
    clean_task = _mapping(robot.get("SweeperCleanTask"))

    battery = _integer(power.get("SurplusPower"))
    if battery is not None:
        battery = max(0, min(100, battery))
    charging = _boolean(current.get("inCharging"))
    task_state = normalize_task_state(_text(current.get("taskState")))
    if charging is True:
        task_state = "docked"
    elif not task_state and charging is False:
        task_state = "idle"

    return VacuumData(
        serial=serial,
        name=_text(info.get("name")) or "EZVIZ Vacuum",
        model=_text(info.get("deviceType") or info.get("model")),
        firmware=_text(info.get("version") or info.get("firmwareVersion")),
        available=_available(raw_device, info, robot),
        battery_level=battery,
        charging=charging,
        task_state=task_state,
        task_id=_integer(current.get("ID")),
        exception=_text(current.get("exception")),
        fan_speed=_text(clean_cfg.get("fanMode")),
        water_quantity=_text(clean_cfg.get("waterQuantity")),
        map_id=_integer(map_data.get("mapID")),
        hepa=_consumable(consumables.get("HepaWorkingTime")),
        main_brush=_consumable(consumables.get("RotatingBrushWorkingTime")),
        side_brush=_consumable(consumables.get("EdgeBrushWorkingTime")),
        mop=_consumable(consumables.get("MopWorkingTime")),
        sensors=_consumable(consumables.get("SensorWorkingTime")),
        carpet_turbo_enabled=_setting_boolean(clean_task.get("CarpetTurboCleanSwitch")),
        rest_mode_enabled=_setting_boolean(sweeper_mgr.get("RestMode")),
        rest_mode_start=_text(rest_mode.get("startTime")),
        rest_mode_end=_text(rest_mode.get("endTime")),
        clean_times=(
            count
            if (count := _integer(clean_cfg.get("cleanTimes"))) in (1, 2)
            else None
        ),
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


def apply_live_task(data: VacuumData, task: Mapping[str, Any]) -> VacuumData:
    """Interpret QueryCurrentTask, whose main task stays 'clean' when paused."""

    task_type = _text(task.get("currentTask"))
    detail = _mapping(task.get(f"{task_type}TaskInfo")) if task_type else {}
    phase = _text(detail.get("status"))
    charging = _boolean(task.get("inCharging"))
    if charging is True:
        state = "docked"
    elif phase in {"pause", "paused"}:
        state = "paused"
    elif task_type == "clean":
        state = "cleaning"
    elif task_type == "recharge":
        state = "returning"
    elif task_type == "standby":
        state = "idle"
    else:
        state = normalize_task_state(task_type)
    exception = _text(task.get("exceptionCode"))
    if exception in {"0", "0x00000000"}:
        exception = None
    return replace(
        data,
        available=True,
        charging=charging,
        task_state=state,
        task_id=_integer(task.get("taskID")),
        exception=exception,
        map_id=_integer(task.get("currentMapID")),
        task_phase=phase,
        task_duration=_integer(task.get("taskDuration")),
        on_base_station=_boolean(task.get("isOnBasestation")),
        picked_up=_boolean(task.get("pickup")),
        in_dnd_mode=_boolean(task.get("inDNDMode")),
    )


def masked_serial(serial: str | None) -> str:
    """Mask a serial for safe debug logging."""

    if not serial:
        return "unknown"
    if len(serial) <= 6:
        return "***"
    return f"{serial[:3]}***{serial[-3:]}"
