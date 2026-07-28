"""Diagnostics support with recursive secret redaction."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
from typing import Any

from homeassistant.core import HomeAssistant

from . import EzvizVacuumConfigEntry
from .models import masked_serial

REDACT_KEYS = {
    "username",
    "password",
    "accesstoken",
    "token",
    "session",
    "sessionid",
    "deviceserial",
    "fullserial",
    "secretkey",
    "publickey",
    "resourceid",
    "wanip",
    "externalip",
    "internalip",
    "address",
    "ssid",
    "mac",
    "authcode",
    "casip",
}


def _redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): (
                "**REDACTED**"
                if str(key).replace("_", "").lower() in REDACT_KEYS
                else _redact(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: EzvizVacuumConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data.coordinator
    vacuums = {
        masked_serial(serial): _redact(asdict(data))
        for serial, data in coordinator.data.items()
    }
    return {
        "entry": _redact(dict(entry.data)),
        "mqtt_connected": coordinator.mqtt_connected,
        "last_mqtt_event": (
            coordinator.last_mqtt_event.isoformat()
            if coordinator.last_mqtt_event
            else None
        ),
        "last_update_success": coordinator.last_update_success,
        "poll_interval_seconds": (
            coordinator.update_interval.total_seconds()
            if coordinator.update_interval
            else None
        ),
        "vacuums": vacuums,
    }
