"""Async TCP/Telnet client for AVPro Edge AC-MX42/82-AUHD matrices."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Final

from .const import DEFAULT_MODEL, MODEL_MX42, MODEL_MX82, input_count_for_model

_LOGGER = logging.getLogger(__name__)


class AvproError(Exception):
    """Base error for the AVPro client."""


class AvproConnectionError(AvproError):
    """Raised when the matrix cannot be reached."""


class AvproProtocolError(AvproError):
    """Raised when a response cannot be interpreted."""


@dataclass(slots=True)
class MatrixState:
    """State exposed by the matrix."""

    output_sources: dict[int, int]
    output_streams: dict[int, bool]
    auto_switch: dict[int, bool]
    output1_scaler: bool
    audio_binding: int | None = None
    avr_mirror: bool | None = None
    extracted_audio: bool | None = None
    hdmi_audio_muted: dict[int, bool | None] = field(default_factory=dict)


_MAX_RESPONSE_BYTES: Final = 16384
_BANNER_FIRST_BYTE_TIMEOUT: Final = 0.75
_RESPONSE_FIRST_BYTE_TIMEOUT: Final = 1.25
_RESPONSE_IDLE_TIMEOUT: Final = 0.18

# Telnet protocol bytes.
_IAC: Final = 255
_DONT: Final = 254
_DO: Final = 253
_WONT: Final = 252
_WILL: Final = 251
_SB: Final = 250
_SE: Final = 240


class AvproMxAuHDClient:
    """Talk to an AC-MX42/82-AUHD using its TCP ASCII/Telnet interface."""

    def __init__(
        self,
        host: str,
        port: int = 23,
        timeout: float = 3.0,
        model: str = DEFAULT_MODEL,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.model = model
        self.input_count = input_count_for_model(model)
        self._lock = asyncio.Lock()
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._telnet_pending = bytearray()
        self.banner: str = ""
        self.last_command: str = ""
        self.last_response: str = ""

    async def async_close(self) -> None:
        """Close the persistent Telnet session."""
        writer = self._writer
        self._reader = None
        self._writer = None
        self._telnet_pending.clear()
        if writer is None:
            return
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            pass

    async def _async_connect(self) -> None:
        """Open a session and consume the legacy firmware startup banner."""
        await self.async_close()
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self.timeout,
            )
        except (TimeoutError, OSError) as err:
            raise AvproConnectionError(
                f"Unable to connect to {self.host}:{self.port}: {err}"
            ) from err

        try:
            banner_bytes = await self._async_read_response(
                first_byte_timeout=_BANNER_FIRST_BYTE_TIMEOUT,
                allow_empty=True,
            )
        except AvproConnectionError:
            await self.async_close()
            raise

        self.banner = banner_bytes.decode("ascii", errors="replace").strip()
        if self.banner:
            _LOGGER.debug("AVPro Telnet banner from %s: %r", self.host, self.banner)

    async def _async_ensure_connected(self) -> None:
        if (
            self._reader is None
            or self._writer is None
            or self._writer.is_closing()
            or self._reader.at_eof()
        ):
            await self._async_connect()

    async def command(self, command: str) -> str:
        """Send one command over a persistent Telnet-style session."""
        cleaned = command.strip().replace("\r", "").replace("\n", "")
        if not cleaned:
            raise ValueError("Command must not be empty")
        try:
            encoded = cleaned.encode("ascii")
        except UnicodeEncodeError as err:
            raise ValueError("Command must contain ASCII characters only") from err

        async with self._lock:
            # Retry once because the embedded controller can close idle Telnet sessions.
            for attempt in range(2):
                await self._async_ensure_connected()
                assert self._writer is not None

                try:
                    # AC-MX42 F/W 1.xx is proven to require/welcome a leading empty
                    # line. The AC-MX82 manual specifies a command followed by Return,
                    # so use normal CRLF framing there.
                    prefix = b"\r\n" if self.model == MODEL_MX42 else b""
                    self._writer.write(prefix + encoded + b"\r\n")
                    await asyncio.wait_for(self._writer.drain(), timeout=self.timeout)
                    response_bytes = await self._async_read_response(
                        first_byte_timeout=_RESPONSE_FIRST_BYTE_TIMEOUT,
                        allow_empty=True,
                    )
                    response = response_bytes.decode(
                        "ascii", errors="replace"
                    ).strip(" \t\r\n\x00")
                    if not response and self._reader is not None and self._reader.at_eof():
                        await self.async_close()
                        if attempt == 0:
                            continue
                    self.last_command = cleaned
                    self.last_response = response
                    _LOGGER.debug("AVPro command %r response: %r", cleaned, response)
                    return response
                except (TimeoutError, OSError, AvproConnectionError) as err:
                    await self.async_close()
                    if attempt == 0:
                        continue
                    raise AvproConnectionError(
                        f"Communication with {self.host}:{self.port} failed: {err}"
                    ) from err

        raise AvproConnectionError(f"Communication with {self.host}:{self.port} failed")

    async def _async_read_response(
        self,
        *,
        first_byte_timeout: float,
        allow_empty: bool,
    ) -> bytes:
        """Read payload until the connection goes briefly idle."""
        reader = self._reader
        writer = self._writer
        if reader is None or writer is None:
            raise AvproConnectionError("Telnet session is not connected")

        chunks: list[bytes] = []
        total = 0
        timeout = first_byte_timeout
        received_payload = False

        while total < _MAX_RESPONSE_BYTES:
            try:
                raw = await asyncio.wait_for(
                    reader.read(min(4096, _MAX_RESPONSE_BYTES - total)),
                    timeout=timeout,
                )
            except TimeoutError:
                if chunks or allow_empty:
                    break
                raise AvproConnectionError("Timed out waiting for a matrix response")

            if not raw:
                break

            payload, negotiation_reply = self._consume_telnet(raw)
            if negotiation_reply:
                writer.write(negotiation_reply)
                try:
                    await asyncio.wait_for(writer.drain(), timeout=self.timeout)
                except (TimeoutError, OSError) as err:
                    raise AvproConnectionError(
                        f"Telnet negotiation with {self.host}:{self.port} failed: {err}"
                    ) from err

            if payload:
                chunks.append(payload)
                total += len(payload)
                received_payload = True

            # Telnet negotiation may arrive before the banner or command reply.
            # Only switch to the short idle timeout after actual text arrives.
            if received_payload:
                timeout = _RESPONSE_IDLE_TIMEOUT

        return b"".join(chunks)

    def _consume_telnet(self, raw: bytes) -> tuple[bytes, bytes]:
        """Remove Telnet control sequences and reject unsupported options."""
        data = bytes(self._telnet_pending) + raw
        payload = bytearray()
        reply = bytearray()
        index = 0

        while index < len(data):
            if data[index] != _IAC:
                payload.append(data[index])
                index += 1
                continue

            if index + 1 >= len(data):
                break
            command = data[index + 1]

            if command == _IAC:
                payload.append(_IAC)
                index += 2
                continue

            if command in (_WILL, _WONT, _DO, _DONT):
                if index + 2 >= len(data):
                    break
                option = data[index + 2]
                if command == _WILL:
                    reply.extend((_IAC, _DONT, option))
                elif command == _DO:
                    reply.extend((_IAC, _WONT, option))
                index += 3
                continue

            if command == _SB:
                end = data.find(bytes((_IAC, _SE)), index + 2)
                if end == -1:
                    break
                index = end + 2
                continue

            # Other two-byte Telnet commands are ignored.
            index += 2

        self._telnet_pending = bytearray(data[index:])
        return bytes(payload), bytes(reply)

    async def test_connection(self) -> str:
        """Verify the matrix and return its stable MAC address."""
        mac = await self.get_mac()
        response = await self.command("GET OUT1 VS")
        source = self.parse_output_source(response, 1)
        self._validate_source_for_device(source)
        return mac

    async def get_mac(self) -> str:
        """Return the matrix MAC address normalized as 12 lowercase hex digits."""
        return self.parse_mac(await self.command("GET MAC"))

    async def get_state(self) -> MatrixState:
        """Fetch the state needed by Home Assistant entities."""
        out1_source = self.parse_output_source(await self.command("GET OUT1 VS"), 1)
        out2_source = self.parse_output_source(await self.command("GET OUT2 VS"), 2)
        self._validate_source_for_device(out1_source)
        self._validate_source_for_device(out2_source)
        out1_stream = self.parse_enabled(await self.command("GET OUT1 STREAM"))
        out2_stream = self.parse_enabled(await self.command("GET OUT2 STREAM"))
        auto1 = self.parse_enabled(await self.command("GET HD1 AUTO"))
        auto2 = self.parse_enabled(await self.command("GET HD2 AUTO"))
        scaler = self.parse_scaler(await self.command("GET OUT1 VIDEO"))

        audio_binding: int | None = None
        avr_mirror: bool | None = None
        extracted_audio: bool | None = None
        hdmi_audio_muted: dict[int, bool | None] = {}
        if self.model == MODEL_MX82:
            audio_binding = await self._optional_status(
                "GET EXA BTV OUT", self.parse_audio_binding
            )
            avr_mirror = await self._optional_status(
                "GET SWITCH MODE", self.parse_switch_mode
            )
            extracted_audio = await self._optional_status(
                "GET OUT0 EXA", self.parse_enabled
            )
            for output in (1, 2):
                hdmi_audio_muted[output] = await self._optional_status(
                    f"GET OUT{output} HA MUTE", self.parse_enabled
                )

        return MatrixState(
            output_sources={1: out1_source, 2: out2_source},
            output_streams={1: out1_stream, 2: out2_stream},
            auto_switch={1: auto1, 2: auto2},
            output1_scaler=scaler,
            audio_binding=audio_binding,
            avr_mirror=avr_mirror,
            extracted_audio=extracted_audio,
            hdmi_audio_muted=hdmi_audio_muted,
        )

    async def _optional_status(self, command: str, parser):
        """Read an advanced MX82 state without taking core routing offline."""
        try:
            return parser(await self.command(command))
        except (AvproError, ValueError) as err:
            _LOGGER.debug("Optional AVPro status %r was unavailable: %s", command, err)
            return None

    async def set_output_source(self, output: int, source: int) -> None:
        self._validate_output(output)
        if source not in range(1, self.input_count + 1):
            raise ValueError(f"Source must be between 1 and {self.input_count}")
        await self.command(f"SET OUT{output} VS IN{source}")

    async def set_output_stream(self, output: int, enabled: bool) -> None:
        self._validate_output(output)
        await self.command(f"SET OUT{output} STREAM {'ON' if enabled else 'OFF'}")

    async def set_auto_switch(self, output: int, enabled: bool) -> None:
        self._validate_output(output)
        await self.command(f"SET HD{output} AUTO {'EN' if enabled else 'DIS'}")

    async def set_output1_scaler(self, enabled: bool) -> None:
        # Firmware command value 1 is bypass; 2 enables 4K-to-2K/1080p scaling.
        await self.command(f"SET OUT1 VIDEO{2 if enabled else 1}")

    async def set_audio_binding(self, output: int) -> None:
        """Bind the MX82 extracted analog/Toslink audio to Output 1 or 2."""
        self._require_mx82()
        self._validate_output(output)
        await self.command(f"SET EXA BTV OUT{output}")

    async def set_avr_mirror(self, enabled: bool) -> None:
        """Enable MX82 double-switch/AVR mirror mode."""
        self._require_mx82()
        await self.command(f"SET SWITCH MODE{1 if enabled else 0}")

    async def set_extracted_audio(self, enabled: bool) -> None:
        """Enable or mute the MX82 extracted audio outputs."""
        self._require_mx82()
        await self.command(f"SET OUT0 EXA {'EN' if enabled else 'DIS'}")

    async def set_hdmi_audio_mute(self, output: int, muted: bool) -> None:
        """Mute/unmute audio embedded in one MX82 HDMI output."""
        self._require_mx82()
        self._validate_output(output)
        await self.command(f"SET OUT{output} HA MUTE {'ON' if muted else 'OFF'}")

    def _require_mx82(self) -> None:
        if self.model != MODEL_MX82:
            raise ValueError(f"This control is only exposed for {MODEL_MX82}")

    def _validate_source_for_device(self, source: int) -> None:
        if source not in range(1, self.input_count + 1):
            raise AvproProtocolError(
                f"Matrix reported input {source}, but {self.model} supports "
                f"inputs 1-{self.input_count}"
            )

    @staticmethod
    def _validate_output(output: int) -> None:
        if output not in (1, 2):
            raise ValueError("Output must be 1 or 2")

    @staticmethod
    def _normalize(response: str) -> str:
        return " ".join(response.upper().replace("\x00", " ").split())

    @classmethod
    def parse_mac(cls, response: str) -> str:
        """Extract and normalize a MAC address from a GET MAC response."""
        normalized = cls._normalize(response)
        separated = re.findall(
            r"(?:^|\bMAC\b|\s)((?:[0-9A-F]{2}[\s:.\-]){5}[0-9A-F]{2})(?:\s|$)",
            normalized,
        )
        if separated:
            compact = re.sub(r"[^0-9A-F]", "", separated[-1])
            if len(compact) == 12:
                return compact.lower()

        compact_matches = re.findall(r"(?<![0-9A-F])([0-9A-F]{12})(?![0-9A-F])", normalized)
        if compact_matches:
            return compact_matches[-1].lower()

        raise AvproProtocolError(f"Could not determine MAC address: {response!r}")

    @classmethod
    def parse_output_source(cls, response: str, output: int) -> int:
        """Extract an input number from legacy and current routing replies."""
        normalized = cls._normalize(response)
        patterns = (
            rf"OUT\s*{output}\D+IN\s*([1-8])",
            rf"OUT\s*{output}\s+(?:V?S|VIDEO\s+SOURCE|SOURCE|ROUTE)\s*(?:=|:)?\s*(?:IN\s*)?([1-8])",
            rf"OUTPUT\s*{output}\D+INPUT\s*([1-8])",
            r"(?:^|\s)IN\s*([1-8])(?:\s|$)",
        )
        for pattern in patterns:
            matches = re.findall(pattern, normalized)
            if matches:
                return int(matches[-1])

        # Some early controllers echo the command and answer with only INx or x
        # on the following line. Parse only a complete line so banner versions such
        # as "F/W Version : 1.72" cannot be mistaken for an input number.
        for line in reversed(response.replace("\x00", "").splitlines()):
            match = re.fullmatch(r"\s*(?:IN\s*)?([1-8])\s*", line, re.IGNORECASE)
            if match:
                return int(match.group(1))

        raise AvproProtocolError(
            f"Could not determine Output {output} source from response: {response!r}"
        )

    @classmethod
    def parse_audio_binding(cls, response: str) -> int:
        """Return which HDMI output the extracted audio follows."""
        normalized = cls._normalize(response)
        matches = re.findall(r"\bOUT\s*([12])\b", normalized)
        if matches:
            return int(matches[-1])
        matches = re.findall(r"(?:BTV|BIND|BINDING)\D*([12])(?:\s|$)", normalized)
        if matches:
            return int(matches[-1])
        raise AvproProtocolError(
            f"Could not determine extracted-audio binding: {response!r}"
        )

    @classmethod
    def parse_switch_mode(cls, response: str) -> bool:
        """Return True for double-switch/AVR mirror mode, False for independent."""
        normalized = cls._normalize(response)
        if re.search(r"\b(DOUBLE|MIRROR(?:ED)?)\b", normalized):
            return True
        if re.search(r"\b(SINGLE|INDEPENDENT)\b", normalized):
            return False
        matches = re.findall(r"\bMODE\s*([01])\b", normalized)
        if matches:
            return matches[-1] == "1"
        # Some firmware responds with a bare 0/1 on the final line.
        for line in reversed(response.replace("\x00", "").splitlines()):
            match = re.fullmatch(r"\s*([01])\s*", line)
            if match:
                return match.group(1) == "1"
        raise AvproProtocolError(f"Could not determine switch mode: {response!r}")

    @classmethod
    def parse_enabled(cls, response: str) -> bool:
        """Parse common AVPro enabled/disabled and on/off replies."""
        normalized = cls._normalize(response)
        tokens = re.findall(r"\b(ON|OFF|EN|DIS|ENABLE|ENABLED|DISABLE|DISABLED)\b", normalized)
        if not tokens:
            raise AvproProtocolError(f"Could not determine enabled state: {response!r}")
        return tokens[-1] in {"ON", "EN", "ENABLE", "ENABLED"}

    @classmethod
    def parse_scaler(cls, response: str) -> bool:
        """Return True when Output 1 scaling is enabled."""
        normalized = cls._normalize(response)
        if re.search(r"(?:4K\s*[-=]>?\s*2K|4K\s*TO\s*2K|1080P|VIDEO\s*2|VIDEO2)", normalized):
            return True
        if re.search(r"(?:BYPASS|VIDEO\s*1|VIDEO1|\bBP\b)", normalized):
            return False
        values = re.findall(r"(?:^|\s)([12])(?:\s|$)", normalized)
        if values:
            return values[-1] == "2"
        raise AvproProtocolError(f"Could not determine scaler state: {response!r}")


# Backward-compatible internal import name used by v0.2.x code/tests.
AvproMx42Client = AvproMxAuHDClient
