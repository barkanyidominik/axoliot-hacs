"""A ciklus-követő logika tesztjei (Home Assistant nélkül futtathatók).

Futtatás a repó gyökeréből:  python -m unittest discover -s tests
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

# A modult közvetlenül töltjük be, hogy a csomag __init__.py-ja (HA importok) ne fusson.
_PATH = Path(__file__).parents[1] / "custom_components" / "axoliot" / "dhw_cop_tracker.py"
_spec = importlib.util.spec_from_file_location("dhw_cop_tracker", _PATH)
tracker_mod = importlib.util.module_from_spec(_spec)
sys.modules["dhw_cop_tracker"] = tracker_mod
_spec.loader.exec_module(tracker_mod)
CycleTracker = tracker_mod.CycleTracker


def bucket(t: CycleTracker, hp, temp, res=0.0, outdoor=None, end="t", window_min=None):
    return t.on_bucket(
        hp_kwh=hp,
        res_kwh=res,
        temp=temp,
        outdoor=outdoor,
        bucket_start="s",
        bucket_end=end,
        window_min_temp=window_min,
    )


class CycleTrackerTest(unittest.TestCase):
    def test_normal_cycle(self):
        """41 -> 60 °C, 1,0 kWh: COP = 19 * 110 * 1,163 / 1000 / 1,0 = 2,43."""
        t = CycleTracker(volume_l=110)
        self.assertIsNone(bucket(t, 0.0, 42))
        for temp in (42, 41):
            t.on_temperature(temp)
        self.assertIsNone(bucket(t, 0.4, 47, outdoor=6.0))
        for temp in (50, 55, 60):
            t.on_temperature(temp)
        self.assertIsNone(bucket(t, 0.6, 60, outdoor=9.0))
        result = bucket(t, 0.0, 60, end="end")
        self.assertIsNotNone(result)
        self.assertEqual(result.t_start, 41)
        self.assertEqual(result.t_end, 60)
        self.assertAlmostEqual(result.hp_kwh, 1.0)
        self.assertEqual(result.cop, 2.43)
        self.assertEqual(result.outdoor_avg, 7.5)
        self.assertEqual(result.end, "end")
        self.assertFalse(t.active)

    def test_stalled_cycle_counts_idle_running(self):
        """A csúcs utáni, emelkedés nélküli futás is a ciklus része (alacsony COP)."""
        t = CycleTracker(volume_l=110)
        bucket(t, 0.0, 42)
        t.on_temperature(41)
        bucket(t, 0.3, 45)
        t.on_temperature(49)
        bucket(t, 0.6, 49)
        t.on_temperature(50)
        bucket(t, 0.6, 50)
        result = bucket(t, 0.005, 50)
        self.assertEqual(result.t_start, 41)
        self.assertEqual(result.t_end, 50)
        self.assertAlmostEqual(result.hp_kwh, 1.5)
        self.assertEqual(result.cop, round(9 * 110 * 1.163 / 1000 / 1.5, 2))

    def test_resistor_only_bucket_keeps_cycle_open(self):
        """Ha csak a fűtőszál megy egy ablakban, a ciklus nem zárul le idő előtt."""
        t = CycleTracker(volume_l=110)
        bucket(t, 0.0, 45)
        bucket(t, 0.3, 50)
        self.assertIsNone(bucket(t, 0.0, 60, res=1.2))
        result = bucket(t, 0.0, 60)
        self.assertAlmostEqual(result.hp_kwh, 0.3)
        self.assertAlmostEqual(result.res_kwh, 1.2)
        self.assertEqual(result.cop, round(15 * 110 * 1.163 / 1000 / 1.5, 2))

    def test_window_min_from_history(self):
        """Újraindítás után a recorderből kapott ablak-minimum lesz a kezdőhőmérséklet."""
        t = CycleTracker(volume_l=110)
        t.on_temperature(48)  # újraindítás után már csak ezt látjuk
        bucket(t, 0.6, 52, window_min=40)
        result = bucket(t, 0.0, 52)
        self.assertEqual(result.t_start, 40)

    def test_temperature_drop_while_idle_lowers_start(self):
        t = CycleTracker(volume_l=110)
        bucket(t, 0.0, 55)
        for temp in (50, 38, 36):
            t.on_temperature(temp)
        bucket(t, 0.5, 45)
        result = bucket(t, 0.0, 58)
        self.assertEqual(result.t_start, 36)

    def test_tiny_energy_gives_no_cop(self):
        t = CycleTracker(volume_l=110, threshold_kwh=0.02)
        bucket(t, 0.0, 50)
        bucket(t, 0.03, 51)
        result = bucket(t, 0.0, 51)
        self.assertIsNotNone(result)
        self.assertIsNone(result.cop)

    def test_unavailable_values_are_ignored_as_zero(self):
        t = CycleTracker(volume_l=110)
        bucket(t, 0.0, 40)
        bucket(t, 0.6, 50)
        self.assertTrue(t.active)
        # Hiányzó (None) adat üresjárati ablaknak számít, és lezárja a ciklust.
        result = bucket(t, None, 50)
        self.assertIsNotNone(result)

    def test_roundtrip_serialization(self):
        t = CycleTracker(volume_l=110)
        bucket(t, 0.0, 40)
        bucket(t, 0.6, 50, outdoor=3.0)
        restored = CycleTracker.from_dict(t.to_dict(), volume_l=120)
        self.assertTrue(restored.active)
        self.assertEqual(restored.t_min, 40)
        self.assertEqual(restored.e_hp, 0.6)
        self.assertEqual(restored.volume_l, 120)
        self.assertEqual(CycleTracker.from_dict({"unknown": 1}).volume_l, 110.0)


if __name__ == "__main__":
    unittest.main()
