from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .bluetooth import A550Client, A550Data
from .const import CONF_ADDRESS, CONF_NAME, DEFAULT_POLL_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class A550Coordinator(DataUpdateCoordinator[A550Data]):
    """Coordinator for the A550 BLE thermometer."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.client = A550Client(
            hass,
            entry.data[CONF_ADDRESS],
            entry.data[CONF_NAME],
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{entry.data[CONF_ADDRESS]}",
            update_interval=DEFAULT_POLL_INTERVAL,
        )

    async def _async_update_data(self) -> A550Data:
        return await self.client.async_update()
