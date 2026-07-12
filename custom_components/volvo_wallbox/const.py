"""Constants for the Volvo Wallbox integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "volvo_wallbox"
PLATFORMS = [Platform.BUTTON, Platform.NUMBER, Platform.SENSOR]

API_BASE_URL = "https://api.volvocars.com/energy-device/v1"
AUTHORIZE_URL = "https://volvoid.eu.volvocars.com/as/authorization.oauth2"
TOKEN_URL = "https://volvoid.eu.volvocars.com/as/token.oauth2"

# Copy the exact scope list from
# https://developer.volvocars.com/apis/energy-device-api/v1/overview/
SCOPES = ["openid"]

CONF_WALLBOX_ID = "wallbox_id"
DEFAULT_SCAN_INTERVAL = 60

MANUFACTURER = "Volvo"
