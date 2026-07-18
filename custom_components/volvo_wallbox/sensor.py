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
        device_class=SensorDeviceClass.ENUM,
        options=["charging", "idle"],
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
        key="energy_this_year",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=lambda data: data.energy_this_year,
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
