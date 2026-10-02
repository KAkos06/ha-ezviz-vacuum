"""Removed location/area counters stay out of entities and diagnostics."""

from dataclasses import replace
from datetime import timedelta
from unittest.mock import MagicMock

from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ezviz_vacuum import (
    EzvizVacuumRuntimeData,
    _remove_obsolete_entities,
)
from custom_components.ezviz_vacuum.const import DOMAIN
from custom_components.ezviz_vacuum.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.ezviz_vacuum.sensor import SENSORS

from .test_live import base_data

REMOVED = ("map_name", "cleaned_area", "clean_pass_current", "clean_pass_total")


async def test_upgrade_removes_obsolete_sensors_and_preserves_controls(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    old = [
        registry.async_get_or_create(
            "sensor", DOMAIN, f"ABC123456_{key}", config_entry=entry
        )
        for key in REMOVED
    ]
    kept = registry.async_get_or_create(
        "select", DOMAIN, "ABC123456_clean_times_control", config_entry=entry
    )
    _remove_obsolete_entities(hass, entry)
    assert all(registry.async_get(entity.entity_id) is None for entity in old)
    assert registry.async_get(kept.entity_id) is not None
    assert not set(REMOVED) & {description.key for description in SENSORS}


async def test_diagnostics_exclude_map_and_removed_task_metrics(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={})
    coordinator = MagicMock()
    coordinator.data = {"ABC123456": replace(base_data(), clean_times=2)}
    coordinator.last_update_success = True
    coordinator.update_interval = timedelta(seconds=15)
    entry.runtime_data = EzvizVacuumRuntimeData(
        api=MagicMock(), coordinator=coordinator
    )
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    device = next(iter(diagnostics["vacuums"].values()))
    assert not set((*REMOVED, "map_id")) & device.keys()
    assert device["clean_times"] == 2
