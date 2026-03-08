from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN
from .coordinator import A550Coordinator


def build_device_info(coordinator: A550Coordinator) -> DeviceInfo:
    """Build shared device metadata for A550 entities."""
    address = coordinator.client.address
    return DeviceInfo(
        connections={(CONNECTION_BLUETOOTH, address)},
        identifiers={(DOMAIN, address)},
        name=coordinator.client.name,
        manufacturer="Clas Ohlson / Grill Smart",
        model="A550",
    )

