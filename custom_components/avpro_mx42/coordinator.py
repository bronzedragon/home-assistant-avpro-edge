"""Data coordinator for the AVPro Edge AC-MX42/82-AUHD integration."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import AvproError, AvproMxAuHDClient, MatrixState
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class AvproCoordinator(DataUpdateCoordinator[MatrixState]):
    """Poll and control an AVPro matrix."""

    def __init__(self, hass: HomeAssistant, client: AvproMxAuHDClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.client = client

    async def _async_update_data(self) -> MatrixState:
        try:
            return await self.client.get_state()
        except AvproError as err:
            raise UpdateFailed(str(err)) from err
