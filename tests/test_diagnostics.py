"""Tests for Volvo Wallbox diagnostics."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.volvo_wallbox.diagnostics import (
    async_get_config_entry_diagnostics,
)

from homeassistant.core import HomeAssistant


@pytest.mark.freeze_time("2026-07-12 12:00:00+00:00")
@pytest.mark.usefixtures("setup_integration")
async def test_diagnostics_redacts_secrets(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Tokens and API key are redacted."""
    diagnostics = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    assert diagnostics["entry_data"]["api_key"] == "**REDACTED**"
    assert diagnostics["entry_data"]["token"]["access_token"] == "**REDACTED**"
    assert diagnostics["entry_data"]["token"]["refresh_token"] == "**REDACTED**"
    assert diagnostics["data"]["state"] == "CHARGING"
    assert len(diagnostics["data"]["sessions"]) == 3
