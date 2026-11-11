"""Config and options flow for Which Car Today."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector as sel

from .const import (
    AREAS,
    CONF_AREA,
    CONF_BATTERY,
    CONF_NORDPOOL_ENTRY,
    CONF_WEATHER,
    DEFAULTS,
    DOMAIN,
    OPT_BATTERY_KWH,
    OPT_CHARGE_LOSS,
    OPT_CHARGER_KW,
    OPT_DIESEL_LONG,
    OPT_DIESEL_SHORT,
    OPT_EV_LONG,
    OPT_EV_SHORT,
    OPT_FAST_PRICE,
    OPT_GRID,
    OPT_MARKUP,
    OPT_PRICE_PLAN,
    OPT_RESERVE_PCT,
    OPT_START_PCT,
    OPT_TAX,
    OPT_VAT,
    PLANS,
)


def _num(low: float, high: float, step: float, unit: str) -> sel.NumberSelector:
    return sel.NumberSelector(
        sel.NumberSelectorConfig(
            min=low, max=high, step=step, unit_of_measurement=unit, mode=sel.NumberSelectorMode.BOX
        )
    )


NUMBER_FIELDS: dict[str, sel.NumberSelector] = {
    OPT_MARKUP: _num(0, 100, 0.01, "öre/kWh"),
    OPT_GRID: _num(0, 300, 0.01, "öre/kWh"),
    OPT_TAX: _num(0, 150, 0.01, "öre/kWh"),
    OPT_VAT: _num(0, 50, 0.5, "%"),
    OPT_FAST_PRICE: _num(0, 20, 0.05, "SEK/kWh"),
    OPT_CHARGER_KW: _num(1.4, 22, 0.1, "kW"),
    OPT_CHARGE_LOSS: _num(0, 30, 1, "%"),
    OPT_EV_SHORT: _num(8, 40, 0.1, "kWh/100 km"),
    OPT_EV_LONG: _num(8, 40, 0.1, "kWh/100 km"),
    OPT_BATTERY_KWH: _num(20, 150, 1, "kWh"),
    OPT_START_PCT: _num(20, 100, 1, "%"),
    OPT_RESERVE_PCT: _num(0, 50, 1, "%"),
    OPT_DIESEL_SHORT: _num(3, 15, 0.1, "L/100 km"),
    OPT_DIESEL_LONG: _num(3, 15, 0.1, "L/100 km"),
}


class WhichCarConfigFlow(ConfigFlow, domain=DOMAIN):
    """Pick the source integrations."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entries = self.hass.config_entries.async_entries("nordpool")
        if not entries:
            return self.async_abort(reason="nordpool_missing")
        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title="Which car today", data=user_input, options=dict(DEFAULTS)
            )
        schema = vol.Schema(
            {
                vol.Required(CONF_NORDPOOL_ENTRY, default=entries[0].entry_id): sel.ConfigEntrySelector(
                    sel.ConfigEntrySelectorConfig(integration="nordpool")
                ),
                vol.Required(CONF_AREA, default="SE3"): sel.SelectSelector(
                    sel.SelectSelectorConfig(options=AREAS, mode=sel.SelectSelectorMode.DROPDOWN)
                ),
                vol.Required(CONF_WEATHER): sel.EntitySelector(
                    sel.EntitySelectorConfig(domain="weather")
                ),
                vol.Optional(CONF_BATTERY): sel.EntitySelector(
                    sel.EntitySelectorConfig(domain="sensor")
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return WhichCarOptionsFlow()


class WhichCarOptionsFlow(OptionsFlow):
    """Fees, charging and car settings."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = {**DEFAULTS, **self.config_entry.options}
        fields: dict[Any, Any] = {
            vol.Required(OPT_PRICE_PLAN, default=current[OPT_PRICE_PLAN]): sel.SelectSelector(
                sel.SelectSelectorConfig(
                    options=PLANS, translation_key="price_plan", mode=sel.SelectSelectorMode.LIST
                )
            )
        }
        for key, field in NUMBER_FIELDS.items():
            fields[vol.Required(key, default=current[key])] = field
        return self.async_show_form(step_id="init", data_schema=vol.Schema(fields))
