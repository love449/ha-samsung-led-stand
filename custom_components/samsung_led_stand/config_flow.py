"""Config flow: enter the lamp's IP address and it is registered."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from .coap import CoapError, SamsungLedStand, StandInfo
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def _probe(host: str) -> StandInfo:
    """Talk to the lamp once; raises CoapError if it is not a reachable LED stand."""
    return await SamsungLedStand(host).async_get_info()


class SamsungLedStandConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._info: StandInfo | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the IP address."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            try:
                info = await _probe(host)
            except CoapError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error while contacting %s", host)
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(info.uuid)
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                return self.async_create_entry(
                    title=info.name, data={CONF_HOST: host}
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_HOST,
                        default=(user_input or {}).get(CONF_HOST, vol.UNDEFINED),
                    ): str
                }
            ),
            errors=errors,
        )

    async def async_step_dhcp(self, discovery_info: DhcpServiceInfo) -> ConfigFlowResult:
        """Offer lamps found on the network (hostname SmartLEDStand...)."""
        host = discovery_info.ip
        try:
            info = await _probe(host)
        except CoapError:
            return self.async_abort(reason="cannot_connect")
        await self.async_set_unique_id(info.uuid)
        # Also keeps the stored IP current if the lamp gets a new address.
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        self._host, self._info = host, info
        self.context["title_placeholders"] = {"name": info.name, "host": host}
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a discovered lamp."""
        assert self._host is not None and self._info is not None
        if user_input is not None:
            return self.async_create_entry(
                title=self._info.name, data={CONF_HOST: self._host}
            )
        self._set_confirm_only()
        return self.async_show_form(
            step_id="confirm",
            description_placeholders={"name": self._info.name, "host": self._host},
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the IP address of an existing lamp."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            try:
                info = await _probe(host)
            except CoapError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error while contacting %s", host)
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(info.uuid)
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_HOST: host}
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_HOST,
                        default=(user_input or {}).get(CONF_HOST, entry.data[CONF_HOST]),
                    ): str
                }
            ),
            errors=errors,
        )
