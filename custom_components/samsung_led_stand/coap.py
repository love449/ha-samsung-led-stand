"""Minimal CoAP client and CBOR codec for Samsung SmartThings Direct Connect devices.

The LED stand answers unsecured CoAP (UDP 5683) requests on the local network.
This module has no Home Assistant imports so it can be tested on its own.
"""

from __future__ import annotations

import asyncio
import os
import socket
import struct
from dataclasses import dataclass
from typing import Any

COAP_PORT = 5683
DEFAULT_TIMEOUT = 2.0
DEFAULT_ATTEMPTS = 3
CONTENT_FORMAT_CBOR = 60

METHOD_GET = 1
METHOD_POST = 2

TYPE_CON = 0
TYPE_NON = 1
TYPE_ACK = 2
TYPE_RST = 3

OPT_URI_PATH = 11
OPT_CONTENT_FORMAT = 12

PATH_DEVICE = "/oic/d"
PATH_SWITCH = "/capability/switch/main/0"
PATH_LEVEL = "/capability/switchLevel/main/0"
PATH_MODE = "/capability/activityLightingMode/main/0"


class CoapError(Exception):
    """Base error for communication problems."""


class CoapTimeout(CoapError):
    """The device did not answer."""


class CoapResponseError(CoapError):
    """The device answered with an error code."""

    def __init__(self, code: int) -> None:
        super().__init__(f"CoAP error {code >> 5}.{code & 31:02d}")
        self.code = code


# --------------------------------------------------------------------------- #
# CBOR (only what the device needs)
# --------------------------------------------------------------------------- #


class _Break:
    """Sentinel for the CBOR "break" stop code."""


_BREAK = _Break()


def _head(major: int, value: int) -> bytes:
    if value < 24:
        return bytes([(major << 5) | value])
    if value < 0x100:
        return bytes([(major << 5) | 24, value])
    if value < 0x10000:
        return bytes([(major << 5) | 25]) + struct.pack("!H", value)
    if value < 0x100000000:
        return bytes([(major << 5) | 26]) + struct.pack("!I", value)
    return bytes([(major << 5) | 27]) + struct.pack("!Q", value)


def cbor_encode(obj: Any) -> bytes:
    """Encode str/int/bool/float/None/list/dict (text keys) as CBOR."""
    if obj is True:
        return b"\xf5"
    if obj is False:
        return b"\xf4"
    if obj is None:
        return b"\xf6"
    if isinstance(obj, int):
        return _head(0, obj) if obj >= 0 else _head(1, -1 - obj)
    if isinstance(obj, float):
        return b"\xfb" + struct.pack("!d", obj)
    if isinstance(obj, str):
        raw = obj.encode()
        return _head(3, len(raw)) + raw
    if isinstance(obj, bytes):
        return _head(2, len(obj)) + obj
    if isinstance(obj, (list, tuple)):
        return _head(4, len(obj)) + b"".join(cbor_encode(v) for v in obj)
    if isinstance(obj, dict):
        return _head(5, len(obj)) + b"".join(
            cbor_encode(k) + cbor_encode(v) for k, v in obj.items()
        )
    raise TypeError(f"cannot CBOR-encode {type(obj)!r}")


def _decode(data: bytes, i: int) -> tuple[Any, int]:
    ib = data[i]
    i += 1
    major, ai = ib >> 5, ib & 31

    if major == 7:
        if ai == 20:
            return False, i
        if ai == 21:
            return True, i
        if ai in (22, 23):
            return None, i
        if ai == 25:
            return struct.unpack("!e", data[i : i + 2])[0], i + 2
        if ai == 26:
            return struct.unpack("!f", data[i : i + 4])[0], i + 4
        if ai == 27:
            return struct.unpack("!d", data[i : i + 8])[0], i + 8
        if ai == 31:
            return _BREAK, i
        raise CoapError(f"unsupported CBOR simple value {ai}")

    if ai < 24:
        arg: int | None = ai
    elif ai == 24:
        arg, i = data[i], i + 1
    elif ai == 25:
        arg, i = int.from_bytes(data[i : i + 2], "big"), i + 2
    elif ai == 26:
        arg, i = int.from_bytes(data[i : i + 4], "big"), i + 4
    elif ai == 27:
        arg, i = int.from_bytes(data[i : i + 8], "big"), i + 8
    elif ai == 31:
        arg = None  # indefinite length
    else:
        raise CoapError("invalid CBOR header")

    if major == 0:
        return arg, i
    if major == 1:
        return -1 - (arg or 0), i
    if major in (2, 3):
        if arg is None:
            raise CoapError("indefinite CBOR strings are not supported")
        raw = bytes(data[i : i + arg])
        if len(raw) != arg:
            raise CoapError("truncated CBOR string")
        return (raw if major == 2 else raw.decode()), i + arg
    if major == 4:
        items: list[Any] = []
        if arg is None:
            while True:
                val, i = _decode(data, i)
                if val is _BREAK:
                    return items, i
                items.append(val)
        for _ in range(arg):
            val, i = _decode(data, i)
            items.append(val)
        return items, i
    if major == 5:
        result: dict[Any, Any] = {}
        if arg is None:
            while True:
                key, i = _decode(data, i)
                if key is _BREAK:
                    return result, i
                val, i = _decode(data, i)
                result[key] = val
        for _ in range(arg):
            key, i = _decode(data, i)
            val, i = _decode(data, i)
            result[key] = val
        return result, i
    raise CoapError(f"unsupported CBOR major type {major}")


def cbor_decode(data: bytes) -> Any:
    """Decode one CBOR item."""
    try:
        value, _ = _decode(data, 0)
    except (IndexError, struct.error, UnicodeDecodeError) as err:
        raise CoapError(f"invalid CBOR payload: {err}") from err
    return value


# --------------------------------------------------------------------------- #
# CoAP message handling
# --------------------------------------------------------------------------- #


@dataclass
class CoapMessage:
    """A parsed CoAP message."""

    type: int
    code: int
    mid: int
    token: bytes
    options: list[tuple[int, bytes]]
    payload: bytes


def _nibble(value: int) -> tuple[int, bytes]:
    if value < 13:
        return value, b""
    if value < 269:
        return 13, bytes([value - 13])
    return 14, struct.pack("!H", value - 269)


def encode_request(
    code: int,
    mid: int,
    path: str,
    payload: bytes | None = None,
    token: bytes = b"",
) -> bytes:
    """Build a confirmable CoAP request."""
    out = bytearray([0x40 | len(token), code])
    out += struct.pack("!H", mid)
    out += token

    options: list[tuple[int, bytes]] = [
        (OPT_URI_PATH, seg.encode()) for seg in path.split("/") if seg
    ]
    if payload:
        options.append((OPT_CONTENT_FORMAT, bytes([CONTENT_FORMAT_CBOR])))

    prev = 0
    for number, value in options:
        d_nib, d_ext = _nibble(number - prev)
        l_nib, l_ext = _nibble(len(value))
        out.append((d_nib << 4) | l_nib)
        out += d_ext + l_ext + value
        prev = number

    if payload:
        out.append(0xFF)
        out += payload
    return bytes(out)


def parse_message(data: bytes) -> CoapMessage:
    """Parse a CoAP datagram."""
    try:
        if len(data) < 4 or data[0] >> 6 != 1:
            raise CoapError("not a CoAP message")
        msg_type = (data[0] >> 4) & 3
        tkl = data[0] & 15
        code = data[1]
        (mid,) = struct.unpack("!H", data[2:4])
        i = 4
        token = bytes(data[i : i + tkl])
        i += tkl

        options: list[tuple[int, bytes]] = []
        payload = b""
        number = 0
        while i < len(data):
            byte = data[i]
            i += 1
            if byte == 0xFF:
                payload = bytes(data[i:])
                break
            delta, length = byte >> 4, byte & 15
            if delta == 13:
                delta, i = data[i] + 13, i + 1
            elif delta == 14:
                delta, i = struct.unpack("!H", data[i : i + 2])[0] + 269, i + 2
            elif delta == 15:
                raise CoapError("invalid option delta")
            if length == 13:
                length, i = data[i] + 13, i + 1
            elif length == 14:
                length, i = struct.unpack("!H", data[i : i + 2])[0] + 269, i + 2
            elif length == 15:
                raise CoapError("invalid option length")
            number += delta
            options.append((number, bytes(data[i : i + length])))
            i += length
        return CoapMessage(msg_type, code, mid, token, options, payload)
    except (IndexError, struct.error) as err:
        raise CoapError(f"malformed CoAP message: {err}") from err


class _Protocol(asyncio.DatagramProtocol):
    """Collect incoming datagrams (or socket errors) into a queue."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[tuple[bytes, Any] | Exception] = asyncio.Queue()

    def datagram_received(self, data: bytes, addr: Any) -> None:
        self.queue.put_nowait((data, addr))

    def error_received(self, exc: Exception) -> None:
        self.queue.put_nowait(exc)


class CoapClient:
    """Tiny CoAP client: one confirmable request per call with retransmission."""

    def __init__(self, host: str, port: int = COAP_PORT) -> None:
        self.host = host
        self.port = port

    async def request(
        self,
        code: int,
        path: str,
        payload: bytes | None = None,
        *,
        timeout: float | None = None,
        attempts: int | None = None,
    ) -> CoapMessage:
        """Send a request and return the response message.

        An unconnected UDP socket is used on purpose: the lamp receives requests
        on port 5683 but may answer from a different UDP port, which a connected
        socket would silently drop. Replies are accepted from any port of the
        lamp's IP address.
        """
        timeout = DEFAULT_TIMEOUT if timeout is None else timeout
        attempts = DEFAULT_ATTEMPTS if attempts is None else attempts
        loop = asyncio.get_running_loop()
        try:
            infos = await loop.getaddrinfo(
                self.host, self.port, family=socket.AF_INET, type=socket.SOCK_DGRAM
            )
            ip = infos[0][4][0]
            transport, proto = await loop.create_datagram_endpoint(
                _Protocol, family=socket.AF_INET
            )
        except (OSError, IndexError) as err:
            raise CoapError(f"cannot open socket to {self.host}: {err}") from err

        target = (ip, self.port)
        mid = int.from_bytes(os.urandom(2), "big")
        token = os.urandom(2)
        packet = encode_request(code, mid, path, payload, token)
        try:
            for _ in range(attempts):
                transport.sendto(packet, target)
                end = loop.time() + timeout
                while (remaining := end - loop.time()) > 0:
                    try:
                        item = await asyncio.wait_for(proto.queue.get(), remaining)
                    except TimeoutError:
                        break
                    if isinstance(item, Exception):
                        raise CoapError(f"network error: {item}") from item
                    data, addr = item
                    if addr[0] != ip:
                        continue
                    try:
                        msg = parse_message(data)
                    except CoapError:
                        continue
                    if msg.type == TYPE_RST and msg.mid == mid:
                        raise CoapError("request was reset by the device")
                    if msg.type == TYPE_ACK and msg.mid == mid:
                        if msg.code == 0:
                            # Empty ACK: the real answer follows separately.
                            end = loop.time() + 5
                            continue
                        return msg
                    if msg.token == token and msg.code != 0:
                        if msg.type == TYPE_CON:
                            transport.sendto(
                                bytes([0x60, 0]) + struct.pack("!H", msg.mid), addr
                            )
                        return msg
            raise CoapTimeout(f"no answer from {self.host}:{self.port}")
        finally:
            transport.close()


# --------------------------------------------------------------------------- #
# Samsung LED stand API
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class StandInfo:
    """Identity of the device."""

    uuid: str
    name: str


@dataclass(frozen=True)
class StandState:
    """Current device state."""

    power: bool
    brightness: int | None  # 1-100 percent
    mode: str | None


class SamsungLedStand:
    """Local control of the Samsung SmartThings LED stand."""

    def __init__(self, host: str, port: int = COAP_PORT) -> None:
        self._client = CoapClient(host, port)
        self._lock = asyncio.Lock()

    @property
    def host(self) -> str:
        """Return the device address."""
        return self._client.host

    async def _get(self, path: str) -> dict[str, Any]:
        msg = await self._client.request(METHOD_GET, path)
        if msg.code >> 5 != 2:
            raise CoapResponseError(msg.code)
        data = cbor_decode(msg.payload)
        if not isinstance(data, dict):
            raise CoapError(f"unexpected payload from {path}")
        return data

    async def _post(self, path: str, data: dict[str, Any]) -> None:
        msg = await self._client.request(METHOD_POST, path, cbor_encode(data))
        if msg.code >> 5 != 2:
            raise CoapResponseError(msg.code)

    async def async_get_info(self) -> StandInfo:
        """Read the device identity (also proves it is reachable)."""
        async with self._lock:
            data = await self._get(PATH_DEVICE)
            switch = await self._get(PATH_SWITCH)
        uuid = data.get("di")
        if not isinstance(uuid, str) or "power" not in switch:
            raise CoapError("this is not a supported LED stand")
        return StandInfo(uuid=uuid, name=str(data.get("n") or "LED Stand"))

    async def async_get_state(self) -> StandState:
        """Read power, brightness and lighting mode."""
        async with self._lock:
            switch = await self._get(PATH_SWITCH)
            level = await self._get(PATH_LEVEL)
            mode = await self._get(PATH_MODE)
        brightness = level.get("dimmingSetting")
        light_mode = mode.get("lightingMode")
        return StandState(
            power=switch.get("power") == "on",
            brightness=brightness if isinstance(brightness, int) else None,
            mode=light_mode if isinstance(light_mode, str) else None,
        )

    async def async_set_power(self, on: bool) -> None:
        """Turn the lamp on or off."""
        async with self._lock:
            await self._post(PATH_SWITCH, {"power": "on" if on else "off"})

    async def async_set_brightness(self, percent: int) -> None:
        """Set brightness, 1-100."""
        async with self._lock:
            await self._post(PATH_LEVEL, {"dimmingSetting": max(1, min(100, percent))})

    async def async_set_mode(self, mode: str) -> None:
        """Set the lighting mode."""
        async with self._lock:
            await self._post(PATH_MODE, {"lightingMode": mode})
