"""Tests for the Volvo Wallbox buttons."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.volvo_wallbox.api import WallboxOperationError

from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

WALLBOX_ID = "WB123"


@pytest.fixture(autouse=True)
def _controls_only_platform() -> Generator[None]:
    """Load only this task's platforms; sensor lands in a parallel task."""
    with patch("custom_components.volvo_wallbox.PLATFORMS", [Platform.BUTTON, Platform.NUMBER]):
        yield


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
