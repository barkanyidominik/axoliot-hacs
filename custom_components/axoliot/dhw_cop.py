"""Melegvíz-hőszivattyú COP modul: HA-oldali figyelő a ciklus-követő logika köré.

Bemenetek (az integráció opcióiban választhatók):
- tartályhőmérséklet: ``water_heater`` entitás (``current_temperature``) vagy hőmérséklet szenzor
- hőszivattyú és (opcionálisan) fűtőszál fogyasztása: periodikusan nullázódó kWh szenzorok,
  amelyek minden ablak végén egy értéket küldenek (pl. ``last_reset`` attribútummal)
- (opcionális) külső hőmérséklet
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.util import dt as dt_util

from .const import (
    CONF_DHW_HP_ENERGY,
    CONF_DHW_OUTDOOR,
    CONF_DHW_RES_ENERGY,
    CONF_DHW_TEMPERATURE,
    CONF_DHW_VOLUME,
    DEFAULT_DHW_VOLUME,
)
from .dhw_cop_tracker import CycleTracker

_LOGGER = logging.getLogger(__name__)

# A hőszivattyú és a fűtőszál ablakértéke közel egyszerre érkezik: ennyit várunk, hogy együtt
# dolgozzuk fel őket.
BUCKET_SETTLE_SECONDS = 30
# Ha a szenzor nem ad last_reset-et, ekkora ablakot feltételezünk.
DEFAULT_BUCKET_LENGTH = timedelta(hours=2)


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _usable(state: State | None) -> bool:
    return state is not None and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)


class DhwCopMonitor:
    """Állapotváltozások figyelése, ciklusok követése, eredmény tárolása."""

    def __init__(self, hass: HomeAssistant, options: dict[str, Any]) -> None:
        self.hass = hass
        self.temp_entity: str = options[CONF_DHW_TEMPERATURE]
        self.hp_entity: str = options[CONF_DHW_HP_ENERGY]
        self.res_entity: str | None = options.get(CONF_DHW_RES_ENERGY) or None
        self.outdoor_entity: str | None = options.get(CONF_DHW_OUTDOOR) or None
        self.volume = float(options.get(CONF_DHW_VOLUME) or DEFAULT_DHW_VOLUME)

        self.tracker = CycleTracker(volume_l=self.volume)
        self.cop: float | None = None
        self.last_result: dict[str, Any] | None = None

        self._listeners: list[Callable[[], None]] = []
        self._unsubs: list[CALLBACK_TYPE] = []
        self._pending: CALLBACK_TYPE | None = None

    # --- mentés / visszaállítás -------------------------------------------------

    def export(self) -> dict[str, Any]:
        return {
            "tracker": self.tracker.to_dict(),
            "cop": self.cop,
            "last_result": self.last_result,
        }

    def restore(self, data: dict[str, Any] | None) -> None:
        if not data:
            return
        # A térfogat mindig az aktuális beállításból jön, nem a mentésből.
        self.tracker = CycleTracker.from_dict(data.get("tracker"), volume_l=self.volume)
        self.cop = _float(data.get("cop"))
        self.last_result = data.get("last_result")

    # --- figyelők ----------------------------------------------------------------

    @callback
    def add_listener(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        self._listeners.append(listener)

        @callback
        def _remove() -> None:
            self._listeners.remove(listener)

        return _remove

    @callback
    def notify(self) -> None:
        for listener in list(self._listeners):
            listener()

    @callback
    def start(self) -> None:
        self._unsubs.append(
            async_track_state_change_event(self.hass, [self.temp_entity], self._on_temperature)
        )
        energy = [e for e in (self.hp_entity, self.res_entity) if e]
        self._unsubs.append(async_track_state_change_event(self.hass, energy, self._on_energy))

    @callback
    def stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if self._pending:
            self._pending()
            self._pending = None

    # --- beolvasás ---------------------------------------------------------------

    def _temperature_of(self, state: State | None) -> float | None:
        if not _usable(state):
            return None
        # A recorder LazyState objektumának nincs .domain attribútuma, az entity_id-ja viszont van.
        if state.entity_id.startswith("water_heater."):
            return _float(state.attributes.get("current_temperature"))
        return _float(state.state)

    def _current_temperature(self) -> float | None:
        return self._temperature_of(self.hass.states.get(self.temp_entity))

    def _value(self, entity_id: str | None) -> float | None:
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        return _float(state.state) if _usable(state) else None

    # --- eseménykezelők ----------------------------------------------------------

    @callback
    def _on_temperature(self, event: Event[EventStateChangedData]) -> None:
        temp = self._temperature_of(event.data["new_state"])
        if temp is None:
            return
        self.tracker.on_temperature(temp)
        self.notify()

    @callback
    def _on_energy(self, event: Event[EventStateChangedData]) -> None:
        # Az ablakérték akkor is új eseményt ad, ha a szám nem változik (last_reset frissül).
        if not _usable(event.data["new_state"]):
            return
        if self._pending:
            self._pending()
        self._pending = async_call_later(self.hass, BUCKET_SETTLE_SECONDS, self._settled)

    @callback
    def _settled(self, _now: datetime) -> None:
        self._pending = None
        self.hass.async_create_task(self._process_bucket(), eager_start=True)

    async def _process_bucket(self) -> None:
        hp_state = self.hass.states.get(self.hp_entity)
        res_state = self.hass.states.get(self.res_entity) if self.res_entity else None
        if not _usable(hp_state) and not _usable(res_state):
            return

        # Egy ablakot csak egyszer dolgozunk fel (azonosító: last_reset, ha van).
        ref = hp_state if _usable(hp_state) else res_state
        key = str(ref.attributes.get("last_reset") or ref.last_updated.isoformat())
        if key == self.tracker.last_bucket:
            return
        self.tracker.last_bucket = key

        bucket_end = ref.last_updated
        bucket_start = dt_util.parse_datetime(str(ref.attributes.get("last_reset") or ""))
        if bucket_start is None or bucket_start >= bucket_end:
            bucket_start = bucket_end - DEFAULT_BUCKET_LENGTH

        hp = self._value(self.hp_entity)
        res = self._value(self.res_entity)
        window_min = None
        if not self.tracker.active and max(hp or 0, res or 0) > self.tracker.threshold_kwh:
            window_min = await self._window_min_temperature(bucket_start, bucket_end)

        result = self.tracker.on_bucket(
            hp_kwh=hp,
            res_kwh=res,
            temp=self._current_temperature(),
            outdoor=self._value(self.outdoor_entity),
            bucket_start=bucket_start.isoformat(),
            bucket_end=bucket_end.isoformat(),
            window_min_temp=window_min,
        )
        if result is not None:
            self.last_result = result.as_dict()
            if result.cop is not None:
                self.cop = result.cop
            _LOGGER.debug("DHW COP ciklus lezárva: %s", self.last_result)
        self.notify()

    async def _window_min_temperature(self, start: datetime, end: datetime) -> float | None:
        """A legkisebb tartályhőmérséklet az ablakban, a recorder előzményeiből."""
        try:
            from homeassistant.components.recorder import get_instance, history  # noqa: PLC0415

            states = await get_instance(self.hass).async_add_executor_job(
                history.state_changes_during_period,
                self.hass,
                start,
                end,
                self.temp_entity,
            )
            temps = [
                t
                for t in (self._temperature_of(s) for s in states.get(self.temp_entity, []))
                if t is not None
            ]
        except Exception:  # noqa: BLE001 - az ablak-minimum csak pontosítás, nem végzetes
            _LOGGER.warning("Az ablak-minimum lekérdezése sikertelen", exc_info=True)
            return None
        return min(temps) if temps else None
