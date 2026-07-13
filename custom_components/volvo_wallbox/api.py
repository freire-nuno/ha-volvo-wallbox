"""API client for the Volvo Energy Device API, bound to Home Assistant OAuth."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any, cast
from urllib.parse import quote

from aiohttp import ClientError, ClientSession

from homeassistant.helpers.config_entry_oauth2_flow import OAuth2Session
from homeassistant.util import dt as dt_util

from .const import API_BASE_URL


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
        json_body: dict[str, Any] | None = None,
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
                json=json_body,
                headers=headers,
            )
            if response.status in (401, 403):
                raise EnergyDeviceAuthError(
                    f"Authentication failed: {response.status}"
                )
            if response.status in (409, 422):
                try:
                    body = await response.json(content_type=None)
                    message = body["message"]
                    code = body["code"]
                except (ValueError, KeyError, TypeError) as err:
                    raise EnergyDeviceApiError(
                        f"API error: {response.status}"
                    ) from err
                raise WallboxOperationError(message, code)
            if response.status >= 400:
                raise EnergyDeviceApiError(f"API error: {response.status}")
            text = await response.text()
        except ClientError as err:
            raise EnergyDeviceApiError(f"Connection error: {err}") from err

        if not text:
            return None
        try:
            return json.loads(text)
        except ValueError as err:
            raise EnergyDeviceApiError(f"Invalid JSON response: {err}") from err

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
            json_body={
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
            "POST", "/user/idTokens", json_body={"name": name, "token": token}
        )

    async def async_update_id_token(self, name: str, token: str) -> None:
        """Update an ID token's name."""
        await self._request(
            "PATCH", "/user/idTokens", json_body={"name": name, "token": token}
        )

    async def async_delete_id_token(self, token: str) -> None:
        """Delete an ID token."""
        await self._request("DELETE", f"/user/idTokens/{quote(token, safe='')}")
