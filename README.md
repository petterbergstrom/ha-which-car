# Which Car Today

A Home Assistant integration that tells you which of two cars is cheaper to drive today: a Volvo EX40 or a Volkswagen Passat 2.0 TDI. It compares the energy cost of a short trip and a long trip using the current electricity price, the diesel price and the weather at the time you leave.

## What you need first

| Purpose | Integration | Notes |
|---|---|---|
| Electricity price | [Nord Pool](https://www.home-assistant.io/integrations/nordpool) | Built in. Set it up for your price area (SE3 for Lerum) in SEK. |
| Weather | [Met.no](https://www.home-assistant.io/integrations/met) | Built in. Its hourly forecast gives the temperature for your departure time. |
| EX40 charge level | [Volvo](https://www.home-assistant.io/integrations/volvo) | Optional. Without it, a fixed charge level from the settings is used. |

The diesel price needs no setup. The integration fetches the Swedish weekly average itself.

## Install

1. In HACS, open the menu, choose **Custom repositories**, add `https://github.com/petterbergstrom/ha-which-car` and pick the type **Integration**.
2. Download **Which Car Today** and restart Home Assistant.
3. Go to **Settings > Devices & services > Add integration** and search for **Which Car Today**.
4. Pick your Nord Pool entry, price area, Met.no weather entity and, if you have it, the EX40 battery charge level sensor.
5. Select **Configure** on the integration to review fees and car figures.

## Entities

For each trip type (short and long):

- **Recommendation**: Take the EX40, Take the Passat, or Either car (when the difference is under 3% or 1 kr). Its attributes hold the detail: energy and fuel used, consumption per 100 km, fast-charging share and the weather effect on each car.
- **EX40 cost** and **Passat cost** in SEK.
- **Saving** in SEK.
- **Break-even diesel price**: the pump price at which both cars cost the same.

Shared:

- **Diesel price** in SEK/L, with the bulletin week as an attribute.
- **Home electricity price** in SEK/kWh, all fees included.
- **Public charging price** in SEK/kWh, the fast charging price the trip costs use.
- **Short trip distance**, **Long trip distance** and **Leaving in** (hours from now), which you can change from a dashboard.

Values refresh every 15 minutes and whenever you change a trip setting.

## Settings and their defaults

The fee defaults follow Lerum Energi's published 2026 prices.

| Setting | Default | Source |
|---|---|---|
| Electricity contract | Monthly variable price | Lerum Energi "Rörligt elpris" |
| Supplier mark-up incl. certificates, excl. VAT | 8 öre/kWh | Estimate. Lerum Energi does not publish it, so check your invoice |
| Grid transfer fee, incl. VAT | 38.95 öre/kWh | Lerum Energi single tariff |
| Energy tax, incl. VAT | 45.0 öre/kWh | 36.0 öre excl. VAT in 2026 |
| VAT | 25% | |
| Fast charging on the road | 5.50 SEK/kWh | Estimate. Replaced by the fast charging price sensor, if you pick one |
| Fast charging price from a sensor | none | Optional. Any sensor with a price in SEK/kWh or öre/kWh |
| Home charger power | 11 kW | |
| Charging losses | 10% | |
| EX40, mixed roads / motorway at 20 °C | 17 / 21 kWh/100 km | Estimate |
| EX40 usable battery | 79 kWh | The larger battery pack. Replaced by the battery capacity sensor, if you pick one |
| EX40 battery capacity from a sensor | none | Optional. For example the Volvo integration's battery capacity sensor |
| EX40 charge level when leaving / lowest accepted | 90% / 10% | |
| Passat, mixed roads / motorway, warm engine | 6.0 / 5.4 L/100 km | Estimate |

### About the electricity contract

Lerum Energi's "Rörligt elpris" is billed at one volume-weighted price per month, so the hour you charge does not change what you pay. With that contract the integration uses the month-to-date average spot price as its best estimate of this month's price. The daily spot price then moves the result only slowly.

If you have "Rörligt kvartspris" instead, choose one of the quarter-hour options. The integration then prices the recharge at the cheapest hours left today and tomorrow, or at the day average.

## How the cost is calculated

- Electricity at home: (spot + mark-up) × (1 + VAT) + energy tax + grid fee, divided by charging efficiency.
- Whatever the battery cannot cover between the charge level when leaving and the lowest level you accept is priced as fast charging. The trip recommendation shows that energy and its cost (`ex40_fast_charge_kwh`, `ex40_fast_charge_cost_sek`), and the **Public charging price** sensor shows the price used and whether it came from your sensor or the fixed setting.
- Diesel: litres × the Swedish average pump price.
- Cold adds a one-off amount per trip (cabin and battery warm-up, or a cold engine) and a steady amount per kilometre (cabin heat, denser air, winter tyres). Rain, snow and wind above 8 m/s add a few percent.

The consumption figures are typical values. Adjust them to what your own cars show. Costs cover energy only, not wear, tax or parking.

## Example dashboard card

```yaml
type: entities
title: Which car today?
entities:
  - entity: sensor.which_car_today_short_trip_recommendation
  - entity: sensor.which_car_today_short_trip_saving
  - entity: number.which_car_today_short_trip_distance
  - type: divider
  - entity: sensor.which_car_today_long_trip_recommendation
  - entity: sensor.which_car_today_long_trip_saving
  - entity: number.which_car_today_long_trip_distance
  - type: divider
  - entity: number.which_car_today_leaving_in
  - entity: sensor.which_car_today_home_electricity_price
  - entity: sensor.which_car_today_diesel_price
```

## Example morning notification

```yaml
alias: Which car today
triggers:
  - trigger: time
    at: "06:30:00"
actions:
  - action: notify.notify
    data:
      title: Which car today?
      message: >-
        Short trip: {{ state_translated('sensor.which_car_today_short_trip_recommendation') }}
        (saves {{ states('sensor.which_car_today_short_trip_saving') | round(0) }} kr).
        Long trip: {{ state_translated('sensor.which_car_today_long_trip_recommendation') }}
        (saves {{ states('sensor.which_car_today_long_trip_saving') | round(0) }} kr).
```

## Data sources

- Spot prices: Nord Pool, through the Home Assistant Nord Pool integration.
- Diesel: European Commission Weekly Oil Bulletin (CC BY 4.0), via [fuel-prices.eu](https://www.fuel-prices.eu/Sweden/sv). It is a national average published weekly and converted from EUR with the exchange rate implied by Nord Pool's SEK and EUR prices.
- Weather: MET Norway, through the Home Assistant Met.no integration.

## Development

```
pip install -r requirements_test.txt
pytest -q
```
