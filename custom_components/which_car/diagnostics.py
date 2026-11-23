"""Diagnostics for Which Car Today."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from homeassistant.core import HomeAssistant

from . import WhichCarConfigEntry
from .const import CONF_NORDPOOL_ENTRY


def _plain(value: Any) -> Any:
    return asdict(value) if is_dataclass(value) and not isinstance(value, type) else value


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: WhichCarConfigEntry
) -> dict[str, Any]:
    """Settings, inputs and the last result. Nothing here is secret."""
    coordinator = entry.runtime_data
    return {
        "data": dict(entry.data),
        "options": dict(entry.options),
        "nordpool_entry_exists": hass.config_entries.async_get_entry(entry.data[CONF_NORDPOOL_ENTRY])
        is not None,
        "trip": dict(coordinator.trip),
        "last_update_success": coordinator.last_update_success,
        "result": {k: _plain(v) for k, v in (coordinator.data or {}).items()},
        "cache": coordinator.cache,
    }
