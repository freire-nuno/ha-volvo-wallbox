"""Tests for the Volvo Wallbox sensors."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.volvo_wallbox.coordinator import WallboxData

from homeassistant.const import STATE_UNKNOWN, Platform
from homeassistant.core import HomeAssistant


@pytest.fixture(autouse=True)
def _sensor_only_platform() -> Generator[None]:
    """Load only the sensor platform; other platforms land in parallel tasks."""
    with patch("custom_components.volvo_wallbox.PLATFORMS", [Platform.SENSOR]):
        yield


@pytest.mark.freeze_time("2026-07-12 12:00:00+00:00")
@pytest.mark.usefixtures("setup_integration")
@pytest.mark.parametrize(
    ("entity_id", "expected_state"),
    [
        pytest.param("sensor.volvo_wallbox_charging_state", "CHARGING", id="state"),
        pytest.param(
            "sensor.volvo_wallbox_current_session_energy", "2.5", id="current"
        ),
        # "today" starts at local midnight; the test hass defaults to
        # US/Pacific, so the 06:00 UTC session falls on the Pacific-local
        # previous day and only the 09:00 UTC session (2.5 kWh) counts.
        pytest.param("sensor.volvo_wallbox_energy_today", "2.5", id="today"),
        pytest.param("sensor.volvo_wallbox_energy_this_month", "18.0", id="month"),
        pytest.param(
            "sensor.volvo_wallbox_last_session_energy", "5.5", id="last_energy"
        ),
        pytest.param(
            "sensor.volvo_wallbox_last_session_start",
            "2026-07-12T06:00:00+00:00",
            id="last_start",
        ),
        pytest.param(
            "sensor.volvo_wallbox_last_session_end",
            "2026-07-12T07:00:00+00:00",
            id="last_end",
        ),
    ],
)
async def test_sensor_states(
    hass: HomeAssistant, entity_id: str, expected_state: str
) -> None:
    """Sensors expose the coordinator-derived values."""
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == expected_state


@pytest.mark.freeze_time("2026-07-12 12:00:00+00:00")
@pytest.mark.usefixtures("setup_integration")
@pytest.mark.parametrize(
    ("entity_id", "expected_state"),
    [
        pytest.param(
            "sensor.volvo_wallbox_current_session_energy", "0.0", id="idle"
        ),
        pytest.param(
            "sensor.volvo_wallbox_last_session_energy",
            STATE_UNKNOWN,
            id="no_last_energy",
        ),
        pytest.param(
            "sensor.volvo_wallbox_last_session_start",
            STATE_UNKNOWN,
            id="no_last_start",
        ),
        pytest.param(
            "sensor.volvo_wallbox_last_session_end",
            STATE_UNKNOWN,
            id="no_last_end",
        ),
    ],
)
async def test_sensor_states_no_sessions(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    entity_id: str,
    expected_state: str,
) -> None:
    """Sensors fall back correctly when there are no sessions."""
    coordinator = mock_config_entry.runtime_data
    coordinator.async_set_updated_data(
        WallboxData(
            state="AVAILABLE",
            sessions=[],
            current_session=None,
            last_session=None,
            energy_today=0.0,
            energy_this_month=0.0,
        )
    )
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == expected_state
