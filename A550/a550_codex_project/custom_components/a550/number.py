from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, PROBE_COUNT, TIMER_SLOT_COUNT
from .coordinator import A550Coordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: A550Coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        A550TimerNumber(coordinator, probe_id, slot)
        for probe_id in range(PROBE_COUNT)
        for slot in range(TIMER_SLOT_COUNT)
    ]
    async_add_entities(entities)


class A550TimerNumber(CoordinatorEntity[A550Coordinator], NumberEntity):
    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 2047
    _attr_native_step = 1
    _attr_translation_key = "timer_slot"

    def __init__(self, coordinator: A550Coordinator, probe_id: int, slot: int) -> None:
        super().__init__(coordinator)
        self._probe_id = probe_id
        self._slot = slot
        self._attr_unique_id = f"{coordinator.client.address}_probe_{probe_id}_timer_{slot}"
        self._attr_translation_placeholders = {"probe": str(probe_id), "slot": str(slot)}
        address = coordinator.client.address
        self._attr_device_info = DeviceInfo(
            connections={(CONNECTION_BLUETOOTH, address)},
            identifiers={(DOMAIN, address)},
            name=coordinator.client.name,
            manufacturer="Clas Ohlson / Grill Smart",
            model="A550",
        )

    @property
    def native_value(self) -> float | None:
        timers = self.coordinator.data.timers.get(self._probe_id)
        if not timers or self._slot >= len(timers):
            return None
        return float(timers[self._slot])

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.probes[self._probe_id].connected

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.client.async_set_timer_value(self._probe_id, self._slot, int(round(value)))
        await self.coordinator.async_request_refresh()
