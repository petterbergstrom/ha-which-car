"""Cost model for Which Car Today. Pure Python, no Home Assistant imports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

PLAN_MONTHLY = "monthly_average"
PLAN_CHEAPEST = "spot_cheapest_hours"
PLAN_DAY = "spot_day_average"

# Temperature tables: (deg C, value), interpolated linearly.
EV_STEADY = [(-20, 1.20), (-10, 1.15), (0, 1.09), (10, 1.04), (20, 1.0), (30, 1.0)]
# kW of cabin heating or cooling while driving
EV_HEAT = [(-20, 3.0), (-10, 2.0), (0, 1.2), (10, 0.5), (20, 0.0), (30, 0.6)]
# kWh once per trip: cabin and battery warm-up
EV_WARM = [(-20, 2.2), (-10, 1.5), (0, 0.9), (10, 0.4), (20, 0.0), (30, 0.2)]
DIESEL_STEADY = [(-20, 1.14), (-10, 1.10), (0, 1.06), (10, 1.03), (20, 1.0), (30, 1.02)]
# litres once per trip: cold start
DIESEL_COLD = [(-20, 0.40), (-10, 0.30), (0, 0.22), (10, 0.15), (20, 0.10), (30, 0.10)]

SPEED = {"short": 50.0, "long": 100.0}  # average km/h per trip type

RECOMMEND_EV = "ex40"
RECOMMEND_DIESEL = "passat"
RECOMMEND_EITHER = "either"


@dataclass(frozen=True)
class Weather:
    """Weather over a trip."""

    temp_c: float
    rain_mm: float = 0.0
    snow: bool = False
    wind_ms: float = 0.0


REFERENCE_WEATHER = Weather(temp_c=20.0)


@dataclass(frozen=True)
class Slot:
    """One spot price period. Price in SEK/kWh, before fees and VAT."""

    start: datetime
    end: datetime
    price: float

    @property
    def hours(self) -> float:
        return (self.end - self.start).total_seconds() / 3600


@dataclass(frozen=True)
class Settings:
    """User settings."""

    price_plan: str = PLAN_MONTHLY
    markup_ore: float = 8.0
    grid_ore: float = 38.95
    tax_ore: float = 45.0
    vat_pct: float = 25.0
    fast_price: float = 5.5
    charger_kw: float = 11.0
    charge_loss_pct: float = 10.0
    ev_short: float = 17.0
    ev_long: float = 21.0
    battery_kwh: float = 79.0
    start_pct: float = 90.0
    reserve_pct: float = 10.0
    diesel_short: float = 6.0
    diesel_long: float = 5.4


@dataclass(frozen=True)
class TripResult:
    """Outcome for one trip type."""

    km: float
    temp_c: float
    ev_kwh: float
    ev_fast_kwh: float
    ev_grid_kwh: float
    spot_basis: float
    home_price: float
    ev_cost: float
    litres: float
    diesel_price: float
    diesel_cost: float
    ev_weather_pct: float
    diesel_weather_pct: float
    breakeven_diesel: float
    saving: float
    recommendation: str


def interp(table: list[tuple[float, float]], x: float) -> float:
    """Linear interpolation, clamped at both ends."""
    if x <= table[0][0]:
        return table[0][1]
    for (x0, y0), (x1, y1) in zip(table, table[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return table[-1][1]


def road_factor(w: Weather, speed: float) -> float:
    """Extra rolling and air resistance from snow, rain and wind."""
    f = 1.0
    if w.snow or (w.rain_mm > 0.2 and w.temp_c <= 0.5):
        f *= 1.10
    elif w.rain_mm > 0.5:
        f *= 1.04
    if w.wind_ms > 8:
        f *= 1.05 if speed >= 90 else 1.02
    return f


def ev_kwh(km: float, base: float, speed: float, w: Weather) -> float:
    """Battery energy for a trip in kWh."""
    per_100 = base * interp(EV_STEADY, w.temp_c) * road_factor(w, speed)
    per_100 += interp(EV_HEAT, w.temp_c) / speed * 100
    return km * per_100 / 100 + interp(EV_WARM, w.temp_c)


def diesel_litres(km: float, base: float, speed: float, w: Weather) -> float:
    """Diesel for a trip in litres."""
    per_100 = base * interp(DIESEL_STEADY, w.temp_c) * road_factor(w, speed)
    return km * per_100 / 100 + interp(DIESEL_COLD, w.temp_c)


def all_in_price(spot: float, s: Settings) -> float:
    """SEK/kWh at the wall: spot + mark-up, VAT, energy tax and grid fee."""
    return (spot + s.markup_ore / 100) * (1 + s.vat_pct / 100) + (s.tax_ore + s.grid_ore) / 100


def _weighted_mean(slots: list[Slot]) -> float | None:
    hours = sum(x.hours for x in slots)
    if hours <= 0:
        return None
    return sum(x.price * x.hours for x in slots) / hours


def spot_basis(
    grid_kwh: float,
    slots: list[Slot],
    now: datetime,
    s: Settings,
    month_avg: float | None,
) -> float | None:
    """Spot price (SEK/kWh) that the energy for this trip will be billed at."""
    if s.price_plan == PLAN_MONTHLY and month_avg is not None:
        return month_avg
    if not slots:
        return month_avg
    if s.price_plan != PLAN_CHEAPEST:
        today = [x for x in slots if x.start.astimezone(now.tzinfo).date() == now.date()]
        return _weighted_mean(today or slots)
    need = max(grid_kwh / max(s.charger_kw, 0.5), 0.25)
    pool = [x for x in slots if x.end > now]
    if sum(x.hours for x in pool) < max(need, 6):
        pool = list(slots)
    picked: list[Slot] = []
    got = 0.0
    for x in sorted(pool, key=lambda x: x.price):
        if got >= need:
            break
        picked.append(x)
        got += x.hours
    return _weighted_mean(picked)


def calc_trip(
    kind: str,
    km: float,
    w: Weather,
    s: Settings,
    slots: list[Slot],
    now: datetime,
    month_avg: float | None,
    diesel_price: float,
    start_pct: float | None = None,
) -> TripResult | None:
    """Compare both cars for one trip. None if no electricity price is known."""
    speed = SPEED[kind]
    ev_base = s.ev_short if kind == "short" else s.ev_long
    d_base = s.diesel_short if kind == "short" else s.diesel_long
    start = s.start_pct if start_pct is None else start_pct

    kwh = ev_kwh(km, ev_base, speed, w)
    kwh_ref = ev_kwh(km, ev_base, speed, REFERENCE_WEATHER)
    from_home = min(kwh, max(0.0, s.battery_kwh * (start - s.reserve_pct) / 100))
    fast = kwh - from_home
    grid = from_home / (1 - min(s.charge_loss_pct, 60) / 100)
    spot = spot_basis(grid, slots, now, s, month_avg)
    if spot is None:
        return None
    home = all_in_price(spot, s)
    ev_cost = grid * home + fast * s.fast_price

    litres = diesel_litres(km, d_base, speed, w)
    litres_ref = diesel_litres(km, d_base, speed, REFERENCE_WEATHER)
    diesel_cost = litres * diesel_price

    diff = abs(ev_cost - diesel_cost)
    high = max(ev_cost, diesel_cost)
    if diff < max(1.0, high * 0.03):
        rec = RECOMMEND_EITHER
    elif ev_cost < diesel_cost:
        rec = RECOMMEND_EV
    else:
        rec = RECOMMEND_DIESEL

    return TripResult(
        km=km,
        temp_c=w.temp_c,
        ev_kwh=kwh,
        ev_fast_kwh=fast,
        ev_grid_kwh=grid,
        spot_basis=spot,
        home_price=home,
        ev_cost=ev_cost,
        litres=litres,
        diesel_price=diesel_price,
        diesel_cost=diesel_cost,
        ev_weather_pct=(kwh / kwh_ref - 1) * 100,
        diesel_weather_pct=(litres / litres_ref - 1) * 100,
        breakeven_diesel=ev_cost / litres,
        saving=diff,
        recommendation=rec,
    )
