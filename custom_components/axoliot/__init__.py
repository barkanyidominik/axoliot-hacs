"""Axoliot: saját Home Assistant kiegészítések egy csomagban."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from . import matter
from .const import DOMAIN

__all__ = ["DOMAIN"]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Opcionális YAML-os betöltés (a felületi hozzáadás is működik)."""
    matter.async_register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Betöltés a felületről hozzáadott bejegyzésből."""
    matter.async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Szolgáltatások eltávolítása."""
    matter.async_remove_services(hass)
    return True
