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

    assert translations[
        "component.ezviz_vacuum.entity.vacuum."
        "ezviz_vacuum.state.stopping"
    ] == "Leállítás"


def test_verified_features_and_fan_speeds() -> None:
    entity = _entity("docked.json")
    assert entity.supported_features == (
        VacuumEntityFeature.START
        | VacuumEntityFeature.PAUSE
        | VacuumEntityFeature.STOP
        | VacuumEntityFeature.FAN_SPEED
    )
    assert entity.fan_speed_list == list(FAN_SPEEDS)
