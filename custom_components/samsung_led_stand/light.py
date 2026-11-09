"""Light platform for the Samsung LED stand."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util.color import brightness_to_value, value_to_brightness

from .coap import CoapError
from .coordinator import SamsungLedStandConfigEntry
from .entity import SamsungLedStandEntity

# The lamp reports/accepts 1-100 (percent).
PERCENT_RANGE = (1, 100)

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SamsungLedStandConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the lamp."""
    data = entry.runtime_data
    async_add_entities([SamsungLedStandLight(data.coordinator, data.device, data.info)])


class SamsungLedStandLight(SamsungLedStandEntity, LightEntity):
    """On/off and brightness of the LED stand."""

    _attr_name = None
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(self, coordinator, device, info) -> None:
        super().__init__(coordinator, device, info)
        self._attr_unique_id = f"{info.uuid}_light"

    @property
    def is_on(self) -> bool:
        """Return true if the lamp is on."""
        return self.state_data.power

    @property
    def brightness(self) -> int | None:
        """Return brightness 1-255."""
        percent = self.state_data.brightness
        if percent is None:
            return None
        return value_to_brightness(PERCENT_RANGE, max(1, min(100, percent)))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on, optionally setting brightness."""
        try:
            await self._device.async_set_power(True)
            if ATTR_BRIGHTNESS in kwargs:
                await self._device.async_set_brightness(
                    round(brightness_to_value(PERCENT_RANGE, kwargs[ATTR_BRIGHTNESS]))
                )
        except CoapError as err:
            raise HomeAssistantError(f"Cannot control LED stand: {err}") from err
        await self.coordinator.async_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off."""
        try:
            await self._device.async_set_power(False)
        except CoapError as err:
            raise HomeAssistantError(f"Cannot control LED stand: {err}") from err
        await self.coordinator.async_refresh()
