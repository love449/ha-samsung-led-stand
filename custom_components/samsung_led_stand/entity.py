"""Base entity for the Samsung LED stand."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coap import SamsungLedStand, StandInfo, StandState
from .const import DOMAIN
from .coordinator import SamsungLedStandCoordinator


class SamsungLedStandEntity(CoordinatorEntity[SamsungLedStandCoordinator]):
    """Common behaviour of all LED stand entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SamsungLedStandCoordinator,
        device: SamsungLedStand,
        info: StandInfo,
    ) -> None:
        super().__init__(coordinator)
        self._device = device
        self._info = info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, info.uuid)},
            name=info.name,
            manufacturer="Samsung",
            model="SmartThings LED Stand",
            configuration_url=None,
        )

    @property
    def state_data(self) -> StandState:
        """Return the latest polled state."""
        return self.coordinator.data
