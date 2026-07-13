"""Diagnostics for the Volvo Wallbox integration."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_ACCESS_TOKEN, CONF_API_KEY
from homeassistant.core import HomeAssistant

from .coordinator import VolvoWallboxConfigEntry

TO_REDACT = [CONF_ACCESS_TOKEN, CONF_API_KEY, "refresh_token", "id_token"]


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: VolvoWallboxConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "data": async_redact_data(asdict(coordinator.data), TO_REDACT),
    }
