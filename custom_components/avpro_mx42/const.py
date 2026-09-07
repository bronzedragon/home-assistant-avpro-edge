"""Constants for AVPro Edge AC-MX42/82-AUHD integrations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

DOMAIN = "avpro_mx42"  # Kept for backward compatibility with v0.1/v0.2 installs.

CONF_MODEL = "model"
CONF_INPUT_NAMES = "input_names"
CONF_OUTPUT_NAMES = "output_names"

MODEL_MX42 = "AC-MX42-AUHD"
MODEL_MX82 = "AC-MX82-AUHD"
SUPPORTED_MODELS = (MODEL_MX42, MODEL_MX82)
MODEL_INPUT_COUNTS = {
    MODEL_MX42: 4,
    MODEL_MX82: 8,
}
DEFAULT_MODEL = MODEL_MX42
DEFAULT_NAME = ""
DEFAULT_PORT = 23
DEFAULT_TIMEOUT = 3.0
DEFAULT_SCAN_INTERVAL = 15

# Existing platform/entity IDs are preserved; media_player is additive in v0.4.
PLATFORMS = ["select", "switch", "media_player"]

SERVICE_SEND_COMMAND = "send_command"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_COMMAND = "command"

DEFAULT_OUTPUT_NAMES = {
    "output_1": "Output 1",
    "output_2": "Output 2",
}


def configured_model(data: Mapping[str, Any], options: Mapping[str, Any]) -> str:
    """Return configured model, preserving old v0.2 entries as MX42 devices."""
    for source in (options, data):
        value = source.get(CONF_MODEL)
        if value in SUPPORTED_MODELS:
            return value
    return DEFAULT_MODEL


def input_count_for_model(model: str) -> int:
    """Return the number of HDMI inputs for a supported model."""
    return MODEL_INPUT_COUNTS.get(model, MODEL_INPUT_COUNTS[DEFAULT_MODEL])


def default_input_names(model: str) -> dict[str, str]:
    """Build default input labels for the selected matrix model."""
    return {
        f"input_{index}": f"Input {index}"
        for index in range(1, input_count_for_model(model) + 1)
    }


def configured_names(
    data: Mapping[str, Any],
    options: Mapping[str, Any],
    key: str,
    defaults: Mapping[str, str],
) -> dict[str, str]:
    """Return labels from options, with legacy data and defaults as fallbacks."""
    result = dict(defaults)
    for source in (data.get(key), options.get(key)):
        if not isinstance(source, Mapping):
            continue
        for item_key in defaults:
            value = source.get(item_key)
            if isinstance(value, str) and value.strip():
                result[item_key] = value.strip()
    return result
