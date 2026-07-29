"""Parser tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime, time
from pathlib import Path

from custom_components.ezviz_vacuum.models import (
    masked_serial,
    parse_vacuum_devices,
    rest_mode_is_active,
    rest_mode_window,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_parse_docked_and_consumables() -> None:
    vacuum = parse_vacuum_devices(_fixture("docked.json"))["ABC123456"]
    assert vacuum.available is True
    assert vacuum.name == "Bözsi"
    assert vacuum.battery_level == 100
    assert vacuum.charging is True
    assert vacuum.task_state == "docked"
    assert vacuum.map_name == "Lakás"
    assert vacuum.fan_speed == "super"
    assert vacuum.hepa and vacuum.hepa.remaining == 136
    assert vacuum.main_brush and vacuum.main_brush.used == 14
    assert vacuum.carpet_turbo_enabled is True
    assert vacuum.rest_mode_enabled is True
    assert vacuum.rest_mode_start == "22:00:00"
    assert vacuum.rest_mode_end == "07:00:00"
    window = rest_mode_window(
        vacuum, datetime(2026, 7, 28, 23, 0, tzinfo=UTC)
    )
    assert window is not None
    assert window[0] == datetime(2026, 7, 28, 22, 0, tzinfo=UTC)
    assert window[1] == datetime(2026, 7, 29, 7, 0, tzinfo=UTC)
    assert rest_mode_is_active(vacuum, time(23, 0)) is True
    assert rest_mode_is_active(vacuum, time(6, 59)) is True
    assert rest_mode_is_active(vacuum, time(7, 0)) is False
    assert rest_mode_is_active(vacuum, time(12, 0)) is False


def test_rest_mode_window_before_end_and_outside_period() -> None:
    vacuum = parse_vacuum_devices(_fixture("docked.json"))["ABC123456"]

    active_window = rest_mode_window(
        vacuum, datetime(2026, 7, 29, 6, 0, tzinfo=UTC)
    )
    assert active_window is not None
    assert active_window[0] == datetime(2026, 7, 28, 22, 0, tzinfo=UTC)
    assert active_window[1] == datetime(2026, 7, 29, 7, 0, tzinfo=UTC)

    next_window = rest_mode_window(
        vacuum, datetime(2026, 7, 29, 12, 0, tzinfo=UTC)
    )
    assert next_window is not None
    assert next_window[0] == datetime(2026, 7, 29, 22, 0, tzinfo=UTC)
    assert next_window[1] == datetime(2026, 7, 30, 7, 0, tzinfo=UTC)


def test_explicit_offline_status_wins_over_global_status() -> None:
    response = _fixture("docked.json")
    device = response["ABC123456"]
    device["STATUS"]["optionals"]["OnlineStatus"] = 0
    device["deviceInfos"]["status"] = 1
    device["STATUS"]["globalStatus"] = 1

    vacuum = parse_vacuum_devices(response)["ABC123456"]

    assert vacuum.available is False


def test_parse_cleaning_and_types() -> None:
    vacuum = parse_vacuum_devices(_fixture("cleaning.json"))["ABC123456"]
    assert vacuum.battery_level == 72
    assert vacuum.charging is False
    assert vacuum.task_state == "cleaning"
    assert vacuum.task_id == 42


def test_missing_invalid_and_non_vacuum() -> None:
    response = {
        "VAC": {
            "deviceInfos": {
                "deviceCategory": "SweepingRobot",
                "name": "Robot",
            },
            "FEATURE_INFO": {
                "0": {
                    "SweepingRobot": {
                        "PowerMgr": {"SurplusPower": 999},
                        "SweeperTaskMgr": {"CurrentTask": {"inCharging": "invalid"}},
                    }
                }
            },
        },
        "CAM": {"deviceInfos": {"deviceCategory": "Camera"}},
        123: "invalid",
    }
    result = parse_vacuum_devices(response)
    assert set(result) == {"VAC"}
    assert result["VAC"].battery_level == 100
    assert result["VAC"].charging is None


def test_serial_is_masked() -> None:
    assert masked_serial("ABC123456") == "ABC***456"
