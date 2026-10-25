"""Vacuum activity and control tests."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

from homeassistant.components.vacuum import VacuumActivity, VacuumEntityFeature
from homeassistant.helpers.translation import async_get_translations

from custom_components.ezviz_vacuum.api import FAN_SPEEDS
from custom_components.ezviz_vacuum.const import DOMAIN
from custom_components.ezviz_vacuum.models import parse_vacuum_devices
from custom_components.ezviz_vacuum.vacuum import EzvizVacuum

FIXTURES = Path(__file__).parent / "fixtures"


def _entity(fixture: str) -> EzvizVacuum:
    devices = parse_vacuum_devices(
        json.loads((FIXTURES / fixture).read_text(encoding="utf-8"))
    )
    coordinator = MagicMock()
    coordinator.data = devices
    coordinator.last_update_success = True
    coordinator.task_controls_locked.return_value = False
    coordinator.start_controls_locked.return_value = False
    coordinator.settings_locked.return_value = False
    return EzvizVacuum(coordinator, "ABC123456")


def test_docked_activity_and_unique_id() -> None:
    entity = _entity("docked.json")
    assert entity.activity is VacuumActivity.DOCKED
    assert entity.unique_id == "ABC123456"
    assert entity.device_info["identifiers"]


def test_ezviz_clean_activity_is_cleaning() -> None:
    assert _entity("cleaning.json").activity is VacuumActivity.CLEANING


def test_stopping_activity_uses_custom_state() -> None:
    entity = _entity("cleaning.json")
    entity.coordinator.data["ABC123456"] = replace(
        entity.coordinator.data["ABC123456"], task_state="stopping"
    )

    assert entity.activity == "stopping"
    assert entity.state == "stopping"


async def test_stopping_state_has_hungarian_translation(hass) -> None:
    translations = await async_get_translations(
        hass, "hu", "entity", integrations={DOMAIN}
    )

    assert (
        translations["component.ezviz_vacuum.entity.vacuum.ezviz_vacuum.state.stopping"]
        == "Leállítás"
    )


def test_verified_features_and_fan_speeds() -> None:
    entity = _entity("docked.json")
    assert entity.supported_features == (
        VacuumEntityFeature.START
        | VacuumEntityFeature.PAUSE
        | VacuumEntityFeature.STOP
        | VacuumEntityFeature.FAN_SPEED
    )
    assert entity.fan_speed_list == list(FAN_SPEEDS)


def test_start_lock_keeps_features_but_disables_entity() -> None:
    entity = _entity("cleaning.json")
    entity.coordinator.start_controls_locked.return_value = True

    clean_area_feature = getattr(
        VacuumEntityFeature, "CLEAN_AREA", VacuumEntityFeature(0)
    )
    assert entity.supported_features == (
        entity._attr_supported_features & ~clean_area_feature
    )
    assert entity.available is False


async def test_get_segments_and_clean_segments(hass) -> None:
    from unittest.mock import AsyncMock
    entity = _entity("cleaning.json")
    entity.hass = hass
    entity.coordinator.hass.async_add_executor_job = AsyncMock(
        side_effect=lambda fn, *args: fn(*args)
    )
    entity.coordinator.data["ABC123456"] = replace(
        entity.coordinator.data["ABC123456"],
        map_id=5,
        rooms=((0, "Konyha"), (1, "Folyosó")),
    )
    segments = await entity.async_get_segments()
    assert len(segments) == 2
    assert segments[0].id == 0
    assert segments[0].name == "Konyha"
    assert segments[1].id == 1
    assert segments[1].name == "Folyosó"

    await entity.async_clean_segments(["0", "1"])
    entity.coordinator.api.clean_rooms.assert_called_once_with(
        "ABC123456", map_id=5, room_ids=[0, 1]
    )
