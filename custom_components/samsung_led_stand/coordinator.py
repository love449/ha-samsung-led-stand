"""Polling coordinator for the Samsung LED stand."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .coap import CoapError, SamsungLedStand, StandInfo, StandState
from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

type SamsungLedStandConfigEntry = ConfigEntry[SamsungLedStandData]


@dataclass
class SamsungLedStandData:
    """Runtime data stored on the config entry."""

    device: SamsungLedStand
    info: StandInfo
    coordinator: SamsungLedStandCoordinator


class SamsungLedStandCoordinator(DataUpdateCoordinator[StandState]):
    """Read the lamp state every few seconds (local, no cloud)."""

    config_entry: SamsungLedStandConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: SamsungLedStandConfigEntry,
        device: SamsungLedStand,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.device = device

    async def _async_update_data(self) -> StandState:
        try:
            return await self.device.async_get_state()
        except CoapError as err:
            raise UpdateFailed(f"Cannot reach LED stand {self.device.host}: {err}") from err
