"""Melegvíz-hőszivattyú látszólagos COP-ja ciklusonként (HA-független, tesztelhető logika).

Ciklus: amíg a periodikus (pl. 2 órás) fogyasztási ablakok bármelyikében a hőszivattyú
vagy a fűtőszál fogyasztása a küszöb fölött van. Az első üresjárati ablak zárja le.

    leadott hő [kWh] = (T_max - T_min) * térfogat [l] * 1,163 Wh/(l*K) / 1000
    COP              = leadott hő / (hőszivattyú + fűtőszál kWh)

A COP "látszólagos": a ciklus alatti vízvételt nem látja, ezért ilyenkor alulbecsül.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any

WATER_KWH_PER_LITER_KELVIN = 1.163 / 1000
DEFAULT_ACTIVE_THRESHOLD_KWH = 0.02
MIN_CYCLE_ENERGY_KWH = 0.05


@dataclass
class CycleResult:
    """Egy lezárt ciklus adatai."""

    start: str | None
    end: str
    t_start: float | None
    t_end: float | None
    heat_kwh: float
    hp_kwh: float
    res_kwh: float
    cop: float | None
    outdoor_avg: float | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CycleTracker:
    """A futó ciklus állapota. JSON-ként menthető és visszaállítható."""

    volume_l: float = 110.0
    threshold_kwh: float = DEFAULT_ACTIVE_THRESHOLD_KWH
    active: bool = False
    t_min: float | None = None
    t_max: float | None = None
    e_hp: float = 0.0
    e_res: float = 0.0
    o_sum: float = 0.0
    o_n: int = 0
    start: str | None = None
    last_bucket: str | None = None

    # --- mentés / visszaállítás -------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None, **overrides: Any) -> CycleTracker:
        names = {f.name for f in fields(cls)}
        values = {k: v for k, v in (data or {}).items() if k in names}
        values.update(overrides)
        return cls(**values)

    # --- események ---------------------------------------------------------------

    def on_temperature(self, temp: float | None) -> None:
        """Tartályhőmérséklet változott."""
        if temp is None:
            return
        if self.active:
            self.t_max = temp if self.t_max is None else max(self.t_max, temp)
        else:
            self.t_min = temp if self.t_min is None else min(self.t_min, temp)

    def on_bucket(
        self,
        *,
        hp_kwh: float | None,
        res_kwh: float | None,
        temp: float | None,
        outdoor: float | None,
        bucket_start: str | None,
        bucket_end: str,
        window_min_temp: float | None = None,
    ) -> CycleResult | None:
        """Egy fogyasztási ablak lezárult. A hőszivattyú és a fűtőszál adata együtt érkezik.

        ``window_min_temp``: az ablak alatti legkisebb tartályhőmérséklet (pl. a recorderből),
        hogy egy újraindítás utáni ciklus kezdőhőmérséklete is pontos legyen.
        Ha ezzel lezárult egy ciklus, visszaadja az eredményét.
        """
        hp = max(hp_kwh or 0.0, 0.0)
        res = max(res_kwh or 0.0, 0.0)

        if hp > self.threshold_kwh or res > self.threshold_kwh:
            if not self.active:
                self.active = True
                self.start = bucket_start
                for candidate in (window_min_temp, temp):
                    if candidate is not None and (self.t_min is None or candidate < self.t_min):
                        self.t_min = candidate
                self.t_max = temp
            elif temp is not None:
                self.t_max = temp if self.t_max is None else max(self.t_max, temp)
            self.e_hp += hp
            self.e_res += res
            if hp > self.threshold_kwh and outdoor is not None:
                self.o_sum += outdoor
                self.o_n += 1
            return None

        result = self._close(bucket_end) if self.active else None
        self._reset(temp)
        return result

    # --- belső -------------------------------------------------------------------

    def _close(self, end: str) -> CycleResult:
        delta_t = (
            (self.t_max - self.t_min)
            if self.t_max is not None and self.t_min is not None
            else 0.0
        )
        heat = delta_t * self.volume_l * WATER_KWH_PER_LITER_KELVIN
        energy = self.e_hp + self.e_res
        cop = round(heat / energy, 2) if energy > MIN_CYCLE_ENERGY_KWH else None
        return CycleResult(
            start=self.start,
            end=end,
            t_start=self.t_min,
            t_end=self.t_max,
            heat_kwh=round(heat, 2),
            hp_kwh=round(self.e_hp, 3),
            res_kwh=round(self.e_res, 3),
            cop=cop,
            outdoor_avg=round(self.o_sum / self.o_n, 1) if self.o_n else None,
        )

    def _reset(self, temp: float | None) -> None:
        self.active = False
        self.e_hp = self.e_res = self.o_sum = 0.0
        self.o_n = 0
        self.start = None
        self.t_min = self.t_max = temp
