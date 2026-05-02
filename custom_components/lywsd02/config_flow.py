from __future__ import annotations

import re
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.bluetooth import async_discovered_service_info
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from . import DOMAIN

_MANUAL = "manual"
_MAC_RE = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")
_TEMP_MODES = {"": "Auto-detect", "C": "Celsius (°C)", "F": "Fahrenheit (°F)"}


def _settings_schema(defaults: dict[str, Any] | None = None) -> dict:
    d = defaults or {}
    return {
        vol.Optional("temp_mode", default=d.get("temp_mode", "")): vol.In(_TEMP_MODES),
        vol.Optional("timeout", default=d.get("timeout", 60)): vol.All(
            vol.Coerce(int), vol.Range(min=1)
        ),
    }


class Lywsd02ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, str] = {}  # address -> display label

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        configured = self._async_current_ids()
        for info in async_discovered_service_info(self.hass, connectable=True):
            if info.address in configured:
                continue
            if "LYWSD02" in (info.name or ""):
                self._discovered[info.address] = f"{info.name} ({info.address})"

        if not self._discovered:
            return await self.async_step_manual()

        if user_input is not None:
            mac = user_input.pop("mac")
            if mac == _MANUAL:
                return await self.async_step_manual()
            await self.async_set_unique_id(mac)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=self._discovered[mac],
                data={"mac": mac, **user_input},
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("mac"): vol.In(
                        {**self._discovered, _MANUAL: "Enter MAC manually…"}
                    ),
                    **_settings_schema(),
                }
            ),
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            mac = user_input.pop("mac").upper().strip()
            if not _MAC_RE.match(mac):
                errors["mac"] = "invalid_mac"
            else:
                await self.async_set_unique_id(mac)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"LYWSD02 {mac}",
                    data={"mac": mac, **user_input},
                )

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {
                    vol.Required("mac"): str,
                    **_settings_schema(),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return Lywsd02OptionsFlow(config_entry)


class Lywsd02OptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        current = {**self._entry.data, **self._entry.options}
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(_settings_schema(current)),
        )
