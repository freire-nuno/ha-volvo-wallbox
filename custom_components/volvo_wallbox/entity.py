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
