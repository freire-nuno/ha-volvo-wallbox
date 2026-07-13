"""Tests for the Volvo Wallbox services."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.volvo_wallbox.const import DOMAIN

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr

WALLBOX_ID = "WB123"


@pytest.fixture(autouse=True)
def _no_platforms() -> Generator[None]:
    """No platform modules exist in this worktree; they land in parallel tasks."""
    with patch("custom_components.volvo_wallbox.PLATFORMS", []):
        yield


@pytest.fixture
def wallbox_device(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> dr.DeviceEntry:
    """Register the wallbox device, normally created by the entity platforms."""
    return dr.async_get(hass).async_get_or_create(
        config_entry_id=mock_config_entry.entry_id,
        identifiers={(DOMAIN, WALLBOX_ID)},
    )


@pytest.mark.usefixtures("setup_integration")
async def test_start_charging_with_token(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    wallbox_device: dr.DeviceEntry,
) -> None:
    """start_charging passes the RFID token."""
    await hass.services.async_call(
        DOMAIN,
        "start_charging",
        {
            "device_id": wallbox_device.id,
            "id_token": "rfid-1",
        },
        blocking=True,
    )

    mock_api.async_start_charging.assert_called_once_with(WALLBOX_ID, "rfid-1")


@pytest.mark.usefixtures("setup_integration")
async def test_get_charging_sessions_response(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    wallbox_device: dr.DeviceEntry,
) -> None:
    """get_charging_sessions returns serialized sessions."""
    # setup_integration triggers the coordinator's own first refresh, which
    # already calls async_get_charging_sessions once with real-clock args.
    mock_api.async_get_charging_sessions.reset_mock()
    response = await hass.services.async_call(
        DOMAIN,
        "get_charging_sessions",
        {
            "device_id": wallbox_device.id,
            "start": "2026-07-01T00:00:00+00:00",
            "end": "2026-07-12T12:00:00+00:00",
        },
        blocking=True,
        return_response=True,
    )

    sessions = response["sessions"]
    assert len(sessions) == 3
    assert sessions[0]["transaction_id"] == "tx-1"
    assert sessions[0]["charged_energy"] == 10.0
    assert sessions[0]["start"] == "2026-07-01T08:00:00+00:00"
    assert sessions[2]["end"] is None
    mock_api.async_get_charging_sessions.assert_called_once_with(
        WALLBOX_ID,
        datetime(2026, 7, 1, 0, 0, tzinfo=UTC),
        datetime(2026, 7, 12, 12, 0, tzinfo=UTC),
        None,
    )


@pytest.mark.usefixtures("setup_integration")
async def test_apply_charging_schedule(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    wallbox_device: dr.DeviceEntry,
) -> None:
    """apply_charging_schedule maps periods to the API contract."""
    await hass.services.async_call(
        DOMAIN,
        "apply_charging_schedule",
        {
            "device_id": wallbox_device.id,
            "start": "2026-07-12T22:00:00+00:00",
            "periods": [
                {"type": "watt", "value": 7400, "duration": "02:00:00"},
                {"type": "ampere", "value": 16, "duration": "01:30:00"},
            ],
            "schedule_id": "night",
        },
        blocking=True,
    )

    mock_api.async_apply_charging_schedule.assert_called_once_with(
        WALLBOX_ID,
        datetime(2026, 7, 12, 22, 0, tzinfo=UTC),
        [
            {"$type": "WattPeriod", "watt": 7400.0, "duration": "02:00:00"},
            {"$type": "AmperePeriod", "ampere": 16.0, "duration": "01:30:00"},
        ],
        "night",
    )


@pytest.mark.usefixtures("setup_integration")
async def test_add_id_token(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    wallbox_device: dr.DeviceEntry,
) -> None:
    """add_id_token registers the token."""
    await hass.services.async_call(
        DOMAIN,
        "add_id_token",
        {
            "device_id": wallbox_device.id,
            "name": "My card",
            "token": "rfid-9",
        },
        blocking=True,
    )

    mock_api.async_add_id_token.assert_called_once_with("My card", "rfid-9")


@pytest.mark.usefixtures("setup_integration")
async def test_unknown_device_raises(hass: HomeAssistant) -> None:
    """An unknown device id raises a validation error."""
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "read_id_token",
            {"device_id": "not-a-device"},
            blocking=True,
        )
