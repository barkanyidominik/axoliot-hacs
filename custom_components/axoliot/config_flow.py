"""Egyszerű, egy példányos config flow, opciókkal a modulok beállításához."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_DHW_COP_ENABLED,
    CONF_DHW_HP_ENERGY,
    CONF_DHW_OUTDOOR,
    CONF_DHW_RES_ENERGY,
    CONF_DHW_TEMPERATURE,
    CONF_DHW_VOLUME,
    DEFAULT_DHW_VOLUME,
    DOMAIN,
)


class AxoliotConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow a Axoliot integrációhoz."""

    VERSION = 1

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(title="Axoliot", data={})
        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return AxoliotOptionsFlow()


DHW_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DHW_COP_ENABLED, default=False): selector.BooleanSelector(),
        vol.Optional(CONF_DHW_TEMPERATURE): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["water_heater", "sensor"])
        ),
        vol.Optional(CONF_DHW_HP_ENERGY): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class="energy")
        ),
        vol.Optional(CONF_DHW_RES_ENERGY): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class="energy")
        ),
        vol.Optional(CONF_DHW_OUTDOOR): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
        ),
        vol.Required(CONF_DHW_VOLUME, default=DEFAULT_DHW_VOLUME): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=10, max=1000, step=1, unit_of_measurement="L", mode="box"
            )
        ),
    }
)


class AxoliotOptionsFlow(OptionsFlow):
    """Modulok beállítása (jelenleg: melegvíz-hőszivattyú COP)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input.get(CONF_DHW_COP_ENABLED) and not (
                user_input.get(CONF_DHW_TEMPERATURE) and user_input.get(CONF_DHW_HP_ENERGY)
            ):
                errors["base"] = "dhw_missing_entities"
            else:
                return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                DHW_SCHEMA, user_input or self.config_entry.options
            ),
            errors=errors,
        )
