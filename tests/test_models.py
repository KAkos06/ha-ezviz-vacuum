"""Parser tests."""

from __future__ import annotations

import json
from pathlib import Path

from custom_components.ezviz_vacuum.models import (
    masked_serial,
    parse_mqtt_event,
    parse_vacuum_devices,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_parse_docked_and_consumables() -> None:
    vacuum = parse_vacuum_devices(_fixture("docked.json"))["ABC123456"]
    assert vacuum.name == "Bözsi"
    assert vacuum.battery_level == 100
    assert vacuum.charging is True
    assert vacuum.map_name == "Lakás"
    assert vacuum.fan_speed == "super"
    assert vacuum.hepa and vacuum.hepa.remaining == 136
    assert vacuum.main_brush and vacuum.main_brush.used == 14
    assert vacuum.carpet_turbo_enabled is True
    assert vacuum.rest_mode_enabled is False


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


def test_mqtt_is_redacted_to_metadata() -> None:
    event = parse_mqtt_event(_fixture("mqtt_event.json"))
    assert event.serial == "ABC123456"
    assert event.event_type == "vacuum_state"
    assert event.payload_keys == ("body", "ext")
    assert not hasattr(event, "payload")
    assert masked_serial(event.serial) == "ABC***456"
