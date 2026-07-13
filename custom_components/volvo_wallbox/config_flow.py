"""Config flow for the Volvo Wallbox integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    SOURCE_REAUTH,
    ConfigEntry,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import (
    CONF_ACCESS_TOKEN,
    CONF_API_KEY,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.config_entry_oauth2_flow import AbstractOAuth2FlowHandler
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import ConfigFlowAuth, EnergyDeviceApi, EnergyDeviceApiError
from .const import CONF_WALLBOX_ID, DEFAULT_SCAN_INTERVAL, DOMAIN, SCOPES

_LOGGER = logging.getLogger(__name__)


def _create_api(hass: HomeAssistant, access_token: str, api_key: str) -> EnergyDeviceApi:
    session = aiohttp_client.async_get_clientsession(hass)
    return EnergyDeviceApi(session, ConfigFlowAuth(access_token), api_key)


class VolvoWallboxFlowHandler(AbstractOAuth2FlowHandler, domain=DOMAIN):
    """Config flow handling Volvo ID OAuth2 authentication."""

    VERSION = 1
    DOMAIN = DOMAIN

    def __init__(self) -> None:
        """Initialize the flow."""
        super().__init__()
        self._config_data: dict[str, Any] = {}

    @property
    def extra_authorize_data(self) -> dict:
        """Extra data appended to the authorize url."""
        return super().extra_authorize_data | {"scope": " ".join(SCOPES)}

    @property
    def logger(self) -> logging.Logger:
        """Return logger."""
        return _LOGGER

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> VolvoWallboxOptionsFlow:
        """Return the options flow."""
        return VolvoWallboxOptionsFlow()

    async def async_oauth_create_entry(self, data: dict) -> ConfigFlowResult:
        """Continue the flow after OAuth."""
        self._config_data |= (self.init_data or {}) | data
        return await self.async_step_api_key()

    async def async_step_reauth(self, _: Mapping[str, Any]) -> ConfigFlowResult:
        """Perform reauth upon an API authentication error."""
        self._config_data = dict(self._get_reauth_entry().data)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm reauth dialog."""
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")
        return await self.async_step_user()

    async def async_step_api_key(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for and validate the VCC API key."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api = _create_api(
                self.hass,
                self._config_data[CONF_TOKEN][CONF_ACCESS_TOKEN],
                user_input[CONF_API_KEY],
            )
            try:
                await api.async_get_id_tokens()
            except EnergyDeviceApiError:
                _LOGGER.debug("API key validation failed", exc_info=True)
                errors["base"] = "invalid_api_key"
            else:
                self._config_data |= user_input
                return await self.async_step_wallbox_id()

        suggested = user_input or {CONF_API_KEY: self._config_data.get(CONF_API_KEY, "")}
        schema = self.add_suggested_values_to_schema(
            vol.Schema(
                {
                    vol.Required(CONF_API_KEY): TextSelector(
                        TextSelectorConfig(
                            type=TextSelectorType.PASSWORD, autocomplete="password"
                        )
                    )
                }
            ),
            suggested,
        )
        return self.async_show_form(
            step_id="api_key",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "volvo_dev_portal": "https://developer.volvocars.com/account/#your-api-applications"
            },
        )

    async def async_step_wallbox_id(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for and validate the wallbox ID."""
        errors: dict[str, str] = {}

        if self.source == SOURCE_REAUTH:
            # Keep the existing wallbox ID on reauth.
            return await self._async_create_or_update()

        if user_input is not None:
            api = _create_api(
                self.hass,
                self._config_data[CONF_TOKEN][CONF_ACCESS_TOKEN],
                self._config_data[CONF_API_KEY],
            )
            try:
                await api.async_get_wallbox_state(user_input[CONF_WALLBOX_ID])
            except EnergyDeviceApiError:
                _LOGGER.debug("Wallbox ID validation failed", exc_info=True)
                errors["base"] = "invalid_wallbox_id"
            else:
                self._config_data |= user_input
                return await self._async_create_or_update()

        schema = vol.Schema({vol.Required(CONF_WALLBOX_ID): str})
        return self.async_show_form(
            step_id="wallbox_id", data_schema=schema, errors=errors
        )

    async def _async_create_or_update(self) -> ConfigFlowResult:
        wallbox_id = self._config_data[CONF_WALLBOX_ID]
        await self.async_set_unique_id(wallbox_id)

        if self.source == SOURCE_REAUTH:
            self._abort_if_unique_id_mismatch()
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(), data_updates=self._config_data
            )

        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=f"Volvo Wallbox {wallbox_id}", data=self._config_data
        )


class VolvoWallboxOptionsFlow(OptionsFlowWithReload):
    """Options flow for the polling interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        schema = self.add_suggested_values_to_schema(
            vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL): NumberSelector(
                        NumberSelectorConfig(
                            min=30, max=600, step=10, mode=NumberSelectorMode.BOX
                        )
                    )
                }
            ),
            {
                CONF_SCAN_INTERVAL: self.config_entry.options.get(
                    CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                )
            },
        )
        return self.async_show_form(step_id="init", data_schema=schema)
