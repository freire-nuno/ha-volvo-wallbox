"""Common fixtures for Volvo Wallbox tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime
import time
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.volvo_wallbox.api import ChargingSession
from custom_components.volvo_wallbox.const import CONF_WALLBOX_ID, DOMAIN

from homeassistant.const import CONF_API_KEY, CONF_TOKEN
from homeassistant.core import HomeAssistant

WALLBOX_ID = "WB123"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading custom integrations in all tests."""


@pytest.fixture
def mock_config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Return a mocked config entry, added to hass."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=f"Volvo Wallbox {WALLBOX_ID}",
        unique_id=WALLBOX_ID,
        data={
            "auth_implementation": DOMAIN,
            CONF_TOKEN: {
                "access_token": "mock-access-token",
                "refresh_token": "mock-refresh-token",
                "expires_at": time.time() + 3600,
            },
            CONF_API_KEY: "vcc-key",
            CONF_WALLBOX_ID: WALLBOX_ID,
        },
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def mock_api() -> Generator[AsyncMock]:
    """Mock the EnergyDeviceApi used by the integration."""
    sessions = [
        ChargingSession(
            wallbox_id=WALLBOX_ID,
            transaction_id="tx-1",
            id_token="rfid-1",
            start=datetime(2026, 7, 1, 8, 0, tzinfo=UTC),
            end=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
            charged_energy=10.0,
            connector_id=1,
        ),
        ChargingSession(
            wallbox_id=WALLBOX_ID,
            transaction_id="tx-2",
            id_token="rfid-1",
            start=datetime(2026, 7, 12, 6, 0, tzinfo=UTC),
            end=datetime(2026, 7, 12, 7, 0, tzinfo=UTC),
            charged_energy=5.5,
            connector_id=1,
        ),
        ChargingSession(
            wallbox_id=WALLBOX_ID,
            transaction_id="tx-3",
            id_token="rfid-1",
            start=datetime(2026, 7, 12, 9, 0, tzinfo=UTC),
            end=None,
            charged_energy=2.5,
            connector_id=1,
        ),
    ]
    with (
        patch(
            "custom_components.volvo_wallbox.EnergyDeviceApi", autospec=True
        ) as mock_class,
        patch(
            "custom_components.volvo_wallbox.VolvoWallboxAuth", autospec=True
        ),
        patch(
            "custom_components.volvo_wallbox.async_get_config_entry_implementation",
            return_value=AsyncMock(),
        ),
    ):
        api = mock_class.return_value
        api.async_get_wallbox_state.return_value = "CHARGING"
        api.async_get_charging_sessions.return_value = sessions
        yield api


@pytest.fixture
async def setup_integration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AsyncMock,
) -> AsyncGenerator[None]:
    """Set the integration up."""
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    yield
