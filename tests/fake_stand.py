"""A fake Samsung LED stand speaking unsecured CoAP, for tests."""

from __future__ import annotations

import asyncio
import importlib.util
import struct
from pathlib import Path
from typing import Any

_COAP_PATH = (
    Path(__file__).parent.parent / "custom_components" / "samsung_led_stand" / "coap.py"
)
_spec = importlib.util.spec_from_file_location("samsung_led_stand_coap", _COAP_PATH)
coap = importlib.util.module_from_spec(_spec)
import sys  # noqa: E402

sys.modules["samsung_led_stand_coap"] = coap
_spec.loader.exec_module(coap)

UUID = "52128ab4-8d72-8324-7cd2-2afc0714972c"


def _indefinite_map(items: dict[str, Any]) -> bytes:
    """Encode like the real device: indefinite-length CBOR map."""
    out = b"\xbf"
    for key, value in items.items():
        out += coap.cbor_encode(key) + coap.cbor_encode(value)
    return out + b"\xff"


class FakeStand(asyncio.DatagramProtocol):
    """Fake device with the same three resources as the real lamp."""

    def __init__(self) -> None:
        self.power = "off"
        self.level = 100
        self.mode = "reading"
        self.requests: list[tuple[int, str, Any]] = []
        self.drop_next = 0  # silently ignore this many requests
        self.reject_modes: set[str] = set()
        self.transport: asyncio.DatagramTransport | None = None
        # Like the real lamp: requests arrive on 5683 but answers are sent from
        # a different (unicast) UDP port.
        self.reply_transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        self.transport = transport

    def _resource(self, path: str) -> dict[str, Any] | None:
        if path == "/oic/d":
            return {"di": UUID, "n": "LED Stand", "icv": "core.1.1.0"}
        if path == coap.PATH_SWITCH:
            return {"power": self.power}
        if path == coap.PATH_LEVEL:
            return {"dimmingSetting": self.level}
        if path == coap.PATH_MODE:
            return {"lightingMode": self.mode}
        return None

    def datagram_received(self, data: bytes, addr: Any) -> None:
        msg = coap.parse_message(data)
        path = "/" + "/".join(v.decode() for n, v in msg.options if n == 11)
        body = coap.cbor_decode(msg.payload) if msg.payload else None
        self.requests.append((msg.code, path, body))

        if self.drop_next:
            self.drop_next -= 1
            return

        resource = self._resource(path)
        if resource is None:
            code, payload = 0x84, b""  # 4.04
        elif msg.code == 1:
            code, payload = 0x45, _indefinite_map(resource)
        elif msg.code == 2 and isinstance(body, dict):
            if body.get("lightingMode") in self.reject_modes:
                code, payload = 0x80, b""  # 4.00
            else:
                if "power" in body:
                    self.power = body["power"]
                if "dimmingSetting" in body:
                    self.level = body["dimmingSetting"]
                if "lightingMode" in body:
                    value = body["lightingMode"]
                    if value == "sleep":  # real lamp stores it as sleepPreparation
                        value = "sleepPreparation"
                    if value in ("reading", "writing", "computer", "night", "sleepPreparation"):
                        self.mode = value  # unknown values are silently ignored
                code, payload = 0x44, _indefinite_map(self._resource(path))
        else:
            code, payload = 0x85, b""

        reply = bytearray([0x60 | len(msg.token), code])
        reply += struct.pack("!H", msg.mid) + msg.token
        if payload:
            reply += b"\xc1\x3c\xff" + payload
        sender = self.reply_transport or self.transport
        assert sender is not None
        sender.sendto(bytes(reply), addr)


async def start_fake(host: str = "127.0.0.1", port: int = 0):
    """Start the fake device and return (protocol, port, transport)."""
    loop = asyncio.get_running_loop()
    transport, proto = await loop.create_datagram_endpoint(
        FakeStand, local_addr=(host, port)
    )
    reply_transport, _ = await loop.create_datagram_endpoint(
        asyncio.DatagramProtocol, local_addr=(host, 0)
    )
    proto.reply_transport = reply_transport

    class _Both:
        """Close both sockets together."""

        def close(self) -> None:
            transport.close()
            reply_transport.close()

        def get_extra_info(self, *args, **kwargs):
            return transport.get_extra_info(*args, **kwargs)

    return proto, transport.get_extra_info("sockname")[1], _Both()
