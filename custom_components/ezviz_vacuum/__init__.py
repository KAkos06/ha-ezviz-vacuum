"""EZVIZ Vacuum integration setup."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er

from .api import EzvizVacuumApi, EzvizVacuumAuthError, EzvizVacuumError
from .const import CONF_REGION, PLATFORMS
from .coordinator import EzvizVacuumCoordinator


@dataclass(slots=True)
class EzvizVacuumRuntimeData:
    api: EzvizVacuumApi
    coordinator: EzvizVacuumCoordinator


type EzvizVacuumConfigEntry = ConfigEntry[EzvizVacuumRuntimeData]

_OBSOLETE_ENTITY_SUFFIXES = (
    "_last_mqtt_event",
    "_mqtt_connection",
    "_mqtt_connected",
    "_rest_mode_schedule",
)


async def async_setup_entry(hass: HomeAssistant, entry: EzvizVacuumConfigEntry) -> bool:
    api = EzvizVacuumApi(
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        entry.data[CONF_REGION],
    )
    try:
        await hass.async_add_executor_job(api.login)
    except EzvizVacuumAuthError as err:
        await api_close(hass, api)
        raise ConfigEntryAuthFailed from err
    except EzvizVacuumError as err:
        await api_close(hass, api)
        raise ConfigEntryNotReady from err

    coordinator = EzvizVacuumCoordinator(hass, api, entry)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await api_close(hass, api)
        raise

    entry.runtime_data = EzvizVacuumRuntimeData(api, coordinator)
    _remove_obsolete_entities(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def api_close(hass: HomeAssistant, api: EzvizVacuumApi) -> None:
    await hass.async_add_executor_job(api.close)


def _remove_obsolete_entities(
    hass: HomeAssistant, entry: EzvizVacuumConfigEntry
) -> None:
    """Remove entities exposed by earlier versions."""

    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.unique_id.endswith(_OBSOLETE_ENTITY_SUFFIXES):
            registry.async_remove(entity.entity_id)


async def async_unload_entry(
    hass: HomeAssistant, entry: EzvizVacuumConfigEntry
) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.coordinator.async_shutdown()
        await api_close(hass, entry.runtime_data.api)
    return unloaded


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
