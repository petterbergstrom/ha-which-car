"""Collects prices and weather and runs the cost model."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
import logging
import math
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfSpeed, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import SpeedConverter, TemperatureConverter

from .const import (
    CONF_AREA,
    CONF_BATTERY,
    CONF_NORDPOOL_ENTRY,
    CONF_WEATHER,
    DEFAULTS,
    DIESEL_URL,
    DOMAIN,
    FALLBACK_EUR_SEK,
    OPT_PRICE_PLAN,
    PLAN_MONTHLY,
    TRIP_DEFAULTS,
    TRIP_LONG,
    TRIP_SHORT,
    USER_AGENT,
)
from .model import SPEED, Settings, Slot, Weather, all_in_price, calc_trip

_LOGGER = logging.getLogger(__name__)

SNOW_CONDITIONS = {"snowy", "snowy-rainy"}
RAIN_CONDITIONS = {"rainy", "pouring", "lightning-rainy", "hail"}
BACKFILL_PER_UPDATE = 8
DIESEL_REFRESH = timedelta(hours=6)


class WhichCarCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetches inputs and computes the recommendation."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(minutes=15),
        )
        self.trip: dict[str, float] = dict(TRIP_DEFAULTS)
        self._store: Store[dict[str, Any]] = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self._saved: dict[str, Any] = {}
        self._slots: dict[date, list[Slot]] = {}
        self._exr_day: date | None = None
        self._diesel_at: datetime | None = None
        self._dirty = False

    async def async_load(self) -> None:
        """Load cached values from disk."""
        self._saved = await self._store.async_load() or {}
        self._saved.setdefault("daily_avg", {})

    @property
    def settings(self) -> Settings:
        opts = {**DEFAULTS, **self.config_entry.options}
        return Settings(**{k: opts[k] for k in Settings.__dataclass_fields__})

    # ---------- electricity ----------

    async def _fetch_prices(self, day: date, currency: str = "SEK") -> list[Slot]:
        """Spot prices for one day through the Nord Pool integration, in currency/kWh."""
        area = self.config_entry.data[CONF_AREA]
        resp = await self.hass.services.async_call(
            "nordpool",
            "get_prices_for_date",
            {
                "config_entry": self.config_entry.data[CONF_NORDPOOL_ENTRY],
                "date": day.isoformat(),
                "areas": area,
                "currency": currency,
            },
            blocking=True,
            return_response=True,
        )
        slots: list[Slot] = []
        for row in (resp or {}).get(area) or []:
            start = dt_util.parse_datetime(str(row["start"]))
            end = dt_util.parse_datetime(str(row["end"]))
            if start is None or end is None or row.get("price") is None:
                continue
            slots.append(Slot(start, end, float(row["price"]) / 1000))
        if not slots:
            raise HomeAssistantError(f"No Nord Pool prices for {day}")
        return slots

    async def _update_electricity(self, now: datetime) -> tuple[list[Slot], float | None]:
        today = now.date()
        tomorrow = today + timedelta(days=1)
        for old in [d for d in self._slots if d < today]:
            del self._slots[old]

        if today not in self._slots:
            try:
                self._slots[today] = await self._fetch_prices(today)
            except HomeAssistantError as err:
                _LOGGER.debug("Today's prices unavailable: %s", err)
        if tomorrow not in self._slots and now.hour >= 13:
            try:
                self._slots[tomorrow] = await self._fetch_prices(tomorrow)
            except HomeAssistantError:
                pass  # not published yet

        month_avg: float | None = None
        daily: dict[str, float] = self._saved["daily_avg"]
        changed = False
        if today in self._slots:
            prices = self._slots[today]
            avg = sum(x.price * x.hours for x in prices) / sum(x.hours for x in prices)
            if daily.get(today.isoformat()) != avg:
                daily[today.isoformat()] = avg
                changed = True
        if self.settings.price_plan == PLAN_MONTHLY:
            prefix = today.strftime("%Y-%m-")
            for key in [k for k in daily if not k.startswith(prefix)]:
                del daily[key]
                changed = True
            fetched = 0
            for n in range(1, today.day):
                day = today.replace(day=n)
                if day.isoformat() in daily or fetched >= BACKFILL_PER_UPDATE:
                    continue
                fetched += 1
                try:
                    prices = await self._fetch_prices(day)
                except HomeAssistantError as err:
                    _LOGGER.debug("No prices for %s: %s", day, err)
                    continue
                daily[day.isoformat()] = sum(x.price * x.hours for x in prices) / sum(
                    x.hours for x in prices
                )
                changed = True
            if daily:
                month_avg = sum(daily.values()) / len(daily)
        if changed:
            self._dirty = True

        slots = [x for d in sorted(self._slots) for x in self._slots[d]]
        return slots, month_avg

    async def _update_exchange_rate(self, now: datetime, slots: list[Slot]) -> float:
        """EUR to SEK, taken from the same Nord Pool prices in both currencies."""
        today = now.date()
        if self._exr_day != today and today in self._slots:
            try:
                eur = await self._fetch_prices(today, "EUR")
                sek = self._slots[today]
                pairs = [
                    (s.price, e.price)
                    for s, e in zip(sek, eur)
                    if s.start == e.start and abs(e.price) > 0.001
                ]
                if pairs:
                    s_price, e_price = max(pairs, key=lambda p: abs(p[1]))
                    rate = s_price / e_price
                    if 5 < rate < 20:
                        self._saved["exr"] = rate
                        self._exr_day = today
                        self._dirty = True
            except HomeAssistantError as err:
                _LOGGER.debug("Could not derive EUR/SEK: %s", err)
        return float(self._saved.get("exr") or FALLBACK_EUR_SEK)

    # ---------- diesel ----------

    async def _update_diesel(self, now: datetime) -> dict[str, Any] | None:
        if self._diesel_at is None or now - self._diesel_at > DIESEL_REFRESH:
            session = async_get_clientsession(self.hass)
            try:
                async with asyncio.timeout(20):
                    resp = await session.get(DIESEL_URL, headers={"User-Agent": USER_AGENT})
                    resp.raise_for_status()
                    body = await resp.json(content_type=None)
                for label, value in zip(reversed(body["labels"]), reversed(body["diesel"])):
                    if value and float(value) > 0:
                        self._saved["diesel"] = {"eur": float(value), "week": str(label)}
                        self._diesel_at = now
                        self._dirty = True
                        break
            except Exception as err:  # noqa: BLE001 - keep the last known price
                _LOGGER.warning("Could not fetch the diesel price: %s", err)
        return self._saved.get("diesel")

    # ---------- weather ----------

    async def _update_weather(self) -> tuple[Any, list[dict[str, Any]]]:
        entity_id = self.config_entry.data[CONF_WEATHER]
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None, []
        forecast: list[dict[str, Any]] = []
        try:
            resp = await self.hass.services.async_call(
                "weather",
                "get_forecasts",
                {"entity_id": entity_id, "type": "hourly"},
                blocking=True,
                return_response=True,
            )
            forecast = ((resp or {}).get(entity_id) or {}).get("forecast") or []
        except HomeAssistantError as err:
            _LOGGER.debug("No hourly forecast from %s: %s", entity_id, err)
        return state, forecast

    @staticmethod
    def _trip_weather(
        state: Any, forecast: list[dict[str, Any]], depart: datetime, hours: int
    ) -> Weather | None:
        attrs = state.attributes
        t_unit = attrs.get("temperature_unit") or UnitOfTemperature.CELSIUS
        w_unit = attrs.get("wind_speed_unit") or UnitOfSpeed.KILOMETERS_PER_HOUR
        rain_k = 25.4 if attrs.get("precipitation_unit") == "in" else 1.0

        def temp(v: float) -> float:
            return TemperatureConverter.convert(float(v), t_unit, UnitOfTemperature.CELSIUS)

        def wind(v: float) -> float:
            return SpeedConverter.convert(float(v), w_unit, UnitOfSpeed.METERS_PER_SECOND)

        first = depart.replace(minute=0, second=0, microsecond=0)
        last = first + timedelta(hours=hours)
        points = []
        for row in forecast:
            when = dt_util.parse_datetime(str(row.get("datetime")))
            if when is not None and first <= when < last and row.get("temperature") is not None:
                points.append(row)
        if points:
            winds = [wind(p["wind_speed"]) for p in points if p.get("wind_speed") is not None]
            return Weather(
                temp_c=sum(temp(p["temperature"]) for p in points) / len(points),
                rain_mm=max((float(p.get("precipitation") or 0) * rain_k for p in points), default=0),
                snow=any(p.get("condition") in SNOW_CONDITIONS for p in points),
                wind_ms=sum(winds) / len(winds) if winds else 0.0,
            )
        if attrs.get("temperature") is None:
            return None
        return Weather(
            temp_c=temp(attrs["temperature"]),
            rain_mm=1.0 if state.state in RAIN_CONDITIONS else 0.0,
            snow=state.state in SNOW_CONDITIONS,
            wind_ms=wind(attrs["wind_speed"]) if attrs.get("wind_speed") is not None else 0.0,
        )

    def _battery_pct(self) -> float | None:
        entity_id = self.config_entry.data.get(CONF_BATTERY)
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        try:
            return min(100.0, max(0.0, float(state.state)))  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            return None

    # ---------- update ----------

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self._compute()
        finally:
            if self._dirty:
                self._dirty = False
                await self._store.async_save(self._saved)

    async def _compute(self) -> dict[str, Any]:
        now = dt_util.now()
        settings = self.settings

        slots, month_avg = await self._update_electricity(now)
        if not slots and month_avg is None:
            raise UpdateFailed("No electricity prices from the Nord Pool integration yet")
        exr = await self._update_exchange_rate(now, slots)

        diesel = await self._update_diesel(now)
        if diesel is None:
            raise UpdateFailed("No diesel price available yet")
        diesel_price = diesel["eur"] * exr

        state, forecast = await self._update_weather()
        if state is None:
            raise UpdateFailed(f"Weather entity {self.config_entry.data[CONF_WEATHER]} is not available")

        depart = now + timedelta(hours=self.trip["leave_in_h"])
        battery = self._battery_pct()
        data: dict[str, Any] = {
            "diesel_price": diesel_price,
            "diesel_week": diesel["week"],
            "diesel_eur": diesel["eur"],
            "eur_sek": exr,
            "battery_pct": battery,
            "month_avg_spot": month_avg,
            "price_plan": self.config_entry.options.get(OPT_PRICE_PLAN, PLAN_MONTHLY),
            "tomorrow_prices": (now.date() + timedelta(days=1)) in self._slots,
        }
        for kind in (TRIP_SHORT, TRIP_LONG):
            km = self.trip[f"{kind}_km"]
            weather = self._trip_weather(state, forecast, depart, max(1, math.ceil(km / SPEED[kind])))
            if weather is None:
                raise UpdateFailed("The weather entity reports no temperature")
            data[kind] = calc_trip(
                kind, km, weather, settings, slots, now, month_avg, diesel_price, battery
            )
            data[f"{kind}_weather"] = weather
        if data[TRIP_LONG] is None or data[TRIP_SHORT] is None:
            raise UpdateFailed("No electricity price for today yet")
        data["home_price"] = data[TRIP_LONG].home_price
        data["spot_basis"] = data[TRIP_LONG].spot_basis
        data["fees_only"] = all_in_price(0.0, settings)
        return data
