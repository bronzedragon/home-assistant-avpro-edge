"""Config flow for AVPro Edge AC-MX42/82-AUHD matrices."""

from __future__ import annotations

from typing import Any, override

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import callback

from .client import AvproError, AvproMxAuHDClient
from .const import (
    CONF_INPUT_NAMES,
    CONF_MODEL,
    CONF_OUTPUT_NAMES,
    DEFAULT_MODEL,
    DEFAULT_NAME,
    DEFAULT_OUTPUT_NAMES,
    DEFAULT_PORT,
    DOMAIN,
    SUPPORTED_MODELS,
    configured_model,
    configured_names,
    default_input_names,
    input_count_for_model,
)


def _normalized_names(
    user_input: dict[str, Any],
    prefix: str,
    count: int,
    defaults: dict[str, str],
) -> dict[str, str]:
    """Convert form fields into the stored label dictionary."""
    return {
        f"{prefix}_{index}": (
            user_input[f"{prefix}_{index}_name"].strip()
            or defaults[f"{prefix}_{index}"]
        )
        for index in range(1, count + 1)
    }


def _names_are_unique(names: dict[str, str]) -> bool:
    """Return whether labels are unique, ignoring case and surrounding spaces."""
    normalized = [name.strip().casefold() for name in names.values()]
    return len(normalized) == len(set(normalized))


def _labels_schema(
    input_names: dict[str, str], output_names: dict[str, str]
) -> vol.Schema:
    """Build a form schema for the model's input labels and both outputs."""
    fields: dict[Any, Any] = {}
    for index in range(1, len(input_names) + 1):
        key = f"input_{index}"
        fields[vol.Required(f"input_{index}_name", default=input_names[key])] = str
    for index in (1, 2):
        key = f"output_{index}"
        fields[vol.Required(f"output_{index}_name", default=output_names[key])] = str
    return vol.Schema(fields)


class AvproMxConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle an AVPro AC-MX42/82-AUHD config flow."""

    VERSION = 1

    def __init__(self) -> None:
        super().__init__()
        self._setup_data: dict[str, Any] = {}
        self._setup_model = DEFAULT_MODEL
        self._setup_mac = ""

    @staticmethod
    @callback
    @override
    def async_get_options_flow(config_entry: ConfigEntry) -> AvproMxOptionsFlow:
        """Return the model/label options flow."""
        return AvproMxOptionsFlow()

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure connection details and matrix model."""
        errors: dict[str, str] = {}

        if user_input is not None:
            model = user_input[CONF_MODEL]
            host = user_input[CONF_HOST].strip()
            port = user_input[CONF_PORT]
            client = AvproMxAuHDClient(host, port, model=model)
            try:
                mac = await client.test_connection()
            except AvproError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(mac)
                self._abort_if_unique_id_configured()
                self._setup_model = model
                self._setup_mac = mac
                self._setup_data = {
                    CONF_HOST: host,
                    CONF_PORT: port,
                    CONF_NAME: user_input[CONF_NAME].strip(),
                }
                await client.async_close()
                return await self.async_step_labels()
            finally:
                await client.async_close()

        schema = vol.Schema(
            {
                vol.Required(CONF_MODEL, default=DEFAULT_MODEL): vol.In(SUPPORTED_MODELS),
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_labels(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Assign labels for the selected model's inputs and outputs."""
        if not self._setup_data:
            return self.async_abort(reason="setup_incomplete")

        errors: dict[str, str] = {}
        input_defaults = default_input_names(self._setup_model)
        input_count = input_count_for_model(self._setup_model)

        if user_input is not None:
            input_names = _normalized_names(
                user_input, "input", input_count, input_defaults
            )
            output_names = _normalized_names(
                user_input, "output", 2, DEFAULT_OUTPUT_NAMES
            )
            if not _names_are_unique(input_names):
                errors["base"] = "duplicate_input_names"
            elif not _names_are_unique(output_names):
                errors["base"] = "duplicate_output_names"
            else:
                requested_name = self._setup_data.get(CONF_NAME, "")
                title = requested_name or f"AVPro Edge {self._setup_model}"
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_HOST: self._setup_data[CONF_HOST],
                        CONF_PORT: self._setup_data[CONF_PORT],
                        CONF_MODEL: self._setup_model,
                    },
                    options={
                        CONF_INPUT_NAMES: input_names,
                        CONF_OUTPUT_NAMES: output_names,
                    },
                )

        return self.async_show_form(
            step_id="labels",
            data_schema=_labels_schema(input_defaults, DEFAULT_OUTPUT_NAMES),
            errors=errors,
            description_placeholders={"model": self._setup_model},
        )


class AvproMxOptionsFlow(OptionsFlow):
    """Allow model and input/output labels to be changed after setup."""

    def __init__(self) -> None:
        super().__init__()
        self._selected_model: str | None = None

    @override
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the matrix model before editing labels."""
        current_model = configured_model(self.config_entry.data, self.config_entry.options)
        if user_input is not None:
            self._selected_model = user_input[CONF_MODEL]
            return await self.async_step_labels()

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MODEL, default=current_model): vol.In(
                        SUPPORTED_MODELS
                    )
                }
            ),
        )

    async def async_step_labels(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage labels for the selected matrix model."""
        model = self._selected_model or configured_model(
            self.config_entry.data, self.config_entry.options
        )
        input_defaults = default_input_names(model)
        input_count = input_count_for_model(model)
        current_inputs = configured_names(
            self.config_entry.data,
            self.config_entry.options,
            CONF_INPUT_NAMES,
            input_defaults,
        )
        current_outputs = configured_names(
            self.config_entry.data,
            self.config_entry.options,
            CONF_OUTPUT_NAMES,
            DEFAULT_OUTPUT_NAMES,
        )
        errors: dict[str, str] = {}

        if user_input is not None:
            input_names = _normalized_names(
                user_input, "input", input_count, input_defaults
            )
            output_names = _normalized_names(
                user_input, "output", 2, DEFAULT_OUTPUT_NAMES
            )
            if not _names_are_unique(input_names):
                errors["base"] = "duplicate_input_names"
            elif not _names_are_unique(output_names):
                errors["base"] = "duplicate_output_names"
            else:
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_MODEL: model,
                        CONF_INPUT_NAMES: input_names,
                        CONF_OUTPUT_NAMES: output_names,
                    },
                )

        return self.async_show_form(
            step_id="labels",
            data_schema=_labels_schema(current_inputs, current_outputs),
            errors=errors,
            description_placeholders={"model": model},
        )


# Preserve the old class names for internal/backward compatibility.
AvproMx42ConfigFlow = AvproMxConfigFlow
AvproMx42OptionsFlow = AvproMxOptionsFlow
