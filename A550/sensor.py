from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ASSUME_FAHRENHEIT, DOMAIN, PROBE_COUNT
from .coordinator import A550Coordinator


@dataclass(frozen=True, kw_only=True)
class A550SensorDescription(SensorEntityDescription):
    value_fn: Callable[[Any], Any]
    available_fn: Callable[[Any], bool]


PROBE_DESCRIPTIONS = [
    A550SensorDescription(
        key=f"probe_{idx}",
        translation_key="probe_temperature",
        name=None,
        native_unit_of_measurement=(UnitOfTemperature.FAHRENHEIT if ASSUME_FAHRENHEIT else UnitOfTemperature.CELSIUS),
        suggested_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=(lambda probe_idx: (lambda data: data.probes[probe_idx].temperature_f if ASSUME_FAHRENHEIT else data.probes[probe_idx].temperature_c))(idx),
        available_fn=(lambda probe_idx: (lambda data: data.probes[probe_idx].connected))(idx),
    )
    for idx in range(PROBE_COUNT)
]

BATTERY_DESCRIPTION = A550SensorDescription(
    key="battery",
    translation_key="battery",
    name=None,
    native_unit_of_measurement=PERCENTAGE,
    device_class=SensorDeviceClass.BATTERY,
    state_class=SensorStateClass.MEASUREMENT,
    entity_category=EntityCategory.DIAGNOSTIC,
    value_fn=lambda data: data.battery_percent,
    available_fn=lambda data: data.battery_percent is not None,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: A550Coordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [
        A550ProbeSensor(coordinator, description, idx)
        for idx, description in enumerate(PROBE_DESCRIPTIONS)
    ]
    entities.append(A550BatterySensor(coordinator, BATTERY_DESCRIPTION))
    async_add_entities(entities)


class A550BaseSensor(CoordinatorEntity[A550Coordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: A550Coordinator, description: A550SensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        address = coordinator.client.address
        self._attr_device_info = DeviceInfo(
            connections={(CONNECTION_BLUETOOTH, address)},
            identifiers={(DOMAIN, address)},
            name=coordinator.client.name,
            manufacturer="Clas Ohlson / Grill Smart",
            model="A550",
        )


class A550ProbeSensor(A550BaseSensor):
    def __init__(self, coordinator: A550Coordinator, description: A550SensorDescription, probe_id: int) -> None:
        super().__init__(coordinator, description)
        self._probe_id = probe_id
        self._attr_unique_id = f"{coordinator.client.address}_probe_{probe_id}"
        self._attr_translation_placeholders = {"probe": str(probe_id)}

    @property
    def available(self) -> bool:
        data = self.coordinator.data
        return super().available and self.entity_description.available_fn(data)

    @property
    def native_value(self):
        data = self.coordinator.data
        return self.entity_description.value_fn(data)


class A550BatterySensor(A550BaseSensor):
    def __init__(self, coordinator: A550Coordinator, description: A550SensorDescription) -> None:
        super().__init__(coordinator, description)
        self._attr_unique_id = f"{coordinator.client.address}_battery"

    @property
    def available(self) -> bool:
        data = self.coordinator.data
        return super().available and self.entity_description.available_fn(data)

    @property
    def native_value(self):
        data = self.coordinator.data
        return self.entity_description.value_fn(data)
