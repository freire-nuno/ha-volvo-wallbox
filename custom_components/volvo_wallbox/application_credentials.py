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
