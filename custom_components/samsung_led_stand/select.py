"""Lighting mode select for the Samsung LED stand."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coap import CoapError
from .const import LIGHTING_MODES, MODE_WRITE_VALUE
from .coordinator import SamsungLedStandConfigEntry
from .entity import SamsungLedStandEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SamsungLedStandConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the mode select."""
    data = entry.runtime_data
    async_add_entities([SamsungLedStandModeSelect(data.coordinator, data.device, data.info)])


class SamsungLedStandModeSelect(SamsungLedStandEntity, SelectEntity):
    """Lighting mode (study / night / sleep ...)."""

    _attr_translation_key = "lighting_mode"

    def __init__(self, coordinator, device, info) -> None:
        super().__init__(coordinator, device, info)
        self._attr_unique_id = f"{info.uuid}_lighting_mode"
        self._seen: list[str] = []

    @property
    def options(self) -> list[str]:
        """Known modes plus any other mode the lamp has reported."""
        mode = self.state_data.mode
        if mode and mode not in LIGHTING_MODES and mode not in self._seen:
            self._seen.append(mode)
        return [*LIGHTING_MODES, *self._seen]

    @property
    def current_option(self) -> str | None:
        """Return the active mode."""
        return self.state_data.mode

    async def async_select_option(self, option: str) -> None:
        """Change the lighting mode."""
        try:
            await self._device.async_set_mode(MODE_WRITE_VALUE.get(option, option))
        except CoapError as err:
            raise HomeAssistantError(
                f"LED stand did not accept mode '{option}': {err}"
            ) from err
        await self.coordinator.async_refresh()
