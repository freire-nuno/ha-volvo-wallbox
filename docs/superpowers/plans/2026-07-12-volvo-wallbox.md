# Volvo Wallbox Custom Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `volvo_wallbox` Home Assistant custom integration that reads consumption data and controls a Volvo-branded wallbox via the official Volvo Energy Device API.

**Architecture:** Self-contained custom component mirroring the core `volvo` integration: HA `application_credentials` OAuth2 (PKCE) against Volvo ID, an inline aiohttp API client, one `DataUpdateCoordinator` polling wallbox state + current-month charging sessions, and sensor/button/number platforms plus services derived from that data.

**Tech Stack:** Python 3.13+, Home Assistant ≥ 2025.8, aiohttp, pytest with `pytest-homeassistant-custom-component`.

## Global Constraints

- Repo root: `/Users/nfreire/projects/ha-volvo-wallbox` (git repo already initialized; spec at `docs/superpowers/specs/2026-07-12-volvo-wallbox-design.md`, OpenAPI spec at `docs/energy-device-api-specification.json`).
- Integration domain: `volvo_wallbox`. All integration code under `custom_components/volvo_wallbox/`.
- API base URL: `https://api.volvocars.com/energy-device/v1`. OAuth URLs: `https://volvoid.eu.volvocars.com/as/authorization.oauth2` and `https://volvoid.eu.volvocars.com/as/token.oauth2`.
- Every request carries `authorization: Bearer <token>` and `vcc-api-key: <key>` headers.
- `chargedEnergy` from the API is treated as kWh.
- OAuth scopes: `SCOPES` constant in `const.py` starts as `["openid"]`; the user supplies the real Energy Device API scopes from the developer portal (single-line change, flagged in README).
- All test functions have typed parameters. No conditionals in tests. Use `from __future__ import annotations` in all modules.
- Test commands run from the repo root using the venv created in Task 1: `.venv/bin/python -m pytest tests -v`.
- Commit after every green test cycle. Never amend pushed commits.

## Parallel Execution Waves

- **Wave 1:** Task 1 (scaffolding)
- **Wave 2:** Task 2 (API client)
- **Wave 3:** Task 3 (config flow + all translations) ∥ Task 4 (coordinator + init + entity base)
- **Wave 4:** Task 5 (sensors) ∥ Task 6 (buttons + numbers) ∥ Task 7 (services)
- **Wave 5:** Task 8 (diagnostics, README, final check)

Tasks within a wave touch disjoint files (all user-facing strings land in Task 3 so Tasks 5–7 don't edit translation files; Task 7 owns the only post-Wave-3 edit to `__init__.py`).

---

### Task 1: Repo scaffolding and test harness

**Files:**
- Create: `custom_components/volvo_wallbox/__init__.py` (stub)
- Create: `custom_components/volvo_wallbox/const.py`
- Create: `custom_components/volvo_wallbox/manifest.json`
- Create: `hacs.json`
- Create: `requirements_test.txt`
- Create: `tests/__init__.py`, `tests/conftest.py`
- Create: `.gitignore`

**Interfaces:**
- Consumes: nothing.
- Produces: `const.py` constants used by every later task: `DOMAIN`, `PLATFORMS`, `API_BASE_URL`, `AUTHORIZE_URL`, `TOKEN_URL`, `SCOPES`, `CONF_WALLBOX_ID`, `DEFAULT_SCAN_INTERVAL`, `MANUFACTURER`. Test venv + `auto_enable_custom_integrations` fixture.

- [ ] **Step 1: Create package files**

`custom_components/volvo_wallbox/const.py`:

```python
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
```

`custom_components/volvo_wallbox/__init__.py` (stub, replaced in Task 4):

```python
"""The Volvo Wallbox integration."""
```

`custom_components/volvo_wallbox/manifest.json`:

```json
{
  "domain": "volvo_wallbox",
  "name": "Volvo Wallbox",
  "codeowners": [],
  "config_flow": true,
  "dependencies": ["application_credentials"],
  "documentation": "https://github.com/nfreire/ha-volvo-wallbox",
  "integration_type": "device",
  "iot_class": "cloud_polling",
  "issue_tracker": "https://github.com/nfreire/ha-volvo-wallbox/issues",
  "requirements": [],
  "version": "0.1.0"
}
```

`hacs.json`:

```json
{
  "name": "Volvo Wallbox",
  "homeassistant": "2025.8.0"
}
```

`requirements_test.txt`:

```
pytest-homeassistant-custom-component
```

`.gitignore`:

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
.coverage
```

`tests/__init__.py`:

```python
"""Tests for the Volvo Wallbox integration."""
```

`tests/conftest.py`:

```python
"""Common fixtures for Volvo Wallbox tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading custom integrations in all tests."""
```

- [ ] **Step 2: Create venv and install test dependencies**

Run:
```bash
cd /Users/nfreire/projects/ha-volvo-wallbox
python3 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
```
Expected: install succeeds (pulls homeassistant + pytest).

- [ ] **Step 3: Sanity-check the harness**

Run: `.venv/bin/python -m pytest tests -v`
Expected: `no tests ran` (collects 0 tests, exit without import errors).

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "feat: scaffold volvo_wallbox custom component and test harness"
```

---

### Task 2: API client (`api.py`)

**Files:**
- Create: `custom_components/volvo_wallbox/api.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `const.API_BASE_URL`.
- Produces (used by Tasks 3–8):
  - Exceptions: `EnergyDeviceApiError(Exception)`, `EnergyDeviceAuthError(EnergyDeviceApiError)`, `WallboxOperationError(EnergyDeviceApiError)` with attribute `code: str`.
  - `@dataclass(frozen=True) ChargingSession(wallbox_id: str, transaction_id: str, id_token: str, start: datetime, end: datetime | None, charged_energy: float, connector_id: int | None)` with `ChargingSession.from_json(data: dict) -> ChargingSession`.
  - `@dataclass(frozen=True) IdToken(name: str, token: str)`.
  - `class VolvoWallboxAuth(oauth_session: OAuth2Session)` and `class ConfigFlowAuth(token: str)`, both with `async_get_access_token() -> str`.
  - `class EnergyDeviceApi(session: ClientSession, auth, api_key: str)` with methods:
    - `async_get_wallbox_state(wallbox_id: str) -> str`
    - `async_get_charging_sessions(wallbox_id: str, start: datetime, end: datetime, id_token: str | None = None) -> list[ChargingSession]`
    - `async_start_charging(wallbox_id: str, id_token: str | None = None) -> None`
    - `async_pause_charging(wallbox_id: str) -> None`
    - `async_set_charging_amp_limit(wallbox_id: str, limit: float) -> None`
    - `async_set_discharging_amp_limit(wallbox_id: str, limit: float) -> None`
    - `async_apply_charging_schedule(wallbox_id: str, start: datetime, periods: list[dict], schedule_id: str | None = None) -> None`
    - `async_read_id_token(wallbox_id: str) -> None`
    - `async_get_id_tokens() -> list[IdToken]`
    - `async_add_id_token(name: str, token: str) -> None`
    - `async_update_id_token(name: str, token: str) -> None`
    - `async_delete_id_token(token: str) -> None`

- [ ] **Step 1: Write failing tests**

`tests/test_api.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'custom_components.volvo_wallbox.api'`

- [ ] **Step 3: Implement `api.py`**

`custom_components/volvo_wallbox/api.py`:

```python
"""API client for the Volvo Energy Device API, bound to Home Assistant OAuth."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Any, cast

from aiohttp import ClientError, ClientSession

from homeassistant.helpers.config_entry_oauth2_flow import OAuth2Session
from homeassistant.util import dt as dt_util

from .const import API_BASE_URL

_LOGGER = logging.getLogger(__name__)


class EnergyDeviceApiError(Exception):
    """Raised when the Energy Device API returns an error."""


class EnergyDeviceAuthError(EnergyDeviceApiError):
    """Raised when authentication with the Energy Device API fails."""


class WallboxOperationError(EnergyDeviceApiError):
    """Raised when a wallbox operation fails (HTTP 409/422)."""

    def __init__(self, message: str, code: str) -> None:
        """Initialize the error."""
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ChargingSession:
    """A wallbox charging session."""

    wallbox_id: str
    transaction_id: str
    id_token: str
    start: datetime
    end: datetime | None
    charged_energy: float
    connector_id: int | None

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ChargingSession:
        """Create a session from an API response item."""
        end_raw = data.get("end")
        return cls(
            wallbox_id=data["wallboxId"],
            transaction_id=data["transactionId"],
            id_token=data["idToken"],
            start=dt_util.parse_datetime(data["start"], raise_on_error=True),
            end=dt_util.parse_datetime(end_raw, raise_on_error=True)
            if end_raw
            else None,
            charged_energy=float(data["chargedEnergy"]),
            connector_id=data.get("connectorId"),
        )


@dataclass(frozen=True)
class IdToken:
    """An RFID ID token registered to the user."""

    name: str
    token: str


class VolvoWallboxAuth:
    """Provide access tokens from an OAuth2 based config entry."""

    def __init__(self, oauth_session: OAuth2Session) -> None:
        """Initialize the auth provider."""
        self._oauth_session = oauth_session

    async def async_get_access_token(self) -> str:
        """Return a valid access token."""
        await self._oauth_session.async_ensure_token_valid()
        return cast(str, self._oauth_session.token["access_token"])


class ConfigFlowAuth:
    """Provide a fixed access token before a config entry exists."""

    def __init__(self, token: str) -> None:
        """Initialize the auth provider."""
        self._token = token

    async def async_get_access_token(self) -> str:
        """Return the token."""
        return self._token


class EnergyDeviceApi:
    """Async client for the Volvo Energy Device API."""

    def __init__(
        self,
        session: ClientSession,
        auth: VolvoWallboxAuth | ConfigFlowAuth,
        api_key: str,
    ) -> None:
        """Initialize the client."""
        self._session = session
        self._auth = auth
        self._api_key = api_key

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        token = await self._auth.async_get_access_token()
        headers = {
            "authorization": f"Bearer {token}",
            "vcc-api-key": self._api_key,
        }
        try:
            response = await self._session.request(
                method,
                f"{API_BASE_URL}{path}",
                params=params,
                json=json,
                headers=headers,
            )
        except ClientError as err:
            raise EnergyDeviceApiError(f"Connection error: {err}") from err

        if response.status in (401, 403):
            raise EnergyDeviceAuthError(f"Authentication failed: {response.status}")
        if response.status in (409, 422):
            body = await response.json()
            raise WallboxOperationError(body["message"], body["code"])
        if response.status >= 400:
            raise EnergyDeviceApiError(f"API error: {response.status}")
        if response.content_type == "application/json":
            return await response.json()
        return None

    async def async_get_wallbox_state(self, wallbox_id: str) -> str:
        """Return the wallbox state."""
        data = await self._request("GET", f"/wallbox/{wallbox_id}")
        return cast(str, data["value"])

    async def async_get_charging_sessions(
        self,
        wallbox_id: str,
        start: datetime,
        end: datetime,
        id_token: str | None = None,
    ) -> list[ChargingSession]:
        """Return charging sessions in the given window."""
        params = {
            "start": dt_util.as_utc(start).isoformat(),
            "end": dt_util.as_utc(end).isoformat(),
        }
        if id_token:
            params["idToken"] = id_token
        data = await self._request(
            "GET", f"/wallbox/{wallbox_id}/chargingsessions", params=params
        )
        return [ChargingSession.from_json(item) for item in data]

    async def async_start_charging(
        self, wallbox_id: str, id_token: str | None = None
    ) -> None:
        """Start charging."""
        params = {"idToken": id_token} if id_token else None
        await self._request("POST", f"/wallbox/{wallbox_id}/start", params=params)

    async def async_pause_charging(self, wallbox_id: str) -> None:
        """Pause charging."""
        await self._request("POST", f"/wallbox/{wallbox_id}/pause")

    async def async_set_charging_amp_limit(
        self, wallbox_id: str, limit: float
    ) -> None:
        """Set the charging amp limit."""
        await self._request(
            "POST",
            f"/wallbox/{wallbox_id}/setChargingAmpLimit",
            params={"limit": str(limit)},
        )

    async def async_set_discharging_amp_limit(
        self, wallbox_id: str, limit: float
    ) -> None:
        """Set the discharging amp limit."""
        await self._request(
            "POST",
            f"/wallbox/{wallbox_id}/setDischargingAmpLimit",
            params={"limit": str(limit)},
        )

    async def async_apply_charging_schedule(
        self,
        wallbox_id: str,
        start: datetime,
        periods: list[dict[str, Any]],
        schedule_id: str | None = None,
    ) -> None:
        """Apply a transactional charging schedule."""
        await self._request(
            "POST",
            f"/wallbox/{wallbox_id}/chargingSchedule",
            json={
                "start": dt_util.as_utc(start).isoformat(),
                "periods": periods,
                "scheduleId": {"value": schedule_id},
            },
        )

    async def async_read_id_token(self, wallbox_id: str) -> None:
        """Put the wallbox in RFID read mode."""
        await self._request("POST", f"/wallbox/{wallbox_id}/readIdToken")

    async def async_get_id_tokens(self) -> list[IdToken]:
        """Return the user's ID tokens."""
        data = await self._request("GET", "/user/idTokens")
        return [IdToken(name=item["name"], token=item["token"]) for item in data]

    async def async_add_id_token(self, name: str, token: str) -> None:
        """Add an ID token."""
        await self._request(
            "POST", "/user/idTokens", json={"name": name, "token": token}
        )

    async def async_update_id_token(self, name: str, token: str) -> None:
        """Update an ID token's name."""
        await self._request(
            "PATCH", "/user/idTokens", json={"name": name, "token": token}
        )

    async def async_delete_id_token(self, token: str) -> None:
        """Delete an ID token."""
        await self._request("DELETE", f"/user/idTokens/{token}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_api.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/volvo_wallbox/api.py tests/test_api.py
git commit -m "feat: add Energy Device API client"
```

---

### Task 3: OAuth, config flow, and all translations

**Files:**
- Create: `custom_components/volvo_wallbox/application_credentials.py`
- Create: `custom_components/volvo_wallbox/config_flow.py`
- Create: `custom_components/volvo_wallbox/strings.json`
- Create: `custom_components/volvo_wallbox/translations/en.json`
- Test: `tests/test_config_flow.py`

**Interfaces:**
- Consumes: `EnergyDeviceApi`, `ConfigFlowAuth`, exceptions from Task 2; constants from Task 1.
- Produces: config entries with `data = {auth_implementation, token, api_key, wallbox_id}`, `unique_id = wallbox_id`, `options = {scan_interval}`. Translation keys for ALL tasks (entities, services, exceptions) live here — Tasks 5–7 must NOT edit `strings.json`/`translations/en.json`; the keys they need are defined below.

- [ ] **Step 1: Write `application_credentials.py`**

```python
"""Application credentials platform for the Volvo Wallbox integration."""

from __future__ import annotations

from homeassistant.components.application_credentials import ClientCredential
from homeassistant.core import HomeAssistant
from homeassistant.helpers.config_entry_oauth2_flow import (
    LocalOAuth2ImplementationWithPkce,
)

from .const import AUTHORIZE_URL, SCOPES, TOKEN_URL


async def async_get_auth_implementation(
    hass: HomeAssistant, auth_domain: str, credential: ClientCredential
) -> VolvoWallboxOAuth2Implementation:
    """Return auth implementation."""
    return VolvoWallboxOAuth2Implementation(
        hass,
        auth_domain,
        credential.client_id,
        AUTHORIZE_URL,
        TOKEN_URL,
        credential.client_secret,
    )


class VolvoWallboxOAuth2Implementation(LocalOAuth2ImplementationWithPkce):
    """Volvo ID OAuth2 implementation with PKCE."""

    @property
    def extra_authorize_data(self) -> dict:
        """Extra data appended to the authorize url."""
        return super().extra_authorize_data | {"scope": " ".join(SCOPES)}
```

- [ ] **Step 2: Write failing config flow tests**

`tests/test_config_flow.py`:

```python
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
from homeassistant.const import CONF_API_KEY
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_config_flow.py -v`
Expected: FAIL — no config flow registered / `ModuleNotFoundError`.

- [ ] **Step 4: Implement `config_flow.py`**

```python
"""Config flow for the Volvo Wallbox integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    SOURCE_REAUTH,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import (
    CONF_ACCESS_TOKEN,
    CONF_API_KEY,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.config_entry_oauth2_flow import AbstractOAuth2FlowHandler
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import ConfigFlowAuth, EnergyDeviceApi, EnergyDeviceApiError
from .const import CONF_WALLBOX_ID, DEFAULT_SCAN_INTERVAL, DOMAIN, SCOPES

_LOGGER = logging.getLogger(__name__)


def _create_api(hass: HomeAssistant, access_token: str, api_key: str) -> EnergyDeviceApi:
    session = aiohttp_client.async_get_clientsession(hass)
    return EnergyDeviceApi(session, ConfigFlowAuth(access_token), api_key)


class VolvoWallboxFlowHandler(AbstractOAuth2FlowHandler, domain=DOMAIN):
    """Config flow handling Volvo ID OAuth2 authentication."""

    VERSION = 1
    DOMAIN = DOMAIN

    def __init__(self) -> None:
        """Initialize the flow."""
        super().__init__()
        self._config_data: dict[str, Any] = {}

    @property
    def extra_authorize_data(self) -> dict:
        """Extra data appended to the authorize url."""
        return super().extra_authorize_data | {"scope": " ".join(SCOPES)}

    @property
    def logger(self) -> logging.Logger:
        """Return logger."""
        return _LOGGER

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> VolvoWallboxOptionsFlow:  # noqa: ANN001
        """Return the options flow."""
        return VolvoWallboxOptionsFlow()

    async def async_oauth_create_entry(self, data: dict) -> ConfigFlowResult:
        """Continue the flow after OAuth."""
        self._config_data |= (self.init_data or {}) | data
        return await self.async_step_api_key()

    async def async_step_reauth(self, _: Mapping[str, Any]) -> ConfigFlowResult:
        """Perform reauth upon an API authentication error."""
        self._config_data = dict(self._get_reauth_entry().data)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm reauth dialog."""
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")
        return await self.async_step_user()

    async def async_step_api_key(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for and validate the VCC API key."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api = _create_api(
                self.hass,
                self._config_data[CONF_TOKEN][CONF_ACCESS_TOKEN],
                user_input[CONF_API_KEY],
            )
            try:
                await api.async_get_id_tokens()
            except EnergyDeviceApiError:
                _LOGGER.exception("API key validation failed")
                errors["base"] = "invalid_api_key"
            else:
                self._config_data |= user_input
                return await self.async_step_wallbox_id()

        suggested = user_input or {CONF_API_KEY: self._config_data.get(CONF_API_KEY, "")}
        schema = self.add_suggested_values_to_schema(
            vol.Schema(
                {
                    vol.Required(CONF_API_KEY): TextSelector(
                        TextSelectorConfig(
                            type=TextSelectorType.TEXT, autocomplete="password"
                        )
                    )
                }
            ),
            suggested,
        )
        return self.async_show_form(
            step_id="api_key",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "volvo_dev_portal": "https://developer.volvocars.com/account/#your-api-applications"
            },
        )

    async def async_step_wallbox_id(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for and validate the wallbox ID."""
        errors: dict[str, str] = {}

        if self.source == SOURCE_REAUTH:
            # Keep the existing wallbox ID on reauth.
            return await self._async_create_or_update()

        if user_input is not None:
            api = _create_api(
                self.hass,
                self._config_data[CONF_TOKEN][CONF_ACCESS_TOKEN],
                self._config_data[CONF_API_KEY],
            )
            try:
                await api.async_get_wallbox_state(user_input[CONF_WALLBOX_ID])
            except EnergyDeviceApiError:
                _LOGGER.exception("Wallbox ID validation failed")
                errors["base"] = "invalid_wallbox_id"
            else:
                self._config_data |= user_input
                return await self._async_create_or_update()

        schema = vol.Schema({vol.Required(CONF_WALLBOX_ID): str})
        return self.async_show_form(
            step_id="wallbox_id", data_schema=schema, errors=errors
        )

    async def _async_create_or_update(self) -> ConfigFlowResult:
        wallbox_id = self._config_data[CONF_WALLBOX_ID]
        await self.async_set_unique_id(wallbox_id)

        if self.source == SOURCE_REAUTH:
            self._abort_if_unique_id_mismatch()
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(), data_updates=self._config_data
            )

        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=f"Volvo Wallbox {wallbox_id}", data=self._config_data
        )


class VolvoWallboxOptionsFlow(OptionsFlowWithReload):
    """Options flow for the polling interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        schema = self.add_suggested_values_to_schema(
            vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL): NumberSelector(
                        NumberSelectorConfig(
                            min=30, max=600, step=10, mode=NumberSelectorMode.BOX
                        )
                    )
                }
            ),
            {
                CONF_SCAN_INTERVAL: self.config_entry.options.get(
                    CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                )
            },
        )
        return self.async_show_form(step_id="init", data_schema=schema)
```

- [ ] **Step 5: Write ALL translations (config + entities + services + exceptions)**

`custom_components/volvo_wallbox/strings.json` and an **identical copy** at `custom_components/volvo_wallbox/translations/en.json` (custom components load `translations/en.json` at runtime; `strings.json` is kept as source of truth for a future core migration):

```json
{
  "config": {
    "step": {
      "pick_implementation": {
        "title": "Pick authentication method"
      },
      "reauth_confirm": {
        "title": "Re-authenticate Volvo Wallbox",
        "description": "The Volvo Wallbox integration needs to re-authenticate your account."
      },
      "api_key": {
        "title": "Enter your API key",
        "description": "Get your API key from the [Volvo developers portal]({volvo_dev_portal}).",
        "data": {
          "api_key": "API key"
        }
      },
      "wallbox_id": {
        "title": "Enter your wallbox ID",
        "description": "The ID of your wallbox (for example its serial number). It is validated against the Volvo API, so if one candidate fails, try another.",
        "data": {
          "wallbox_id": "Wallbox ID"
        }
      }
    },
    "error": {
      "invalid_api_key": "The API key is not valid for the Energy Device API.",
      "invalid_wallbox_id": "No wallbox found with this ID. Try another value (serial number, PNC, ...)."
    },
    "abort": {
      "already_configured": "This wallbox is already configured.",
      "already_in_progress": "Configuration flow is already in progress.",
      "authorize_url_timeout": "Timeout generating authorize URL.",
      "missing_configuration": "The component is not configured. Please follow the documentation.",
      "no_url_available": "No URL available.",
      "oauth_error": "Received invalid token data.",
      "oauth_failed": "Error while obtaining access token.",
      "oauth_timeout": "Timeout resolving OAuth token.",
      "oauth_unauthorized": "OAuth authorization error while obtaining access token.",
      "reauth_successful": "Re-authentication was successful.",
      "unique_id_mismatch": "The authenticated account does not match the configured wallbox."
    }
  },
  "options": {
    "step": {
      "init": {
        "title": "Volvo Wallbox options",
        "data": {
          "scan_interval": "Polling interval (seconds)"
        }
      }
    }
  },
  "entity": {
    "sensor": {
      "charging_state": { "name": "Charging state" },
      "current_session_energy": { "name": "Current session energy" },
      "energy_today": { "name": "Energy today" },
      "energy_this_month": { "name": "Energy this month" },
      "last_session_energy": { "name": "Last session energy" },
      "last_session_start": { "name": "Last session start" },
      "last_session_end": { "name": "Last session end" }
    },
    "button": {
      "start_charging": { "name": "Start charging" },
      "pause_charging": { "name": "Pause charging" }
    },
    "number": {
      "charging_amp_limit": { "name": "Charging amp limit" },
      "discharging_amp_limit": { "name": "Discharging amp limit" }
    }
  },
  "services": {
    "start_charging": {
      "name": "Start charging",
      "description": "Starts charging, optionally on behalf of an RFID ID token.",
      "fields": {
        "device_id": { "name": "Wallbox", "description": "The wallbox device." },
        "id_token": { "name": "ID token", "description": "Optional RFID ID token to start the session with." }
      }
    },
    "apply_charging_schedule": {
      "name": "Apply charging schedule",
      "description": "Applies a transactional charging schedule to the wallbox.",
      "fields": {
        "device_id": { "name": "Wallbox", "description": "The wallbox device." },
        "start": { "name": "Start", "description": "When the schedule starts." },
        "periods": { "name": "Periods", "description": "List of periods, each with type (watt or ampere), value and duration (HH:MM:SS)." },
        "schedule_id": { "name": "Schedule ID", "description": "Optional schedule identifier." }
      }
    },
    "get_charging_sessions": {
      "name": "Get charging sessions",
      "description": "Returns charging sessions in a time range.",
      "fields": {
        "device_id": { "name": "Wallbox", "description": "The wallbox device." },
        "start": { "name": "Start", "description": "Range start." },
        "end": { "name": "End", "description": "Range end." },
        "id_token": { "name": "ID token", "description": "Optional RFID ID token filter." }
      }
    },
    "read_id_token": {
      "name": "Read ID token",
      "description": "Puts the wallbox in RFID read mode to learn a new token.",
      "fields": {
        "device_id": { "name": "Wallbox", "description": "The wallbox device." }
      }
    },
    "add_id_token": {
      "name": "Add ID token",
      "description": "Registers a new RFID ID token on your account.",
      "fields": {
        "name": { "name": "Name", "description": "Friendly name for the token." },
        "token": { "name": "Token", "description": "The RFID token value." }
      }
    },
    "update_id_token": {
      "name": "Update ID token",
      "description": "Renames an existing RFID ID token.",
      "fields": {
        "name": { "name": "Name", "description": "New friendly name." },
        "token": { "name": "Token", "description": "The RFID token value." }
      }
    },
    "delete_id_token": {
      "name": "Delete ID token",
      "description": "Removes an RFID ID token from your account.",
      "fields": {
        "token": { "name": "Token", "description": "The RFID token value to delete." }
      }
    }
  },
  "exceptions": {
    "operation_failed": {
      "message": "Wallbox operation failed: {message} ({code})"
    },
    "device_not_found": {
      "message": "No Volvo Wallbox found for the given device."
    },
    "entry_not_loaded": {
      "message": "The Volvo Wallbox config entry is not loaded."
    }
  }
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_config_flow.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add custom_components/volvo_wallbox/application_credentials.py \
        custom_components/volvo_wallbox/config_flow.py \
        custom_components/volvo_wallbox/strings.json \
        custom_components/volvo_wallbox/translations/en.json \
        tests/test_config_flow.py
git commit -m "feat: add OAuth config flow with API key and wallbox ID validation"
```

---

### Task 4: Coordinator, entry setup, and base entity

**Files:**
- Create: `custom_components/volvo_wallbox/coordinator.py`
- Create: `custom_components/volvo_wallbox/entity.py`
- Modify: `custom_components/volvo_wallbox/__init__.py` (replace stub)
- Test: `tests/test_coordinator.py`
- Modify: `tests/conftest.py` (add shared fixtures)

**Interfaces:**
- Consumes: `EnergyDeviceApi`, `VolvoWallboxAuth`, `ChargingSession`, exceptions (Task 2); constants (Task 1).
- Produces (used by Tasks 5–8):
  - `@dataclass WallboxData(state: str, sessions: list[ChargingSession], current_session: ChargingSession | None, last_session: ChargingSession | None, energy_today: float, energy_this_month: float)`
  - Pure functions: `find_current_session(sessions) -> ChargingSession | None`, `find_last_completed_session(sessions) -> ChargingSession | None`, `energy_since(sessions, cutoff: datetime) -> float`
  - `class WallboxCoordinator(DataUpdateCoordinator[WallboxData])` with attributes `api: EnergyDeviceApi`, `wallbox_id: str`
  - `type VolvoWallboxConfigEntry = ConfigEntry[WallboxCoordinator]` (in `coordinator.py`); `entry.runtime_data` is the coordinator
  - `class VolvoWallboxEntity(CoordinatorEntity[WallboxCoordinator])` with `__init__(coordinator, key: str)` setting `unique_id = f"{wallbox_id}_{key}"`, `translation_key = key`, and shared `DeviceInfo(identifiers={(DOMAIN, wallbox_id)})`
  - Test fixtures in `conftest.py`: `mock_config_entry`, `mock_api`, `setup_integration`

- [ ] **Step 1: Write failing tests**

`tests/test_coordinator.py`:

```python
"""Tests for the Volvo Wallbox coordinator and derivation logic."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

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
    assert coordinator.data.state == "CHARGING"
    assert coordinator.data.energy_this_month == 18.0


async def test_setup_entry_auth_error_starts_reauth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: AsyncMock,
) -> None:
    """An auth error during setup puts the entry in reauth."""
    mock_api.async_get_wallbox_state.side_effect = EnergyDeviceAuthError("expired")

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
    mock_api.async_get_wallbox_state.side_effect = EnergyDeviceApiError("boom")

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
```

Append to `tests/conftest.py` (keep the existing fixture):

```python
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
```

Note for the implementer: with `dt_util.now()` returning the real current date, `energy_today`/`energy_this_month` assertions in later tasks must not depend on the wall clock — the two setup tests above only assert `energy_this_month == 18.0` because the fixture dates (July 2026) match today's month only on 2026-07. To make this deterministic, `test_setup_entry` MUST freeze time: use the `freezer` fixture from `freezegun` (bundled with pytest-homeassistant-custom-component) — add `@pytest.mark.freeze_time("2026-07-12 12:00:00+00:00")` on `test_setup_entry` and on every later test that asserts derived energy values.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_coordinator.py -v`
Expected: FAIL — `ImportError` (no `coordinator` module).

- [ ] **Step 3: Implement `coordinator.py`**

```python
"""Coordinator for the Volvo Wallbox integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    ChargingSession,
    EnergyDeviceApi,
    EnergyDeviceApiError,
    EnergyDeviceAuthError,
)
from .const import CONF_WALLBOX_ID, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

type VolvoWallboxConfigEntry = ConfigEntry[WallboxCoordinator]


@dataclass
class WallboxData:
    """Data for the wallbox."""

    state: str
    sessions: list[ChargingSession]
    current_session: ChargingSession | None
    last_session: ChargingSession | None
    energy_today: float
    energy_this_month: float


def find_current_session(
    sessions: list[ChargingSession],
) -> ChargingSession | None:
    """Return the open session, if any."""
    open_sessions = [s for s in sessions if s.end is None]
    return max(open_sessions, key=lambda s: s.start, default=None)


def find_last_completed_session(
    sessions: list[ChargingSession],
) -> ChargingSession | None:
    """Return the completed session with the latest end, if any."""
    completed = [s for s in sessions if s.end is not None]
    return max(completed, key=lambda s: s.end, default=None)


def energy_since(sessions: list[ChargingSession], cutoff: datetime) -> float:
    """Sum charged energy of sessions starting at or after the cutoff."""
    return sum(s.charged_energy for s in sessions if s.start >= cutoff)


class WallboxCoordinator(DataUpdateCoordinator[WallboxData]):
    """Coordinator polling wallbox state and charging sessions."""

    config_entry: VolvoWallboxConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: VolvoWallboxConfigEntry,
        api: EnergyDeviceApi,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )
        self.api = api
        self.wallbox_id: str = entry.data[CONF_WALLBOX_ID]

    async def _async_update_data(self) -> WallboxData:
        """Fetch wallbox state and this month's sessions."""
        now = dt_util.now()
        month_start = dt_util.start_of_local_day(now.replace(day=1))
        today_start = dt_util.start_of_local_day(now)

        try:
            state = await self.api.async_get_wallbox_state(self.wallbox_id)
            sessions = await self.api.async_get_charging_sessions(
                self.wallbox_id, month_start, now
            )
        except EnergyDeviceAuthError as err:
            raise ConfigEntryAuthFailed(err) from err
        except EnergyDeviceApiError as err:
            raise UpdateFailed(f"Error communicating with the Volvo API: {err}") from err

        return WallboxData(
            state=state,
            sessions=sessions,
            current_session=find_current_session(sessions),
            last_session=find_last_completed_session(sessions),
            energy_today=energy_since(sessions, today_start),
            energy_this_month=energy_since(sessions, month_start),
        )
```

- [ ] **Step 4: Implement `entity.py`**

```python
"""Base entity for the Volvo Wallbox integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import WallboxCoordinator


class VolvoWallboxEntity(CoordinatorEntity[WallboxCoordinator]):
    """Base class for Volvo Wallbox entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: WallboxCoordinator, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        wallbox_id = coordinator.wallbox_id
        self._attr_unique_id = f"{wallbox_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, wallbox_id)},
            manufacturer=MANUFACTURER,
            name="Volvo Wallbox",
            serial_number=wallbox_id,
        )
```

- [ ] **Step 5: Implement `__init__.py`** (replaces the Task 1 stub)

```python
"""The Volvo Wallbox integration."""

from __future__ import annotations

from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.config_entry_oauth2_flow import (
    OAuth2Session,
    async_get_config_entry_implementation,
)

from .api import EnergyDeviceApi, VolvoWallboxAuth
from .const import PLATFORMS
from .coordinator import VolvoWallboxConfigEntry, WallboxCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: VolvoWallboxConfigEntry
) -> bool:
    """Set up Volvo Wallbox from a config entry."""
    implementation = await async_get_config_entry_implementation(hass, entry)
    oauth_session = OAuth2Session(hass, entry, implementation)
    web_session = aiohttp_client.async_get_clientsession(hass)

    api = EnergyDeviceApi(
        web_session, VolvoWallboxAuth(oauth_session), entry.data[CONF_API_KEY]
    )
    coordinator = WallboxCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: VolvoWallboxConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_coordinator.py tests/test_api.py -v`
Expected: all PASS (coordinator setup tests exercise `__init__.py` with the mocked API).

- [ ] **Step 7: Commit**

```bash
git add custom_components/volvo_wallbox/coordinator.py \
        custom_components/volvo_wallbox/entity.py \
        custom_components/volvo_wallbox/__init__.py \
        tests/test_coordinator.py tests/conftest.py
git commit -m "feat: add coordinator with session-derived consumption data"
```

---

### Task 5: Sensor platform

**Files:**
- Create: `custom_components/volvo_wallbox/sensor.py`
- Test: `tests/test_sensor.py`

**Interfaces:**
- Consumes: `WallboxData`, `VolvoWallboxConfigEntry` (Task 4), `VolvoWallboxEntity` (Task 4). Translation keys `charging_state`, `current_session_energy`, `energy_today`, `energy_this_month`, `last_session_energy`, `last_session_start`, `last_session_end` (Task 3). Fixtures from `conftest.py`.
- Produces: seven sensors on the wallbox device. Do NOT edit translation files.

- [ ] **Step 1: Write failing tests**

`tests/test_sensor.py`:

```python
"""Tests for the Volvo Wallbox sensors."""

from __future__ import annotations

import pytest

from homeassistant.core import HomeAssistant


@pytest.mark.freeze_time("2026-07-12 12:00:00+00:00")
@pytest.mark.usefixtures("setup_integration")
@pytest.mark.parametrize(
    ("entity_id", "expected_state"),
    [
        pytest.param("sensor.volvo_wallbox_charging_state", "CHARGING", id="state"),
        pytest.param(
            "sensor.volvo_wallbox_current_session_energy", "2.5", id="current"
        ),
        pytest.param("sensor.volvo_wallbox_energy_today", "8.0", id="today"),
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_sensor.py -v`
Expected: FAIL — entities not found (sensor platform missing).

- [ ] **Step 3: Implement `sensor.py`**

```python
"""Sensors for the Volvo Wallbox integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .coordinator import VolvoWallboxConfigEntry, WallboxCoordinator, WallboxData
from .entity import VolvoWallboxEntity


@dataclass(frozen=True, kw_only=True)
class VolvoWallboxSensorDescription(SensorEntityDescription):
    """Describes a Volvo Wallbox sensor."""

    value_fn: Callable[[WallboxData], StateType | datetime]


SENSOR_DESCRIPTIONS: tuple[VolvoWallboxSensorDescription, ...] = (
    VolvoWallboxSensorDescription(
        key="charging_state",
        value_fn=lambda data: data.state,
    ),
    VolvoWallboxSensorDescription(
        key="current_session_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=lambda data: data.current_session.charged_energy
        if data.current_session
        else 0.0,
    ),
    VolvoWallboxSensorDescription(
        key="energy_today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=lambda data: data.energy_today,
    ),
    VolvoWallboxSensorDescription(
        key="energy_this_month",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=lambda data: data.energy_this_month,
    ),
    VolvoWallboxSensorDescription(
        key="last_session_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=lambda data: data.last_session.charged_energy
        if data.last_session
        else None,
    ),
    VolvoWallboxSensorDescription(
        key="last_session_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.last_session.start if data.last_session else None,
    ),
    VolvoWallboxSensorDescription(
        key="last_session_end",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.last_session.end if data.last_session else None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VolvoWallboxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        VolvoWallboxSensor(coordinator, description)
        for description in SENSOR_DESCRIPTIONS
    )


class VolvoWallboxSensor(VolvoWallboxEntity, SensorEntity):
    """A Volvo Wallbox sensor."""

    entity_description: VolvoWallboxSensorDescription

    def __init__(
        self,
        coordinator: WallboxCoordinator,
        description: VolvoWallboxSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType | datetime:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_sensor.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/volvo_wallbox/sensor.py tests/test_sensor.py
git commit -m "feat: add consumption and state sensors"
```

---

### Task 6: Button and number platforms

**Files:**
- Create: `custom_components/volvo_wallbox/button.py`
- Create: `custom_components/volvo_wallbox/number.py`
- Test: `tests/test_button.py`, `tests/test_number.py`

**Interfaces:**
- Consumes: `VolvoWallboxEntity`, `VolvoWallboxConfigEntry`, `WallboxCoordinator` (Task 4); `EnergyDeviceApi` method signatures and `WallboxOperationError` (Task 2). Translation keys `start_charging`, `pause_charging`, `charging_amp_limit`, `discharging_amp_limit`, exception key `operation_failed` (Task 3). Do NOT edit translation files.
- Produces: 2 buttons, 2 numbers.

- [ ] **Step 1: Write failing tests**

`tests/test_button.py`:

```python
"""Tests for the Volvo Wallbox buttons."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.volvo_wallbox.api import WallboxOperationError

from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

WALLBOX_ID = "WB123"


@pytest.mark.usefixtures("setup_integration")
@pytest.mark.parametrize(
    ("entity_id", "api_method"),
    [
        pytest.param(
            "button.volvo_wallbox_start_charging",
            "async_start_charging",
            id="start",
        ),
        pytest.param(
            "button.volvo_wallbox_pause_charging",
            "async_pause_charging",
            id="pause",
        ),
    ],
)
async def test_button_press(
    hass: HomeAssistant, mock_api: AsyncMock, entity_id: str, api_method: str
) -> None:
    """Pressing a button calls the matching API method."""
    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    getattr(mock_api, api_method).assert_called_once_with(WALLBOX_ID)


@pytest.mark.usefixtures("setup_integration")
async def test_button_press_operation_error(
    hass: HomeAssistant, mock_api: AsyncMock
) -> None:
    """A wallbox operation error surfaces as HomeAssistantError."""
    mock_api.async_start_charging.side_effect = WallboxOperationError(
        "offline", "WALLBOX_OFFLINE"
    )

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            BUTTON_DOMAIN,
            SERVICE_PRESS,
            {ATTR_ENTITY_ID: "button.volvo_wallbox_start_charging"},
            blocking=True,
        )
```

`tests/test_number.py`:

```python
"""Tests for the Volvo Wallbox numbers."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.volvo_wallbox.api import WallboxOperationError

from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

WALLBOX_ID = "WB123"


@pytest.mark.usefixtures("setup_integration")
@pytest.mark.parametrize(
    ("entity_id", "api_method"),
    [
        pytest.param(
            "number.volvo_wallbox_charging_amp_limit",
            "async_set_charging_amp_limit",
            id="charging",
        ),
        pytest.param(
            "number.volvo_wallbox_discharging_amp_limit",
            "async_set_discharging_amp_limit",
            id="discharging",
        ),
    ],
)
async def test_set_amp_limit(
    hass: HomeAssistant, mock_api: AsyncMock, entity_id: str, api_method: str
) -> None:
    """Setting a number calls the matching API method and keeps the value."""
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: 16},
        blocking=True,
    )

    getattr(mock_api, api_method).assert_called_once_with(WALLBOX_ID, 16.0)
    assert hass.states.get(entity_id).state == "16.0"


@pytest.mark.usefixtures("setup_integration")
async def test_discharge_not_supported_marks_unavailable(
    hass: HomeAssistant, mock_api: AsyncMock
) -> None:
    """NOT_SUPPORTED_BY_WALLBOX marks the discharge number unavailable."""
    entity_id = "number.volvo_wallbox_discharging_amp_limit"
    mock_api.async_set_discharging_amp_limit.side_effect = WallboxOperationError(
        "unsupported", "NOT_SUPPORTED_BY_WALLBOX"
    )

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: 10},
            blocking=True,
        )

    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_button.py tests/test_number.py -v`
Expected: FAIL — entities not found.

- [ ] **Step 3: Implement `button.py`**

```python
"""Buttons for the Volvo Wallbox integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import EnergyDeviceApi, WallboxOperationError
from .const import DOMAIN
from .coordinator import VolvoWallboxConfigEntry, WallboxCoordinator
from .entity import VolvoWallboxEntity


@dataclass(frozen=True, kw_only=True)
class VolvoWallboxButtonDescription(ButtonEntityDescription):
    """Describes a Volvo Wallbox button."""

    press_fn: Callable[[EnergyDeviceApi, str], Awaitable[None]]


BUTTON_DESCRIPTIONS: tuple[VolvoWallboxButtonDescription, ...] = (
    VolvoWallboxButtonDescription(
        key="start_charging",
        press_fn=lambda api, wallbox_id: api.async_start_charging(wallbox_id),
    ),
    VolvoWallboxButtonDescription(
        key="pause_charging",
        press_fn=lambda api, wallbox_id: api.async_pause_charging(wallbox_id),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VolvoWallboxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up buttons."""
    coordinator = entry.runtime_data
    async_add_entities(
        VolvoWallboxButton(coordinator, description)
        for description in BUTTON_DESCRIPTIONS
    )


class VolvoWallboxButton(VolvoWallboxEntity, ButtonEntity):
    """A Volvo Wallbox button."""

    entity_description: VolvoWallboxButtonDescription

    def __init__(
        self,
        coordinator: WallboxCoordinator,
        description: VolvoWallboxButtonDescription,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        """Press the button."""
        try:
            await self.entity_description.press_fn(
                self.coordinator.api, self.coordinator.wallbox_id
            )
        except WallboxOperationError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="operation_failed",
                translation_placeholders={"message": str(err), "code": err.code},
            ) from err
        await self.coordinator.async_request_refresh()
```

- [ ] **Step 4: Implement `number.py`**

```python
"""Numbers for the Volvo Wallbox integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.number import (
    NumberEntityDescription,
    NumberMode,
    RestoreNumber,
)
from homeassistant.const import UnitOfElectricCurrent
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import EnergyDeviceApi, WallboxOperationError
from .const import DOMAIN
from .coordinator import VolvoWallboxConfigEntry, WallboxCoordinator
from .entity import VolvoWallboxEntity


@dataclass(frozen=True, kw_only=True)
class VolvoWallboxNumberDescription(NumberEntityDescription):
    """Describes a Volvo Wallbox number."""

    set_fn: Callable[[EnergyDeviceApi, str, float], Awaitable[None]]


NUMBER_DESCRIPTIONS: tuple[VolvoWallboxNumberDescription, ...] = (
    VolvoWallboxNumberDescription(
        key="charging_amp_limit",
        native_min_value=6,
        native_max_value=32,
        native_step=1,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        mode=NumberMode.BOX,
        set_fn=lambda api, wallbox_id, value: api.async_set_charging_amp_limit(
            wallbox_id, value
        ),
    ),
    VolvoWallboxNumberDescription(
        key="discharging_amp_limit",
        native_min_value=0,
        native_max_value=32,
        native_step=1,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        mode=NumberMode.BOX,
        set_fn=lambda api, wallbox_id, value: api.async_set_discharging_amp_limit(
            wallbox_id, value
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VolvoWallboxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up numbers."""
    coordinator = entry.runtime_data
    async_add_entities(
        VolvoWallboxNumber(coordinator, description)
        for description in NUMBER_DESCRIPTIONS
    )


class VolvoWallboxNumber(VolvoWallboxEntity, RestoreNumber):
    """A Volvo Wallbox amp limit number.

    The API offers no read-back for limits, so the value is optimistic.
    """

    entity_description: VolvoWallboxNumberDescription
    _attr_assumed_state = True

    def __init__(
        self,
        coordinator: WallboxCoordinator,
        description: VolvoWallboxNumberDescription,
    ) -> None:
        """Initialize the number."""
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_available = True

    async def async_added_to_hass(self) -> None:
        """Restore the last set value."""
        await super().async_added_to_hass()
        if (last_data := await self.async_get_last_number_data()) is not None:
            self._attr_native_value = last_data.native_value

    async def async_set_native_value(self, value: float) -> None:
        """Set the amp limit."""
        try:
            await self.entity_description.set_fn(
                self.coordinator.api, self.coordinator.wallbox_id, value
            )
        except WallboxOperationError as err:
            if err.code == "NOT_SUPPORTED_BY_WALLBOX":
                self._attr_available = False
                self.async_write_ha_state()
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="operation_failed",
                translation_placeholders={"message": str(err), "code": err.code},
            ) from err
        self._attr_native_value = value
        self.async_write_ha_state()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_button.py tests/test_number.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add custom_components/volvo_wallbox/button.py \
        custom_components/volvo_wallbox/number.py \
        tests/test_button.py tests/test_number.py
git commit -m "feat: add charging control buttons and amp limit numbers"
```

---

### Task 7: Services

**Files:**
- Create: `custom_components/volvo_wallbox/services.py`
- Create: `custom_components/volvo_wallbox/services.yaml`
- Modify: `custom_components/volvo_wallbox/__init__.py` (add `async_setup` registering services)
- Test: `tests/test_services.py`

**Interfaces:**
- Consumes: `WallboxCoordinator` via `entry.runtime_data` (Task 4); `EnergyDeviceApi` methods and `WallboxOperationError` (Task 2). Service/exception translation keys (Task 3). Do NOT edit translation files.
- Produces: services `volvo_wallbox.start_charging`, `apply_charging_schedule`, `get_charging_sessions` (response-only), `read_id_token`, `add_id_token`, `update_id_token`, `delete_id_token`.

- [ ] **Step 1: Write failing tests**

`tests/test_services.py`:

```python
"""Tests for the Volvo Wallbox services."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.volvo_wallbox.const import DOMAIN

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr

WALLBOX_ID = "WB123"


def _device_id(hass: HomeAssistant, entry: MockConfigEntry) -> str:
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, WALLBOX_ID)})
    assert device is not None
    return device.id


@pytest.mark.usefixtures("setup_integration")
async def test_start_charging_with_token(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_api: AsyncMock
) -> None:
    """start_charging passes the RFID token."""
    await hass.services.async_call(
        DOMAIN,
        "start_charging",
        {
            "device_id": _device_id(hass, mock_config_entry),
            "id_token": "rfid-1",
        },
        blocking=True,
    )

    mock_api.async_start_charging.assert_called_once_with(WALLBOX_ID, "rfid-1")


@pytest.mark.usefixtures("setup_integration")
async def test_get_charging_sessions_response(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_api: AsyncMock
) -> None:
    """get_charging_sessions returns serialized sessions."""
    response = await hass.services.async_call(
        DOMAIN,
        "get_charging_sessions",
        {
            "device_id": _device_id(hass, mock_config_entry),
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
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_api: AsyncMock
) -> None:
    """apply_charging_schedule maps periods to the API contract."""
    await hass.services.async_call(
        DOMAIN,
        "apply_charging_schedule",
        {
            "device_id": _device_id(hass, mock_config_entry),
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
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_api: AsyncMock
) -> None:
    """add_id_token registers the token."""
    await hass.services.async_call(
        DOMAIN,
        "add_id_token",
        {
            "device_id": _device_id(hass, mock_config_entry),
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_services.py -v`
Expected: FAIL — services not registered.

- [ ] **Step 3: Implement `services.py`**

```python
"""Services for the Volvo Wallbox integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.util import dt as dt_util

from .api import WallboxOperationError
from .const import DOMAIN
from .coordinator import WallboxCoordinator

ATTR_DEVICE_ID = "device_id"
ATTR_ID_TOKEN = "id_token"
ATTR_START = "start"
ATTR_END = "end"
ATTR_PERIODS = "periods"
ATTR_SCHEDULE_ID = "schedule_id"
ATTR_NAME = "name"
ATTR_TOKEN = "token"

SERVICE_START_CHARGING = "start_charging"
SERVICE_APPLY_CHARGING_SCHEDULE = "apply_charging_schedule"
SERVICE_GET_CHARGING_SESSIONS = "get_charging_sessions"
SERVICE_READ_ID_TOKEN = "read_id_token"
SERVICE_ADD_ID_TOKEN = "add_id_token"
SERVICE_UPDATE_ID_TOKEN = "update_id_token"
SERVICE_DELETE_ID_TOKEN = "delete_id_token"

_PERIOD_SCHEMA = vol.Schema(
    {
        vol.Required("type"): vol.In(["watt", "ampere"]),
        vol.Required("value"): vol.Coerce(float),
        vol.Required("duration"): cv.string,
    }
)

_DEVICE_SCHEMA = {vol.Required(ATTR_DEVICE_ID): cv.string}

START_CHARGING_SCHEMA = vol.Schema(
    _DEVICE_SCHEMA | {vol.Optional(ATTR_ID_TOKEN): cv.string}
)
APPLY_SCHEDULE_SCHEMA = vol.Schema(
    _DEVICE_SCHEMA
    | {
        vol.Required(ATTR_START): cv.datetime,
        vol.Required(ATTR_PERIODS): vol.All(cv.ensure_list, [_PERIOD_SCHEMA]),
        vol.Optional(ATTR_SCHEDULE_ID): cv.string,
    }
)
GET_SESSIONS_SCHEMA = vol.Schema(
    _DEVICE_SCHEMA
    | {
        vol.Required(ATTR_START): cv.datetime,
        vol.Required(ATTR_END): cv.datetime,
        vol.Optional(ATTR_ID_TOKEN): cv.string,
    }
)
READ_ID_TOKEN_SCHEMA = vol.Schema(_DEVICE_SCHEMA)
ID_TOKEN_SCHEMA = vol.Schema(
    _DEVICE_SCHEMA
    | {vol.Required(ATTR_NAME): cv.string, vol.Required(ATTR_TOKEN): cv.string}
)
DELETE_ID_TOKEN_SCHEMA = vol.Schema(
    _DEVICE_SCHEMA | {vol.Required(ATTR_TOKEN): cv.string}
)


def _get_coordinator(call: ServiceCall) -> WallboxCoordinator:
    """Resolve the coordinator from the device id in the call."""
    device_id = call.data[ATTR_DEVICE_ID]
    device = dr.async_get(call.hass).async_get(device_id)
    if device is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="device_not_found"
        )
    for entry_id in device.config_entries:
        entry = call.hass.config_entries.async_get_entry(entry_id)
        if entry and entry.domain == DOMAIN:
            if entry.state is not ConfigEntryState.LOADED:
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="entry_not_loaded"
                )
            return entry.runtime_data
    raise ServiceValidationError(
        translation_domain=DOMAIN, translation_key="device_not_found"
    )


def _wrap_operation_error(err: WallboxOperationError) -> HomeAssistantError:
    return HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key="operation_failed",
        translation_placeholders={"message": str(err), "code": err.code},
    )


async def _start_charging(call: ServiceCall) -> None:
    coordinator = _get_coordinator(call)
    try:
        await coordinator.api.async_start_charging(
            coordinator.wallbox_id, call.data.get(ATTR_ID_TOKEN)
        )
    except WallboxOperationError as err:
        raise _wrap_operation_error(err) from err


async def _apply_charging_schedule(call: ServiceCall) -> None:
    coordinator = _get_coordinator(call)
    periods: list[dict[str, Any]] = []
    for period in call.data[ATTR_PERIODS]:
        if period["type"] == "watt":
            periods.append(
                {
                    "$type": "WattPeriod",
                    "watt": period["value"],
                    "duration": period["duration"],
                }
            )
        else:
            periods.append(
                {
                    "$type": "AmperePeriod",
                    "ampere": period["value"],
                    "duration": period["duration"],
                }
            )
    try:
        await coordinator.api.async_apply_charging_schedule(
            coordinator.wallbox_id,
            dt_util.as_utc(call.data[ATTR_START]),
            periods,
            call.data.get(ATTR_SCHEDULE_ID),
        )
    except WallboxOperationError as err:
        raise _wrap_operation_error(err) from err


async def _get_charging_sessions(call: ServiceCall) -> ServiceResponse:
    coordinator = _get_coordinator(call)
    try:
        sessions = await coordinator.api.async_get_charging_sessions(
            coordinator.wallbox_id,
            dt_util.as_utc(call.data[ATTR_START]),
            dt_util.as_utc(call.data[ATTR_END]),
            call.data.get(ATTR_ID_TOKEN),
        )
    except WallboxOperationError as err:
        raise _wrap_operation_error(err) from err
    return {
        "sessions": [
            {
                "transaction_id": session.transaction_id,
                "id_token": session.id_token,
                "start": session.start.isoformat(),
                "end": session.end.isoformat() if session.end else None,
                "charged_energy": session.charged_energy,
                "connector_id": session.connector_id,
            }
            for session in sessions
        ]
    }


async def _read_id_token(call: ServiceCall) -> None:
    coordinator = _get_coordinator(call)
    try:
        await coordinator.api.async_read_id_token(coordinator.wallbox_id)
    except WallboxOperationError as err:
        raise _wrap_operation_error(err) from err


async def _add_id_token(call: ServiceCall) -> None:
    coordinator = _get_coordinator(call)
    await coordinator.api.async_add_id_token(
        call.data[ATTR_NAME], call.data[ATTR_TOKEN]
    )


async def _update_id_token(call: ServiceCall) -> None:
    coordinator = _get_coordinator(call)
    await coordinator.api.async_update_id_token(
        call.data[ATTR_NAME], call.data[ATTR_TOKEN]
    )


async def _delete_id_token(call: ServiceCall) -> None:
    coordinator = _get_coordinator(call)
    await coordinator.api.async_delete_id_token(call.data[ATTR_TOKEN])


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration services."""
    hass.services.async_register(
        DOMAIN, SERVICE_START_CHARGING, _start_charging, START_CHARGING_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_APPLY_CHARGING_SCHEDULE,
        _apply_charging_schedule,
        APPLY_SCHEDULE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_CHARGING_SESSIONS,
        _get_charging_sessions,
        GET_SESSIONS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_READ_ID_TOKEN, _read_id_token, READ_ID_TOKEN_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_ADD_ID_TOKEN, _add_id_token, ID_TOKEN_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_UPDATE_ID_TOKEN, _update_id_token, ID_TOKEN_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_DELETE_ID_TOKEN, _delete_id_token, DELETE_ID_TOKEN_SCHEMA
    )
```

- [ ] **Step 4: Register services in `__init__.py`**

Add to `custom_components/volvo_wallbox/__init__.py` (after the existing imports, before `async_setup_entry`):

```python
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .services import async_setup_services

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Volvo Wallbox integration."""
    async_setup_services(hass)
    return True
```

- [ ] **Step 5: Write `services.yaml`**

```yaml
start_charging:
  fields:
    device_id:
      required: true
      selector:
        device:
          integration: volvo_wallbox
    id_token:
      required: false
      selector:
        text:

apply_charging_schedule:
  fields:
    device_id:
      required: true
      selector:
        device:
          integration: volvo_wallbox
    start:
      required: true
      selector:
        datetime:
    periods:
      required: true
      selector:
        object:
    schedule_id:
      required: false
      selector:
        text:

get_charging_sessions:
  fields:
    device_id:
      required: true
      selector:
        device:
          integration: volvo_wallbox
    start:
      required: true
      selector:
        datetime:
    end:
      required: true
      selector:
        datetime:
    id_token:
      required: false
      selector:
        text:

read_id_token:
  fields:
    device_id:
      required: true
      selector:
        device:
          integration: volvo_wallbox

add_id_token:
  fields:
    device_id:
      required: true
      selector:
        device:
          integration: volvo_wallbox
    name:
      required: true
      selector:
        text:
    token:
      required: true
      selector:
        text:

update_id_token:
  fields:
    device_id:
      required: true
      selector:
        device:
          integration: volvo_wallbox
    name:
      required: true
      selector:
        text:
    token:
      required: true
      selector:
        text:

delete_id_token:
  fields:
    device_id:
      required: true
      selector:
        device:
          integration: volvo_wallbox
    token:
      required: true
      selector:
        text:
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_services.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add custom_components/volvo_wallbox/services.py \
        custom_components/volvo_wallbox/services.yaml \
        custom_components/volvo_wallbox/__init__.py \
        tests/test_services.py
git commit -m "feat: add schedule, session query and RFID token services"
```

---

### Task 8: Diagnostics, README, full suite

**Files:**
- Create: `custom_components/volvo_wallbox/diagnostics.py`
- Create: `README.md`
- Test: `tests/test_diagnostics.py`

**Interfaces:**
- Consumes: everything above.
- Produces: redacted diagnostics; user-facing README; green full suite.

- [ ] **Step 1: Write failing diagnostics test**

`tests/test_diagnostics.py`:

```python
"""Tests for Volvo Wallbox diagnostics."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.volvo_wallbox.diagnostics import (
    async_get_config_entry_diagnostics,
)

from homeassistant.core import HomeAssistant


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_diagnostics.py -v`
Expected: FAIL — no `diagnostics` module.

- [ ] **Step 3: Implement `diagnostics.py`**

```python
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
```

- [ ] **Step 4: Write `README.md`**

```markdown
# Volvo Wallbox for Home Assistant

Custom integration for Volvo-branded wallboxes using the official
[Volvo Energy Device API](https://developer.volvocars.com/apis/energy-device-api/v1/overview/).

## Features

- Consumption sensors: current session, today, this month, last session
  (Energy-dashboard compatible)
- Charging state sensor
- Start / pause charging buttons
- Charging and discharging (V2G/V2H) amp limit controls
- Services: charging schedules, session queries, RFID ID token management

## Prerequisites

1. A [Volvo developers account](https://developer.volvocars.com/) with an API
   application (gives you the **VCC API key** and OAuth **client ID/secret**).
   The application must include the Energy Device API scopes.
2. **Before first use:** verify the scope list in
   `custom_components/volvo_wallbox/const.py` (`SCOPES`) matches the scopes
   shown on the Energy Device API overview page in the developer portal.
3. Your wallbox ID (try the serial number from the Volvo Cars app or the
   unit's label — the config flow validates it and lets you retry).

## Installation

Copy `custom_components/volvo_wallbox` into your Home Assistant `config/custom_components/`
directory (or add this repository to HACS as a custom repository) and restart
Home Assistant.

## Configuration

1. Settings → Devices & services → Add integration → **Volvo Wallbox**.
2. Enter your OAuth client ID/secret when asked for application credentials.
3. Log in with your Volvo ID.
4. Enter your VCC API key.
5. Enter your wallbox ID.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/python -m pytest tests -v
```
```

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests -v`
Expected: all PASS across all test modules.

- [ ] **Step 6: Commit**

```bash
git add custom_components/volvo_wallbox/diagnostics.py README.md tests/test_diagnostics.py
git commit -m "feat: add diagnostics and README"
```

---

## Self-Review Notes

- **Spec coverage:** consumption sensors (Task 5), state + start/pause (Tasks 5/6), amp limits incl. V2G unavailable-on-unsupported (Task 6), schedules + RFID services (Task 7), OAuth/application-credentials + validated config flow + reauth + options (Task 3), coordinator derivations + error mapping (Task 4), diagnostics (Task 8). Out-of-scope items from the spec are not planned.
- **Known open item (from spec):** `SCOPES` starts as `["openid"]`; the user must paste the real scope list from the developer portal (README documents this; single constant).
- **Type consistency:** `EnergyDeviceApi` method names in Tasks 5–7 match Task 2 signatures; `WallboxData` fields in Task 5 match Task 4; fixture names (`mock_config_entry`, `mock_api`, `setup_integration`) defined in Task 4's conftest and consumed in Tasks 5–8.
- **Entity-ID note:** tests assume entity IDs of the form `sensor.volvo_wallbox_<key>` derived from device name "Volvo Wallbox" + entity name. If HA generates different IDs, fix the test constants, not the entities.
