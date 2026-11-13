# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Home Assistant custom integration (domain `which_car`, distributed via HACS) that recommends whether a Volvo EX40 or a VW Passat 2.0 TDI is cheaper to drive for a short and a long trip, from Nord Pool electricity prices, the Swedish weekly diesel price and the Met.no forecast at departure time. The README is the user-facing spec: it documents the settings, defaults and how cost is calculated, so keep it in sync when behaviour or defaults change.

## Commands

```
pip install -r requirements_test.txt     # pulls pytest-homeassistant-custom-component (and HA itself)
pytest -q                                # all tests (asyncio_mode = auto, testpaths = tests)
pytest tests/test_model.py               # pure cost-model tests, fast
pytest tests/test_init.py -k <name>      # single end-to-end test
```

CI (`.github/workflows/validate.yml`) runs the HACS action, `hassfest` and `pytest` on Python 3.13. Minimum HA version is set in `hacs.json` (2025.8.0).

## Architecture

All code lives in `custom_components/which_car/`.

- **`model.py`** is the pure cost model with **no Home Assistant imports**: `Weather`, `Slot` (one spot-price period, SEK/kWh excl. fees/VAT), `Settings`, `TripResult`, temperature interpolation tables, and `calc_trip()` / `all_in_price()` / `spot_basis()`. Keep it HA-free so `tests/test_model.py` can exercise it directly.
- **`coordinator.py`** (`WhichCarCoordinator`, 15-minute `DataUpdateCoordinator`) gathers inputs and calls `calc_trip` for each trip type:
  - Electricity: calls the `nordpool.get_prices_for_date` service (not an API directly). It needs the built-in Nord Pool integration; the HACS "Nordpool" custom component uses the same `nordpool` domain but has no such action. The Nord Pool config entry ID is stored in `entry.data` and there is no reconfigure flow, so if the user replaces their Nord Pool entry, Which Car Today has to be removed and re-added. Tomorrow's prices are fetched only after 13:00. For the monthly-average price plan it backfills per-day averages for the current month, at most `BACKFILL_PER_UPDATE` days per update.
  - EUR→SEK rate is derived by fetching the same Nord Pool day in both SEK and EUR; falls back to `FALLBACK_EUR_SEK`.
  - Diesel: HTTP fetch of `DIESEL_URL` (fuel-prices.eu, EUR/L), refreshed every 6 h; last known value is kept on failure.
  - Weather: `weather.get_forecasts` (hourly), averaged over the trip window (duration from `SPEED[kind]`), with unit conversion; falls back to current state attributes.
  - Persistent cache in a `Store` (`which_car.<entry_id>`): daily spot averages, exchange rate, diesel price. Written only when `_dirty` is set.
  - Output is a plain `dict` keyed by trip kind (`"short"`/`"long"` → `TripResult`) plus shared values; sensors read from it.
- **`sensor.py`** defines entities declaratively via `WhichCarSensorDescription` (value/attrs callables over the coordinator dict), generated per trip kind.
- **`number.py`**: trip distance and "leaving in" are `RestoreNumber` entities that write into `coordinator.trip` and request a refresh; they are not config options.
- **`config_flow.py`**: setup picks the Nord Pool entry, area, weather entity and optional battery sensor (stored in `entry.data`); the options flow holds fees and car figures (stored in `entry.options`). Changing options reloads the entry.
- **`const.py`** holds config keys and `DEFAULTS`.

### Invariants to preserve

- `coordinator.settings` builds `Settings` by taking `Settings.__dataclass_fields__` from `{**DEFAULTS, **entry.options}`. Every `Settings` field must have a matching key in `DEFAULTS` (and options keys must use the same names). Adding a setting means updating `model.Settings`, `const.DEFAULTS`/`OPT_*`, the options flow schema, `translations/en.json` and the README table.
- Options that pick an entity (`OPT_FAST_PRICE_ENTITY`, `OPT_CAPACITY_ENTITY`) are not `Settings` fields and are not in `DEFAULTS`. The coordinator reads them (`_fast_price`, `_battery_capacity`) and passes the effective values to the model with `dataclasses.replace(settings, ...)`, falling back to the fixed setting when the entity has no usable value.
- `PLAN_*` constants are duplicated in `model.py` and `const.py` (to keep the model HA-free); keep the values identical.
- Entity names come from `translation_key` → `translations/en.json`; new entities need translation entries.

## Tests

`tests/test_init.py` runs the integration end-to-end in a real HA test instance, faking the Nord Pool and `weather.get_forecasts` services by registering service handlers and mocking the diesel URL with `aioclient_mock`. `tests/conftest.py` enables custom integrations and pre-starts the pycares DNS thread so the lingering-thread check doesn't fail.
