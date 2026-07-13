"""Constants for the Volvo Wallbox integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "volvo_wallbox"
PLATFORMS = [Platform.BUTTON, Platform.NUMBER, Platform.SENSOR]

API_BASE_URL = "https://api.volvocars.com/energy-device/v1"
AUTHORIZE_URL = "https://volvoid.eu.volvocars.com/as/authorization.oauth2"
TOKEN_URL = "https://volvoid.eu.volvocars.com/as/token.oauth2"

# Energy Device API scopes; the API application on
# https://developer.volvocars.com/ must have these granted.
SCOPES = [
    "openid",
    "energy_device:user_id_token:readwrite",
    "energy_device:wallbox:read",
    "energy_device:wallbox:write",
    "energy_device:wallbox:control",
]

CONF_WALLBOX_ID = "wallbox_id"
DEFAULT_SCAN_INTERVAL = 60

MANUFACTURER = "Volvo"
