"""Media-player views of AVPro HDMI outputs."""

from __future__ import annotations

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import AvproConfigEntry
from .const import (
    CONF_INPUT_NAMES,
    CONF_OUTPUT_NAMES,
    DEFAULT_OUTPUT_NAMES,
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
    """Expose each matrix output as a source-selecting media player."""
    coordinator = entry.runtime_data
    input_names = configured_names(
        entry.data,
        entry.options,
        CONF_INPUT_NAMES,
        default_input_names(coordinator.client.model),
    )
    output_names = configured_names(
        entry.data, entry.options, CONF_OUTPUT_NAMES, DEFAULT_OUTPUT_NAMES
    )
    async_add_entities(
        AvproOutputMediaPlayer(
            coordinator,
            entry.unique_id or entry.entry_id,
            entry.title,
            output,
            input_names,
            output_names[f"output_{output}"],
        )
        for output in (1, 2)
    )


class AvproOutputMediaPlayer(AvproEntity, MediaPlayerEntity):
    """Media-player facade for one routed HDMI output."""

    _attr_device_class = MediaPlayerDeviceClass.RECEIVER
    _attr_supported_features = (
        MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.SELECT_SOURCE
    )
    _attr_icon = "mdi:hdmi-port"

    def __init__(
        self,
        coordinator: AvproCoordinator,
        entry_id: str,
        device_name: str,
        output: int,
        input_names: dict[str, str],
        output_name: str,
    ) -> None:
        super().__init__(coordinator, entry_id, device_name, f"output_{output}_media")
        self.output = output
        self._source_to_name = {
            index: input_names.get(f"input_{index}", f"Input {index}")
            for index in range(1, coordinator.client.input_count + 1)
        }
        self._name_to_source = {name: index for index, name in self._source_to_name.items()}
        self._attr_source_list = list(self._name_to_source)
        self._attr_name = output_name

    @property
    def state(self) -> MediaPlayerState:
        return (
            MediaPlayerState.ON
            if self.coordinator.data.output_streams[self.output]
            else MediaPlayerState.OFF
        )

    @property
    def source(self) -> str | None:
        return self._source_to_name.get(self.coordinator.data.output_sources.get(self.output))

    async def async_turn_on(self) -> None:
        await self.coordinator.client.set_output_stream(self.output, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        await self.coordinator.client.set_output_stream(self.output, False)
        await self.coordinator.async_request_refresh()

    async def async_select_source(self, source: str) -> None:
        await self.coordinator.client.set_output_source(
            self.output, self._name_to_source[source]
        )
        await self.coordinator.async_request_refresh()
