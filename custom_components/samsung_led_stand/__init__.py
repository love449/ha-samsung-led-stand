"""Samsung SmartThings LED Stand, controlled locally (no SmartThings cloud)."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .coap import CoapError, SamsungLedStand
from .coordinator import (
    SamsungLedStandConfigEntry,
    SamsungLedStandCoordinator,
    SamsungLedStandData,
)

PLATFORMS: list[Platform] = [Platform.LIGHT, Platform.SELECT]


async def async_setup_entry(
    hass: HomeAssistant, entry: SamsungLedStandConfigEntry
) -> bool:
    """Set up the LED stand from a config entry."""
    device = SamsungLedStand(entry.data[CONF_HOST])
    try:
        info = await device.async_get_info()
    except CoapError as err:
        raise ConfigEntryNotReady(
            f"Cannot reach LED stand {device.host}: {err}"
        ) from err

    coordinator = SamsungLedStandCoordinator(hass, entry, device)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = SamsungLedStandData(
        device=device, info=info, coordinator=coordinator
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: SamsungLedStandConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
