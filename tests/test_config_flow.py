"""Config flow tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResultType

from custom_components.ezviz_vacuum.api import (
    EzvizVacuumAuthError,
    EzvizVacuumConnectionError,
    EzvizVacuumError,
)
from custom_components.ezviz_vacuum.config_flow import NoSupportedDevices
from custom_components.ezviz_vacuum.const import CONF_REGION, DOMAIN

INPUT = {
    CONF_USERNAME: " USER@Example.com ",
    CONF_PASSWORD: "secret",
    CONF_REGION: "EU",
}


async def test_successful_flow(hass) -> None:
    with patch(
        "custom_components.ezviz_vacuum.config_flow._validate",
        new=AsyncMock(),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data=dict(INPUT),
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_USERNAME] == "user@example.com"
    assert result["data"][CONF_REGION] == "eu"


@pytest.mark.parametrize(
    ("exception", "error"),
    [
        (EzvizVacuumAuthError("bad login"), "invalid_auth"),
        (EzvizVacuumConnectionError("offline"), "cannot_connect"),
        (NoSupportedDevices(), "no_supported_devices"),
        (EzvizVacuumError("unexpected"), "unknown"),
    ],
)
async def test_flow_errors(hass, exception: Exception, error: str) -> None:
    with patch(
        "custom_components.ezviz_vacuum.config_flow._validate",
        new=AsyncMock(side_effect=exception),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data=dict(INPUT),
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}


async def test_duplicate_account(hass) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="user@example.com",
        data={**INPUT, CONF_USERNAME: "user@example.com"},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data=dict(INPUT),
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauthentication(hass) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="user@example.com",
        data={**INPUT, CONF_USERNAME: "user@example.com"},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
        },
        data=dict(entry.data),
    )
    assert result["type"] is FlowResultType.FORM
    with patch(
        "custom_components.ezviz_vacuum.config_flow._validate",
        new=AsyncMock(),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "new-secret"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "new-secret"
