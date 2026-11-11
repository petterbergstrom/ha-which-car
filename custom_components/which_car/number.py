"""Trip settings you can change from the dashboard."""

from __future__ import annotations

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfLength, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import TRIP_DEFAULTS
from .coordinator import WhichCarCoordinator
from .entity import device_info

# key: (min, max, step, unit, icon)
NUMBERS = {
    "short_km": (1, 150, 1, UnitOfLength.KILOMETERS, "mdi:map-marker-distance"),
    "long_km": (50, 2000, 10, UnitOfLength.KILOMETERS, "mdi:highway"),
    "leave_in_h": (0, 24, 1, UnitOfTime.HOURS, "mdi:clock-start"),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: WhichCarCoordinator = entry.runtime_data
    async_add_entities(TripNumber(coordinator, key) for key in NUMBERS)


class TripNumber(RestoreNumber):
    """A trip parameter."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: WhichCarCoordinator, key: str) -> None:
        low, high, step, unit, icon = NUMBERS[key]
        self._coordinator = coordinator
        self._key = key
        self._attr_translation_key = key
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{key}"
        self._attr_device_info = device_info(coordinator)
        self._attr_native_min_value = low
        self._attr_native_max_value = high
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        self._attr_native_value = TRIP_DEFAULTS[key]

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self._attr_native_value = last.native_value
            if self._coordinator.trip[self._key] != last.native_value:
                self._coordinator.trip[self._key] = last.native_value
                await self._coordinator.async_request_refresh()

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        self._coordinator.trip[self._key] = value
        self.async_write_ha_state()
        await self._coordinator.async_request_refresh()
