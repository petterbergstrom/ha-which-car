"""Shared entity base."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

from .const import DOMAIN
from .coordinator import WhichCarCoordinator


def device_info(coordinator: WhichCarCoordinator) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
        name="Which car today",
        manufacturer="petterbergstrom",
        entry_type=DeviceEntryType.SERVICE,
    )
