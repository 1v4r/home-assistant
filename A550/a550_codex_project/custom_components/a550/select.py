from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, PROBE_COUNT, SETTABLE_COOKING_STATUS
from .coordinator import A550Coordinator
from .entity import build_device_info

OPTIONS = list(SETTABLE_COOKING_STATUS.keys())


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: A550Coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([A550CookingStatusSelect(coordinator, probe_id) for probe_id in range(PROBE_COUNT)])


class A550CookingStatusSelect(CoordinatorEntity[A550Coordinator], SelectEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "cooking_status"
    _attr_options = OPTIONS

    def __init__(self, coordinator: A550Coordinator, probe_id: int) -> None:
        super().__init__(coordinator)
        self._probe_id = probe_id
        self._attr_unique_id = f"{coordinator.client.address}_probe_{probe_id}_cooking_status"
        self._attr_translation_placeholders = {"probe": str(probe_id)}
        self._attr_device_info = build_device_info(coordinator)

    @property
    def current_option(self) -> str | None:
        probe = self.coordinator.data.probes[self._probe_id]
        return self.coordinator.client.cooking_status_name(probe.cooking_status)

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.probes[self._probe_id].connected

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.client.async_set_cooking_status(self._probe_id, option)
        await self.coordinator.async_request_refresh()
