"""Diagnostics for AVPro Edge AC-MX42/82-AUHD."""

from __future__ import annotations

from dataclasses import asdict

from homeassistant.core import HomeAssistant

from . import AvproConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: AvproConfigEntry
) -> dict:
    """Return diagnostics without exposing unnecessary network details."""
    coordinator = entry.runtime_data
    return {
        "entry_title": entry.title,
        "device_identifier": entry.unique_id,
        "model": coordinator.client.model,
        "input_count": coordinator.client.input_count,
        "port": coordinator.client.port,
        "last_update_success": coordinator.last_update_success,
        "telnet_banner": coordinator.client.banner or None,
        "last_command": coordinator.client.last_command or None,
        "last_response": coordinator.client.last_response or None,
        "state": asdict(coordinator.data) if coordinator.data else None,
    }
