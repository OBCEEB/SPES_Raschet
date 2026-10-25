#!/usr/bin/env python3
"""Тесты математического аудита (unittest, без внешних пакетов кроме numpy).

Запуск из research/lipetsk-cloud:
    python audit/math_audit.py
    python audit/timing_impact.py
    python audit/night_and_days_probe.py
    python -m unittest tests.test_math_audit -v
"""

from __future__ import annotations

import json
import math
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import lipetsk_collector as col  # noqa: E402
import lipetsk_gti as gti  # noqa: E402
import lipetsk_q_vs_ngo as qvn  # noqa: E402
import lipetsk_time as ltime  # noqa: E402

AUDIT = json.loads((ROOT / "audit" / "math_audit_numbers.json").read_text(encoding="utf-8"))
TIMING = json.loads((ROOT / "audit" / "timing_impact.json").read_text(encoding="utf-8"))
NIGHT = json.loads((ROOT / "audit" / "night_and_days_probe.json").read_text(encoding="utf-8"))


class Units(unittest.TestCase):
    def test_sp_table_is_latitude_month_interpolation(self):
        a = AUDIT["A_sp_table"]
        self.assertEqual(a["grid_latitudes_deg"], [40, 48, 56, 60])
        self.assertLess(a["max_abs_diff_stored_vs_recomputed_mjm2"], 0.001)

    def test_half_hour_integration_half_width_is_pi_over_48(self):
        self.assertTrue(AUDIT["B_h0"]["half_width_ok"])

    def test_missing_sunrise_clipping_is_negligible_for_kt(self):
        worst = AUDIT["B_h0"]["worst_month_for_Kt_denominator"]["code_over_clipped_slots_I0_gt20"]
        self.assertGreater(worst, 0.999)

    def test_smear_preserves_monthly_reference_sum(self):
        self.assertLess(AUDIT["C_smear"]["max_abs_month_sum_error_mjm2"], 0.05)
        self.assertTrue(AUDIT["C_smear"]["recomputed_equals_stored"])


class Collector(unittest.TestCase):
    def test_quadratic_loss_dimension(self):
        # q = max(0, η0 K G − a1 ΔT − a2 ΔT²): член a2 делится на G внутри η, не (ΔT/G)²
        g, k = 600.0, 1.0
        expected = col.ETA0 * k * g - col.A1 * col.DT_COLL - col.A2 * col.DT_COLL ** 2
        self.assertAlmostEqual(col.qdot(g, k), expected, places=9)

    def test_gcrit_at_unit_iam(self):
        gcrit = (col.A1 * col.DT_COLL + col.A2 * col.DT_COLL ** 2) / col.ETA0
        self.assertAlmostEqual(gcrit, 210.26, places=2)
        self.assertEqual(col.qdot(gcrit - 1e-6, 1.0), 0.0)
        self.assertGreater(col.qdot(gcrit + 1.0, 1.0), 0.0)

    def test_diffuse_iam_constant(self):
        self.assertAlmostEqual(col.IAM_DIFFUSE, 1.0 - col.B0 * (1.0 / math.cos(math.radians(60.0)) - 1.0), places=12)


class Reproduction(unittest.TestCase):
    def test_daily_energy_and_q_reproduce_from_hh_station(self):
        d = AUDIT["DE_daily_and_Q"]
        self.assertEqual(d["max_abs_H_diff_vs_daily_actualize_mjm2"], 0.0)
        self.assertEqual(d["Q_obs_reproduction_max_abs_diff_mjm2"], 0.0)

    def test_oracle_daily_energy_equals_measured_on_same_slots(self):
        self.assertLess(AUDIT["DE_daily_and_Q"]["oracle_daily_energy_max_abs_err_mjm2"], 1e-6)

    def test_ta_gate_does_not_zero_complete_day_slots(self):
        for season in AUDIT["DE_daily_and_Q"]["Ta_gate_by_season"].values():
            self.assertEqual(season["slots_without_Ta"], 0)

    def test_baseline_log_model_reproduces_stored_winter_metrics(self):
        f = AUDIT["F_baseline_log"]
        self.assertAlmostEqual(f["recomputed"]["winter"]["rmse"], f["stored_winter_Kt"]["rmse"], places=4)

    def test_yearwise_split_has_three_disjoint_test_years(self):
        self.assertEqual(AUDIT["K_split"]["years"], [2023, 2024, 2025])


class Timing(unittest.TestCase):
    def test_timestamps_match_solar_geometry(self):
        """Центр суточного хода GHI должен совпадать с ясным небом в пределах 30 мин."""
        shift = TIMING["shift_0h"]["winter"]["median_centroid_shift_min"]
        self.assertLess(abs(shift), 30.0, f"GHI смещён на {shift} мин относительно расчётного полудня")

    def test_i0_filter_drops_under_one_percent_of_energy(self):
        for season in ("winter", "other"):
            self.assertLess(TIMING["shift_0h"][season]["share_of_measured_energy_dropped"], 0.01)

    def test_extra_three_hour_shift_breaks_alignment(self):
        """Метки уже в MSK: повторный сдвиг +3 ч должен снова дать ~180 мин."""
        self.assertGreater(abs(TIMING["shift_3h"]["winter"]["median_centroid_shift_min"]), 150.0)

    def test_no_ghi_when_sun_below_minus_6_deg(self):
        self.assertEqual(NIGHT["ghi_by_elevation_band_new"]["-90..-6"]["share_q_gt_5"], 0.0)

    def test_file_labels_are_converted_once(self):
        t = datetime(2024, 6, 15, 9, 0)
        self.assertEqual(ltime.pyranometer_to_msk(t), t + timedelta(hours=3))
        self.assertEqual(ltime.asmg_to_msk(t), t + timedelta(hours=3))
        self.assertEqual(gti.MSK_H, ltime.MSK_H)


class SlotRules(unittest.TestCase):
    def test_half_hour_is_mean_of_minutes(self):
        t0 = datetime(2024, 6, 15, 12, 0)
        minutes = {t0 + timedelta(minutes=i): float(i) for i in range(30)}
        q, n = qvn.slot_q(minutes, t0)
        self.assertEqual(n, 30)
        self.assertAlmostEqual(q, 14.5)

    def test_short_slot_is_dropped(self):
        t0 = datetime(2024, 6, 15, 12, 0)
        minutes = {t0 + timedelta(minutes=i): 100.0 for i in range(qvn.MIN_MINUTES - 1)}
        self.assertEqual(qvn.slot_q(minutes, t0), (None, qvn.MIN_MINUTES - 1))

    def test_i0_is_zero_before_sunrise_and_clipped_at_sunrise(self):
        night = datetime(2024, 12, 15, 2, 0)
        self.assertEqual(gti.i0_wm2(night)[0], 0.0)
        day = datetime(2024, 12, 15, 12, 0)
        self.assertGreater(gti.i0_wm2(day)[0], 100.0)
        slots = [datetime(2024, 12, 15, 8, 0) + timedelta(minutes=30 * k) for k in range(6)]
        first = next(t for t in slots if gti.i0_wm2(t)[0] > 0)
        self.assertLess(gti.i0_wm2(first)[0], gti.i0_wm2(first + timedelta(minutes=30))[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
