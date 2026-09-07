"""Base entities for AVPro Edge AC-MX42/82-AUHD matrices."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AvproCoordinator


class AvproEntity(CoordinatorEntity[AvproCoordinator]):
    """Base AVPro entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AvproCoordinator,
        device_identifier: str,
        device_name: str,
        unique_suffix: str,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{device_identifier}_{unique_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_identifier)},
            name=device_name,
            manufacturer="AVPro Edge",
            model=coordinator.client.model,
            configuration_url=f"http://{coordinator.client.host}",
        )
