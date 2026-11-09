"""Tests for the CoAP/CBOR layer against a fake device."""

from __future__ import annotations

import asyncio

import pytest

from .fake_stand import UUID, coap, start_fake


def test_cbor_real_device_payloads() -> None:
    """Payload bytes captured from the real lamp decode correctly."""
    assert coap.cbor_decode(b"\xbfepowercoff\xff") == {"power": "off"}
    assert coap.cbor_decode(b"\xbfndimmingSetting\x18d\xff") == {"dimmingSetting": 100}
    assert coap.cbor_decode(b"\xbfllightingModegreading\xff") == {
        "lightingMode": "reading"
    }
    raw = b"\xbfbdix$" + UUID.encode() + b"aniLED Stand\xff"
    assert coap.cbor_decode(raw) == {"di": UUID, "n": "LED Stand"}


def test_cbor_roundtrip() -> None:
    sample = {"a": 1, "b": -5, "c": 300, "d": "x", "e": [1, 2, {"f": True}], "g": None}
    assert coap.cbor_decode(coap.cbor_encode(sample)) == sample


def test_request_encoding_matches_working_probe() -> None:
    """Same bytes as the hand-built packet that worked on the real lamp."""
    pkt = coap.encode_request(1, 0x2002, "/capability/switch/main/0")
    assert pkt.startswith(bytes([0x40, 0x01, 0x20, 0x02, 0xBA]))
    msg = coap.parse_message(pkt)
    assert [v.decode() for n, v in msg.options if n == 11] == [
        "capability",
        "switch",
        "main",
        "0",
    ]
    long_path = coap.encode_request(1, 1, "/capability/activityLightingMode/main/0")
    assert coap.parse_message(long_path).options[1][1] == b"activityLightingMode"


async def test_info_and_state() -> None:
    fake, port, transport = await start_fake()
    try:
        stand = coap.SamsungLedStand("127.0.0.1", port)
        info = await stand.async_get_info()
        assert info.uuid == UUID
        assert info.name == "LED Stand"
        state = await stand.async_get_state()
        assert (state.power, state.brightness, state.mode) == (False, 100, "reading")
    finally:
        transport.close()


async def test_writes() -> None:
    fake, port, transport = await start_fake()
    try:
        stand = coap.SamsungLedStand("127.0.0.1", port)
        await stand.async_set_power(True)
        await stand.async_set_brightness(40)
        await stand.async_set_mode("night")
        state = await stand.async_get_state()
        assert (state.power, state.brightness, state.mode) == (True, 40, "night")
        await stand.async_set_brightness(0)  # clamped to 1
        assert fake.level == 1
        await stand.async_set_power(False)
        assert fake.power == "off"
    finally:
        transport.close()


async def test_rejected_mode_raises() -> None:
    fake, port, transport = await start_fake()
    fake.reject_modes = {"bogus"}
    try:
        stand = coap.SamsungLedStand("127.0.0.1", port)
        with pytest.raises(coap.CoapResponseError):
            await stand.async_set_mode("bogus")
    finally:
        transport.close()


async def test_retransmission_recovers_from_one_lost_packet() -> None:
    fake, port, transport = await start_fake()
    fake.drop_next = 1
    try:
        client = coap.CoapClient("127.0.0.1", port)
        msg = await client.request(1, coap.PATH_SWITCH, timeout=0.3)
        assert msg.code == 0x45
    finally:
        transport.close()


async def test_timeout_when_device_silent() -> None:
    fake, port, transport = await start_fake()
    fake.drop_next = 99
    try:
        client = coap.CoapClient("127.0.0.1", port)
        with pytest.raises(coap.CoapTimeout):
            await client.request(1, coap.PATH_SWITCH, timeout=0.1, attempts=2)
    finally:
        transport.close()


async def test_unknown_resource_is_error_code() -> None:
    fake, port, transport = await start_fake()
    try:
        client = coap.CoapClient("127.0.0.1", port)
        msg = await client.request(1, "/capability/colorTemperature/main/0")
        assert msg.code == 0x84
    finally:
        transport.close()


async def test_connection_refused_is_coap_error() -> None:
    fake, port, transport = await start_fake()
    transport.close()
    await asyncio.sleep(0.05)
    client = coap.CoapClient("127.0.0.1", port)
    with pytest.raises(coap.CoapError):
        await client.request(1, coap.PATH_SWITCH, timeout=0.2, attempts=2)
