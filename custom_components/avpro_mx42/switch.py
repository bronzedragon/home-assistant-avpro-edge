"""Switch entities for AVPro Edge AC-MX42/82-AUHD."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import AvproConfigEntry
from .const import (
    CONF_OUTPUT_NAMES,
    DEFAULT_OUTPUT_NAMES,
    MODEL_MX82,
    configured_names,
)
from .coordinator import AvproCoordinator
from .entity import AvproEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AvproConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up output and advanced MX82 controls."""
    coordinator = entry.runtime_data
    device_id = entry.unique_id or entry.entry_id
    output_names = configured_names(
        entry.data, entry.options, CONF_OUTPUT_NAMES, DEFAULT_OUTPUT_NAMES
    )
    entities: list[SwitchEntity] = []

    for output in (1, 2):
        output_name = output_names[f"output_{output}"]
        entities.append(
            AvproOutputStreamSwitch(
                coordinator, device_id, entry.title, output, output_name
            )
        )
        entities.append(
            AvproAutoSwitch(
                coordinator, device_id, entry.title, output, output_name
            )
        )

    entities.append(
        AvproScalerSwitch(
            coordinator, device_id, entry.title, output_names["output_1"]
        )
    )

    if coordinator.client.model == MODEL_MX82:
        entities.append(AvproAvrMirrorSwitch(coordinator, device_id, entry.title))
        entities.append(AvproExtractedAudioSwitch(coordinator, device_id, entry.title))
        for output in (1, 2):
            entities.append(
                AvproHdmiAudioMuteSwitch(
                    coordinator,
                    device_id,
                    entry.title,
                    output,
                    output_names[f"output_{output}"],
                )
            )

    async_add_entities(entities)


class _AvproWritableSwitch(AvproEntity, SwitchEntity):
    async def _set_and_refresh(self, setter: Callable[[], Awaitable[None]]) -> None:
        await setter()
        await self.coordinator.async_request_refresh()


class AvproOutputStreamSwitch(_AvproWritableSwitch):
    """Enable or disable an HDMI output stream."""

    _attr_icon = "mdi:monitor"

    def __init__(
        self,
        coordinator: AvproCoordinator,
        entry_id: str,
        device_name: str,
        output: int,
        output_name: str,
    ) -> None:
        super().__init__(coordinator, entry_id, device_name, f"output_{output}_stream")
        self.output = output
        self._attr_name = f"{output_name} video"

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.output_streams[self.output]

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set_and_refresh(
            lambda: self.coordinator.client.set_output_stream(self.output, True)
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set_and_refresh(
            lambda: self.coordinator.client.set_output_stream(self.output, False)
        )


class AvproAutoSwitch(_AvproWritableSwitch):
    """Enable or disable hot-plug auto-switching for an output."""

    _attr_icon = "mdi:auto-fix"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: AvproCoordinator,
        entry_id: str,
        device_name: str,
        output: int,
        output_name: str,
    ) -> None:
        super().__init__(coordinator, entry_id, device_name, f"output_{output}_auto")
        self.output = output
        self._attr_name = f"{output_name} auto-switch"

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.auto_switch[self.output]

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set_and_refresh(
            lambda: self.coordinator.client.set_auto_switch(self.output, True)
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set_and_refresh(
            lambda: self.coordinator.client.set_auto_switch(self.output, False)
        )


class AvproScalerSwitch(_AvproWritableSwitch):
    """Control Output 1 4K-to-2K/1080p scaling."""

    _attr_icon = "mdi:resize"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: AvproCoordinator,
        entry_id: str,
        device_name: str,
        output_name: str,
    ) -> None:
        super().__init__(coordinator, entry_id, device_name, "output_1_scaler")
        self._attr_name = f"{output_name} 4K-to-2K scaler"

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.output1_scaler

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set_and_refresh(
            lambda: self.coordinator.client.set_output1_scaler(True)
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set_and_refresh(
            lambda: self.coordinator.client.set_output1_scaler(False)
        )


class AvproAvrMirrorSwitch(_AvproWritableSwitch):
    """Control the MX82 double-switch/AVR mirror mode."""

    _attr_icon = "mdi:call-split"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_name = "AVR mirror mode"

    def __init__(self, coordinator, entry_id, device_name) -> None:
        super().__init__(coordinator, entry_id, device_name, "avr_mirror")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.avr_mirror

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.avr_mirror is not None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set_and_refresh(lambda: self.coordinator.client.set_avr_mirror(True))

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set_and_refresh(lambda: self.coordinator.client.set_avr_mirror(False))


class AvproExtractedAudioSwitch(_AvproWritableSwitch):
    """Enable/mute the MX82 Toslink and analog extracted-audio outputs."""

    _attr_icon = "mdi:audio-input-stereo-minijack"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_name = "Extracted audio"

    def __init__(self, coordinator, entry_id, device_name) -> None:
        super().__init__(coordinator, entry_id, device_name, "extracted_audio")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.extracted_audio

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.extracted_audio is not None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set_and_refresh(
            lambda: self.coordinator.client.set_extracted_audio(True)
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set_and_refresh(
            lambda: self.coordinator.client.set_extracted_audio(False)
        )


class AvproHdmiAudioMuteSwitch(_AvproWritableSwitch):
    """Mute audio embedded in one MX82 HDMI output."""

    _attr_icon = "mdi:volume-mute"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: AvproCoordinator,
        entry_id: str,
        device_name: str,
        output: int,
        output_name: str,
    ) -> None:
        super().__init__(coordinator, entry_id, device_name, f"output_{output}_audio_mute")
        self.output = output
        self._attr_name = f"{output_name} HDMI audio mute"

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.hdmi_audio_muted.get(self.output)

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.coordinator.data.hdmi_audio_muted.get(self.output) is not None
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set_and_refresh(
            lambda: self.coordinator.client.set_hdmi_audio_mute(self.output, True)
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set_and_refresh(
            lambda: self.coordinator.client.set_hdmi_audio_mute(self.output, False)
        )
