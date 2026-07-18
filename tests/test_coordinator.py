"""Tests for the Volvo Wallbox coordinator and derivation logic."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.volvo_wallbox.api import (
    ChargingSession,
    EnergyDeviceApiError,
    EnergyDeviceAuthError,
)
from custom_components.volvo_wallbox.coordinator import (
    energy_since,
    find_current_session,
    find_last_completed_session,
)

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant


def _session(
    start: datetime, end: datetime | None, energy: float
) -> ChargingSession:
    return ChargingSession(
        wallbox_id="WB123",
        transaction_id=f"tx-{start.isoformat()}",
        id_token="rfid-1",
        start=start,
        end=end,
        charged_energy=energy,
        connector_id=1,
    )


SESSIONS = [
    _session(
        datetime(2026, 7, 1, 8, 0, tzinfo=UTC),
        datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        10.0,
    ),
    _session(
        datetime(2026, 7, 12, 6, 0, tzinfo=UTC),
        datetime(2026, 7, 12, 7, 0, tzinfo=UTC),
        5.5,
    ),
    _session(datetime(2026, 7, 12, 9, 0, tzinfo=UTC), None, 2.5),
]


def test_find_current_session() -> None:
    """The open session (no end) is the current one."""
    assert find_current_session(SESSIONS) is SESSIONS[2]
    assert find_current_session(SESSIONS[:2]) is None


def test_find_last_completed_session() -> None:
    """The completed session with the latest end wins."""
    assert find_last_completed_session(SESSIONS) is SESSIONS[1]
    assert find_last_completed_session([SESSIONS[2]]) is None


def test_energy_since() -> None:
    """Only sessions starting at/after the cutoff are summed."""
    cutoff = datetime(2026, 7, 12, 0, 0, tzinfo=UTC)
    assert energy_since(SESSIONS, cutoff) == 8.0
    month_start = datetime(2026, 7, 1, 0, 0, tzinfo=UTC)
    assert energy_since(SESSIONS, month_start) == 18.0


@pytest.fixture
async def setup_integration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AsyncMock,
) -> AsyncGenerator[None]:
    """Set the integration up.

    Overrides the shared conftest fixture for this module only: platform
    files (sensor/button/number) don't exist yet at Task 4, so forwarding
    entry setup to them is stubbed out here. Tasks 5-8 add those platforms
    and rely on the unmodified conftest fixture doing the real forwarding.
    """
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
        return_value=None,
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
    yield


@pytest.mark.freeze_time("2026-07-12 12:00:00+00:00")
async def test_setup_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    setup_integration: None,
) -> None:
    """The entry sets up and exposes coordinator data."""
    assert mock_config_entry.state is ConfigEntryState.LOADED
    coordinator = mock_config_entry.runtime_data
    assert coordinator.data.state == "charging"
    assert coordinator.data.energy_this_month == 18.0
    assert coordinator.data.energy_this_year == 18.0


async def test_setup_entry_auth_error_starts_reauth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AsyncMock,
) -> None:
    """An auth error during setup puts the entry in reauth."""
    mock_api.async_get_charging_sessions.side_effect = EnergyDeviceAuthError("expired")

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(
        mock_config_entry.domain
    )
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == "reauth"


async def test_setup_entry_api_error_retries(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AsyncMock,
) -> None:
    """A generic API error during setup leads to setup retry."""
    mock_api.async_get_charging_sessions.side_effect = EnergyDeviceApiError("boom")

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
