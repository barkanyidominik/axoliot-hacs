"""Egyszerű, egy példányos config flow: egy kattintás a felületen."""

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN


class AxoliotConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow a Axoliot integrációhoz."""

    VERSION = 1

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(title="Axoliot", data={})
        return self.async_show_form(step_id="user")
