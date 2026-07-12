"""Tests for the Energy Device API client."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.volvo_wallbox.api import (
    ChargingSession,
    ConfigFlowAuth,
    EnergyDeviceApi,
    EnergyDeviceApiError,
    EnergyDeviceAuthError,
    IdToken,
    WallboxOperationError,
)
from custom_components.volvo_wallbox.const import API_BASE_URL

from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client

WALLBOX_ID = "WB123"


def _api(hass: HomeAssistant) -> EnergyDeviceApi:
    session = aiohttp_client.async_get_clientsession(hass)
    return EnergyDeviceApi(session, ConfigFlowAuth("test-token"), "test-api-key")


async def test_get_wallbox_state(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """State endpoint returns the value and sends auth headers."""
    aioclient_mock.get(
        f"{API_BASE_URL}/wallbox/{WALLBOX_ID}", json={"value": "AVAILABLE"}
    )

    state = await _api(hass).async_get_wallbox_state(WALLBOX_ID)

    assert state == "AVAILABLE"
    headers = aioclient_mock.mock_calls[0][3]
    assert headers["authorization"] == "Bearer test-token"
    assert headers["vcc-api-key"] == "test-api-key"


async def test_get_charging_sessions(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Sessions are parsed into ChargingSession models."""
    aioclient_mock.get(
        f"{API_BASE_URL}/wallbox/{WALLBOX_ID}/chargingsessions",
        json=[
            {
                "wallboxId": WALLBOX_ID,
                "transactionId": "tx-1",
                "idToken": "rfid-1",
                "start": "2026-07-12T08:00:00Z",
                "end": "2026-07-12T09:30:00Z",
                "chargedEnergy": 7.5,
                "connectorId": 1,
            },
            {
                "wallboxId": WALLBOX_ID,
                "transactionId": "tx-2",
                "idToken": "rfid-1",
                "start": "2026-07-12T10:00:00Z",
                "end": None,
                "chargedEnergy": 1.2,
                "connectorId": None,
            },
        ],
    )

    sessions = await _api(hass).async_get_charging_sessions(
        WALLBOX_ID,
        datetime(2026, 7, 1, tzinfo=UTC),
        datetime(2026, 7, 12, 12, tzinfo=UTC),
    )

    assert sessions == [
        ChargingSession(
            wallbox_id=WALLBOX_ID,
            transaction_id="tx-1",
            id_token="rfid-1",
            start=datetime(2026, 7, 12, 8, 0, tzinfo=UTC),
            end=datetime(2026, 7, 12, 9, 30, tzinfo=UTC),
            charged_energy=7.5,
            connector_id=1,
        ),
        ChargingSession(
            wallbox_id=WALLBOX_ID,
            transaction_id="tx-2",
            id_token="rfid-1",
            start=datetime(2026, 7, 12, 10, 0, tzinfo=UTC),
            end=None,
            charged_energy=1.2,
            connector_id=None,
        ),
    ]


async def test_unauthorized_raises_auth_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A 401 raises EnergyDeviceAuthError."""
    aioclient_mock.get(f"{API_BASE_URL}/wallbox/{WALLBOX_ID}", status=401)

    with pytest.raises(EnergyDeviceAuthError):
        await _api(hass).async_get_wallbox_state(WALLBOX_ID)


async def test_operation_error_carries_code(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A 409 with a WallboxOperationError body raises with its code."""
    aioclient_mock.post(
        f"{API_BASE_URL}/wallbox/{WALLBOX_ID}/start",
        status=409,
        json={"message": "offline", "code": "WALLBOX_OFFLINE"},
    )

    with pytest.raises(WallboxOperationError) as err:
        await _api(hass).async_start_charging(WALLBOX_ID)

    assert err.value.code == "WALLBOX_OFFLINE"


async def test_generic_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A 500 raises EnergyDeviceApiError."""
    aioclient_mock.get(f"{API_BASE_URL}/wallbox/{WALLBOX_ID}", status=500)

    with pytest.raises(EnergyDeviceApiError):
        await _api(hass).async_get_wallbox_state(WALLBOX_ID)


async def test_set_charging_amp_limit(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Amp limit is sent as a query parameter."""
    aioclient_mock.post(
        f"{API_BASE_URL}/wallbox/{WALLBOX_ID}/setChargingAmpLimit", status=202
    )

    await _api(hass).async_set_charging_amp_limit(WALLBOX_ID, 16.0)

    assert aioclient_mock.mock_calls[0][1].query["limit"] == "16.0"


async def test_get_id_tokens(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """ID tokens endpoint returns IdToken models."""
    aioclient_mock.get(
        f"{API_BASE_URL}/user/idTokens",
        json=[{"name": "My card", "token": "rfid-1"}],
    )

    tokens = await _api(hass).async_get_id_tokens()

    assert tokens == [IdToken(name="My card", token="rfid-1")]


async def test_apply_charging_schedule_payload(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Schedule request body matches the API contract."""
    aioclient_mock.post(
        f"{API_BASE_URL}/wallbox/{WALLBOX_ID}/chargingSchedule", status=202
    )

    await _api(hass).async_apply_charging_schedule(
        WALLBOX_ID,
        datetime(2026, 7, 12, 22, 0, tzinfo=UTC),
        [{"$type": "WattPeriod", "watt": 7400.0, "duration": "02:00:00"}],
        schedule_id="night",
    )

    body = aioclient_mock.mock_calls[0][2]
    assert body == {
        "start": "2026-07-12T22:00:00+00:00",
        "periods": [{"$type": "WattPeriod", "watt": 7400.0, "duration": "02:00:00"}],
        "scheduleId": {"value": "night"},
    }
