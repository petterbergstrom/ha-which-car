"""Which Car Today: pick the cheaper car for today's trip."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError

from .const import CONF_NORDPOOL_ENTRY
from .coordinator import WhichCarCoordinator

PLATFORMS = [Platform.SENSOR, Platform.NUMBER]

type WhichCarConfigEntry = ConfigEntry[WhichCarCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: WhichCarConfigEntry) -> bool:
    """Set up from a config entry."""
    if hass.config_entries.async_get_entry(entry.data[CONF_NORDPOOL_ENTRY]) is None:
        raise ConfigEntryError(
            "The Nord Pool integration entry chosen for Which car today no longer exists. "
            "Use Reconfigure on this integration to pick the current one."
        )
    coordinator = WhichCarCoordinator(hass, entry)
    await coordinator.async_load()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WhichCarConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
