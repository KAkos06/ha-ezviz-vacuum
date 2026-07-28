"""UI configuration flow for EZVIZ Vacuum."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    EzvizVacuumApi,
    EzvizVacuumAuthError,
    EzvizVacuumConnectionError,
    EzvizVacuumError,
)
from .const import CONF_REGION, DEFAULT_REGION, DOMAIN

_LOGGER = logging.getLogger(__name__)


def _schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")
            ): cv.string,
            vol.Required(CONF_PASSWORD): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
            vol.Required(
                CONF_REGION, default=defaults.get(CONF_REGION, DEFAULT_REGION)
            ): cv.string,
        }
    )


async def _validate(hass: HomeAssistant, data: dict[str, Any]) -> None:
    api = EzvizVacuumApi(data[CONF_USERNAME], data[CONF_PASSWORD], data[CONF_REGION])
    try:
        await hass.async_add_executor_job(api.login)
        vacuums = await hass.async_add_executor_job(api.get_vacuums)
        if not vacuums:
            raise NoSupportedDevices
    finally:
        await hass.async_add_executor_job(api.close)


class NoSupportedDevices(EzvizVacuumError):
    """No SweepingRobot exists in this account."""


class EzvizVacuumConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle EZVIZ Vacuum setup and reauthentication."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_USERNAME] = user_input[CONF_USERNAME].strip().lower()
            user_input[CONF_REGION] = user_input[CONF_REGION].strip().lower()
            await self.async_set_unique_id(user_input[CONF_USERNAME])
            self._abort_if_unique_id_configured()
            try:
                await _validate(self.hass, user_input)
            except EzvizVacuumAuthError:
                errors["base"] = "invalid_auth"
            except EzvizVacuumConnectionError:
                errors["base"] = "cannot_connect"
            except NoSupportedDevices:
                errors["base"] = "no_supported_devices"
            except EzvizVacuumError as err:
                _LOGGER.debug(
                    "Unexpected EZVIZ API error during setup (%s)",
                    type(err).__name__,
                )
                errors["base"] = "unknown"
            except Exception as err:  # Defensive boundary for an undocumented API.
                _LOGGER.debug("Unexpected setup failure (%s)", type(err).__name__)
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=user_input[CONF_USERNAME], data=user_input
                )
        return self.async_show_form(
            step_id="user", data_schema=_schema(user_input), errors=errors
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._reauth_entry
        if entry is None:
            return self.async_abort(reason="reauth_failed")
        if user_input is not None:
            data = {
                **entry.data,
                CONF_PASSWORD: user_input[CONF_PASSWORD],
            }
            try:
                await _validate(self.hass, data)
            except EzvizVacuumAuthError:
                errors["base"] = "invalid_auth"
            except EzvizVacuumConnectionError:
                errors["base"] = "cannot_connect"
            except NoSupportedDevices:
                errors["base"] = "no_supported_devices"
            except EzvizVacuumError:
                errors["base"] = "unknown"
            except Exception as err:  # Defensive boundary for an undocumented API.
                _LOGGER.debug(
                    "Unexpected reauthentication failure (%s)",
                    type(err).__name__,
                )
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(entry, data_updates=data)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    )
                }
            ),
            errors=errors,
        )
