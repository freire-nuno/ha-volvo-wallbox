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
