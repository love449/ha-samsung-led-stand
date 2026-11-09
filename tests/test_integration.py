"""End-to-end tests: config flow, entities and services against a fake lamp."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.samsung_led_stand.const import DOMAIN

from .fake_stand import UUID


async def _setup_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "127.0.0.1"},
        unique_id=UUID,
        title="LED Stand",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_user_flow_creates_entry_from_ip_only(
    hass: HomeAssistant, fake_stand
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "LED Stand"
    assert result["data"] == {CONF_HOST: "127.0.0.1"}
    await hass.async_block_till_done()

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.state is ConfigEntryState.LOADED
    assert entry.unique_id == UUID
    assert hass.states.get("light.led_stand") is not None
    assert hass.states.get("select.led_stand_lighting_mode") is not None


async def test_user_flow_unreachable_shows_error(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.2"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_duplicate_is_aborted(hass: HomeAssistant, fake_stand) -> None:
    await _setup_entry(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_dhcp_discovery(hass: HomeAssistant, fake_stand) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "dhcp"},
        data=DhcpServiceInfo(
            ip="127.0.0.1", hostname="smartledstand", macaddress="a043b0196a52"
        ),
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: "127.0.0.1"}


async def test_entities_and_registry(hass: HomeAssistant, fake_stand) -> None:
    await _setup_entry(hass)

    state = hass.states.get("light.led_stand")
    assert state.state == "off"
    assert state.attributes["supported_color_modes"] == ["brightness"]

    select_state = hass.states.get("select.led_stand_lighting_mode")
    assert select_state.state == "reading"
    assert select_state.attributes["options"][:5] == [
        "reading",
        "writing",
        "computer",
        "night",
        "sleepPreparation",
    ]

    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, UUID)})
    assert device is not None and device.manufacturer == "Samsung"
    registry = er.async_get(hass)
    assert registry.async_get("light.led_stand").unique_id == f"{UUID}_light"


async def test_light_services(hass: HomeAssistant, fake_stand) -> None:
    await _setup_entry(hass)

    await hass.services.async_call(
        "light", "turn_on", {"entity_id": "light.led_stand", "brightness": 128},
        blocking=True,
    )
    assert fake_stand.power == "on"
    assert fake_stand.level == 50
    state = hass.states.get("light.led_stand")
    assert state.state == "on"
    assert state.attributes["brightness"] in (127, 128)

    await hass.services.async_call(
        "light", "turn_off", {"entity_id": "light.led_stand"}, blocking=True
    )
    assert fake_stand.power == "off"
    assert hass.states.get("light.led_stand").state == "off"


async def test_select_mode_and_unknown_mode_reported(
    hass: HomeAssistant, fake_stand
) -> None:
    await _setup_entry(hass)
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.led_stand_lighting_mode", "option": "night"},
        blocking=True,
    )
    assert fake_stand.mode == "night"
    assert hass.states.get("select.led_stand_lighting_mode").state == "night"

    # A mode we do not know yet is shown instead of "unknown".
    fake_stand.mode = "mystery"
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    state = hass.states.get("select.led_stand_lighting_mode")
    assert state.state == "mystery"
    assert "mystery" in state.attributes["options"]


async def test_state_follows_physical_change(hass: HomeAssistant, fake_stand) -> None:
    await _setup_entry(hass)
    fake_stand.power = "on"
    fake_stand.level = 30
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    state = hass.states.get("light.led_stand")
    assert state.state == "on"
    assert state.attributes["brightness"] == 76


async def test_setup_retries_when_lamp_unreachable(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "127.0.0.2"}, unique_id=UUID)
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_sleep_mode_is_written_as_sleep(hass: HomeAssistant, fake_stand) -> None:
    await _setup_entry(hass)
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.led_stand_lighting_mode", "option": "sleepPreparation"},
        blocking=True,
    )
    posts = [r for r in fake_stand.requests if r[0] == 2]
    assert posts[-1][2] == {"lightingMode": "sleep"}
    assert hass.states.get("select.led_stand_lighting_mode").state == "sleepPreparation"
