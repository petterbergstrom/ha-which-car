"""Tests for the cost model. Run with: pytest tests/test_model.py"""

from datetime import datetime, timedelta, timezone

import pytest

from custom_components.which_car.model import (
    PLAN_CHEAPEST,
    PLAN_DAY,
    PLAN_MONTHLY,
    Settings,
    Slot,
    Weather,
    all_in_price,
    calc_trip,
    diesel_litres,
    ev_kwh,
    interp,
    spot_basis,
)

TZ = timezone(timedelta(hours=1))
NOW = datetime(2026, 11, 11, 10, 0, tzinfo=TZ)


def day_slots(prices):
    start = datetime(2026, 11, 11, 0, 0, tzinfo=TZ)
    return [Slot(start + timedelta(hours=i), start + timedelta(hours=i + 1), p) for i, p in enumerate(prices)]


def test_interp_clamps_and_interpolates():
    table = [(0, 1.0), (10, 2.0)]
    assert interp(table, -5) == 1.0
    assert interp(table, 5) == pytest.approx(1.5)
    assert interp(table, 50) == 2.0


def test_consumption_matches_reference_values():
    # Same figures as the browser version of the app produces.
    w = Weather(temp_c=-2.5, wind_ms=4)
    assert ev_kwh(20, 17, 50, w) == pytest.approx(5.367, abs=1e-3)
    assert diesel_litres(20, 6.0, 50, w) == pytest.approx(1.524, abs=1e-3)
    w = Weather(temp_c=-7 / 3, wind_ms=4)
    assert ev_kwh(300, 21, 100, w) == pytest.approx(74.752, abs=1e-3)
    assert diesel_litres(300, 5.4, 100, w) == pytest.approx(17.5619, abs=1e-3)


def test_cold_hits_short_trips_hardest():
    cold, mild = Weather(temp_c=-10), Weather(temp_c=20)
    short = ev_kwh(20, 17, 50, cold) / ev_kwh(20, 17, 50, mild)
    long = ev_kwh(300, 21, 100, cold) / ev_kwh(300, 21, 100, mild)
    assert short > long > 1


def test_all_in_price_uses_lerum_defaults():
    # (0.50 + 0.08) * 1.25 + 0.45 + 0.3895
    assert all_in_price(0.50, Settings()) == pytest.approx(1.5645)


def test_monthly_plan_ignores_hourly_prices():
    slots = day_slots([0.1] * 12 + [2.0] * 12)
    assert spot_basis(10, slots, NOW, Settings(price_plan=PLAN_MONTHLY), 0.6) == 0.6


def test_cheapest_hours_picks_remaining_low_prices():
    slots = day_slots([0.05] * 6 + [1.0] * 12 + [0.2] * 6)  # cheap night already over
    s = Settings(price_plan=PLAN_CHEAPEST, charger_kw=11)
    assert spot_basis(22, slots, NOW, s, None) == pytest.approx(0.2)
    assert spot_basis(22, slots, NOW, Settings(price_plan=PLAN_DAY), None) == pytest.approx(
        (0.05 * 6 + 12 + 0.2 * 6) / 24
    )


def test_long_trip_buys_the_shortfall_at_fast_chargers():
    r = calc_trip("long", 600, Weather(temp_c=-10), Settings(), [], NOW, 0.6, 22.56)
    assert r.ev_fast_kwh > 0
    assert r.ev_cost == pytest.approx(r.ev_grid_kwh * r.home_price + r.ev_fast_kwh * 5.5)
    low = calc_trip("long", 600, Weather(temp_c=-10), Settings(), [], NOW, 0.6, 22.56, start_pct=40)
    assert low.ev_fast_kwh > r.ev_fast_kwh


def test_recommendation_follows_cost():
    w = Weather(temp_c=5)
    assert calc_trip("short", 20, w, Settings(), [], NOW, 0.6, 22.56).recommendation == "ex40"
    assert calc_trip("short", 20, w, Settings(), [], NOW, 6.0, 5.0).recommendation == "passat"
    r = calc_trip("short", 20, w, Settings(), [], NOW, 0.6, 22.56)
    even = calc_trip("short", 20, w, Settings(), [], NOW, 0.6, r.breakeven_diesel)
    assert even.recommendation == "either"


def test_no_price_gives_no_result():
    assert calc_trip("short", 20, Weather(temp_c=5), Settings(), [], NOW, None, 22.56) is None
