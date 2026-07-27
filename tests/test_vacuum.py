"""Read-only vacuum activity tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from homeassistant.components.vacuum import VacuumActivity

from custom_components.ezviz_vacuum.models import parse_vacuum_devices
from custom_components.ezviz_vacuum.vacuum import EzvizReadOnlyVacuum

FIXTURES = Path(__file__).parent / "fixtures"


def _entity(fixture: str) -> EzvizReadOnlyVacuum:
    devices = parse_vacuum_devices(
        json.loads((FIXTURES / fixture).read_text(encoding="utf-8"))
    )
    coordinator = MagicMock()
    coordinator.data = devices
    coordinator.last_update_success = True
    return EzvizReadOnlyVacuum(coordinator, "ABC123456")


def test_docked_activity_and_unique_id() -> None:
    entity = _entity("docked.json")
    assert entity.activity is VacuumActivity.DOCKED
    assert entity.unique_id == "ABC123456"
    assert entity.device_info["identifiers"]


def test_cleaning_activity() -> None:
    assert _entity("cleaning.json").activity is VacuumActivity.CLEANING
