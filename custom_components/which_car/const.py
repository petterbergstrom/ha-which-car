"""Constants for Which Car Today."""

from __future__ import annotations

DOMAIN = "which_car"

CONF_NORDPOOL_ENTRY = "nordpool_entry"
CONF_AREA = "area"
CONF_WEATHER = "weather_entity"
CONF_BATTERY = "battery_entity"

AREAS = ["SE1", "SE2", "SE3", "SE4"]

PLAN_MONTHLY = "monthly_average"
PLAN_CHEAPEST = "spot_cheapest_hours"
PLAN_DAY = "spot_day_average"
PLANS = [PLAN_MONTHLY, PLAN_CHEAPEST, PLAN_DAY]

OPT_PRICE_PLAN = "price_plan"
OPT_MARKUP = "markup_ore"
OPT_GRID = "grid_ore"
OPT_TAX = "tax_ore"
OPT_VAT = "vat_pct"
OPT_FAST_PRICE = "fast_price"
OPT_CHARGER_KW = "charger_kw"
OPT_CHARGE_LOSS = "charge_loss_pct"
OPT_EV_SHORT = "ev_short"
OPT_EV_LONG = "ev_long"
OPT_BATTERY_KWH = "battery_kwh"
OPT_START_PCT = "start_pct"
OPT_RESERVE_PCT = "reserve_pct"
OPT_DIESEL_SHORT = "diesel_short"
OPT_DIESEL_LONG = "diesel_long"
# Optional entities that override a fixed setting. Kept out of DEFAULTS and Settings.
OPT_FAST_PRICE_ENTITY = "fast_price_entity"
OPT_CAPACITY_ENTITY = "capacity_entity"

# Fee defaults follow Lerum Energi, 2026:
#   grid transfer fee (enkeltariff) 31.16 ore/kWh excl. VAT = 38.95 incl. VAT
#   energy tax 36.0 ore/kWh excl. VAT = 45.0 incl. VAT
#   "Rorligt elpris" is a monthly volume-weighted price, hence PLAN_MONTHLY.
# Lerum Energi does not publish its mark-up separately; 8 ore is an estimate.
DEFAULTS: dict[str, float | str] = {
    OPT_PRICE_PLAN: PLAN_MONTHLY,
    OPT_MARKUP: 8.0,
    OPT_GRID: 38.95,
    OPT_TAX: 45.0,
    OPT_VAT: 25.0,
    OPT_FAST_PRICE: 5.5,
    OPT_CHARGER_KW: 11.0,
    OPT_CHARGE_LOSS: 10.0,
    OPT_EV_SHORT: 17.0,
    OPT_EV_LONG: 21.0,
    OPT_BATTERY_KWH: 79.0,
    OPT_START_PCT: 90.0,
    OPT_RESERVE_PCT: 10.0,
    OPT_DIESEL_SHORT: 6.0,
    OPT_DIESEL_LONG: 5.4,
}

TRIP_SHORT = "short"
TRIP_LONG = "long"
TRIP_DEFAULTS = {"short_km": 20.0, "long_km": 300.0, "leave_in_h": 0.0}

DIESEL_URL = "https://www.fuel-prices.eu/lang/api/country-history.php?cc=SE"
USER_AGENT = "ha-which-car/0.1 (+https://github.com/petterbergstrom/ha-which-car)"
FALLBACK_EUR_SEK = 11.0
