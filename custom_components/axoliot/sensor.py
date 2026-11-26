"""Axoliot szenzorok: melegvíz-hőszivattyú COP modul."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import ExtraStoredData, RestoredExtraData, RestoreEntity

from .const import (
    CONF_DHW_COP_ENABLED,
    CONF_DHW_HP_ENERGY,
    CONF_DHW_TEMPERATURE,
    DOMAIN,
)
from .dhw_cop import DhwCopMonitor


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Szenzorok létrehozása, ha a COP modul be van kapcsolva az opciókban."""
    options = entry.options
    if not (
        options.get(CONF_DHW_COP_ENABLED)
        and options.get(CONF_DHW_TEMPERATURE)
        and options.get(CONF_DHW_HP_ENERGY)
    ):
        return

    monitor = DhwCopMonitor(hass, dict(options))
    device = DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_dhw_cop")},
        name="Melegvíz hőszivattyú",
        manufacturer="Axoliot",
        model="DHW COP monitor",
    )
    async_add_entities(
        [
            DhwCopSensor(entry, monitor, device),
            DhwCycleOutdoorSensor(entry, monitor, device),
        ]
    )


class _DhwBase(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, monitor: DhwCopMonitor, device: DeviceInfo) -> None:
        self._monitor = monitor
        self._attr_device_info = device
        self._attr_unique_id = f"{entry.entry_id}_{self._attr_translation_key}"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._monitor.add_listener(self.async_write_ha_state))


class DhwCopSensor(_DhwBase, RestoreEntity):
    """Az utolsó lezárt ciklus COP-ja; attribútumban a futó és az utolsó ciklus adatai.

    Ez az entitás menti és állítja vissza a ciklus-követő állapotát, és indítja a figyelőt.
    """

    _attr_translation_key = "dhw_cop"
    _attr_icon = "mdi:heat-pump"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_extra_data()) is not None:
            self._monitor.restore(last.as_dict())
        self._monitor.start()
        self.async_on_remove(self._monitor.stop)
        self._monitor.notify()  # a visszaállított értékek megjelenítése

    @property
    def native_value(self) -> float | None:
        return self._monitor.cop

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        t = self._monitor.tracker
        attrs: dict[str, Any] = {
            "cycle_active": t.active,
            "cycle_start": t.start,
            "cycle_t_min": t.t_min,
            "cycle_t_max": t.t_max,
            "cycle_hp_kwh": round(t.e_hp, 3),
            "cycle_resistor_kwh": round(t.e_res, 3),
            "tank_volume_l": t.volume_l,
        }
        for key, value in (self._monitor.last_result or {}).items():
            attrs[f"last_{key}"] = value
        return attrs

    @property
    def extra_restore_state_data(self) -> ExtraStoredData:
        return RestoredExtraData(self._monitor.export())


class DhwCycleOutdoorSensor(_DhwBase):
    """Az utolsó lezárt ciklus alatti átlagos külső hőmérséklet."""

    _attr_translation_key = "dhw_cycle_outdoor_avg"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    @property
    def native_value(self) -> float | None:
        return (self._monitor.last_result or {}).get("outdoor_avg")
