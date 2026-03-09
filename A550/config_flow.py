from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import bluetooth
from homeassistant.data_entry_flow import FlowResult

from .const import CONF_ADDRESS, CONF_NAME, DOMAIN, SERVICE_UUID


class A550ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle an A550 config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        discoveries = bluetooth.async_discovered_service_info(self.hass, connectable=True)

        devices: dict[str, str] = {}
        for info in discoveries:
            local_name = info.name or info.device.name or ""
            service_uuids = {uuid.lower() for uuid in info.service_uuids}
            if not local_name.startswith("GS_") and SERVICE_UUID.lower() not in service_uuids:
                continue
            devices[info.address] = f"{local_name or info.address} ({info.address})"

        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address)
            self._abort_if_unique_id_configured()
            name = devices.get(address, user_input.get(CONF_NAME, address).strip() or address)
            return self.async_create_entry(
                title=name,
                data={
                    CONF_ADDRESS: address,
                    CONF_NAME: name,
                },
            )

        if not devices:
            return self.async_abort(reason="no_devices_found")

        schema = vol.Schema(
            {
                vol.Required(CONF_ADDRESS): vol.In(devices),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)
