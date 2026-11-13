"""Sensors for Which Car Today."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import TRIP_LONG, TRIP_SHORT
from .coordinator import WhichCarCoordinator
from .entity import device_info
from .model import RECOMMEND_DIESEL, RECOMMEND_EITHER, RECOMMEND_EV


@dataclass(frozen=True, kw_only=True)
class WhichCarSensorDescription(SensorEntityDescription):
    """Describes a sensor."""

    value_fn: Callable[[dict[str, Any]], Any]
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


def _trip_attrs(kind: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
    def attrs(d: dict[str, Any]) -> dict[str, Any]:
        r, w = d[kind], d[f"{kind}_weather"]
        return {
            "distance_km": r.km,
            "temperature_c": round(r.temp_c, 1),
            "rain_mm": round(w.rain_mm, 1),
            "snow": w.snow,
            "wind_ms": round(w.wind_ms, 1),
            "ex40_kwh": round(r.ev_kwh, 1),
            "ex40_kwh_per_100km": round(r.ev_kwh / r.km * 100, 1),
            "ex40_from_battery_kwh": round(r.ev_kwh - r.ev_fast_kwh, 1),
            "ex40_fast_charge_kwh": round(r.ev_fast_kwh, 1),
            "ex40_fast_charge_cost_sek": round(r.ev_fast_kwh * d["fast_price"], 2),
            "ex40_weather_effect_pct": round(r.ev_weather_pct),
            "passat_litres": round(r.litres, 1),
            "passat_l_per_100km": round(r.litres / r.km * 100, 1),
            "passat_weather_effect_pct": round(r.diesel_weather_pct),
            "saving_pct": round(r.saving / max(r.ev_cost, r.diesel_cost) * 100),
        }

    return attrs


def _trip_sensors(kind: str) -> list[WhichCarSensorDescription]:
    return [
        WhichCarSensorDescription(
            key=f"{kind}_recommendation",
            translation_key=f"{kind}_recommendation",
            device_class=SensorDeviceClass.ENUM,
            options=[RECOMMEND_EV, RECOMMEND_DIESEL, RECOMMEND_EITHER],
            icon="mdi:car-select",
            value_fn=lambda d: d[kind].recommendation,
            attrs_fn=_trip_attrs(kind),
        ),
        WhichCarSensorDescription(
            key=f"{kind}_ex40_cost",
            translation_key=f"{kind}_ex40_cost",
            native_unit_of_measurement="SEK",
            suggested_display_precision=1,
            icon="mdi:car-electric",
            value_fn=lambda d: d[kind].ev_cost,
        ),
        WhichCarSensorDescription(
            key=f"{kind}_passat_cost",
            translation_key=f"{kind}_passat_cost",
            native_unit_of_measurement="SEK",
            suggested_display_precision=1,
            icon="mdi:gas-station",
            value_fn=lambda d: d[kind].diesel_cost,
        ),
        WhichCarSensorDescription(
            key=f"{kind}_saving",
            translation_key=f"{kind}_saving",
            native_unit_of_measurement="SEK",
            suggested_display_precision=1,
            icon="mdi:piggy-bank-outline",
            value_fn=lambda d: d[kind].saving,
        ),
        WhichCarSensorDescription(
            key=f"{kind}_breakeven_diesel",
            translation_key=f"{kind}_breakeven_diesel",
            native_unit_of_measurement="SEK/L",
            suggested_display_precision=2,
            icon="mdi:scale-balance",
            value_fn=lambda d: d[kind].breakeven_diesel,
        ),
    ]


SENSORS: list[WhichCarSensorDescription] = [
    *_trip_sensors(TRIP_SHORT),
    *_trip_sensors(TRIP_LONG),
    WhichCarSensorDescription(
        key="diesel_price",
        translation_key="diesel_price",
        native_unit_of_measurement="SEK/L",
        suggested_display_precision=2,
        icon="mdi:gas-station",
        value_fn=lambda d: d["diesel_price"],
        attrs_fn=lambda d: {
            "week_of": d["diesel_week"],
            "eur_per_litre": d["diesel_eur"],
            "eur_sek": round(d["eur_sek"], 4),
            "attribution": "European Commission Weekly Oil Bulletin (CC BY 4.0) via fuel-prices.eu",
        },
    ),
    WhichCarSensorDescription(
        key="home_electricity_price",
        translation_key="home_electricity_price",
        native_unit_of_measurement="SEK/kWh",
        suggested_display_precision=2,
        icon="mdi:home-lightning-bolt-outline",
        value_fn=lambda d: d["home_price"],
        attrs_fn=lambda d: {
            "price_plan": d["price_plan"],
            "spot_basis_sek_per_kwh": round(d["spot_basis"], 4),
            "month_to_date_spot_sek_per_kwh": (
                round(d["month_avg_spot"], 4) if d["month_avg_spot"] is not None else None
            ),
            "fees_and_taxes_sek_per_kwh": round(d["fees_only"], 4),
            "tomorrow_prices_available": d["tomorrow_prices"],
            "ex40_battery_pct": d["battery_pct"],
            "ex40_battery_capacity_kwh": round(d["battery_kwh"], 1),
            "ex40_battery_capacity_source": d["battery_kwh_source"],
        },
    ),
    WhichCarSensorDescription(
        key="public_charging_price",
        translation_key="public_charging_price",
        native_unit_of_measurement="SEK/kWh",
        suggested_display_precision=2,
        icon="mdi:ev-station",
        value_fn=lambda d: d["fast_price"],
        attrs_fn=lambda d: {"source": d["fast_price_source"]},
    ),
]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: WhichCarCoordinator = entry.runtime_data
    async_add_entities(WhichCarSensor(coordinator, desc) for desc in SENSORS)


class WhichCarSensor(CoordinatorEntity[WhichCarCoordinator], SensorEntity):
    """A value computed by the coordinator."""

    entity_description: WhichCarSensorDescription
    _attr_has_entity_name = True

    def __init__(self, coordinator: WhichCarCoordinator, desc: WhichCarSensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = desc
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{desc.key}"
        self._attr_device_info = device_info(coordinator)

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data)
