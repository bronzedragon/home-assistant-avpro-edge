"""AVPro Edge AC-MX42/82-AUHD integration."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .client import AvproError, AvproMxAuHDClient
from .const import (
    ATTR_COMMAND,
    ATTR_CONFIG_ENTRY_ID,
    DEFAULT_PORT,
    DOMAIN,
    PLATFORMS,
    SERVICE_SEND_COMMAND,
    configured_model,
)
from .coordinator import AvproCoordinator

_LOGGER = logging.getLogger(__name__)

AvproConfigEntry = ConfigEntry[AvproCoordinator]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def _async_update_listener(hass: HomeAssistant, entry: AvproConfigEntry) -> None:
    """Reload the matrix when editable model/labels change."""
    await hass.config_entries.async_reload(entry.entry_id)


SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_COMMAND): cv.string,
    }
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up integration-wide actions."""

    async def async_send_command(call: ServiceCall) -> None:
        entry_id = call.data[ATTR_CONFIG_ENTRY_ID]
        command = call.data[ATTR_COMMAND].strip()

        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN or entry.runtime_data is None:
            raise HomeAssistantError(
                f"No loaded AVPro AC-MX42/82-AUHD config entry named {entry_id!r}"
            )
        coordinator: AvproCoordinator = entry.runtime_data

        if not command or "\r" in command or "\n" in command:
            raise HomeAssistantError("Command must be one non-empty ASCII command")
        try:
            command.encode("ascii")
        except UnicodeEncodeError as err:
            raise HomeAssistantError("Command must contain ASCII characters only") from err

        try:
            response = await coordinator.client.command(command)
        except AvproError as err:
            raise HomeAssistantError(str(err)) from err

        _LOGGER.info("AVPro raw command %r response: %r", command, response)
        await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_COMMAND,
        async_send_command,
        schema=SERVICE_SCHEMA,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: AvproConfigEntry) -> bool:
    """Set up one matrix from a config entry."""
    model = configured_model(entry.data, entry.options)
    client = AvproMxAuHDClient(
        host=entry.data[CONF_HOST],
        port=entry.data.get(CONF_PORT, DEFAULT_PORT),
        model=model,
    )
    coordinator = AvproCoordinator(hass, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AvproConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded and entry.runtime_data is not None:
        await entry.runtime_data.client.async_close()
    return unloaded
