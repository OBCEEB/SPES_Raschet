#!/usr/bin/env python3
"""Тесты математического аудита (unittest, без внешних пакетов кроме numpy).

Запуск из research/lipetsk-cloud:
    python audit/math_audit.py
    python audit/timing_impact.py
    python -m unittest tests.test_math_audit -v

Тест test_timestamps_match_solar_geometry сейчас ПАДАЕТ намеренно: он фиксирует
блокирующую ошибку шкалы времени пиранометра (см. reports/math_audit_before_writing.md).
"""

from __future__ import annotations

import json
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import lipetsk_collector as col  # noqa: E402

AUDIT = json.loads((ROOT / "audit" / "math_audit_numbers.json").read_text(encoding="utf-8"))
TIMING = json.loads((ROOT / "audit" / "timing_impact.json").read_text(encoding="utf-8"))


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
        # KD_DIFF — угловой модификатор рассеянной (IAM_diffuse), не доля рассеянной
        self.assertAlmostEqual(col.KD_DIFF, 1.0 - col.B0 * (1.0 / math.cos(math.radians(60.0)) - 1.0), places=12)


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

    def test_three_hour_relabel_removes_the_offset(self):
        self.assertLess(abs(TIMING["shift_3h"]["winter"]["median_centroid_shift_min"]), 30.0)
        self.assertLess(TIMING["shift_3h"]["winter"]["share_of_measured_energy_dropped"], 0.01)


if __name__ == "__main__":
    unittest.main(verbosity=2)
