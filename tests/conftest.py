"""Shared fixtures."""

from __future__ import annotations

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def allow_local_sockets(socket_enabled):
    """The fake lamp needs real UDP sockets on localhost."""
    import pytest_socket

    pytest_socket.socket_allow_hosts(["127.0.0.1", "127.0.0.2"], allow_unix_socket=True)
    yield


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow loading custom_components in every test."""
    yield


@pytest.fixture
async def fake_stand():
    """Run a fake lamp on the default CoAP port of localhost."""
    from .fake_stand import start_fake

    fake, _port, transport = await start_fake("127.0.0.1", 5683)
    yield fake
    transport.close()


@pytest.fixture(autouse=True)
def fast_timeouts(monkeypatch):
    """Do not wait seconds for a lamp that is not there."""
    monkeypatch.setattr("custom_components.samsung_led_stand.coap.DEFAULT_TIMEOUT", 0.3)
    monkeypatch.setattr("custom_components.samsung_led_stand.coap.DEFAULT_ATTEMPTS", 2)
