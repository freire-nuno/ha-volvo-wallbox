"""The Volvo Wallbox integration."""

from __future__ import annotations

from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.config_entry_oauth2_flow import (
    OAuth2Session,
    async_get_config_entry_implementation,
)

from .api import EnergyDeviceApi, VolvoWallboxAuth
from .const import PLATFORMS
from .coordinator import VolvoWallboxConfigEntry, WallboxCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: VolvoWallboxConfigEntry
) -> bool:
    """Set up Volvo Wallbox from a config entry."""
    implementation = await async_get_config_entry_implementation(hass, entry)
    oauth_session = OAuth2Session(hass, entry, implementation)
    web_session = aiohttp_client.async_get_clientsession(hass)

    api = EnergyDeviceApi(
        web_session, VolvoWallboxAuth(oauth_session), entry.data[CONF_API_KEY]
    )
    coordinator = WallboxCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: VolvoWallboxConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
