"""Select entities for AVPro Edge AC-MX42/82-AUHD matrices."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import AvproConfigEntry
from .const import (
    CONF_INPUT_NAMES,
    CONF_OUTPUT_NAMES,
    DEFAULT_OUTPUT_NAMES,
    MODEL_MX82,
    configured_names,
    default_input_names,
)
from .coordinator import AvproCoordinator
from .entity import AvproEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AvproConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up source and advanced MX82 selectors."""
    coordinator = entry.runtime_data
    input_defaults = default_input_names(coordinator.client.model)
    input_names = configured_names(
        entry.data, entry.options, CONF_INPUT_NAMES, input_defaults
    )
    output_names = configured_names(
        entry.data, entry.options, CONF_OUTPUT_NAMES, DEFAULT_OUTPUT_NAMES
    )
    entities: list[SelectEntity] = [
        AvproOutputSelect(
            coordinator,
            entry.unique_id or entry.entry_id,
            entry.title,
            output,
            input_names,
            output_names[f"output_{output}"],
        )
        for output in (1, 2)
    ]
    if coordinator.client.model == MODEL_MX82:
        entities.append(
            AvproAudioBindingSelect(
                coordinator,
                entry.unique_id or entry.entry_id,
                entry.title,
                output_names,
            )
        )
    async_add_entities(entities)


class AvproOutputSelect(AvproEntity, SelectEntity):
    """Route one HDMI output to one of the matrix HDMI inputs."""

    _attr_icon = "mdi:video-input-hdmi"

    def __init__(
        self,
        coordinator: AvproCoordinator,
        entry_id: str,
        device_name: str,
        output: int,
        input_names: dict[str, str],
        output_name: str,
    ) -> None:
        super().__init__(coordinator, entry_id, device_name, f"output_{output}_source")
        self.output = output
        self._source_to_name = {
            index: input_names.get(f"input_{index}", f"Input {index}")
            for index in range(1, coordinator.client.input_count + 1)
        }
        self._name_to_source = {
            name: index for index, name in self._source_to_name.items()
        }
        self._attr_options = list(self._name_to_source)
        self._attr_name = f"{output_name} source"

    @property
    def current_option(self) -> str | None:
        source = self.coordinator.data.output_sources.get(self.output)
        return self._source_to_name.get(source)

    async def async_select_option(self, option: str) -> None:
        source = self._name_to_source[option]
        await self.coordinator.client.set_output_source(self.output, source)
        await self.coordinator.async_request_refresh()


class AvproAudioBindingSelect(AvproEntity, SelectEntity):
    """Select which MX82 HDMI output the extracted audio follows."""

    _attr_icon = "mdi:audio-input-stereo-minijack"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: AvproCoordinator,
        entry_id: str,
        device_name: str,
        output_names: dict[str, str],
    ) -> None:
        super().__init__(coordinator, entry_id, device_name, "audio_binding")
        self._output_to_name = {
            1: output_names["output_1"],
            2: output_names["output_2"],
        }
        self._name_to_output = {name: number for number, name in self._output_to_name.items()}
        self._attr_options = list(self._name_to_output)
        self._attr_name = "Extracted audio follows"

    @property
    def current_option(self) -> str | None:
        return self._output_to_name.get(self.coordinator.data.audio_binding)

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.audio_binding is not None

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.client.set_audio_binding(self._name_to_output[option])
        await self.coordinator.async_request_refresh()
