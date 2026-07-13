"""Tests for the Volvo Wallbox config flow."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.volvo_wallbox.const import (
    API_BASE_URL,
    AUTHORIZE_URL,
    CONF_WALLBOX_ID,
    DOMAIN,
    TOKEN_URL,
)

from homeassistant.components.application_credentials import (
    ClientCredential,
    async_import_client_credential,
)
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_API_KEY, CONF_SCAN_INTERVAL, CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.setup import async_setup_component

CLIENT_ID = "client-id"
CLIENT_SECRET = "client-secret"
REDIRECT_URI = "https://example.com/auth/external/callback"
WALLBOX_ID = "WB123"


@pytest.fixture(autouse=True)
async def setup_credentials(hass: HomeAssistant) -> None:
    """Set up application credentials."""
    assert await async_setup_component(hass, "application_credentials", {})
    await async_import_client_credential(
        hass, DOMAIN, ClientCredential(CLIENT_ID, CLIENT_SECRET)
    )


async def _do_oauth(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    aioclient_mock: AiohttpClientMocker,
) -> str:
    """Start the flow and complete the OAuth dance, return flow_id."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    state = config_entry_oauth2_flow._encode_jwt(
        hass,
        {"flow_id": result["flow_id"], "redirect_uri": REDIRECT_URI},
    )
    assert result["url"].startswith(AUTHORIZE_URL)

    client = await hass_client_no_auth()
    resp = await client.get(f"/auth/external/callback?code=abcd&state={state}")
    assert resp.status == 200

    aioclient_mock.post(
        TOKEN_URL,
        json={
            "refresh_token": "mock-refresh-token",
            "access_token": "mock-access-token",
            "type": "Bearer",
            "expires_in": 3600,
        },
    )
    return result["flow_id"]


@pytest.mark.usefixtures("current_request_with_host")
async def test_full_flow(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Full happy path: OAuth -> api key -> wallbox id -> entry created."""
    flow_id = await _do_oauth(hass, hass_client_no_auth, aioclient_mock)

    result = await hass.config_entries.flow.async_configure(flow_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "api_key"

    aioclient_mock.get(f"{API_BASE_URL}/user/idTokens", json=[])
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_API_KEY: "vcc-key"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "wallbox_id"

    aioclient_mock.get(
        f"{API_BASE_URL}/wallbox/{WALLBOX_ID}", json={"value": "AVAILABLE"}
    )
    with patch(
        "custom_components.volvo_wallbox.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_configure(
            flow_id, {CONF_WALLBOX_ID: WALLBOX_ID}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"Volvo Wallbox {WALLBOX_ID}"
    assert result["data"][CONF_API_KEY] == "vcc-key"
    assert result["data"][CONF_WALLBOX_ID] == WALLBOX_ID
    assert result["result"].unique_id == WALLBOX_ID


@pytest.mark.usefixtures("current_request_with_host")
async def test_invalid_api_key(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """An invalid API key shows an error on the api_key step."""
    flow_id = await _do_oauth(hass, hass_client_no_auth, aioclient_mock)
    await hass.config_entries.flow.async_configure(flow_id)

    aioclient_mock.get(f"{API_BASE_URL}/user/idTokens", status=403)
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_API_KEY: "bad-key"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "api_key"
    assert result["errors"] == {"base": "invalid_api_key"}


@pytest.mark.usefixtures("current_request_with_host")
async def test_invalid_wallbox_id(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """An unknown wallbox id shows an error on the wallbox_id step."""
    flow_id = await _do_oauth(hass, hass_client_no_auth, aioclient_mock)
    await hass.config_entries.flow.async_configure(flow_id)

    aioclient_mock.get(f"{API_BASE_URL}/user/idTokens", json=[])
    await hass.config_entries.flow.async_configure(flow_id, {CONF_API_KEY: "vcc-key"})

    aioclient_mock.get(f"{API_BASE_URL}/wallbox/BAD", status=404)
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_WALLBOX_ID: "BAD"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "wallbox_id"
    assert result["errors"] == {"base": "invalid_wallbox_id"}


@pytest.mark.usefixtures("current_request_with_host")
async def test_duplicate_wallbox_aborts(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Configuring an already-configured wallbox aborts."""
    MockConfigEntry(domain=DOMAIN, unique_id=WALLBOX_ID).add_to_hass(hass)

    flow_id = await _do_oauth(hass, hass_client_no_auth, aioclient_mock)
    await hass.config_entries.flow.async_configure(flow_id)

    aioclient_mock.get(f"{API_BASE_URL}/user/idTokens", json=[])
    await hass.config_entries.flow.async_configure(flow_id, {CONF_API_KEY: "vcc-key"})

    aioclient_mock.get(
        f"{API_BASE_URL}/wallbox/{WALLBOX_ID}", json={"value": "AVAILABLE"}
    )
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_WALLBOX_ID: WALLBOX_ID}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.usefixtures("current_request_with_host")
async def test_reauth_flow(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Reauth refreshes the token without asking for the wallbox ID."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=WALLBOX_ID,
        data={
            "auth_implementation": DOMAIN,
            CONF_TOKEN: {
                "access_token": "old-access-token",
                "refresh_token": "old-refresh-token",
                "expires_in": 3600,
            },
            CONF_API_KEY: "vcc-key",
            CONF_WALLBOX_ID: WALLBOX_ID,
        },
    )
    entry.add_to_hass(hass)

    entry.async_start_reauth(hass)
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress()
    assert len(flows) == 1
    flow_id = flows[0]["flow_id"]
    assert flows[0]["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(flow_id, {})
    assert result["type"] is FlowResultType.EXTERNAL_STEP
    assert result["url"].startswith(AUTHORIZE_URL)

    state = config_entry_oauth2_flow._encode_jwt(
        hass,
        {"flow_id": flow_id, "redirect_uri": REDIRECT_URI},
    )
    client = await hass_client_no_auth()
    resp = await client.get(f"/auth/external/callback?code=abcd&state={state}")
    assert resp.status == 200

    aioclient_mock.post(
        TOKEN_URL,
        json={
            "refresh_token": "new-refresh-token",
            "access_token": "new-access-token",
            "type": "Bearer",
            "expires_in": 3600,
        },
    )

    result = await hass.config_entries.flow.async_configure(flow_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "api_key"

    aioclient_mock.get(f"{API_BASE_URL}/user/idTokens", json=[])
    with patch(
        "custom_components.volvo_wallbox.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_configure(
            flow_id, {CONF_API_KEY: "vcc-key"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_TOKEN]["access_token"] == "new-access-token"
    assert entry.data[CONF_WALLBOX_ID] == WALLBOX_ID


async def test_options_flow(hass: HomeAssistant) -> None:
    """The options flow stores the polling interval."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=WALLBOX_ID)
    entry.add_to_hass(hass)

    with patch(
        "custom_components.volvo_wallbox.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "init"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_SCAN_INTERVAL: 120}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_SCAN_INTERVAL] == 120
