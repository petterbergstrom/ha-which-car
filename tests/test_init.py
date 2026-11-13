"""End-to-end test against Home Assistant with faked Nord Pool, weather and diesel sources."""

from datetime import datetime, timedelta

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from custom_components.which_car.const import DEFAULTS, DIESEL_URL, DOMAIN, OPT_PRICE_PLAN, PLAN_CHEAPEST

WEATHER = "weather.forecast_home"
DATA = {"nordpool_entry": "np1", "area": "SE3", "weather_entity": WEATHER}


def fake_sources(hass: HomeAssistant, aioclient_mock, calls: list) -> None:
    async def prices(call: ServiceCall):
        calls.append((str(call.data["date"]), call.data["currency"]))
        assert call.data["areas"] == "SE3"
        day = datetime.fromisoformat(str(call.data["date"])).replace(tzinfo=dt_util.UTC)
        k = 1000.0 if call.data["currency"] == "SEK" else 1000.0 / 11.0
        return {
            "SE3": [
                {
                    "start": (day + timedelta(minutes=15 * i)).isoformat(),
                    "end": (day + timedelta(minutes=15 * (i + 1))).isoformat(),
                    "price": (0.3 + 0.6 * (i % 96) / 96) * k,
                }
                for i in range(96)
            ]
        }

    async def forecasts(call: ServiceCall):
        hour = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
        return {
            WEATHER: {
                "forecast": [
                    {
                        "datetime": (hour + timedelta(hours=i)).isoformat(),
                        "temperature": -5.0,
                        "precipitation": 0.0,
                        "wind_speed": 18.0,
                        "condition": "cloudy",
                    }
                    for i in range(48)
                ]
            }
        }

    hass.services.async_register("nordpool", "get_prices_for_date", prices, supports_response=SupportsResponse.ONLY)
    hass.services.async_register("weather", "get_forecasts", forecasts, supports_response=SupportsResponse.ONLY)
    hass.states.async_set(
        WEATHER, "cloudy", {"temperature": -5.0, "temperature_unit": "°C", "wind_speed": 18.0, "wind_speed_unit": "km/h"}
    )
    aioclient_mock.get(
        DIESEL_URL,
        json={"cc": "SE", "labels": ["2026-10-26", "2026-11-02", "2026-11-09"], "e95": [1.5, 1.5, 0], "diesel": [2.037, 2.061, 0]},
    )


async def setup(hass, aioclient_mock, options=None, data=None):
    calls: list = []
    fake_sources(hass, aioclient_mock, calls)
    entry = MockConfigEntry(domain=DOMAIN, data=data or DATA, options={**DEFAULTS, **(options or {})})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry, calls


async def test_sensors(hass: HomeAssistant, aioclient_mock) -> None:
    entry, calls = await setup(hass, aioclient_mock)

    diesel = hass.states.get("sensor.which_car_today_diesel_price")
    assert abs(float(diesel.state) - 2.061 * 11) < 0.01  # EUR price times the derived exchange rate
    assert diesel.attributes["week_of"] == "2026-11-02"

    assert hass.states.get("sensor.which_car_today_short_trip_recommendation").state == "ex40"
    rec = hass.states.get("sensor.which_car_today_long_trip_recommendation")
    assert rec.state == "ex40"
    assert rec.attributes["temperature_c"] == -5.0
    assert rec.attributes["wind_ms"] == 5.0
    assert rec.attributes["ex40_weather_effect_pct"] > rec.attributes["passat_weather_effect_pct"] > 0

    home = hass.states.get("sensor.which_car_today_home_electricity_price")
    assert home.attributes["price_plan"] == "monthly_average"
    # month-to-date average spot is ~0.6 in the fake data: (0.6+0.08)*1.25+0.45+0.3895
    assert abs(float(home.state) - 1.686) < 0.02

    ev = float(hass.states.get("sensor.which_car_today_long_trip_ex40_cost").state)
    d = float(hass.states.get("sensor.which_car_today_long_trip_passat_cost").state)
    assert abs(float(hass.states.get("sensor.which_car_today_long_trip_saving").state) - (d - ev)) < 0.01

    # Changing the distance recalculates.
    await hass.services.async_call(
        "number", "set_value", {"entity_id": "number.which_car_today_long_trip_distance", "value": 600}, blocking=True
    )
    await hass.async_block_till_done()
    assert float(hass.states.get("sensor.which_car_today_long_trip_ex40_cost").state) > ev * 1.8

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_spot_plan_and_battery_sensor(hass: HomeAssistant, aioclient_mock) -> None:
    hass.states.async_set("sensor.ex40_battery_charge_level", "35")
    await setup(
        hass,
        aioclient_mock,
        options={OPT_PRICE_PLAN: PLAN_CHEAPEST},
        data={**DATA, "battery_entity": "sensor.ex40_battery_charge_level"},
    )
    home = hass.states.get("sensor.which_car_today_home_electricity_price")
    assert home.attributes["month_to_date_spot_sek_per_kwh"] is None
    assert home.attributes["ex40_battery_pct"] == 35.0
    long = hass.states.get("sensor.which_car_today_long_trip_recommendation")
    assert long.attributes["ex40_fast_charge_kwh"] > 40  # only 25% of the battery usable


async def test_config_flow(hass: HomeAssistant, aioclient_mock) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "nordpool_missing"

    MockConfigEntry(domain="nordpool", entry_id="np1").add_to_hass(hass)
    fake_sources(hass, aioclient_mock, [])
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], DATA)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"]["grid_ore"] == 38.95
    await hass.async_block_till_done()

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(result["flow_id"], {**DEFAULTS, "markup_ore": 5.0})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["markup_ore"] == 5.0


async def test_nordpool_error_is_shown(hass: HomeAssistant, aioclient_mock) -> None:
    fake_sources(hass, aioclient_mock, [])

    async def failing(call: ServiceCall):
        raise ServiceValidationError("Nord Pool entry np1 is not loaded")

    hass.services.async_register("nordpool", "get_prices_for_date", failing, supports_response=SupportsResponse.ONLY)
    entry = MockConfigEntry(domain=DOMAIN, data=DATA, options=dict(DEFAULTS))
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert "np1 is not loaded" in entry.reason
