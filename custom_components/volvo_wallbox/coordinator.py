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
    energy_this_year: float


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
        """Fetch wallbox state and this year's sessions."""
        now = dt_util.now()
        year_start = dt_util.start_of_local_day(now.replace(month=1, day=1))
        month_start = dt_util.start_of_local_day(now.replace(day=1))
        today_start = dt_util.start_of_local_day(now)

        try:
            state = await self.api.async_get_wallbox_state(self.wallbox_id)
            sessions = await self.api.async_get_charging_sessions(
                self.wallbox_id, year_start, now
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
            energy_this_year=energy_since(sessions, year_start),
        )
