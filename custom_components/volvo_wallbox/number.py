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

    @property
    def available(self) -> bool:
        """Return if the number is available.

        CoordinatorEntity.available only checks coordinator success; this
        also honors the optimistic unavailability set after an unsupported
        operation.
        """
        return super().available and self._attr_available

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
