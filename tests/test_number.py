"""Tests for the Volvo Wallbox numbers."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.volvo_wallbox.api import WallboxOperationError

from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE, Platform
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
