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
