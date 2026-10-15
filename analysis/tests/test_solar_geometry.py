"""Tests for solar geometry / clear-sky (no SQLite required)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from solar_geometry import (  # noqa: E402
    attach_solar_and_clearsky,
    clearsky_ghi_ineichen,
    solar_position,
)

LAT = 52.135409
LON = 39.163510


class TestSolarGeometry(unittest.TestCase):
    def test_night_approx_zero_gcs(self):
        # Midwinter night at Kon’-Kolodez’ (MSK)
        times = pd.date_range("2024-12-21 00:00:00", periods=6, freq="30min")
        pos = solar_position(times, LAT, LON)
        self.assertTrue((pos["solar_elevation_deg"] < 0).all())
        ghi = clearsky_ghi_ineichen(pos["solar_zenith_deg"].to_numpy(), times.dayofyear.to_numpy())
        self.assertTrue(np.all(ghi == 0.0))

    def test_summer_noon_elevation_sane(self):
        # Approximate solar noon MSK (~10:00 UTC → 13:00 MSK)
        t = pd.Timestamp("2024-06-21 13:00:00")
        pos = solar_position([t], LAT, LON)
        elev = float(pos["solar_elevation_deg"].iloc[0])
        # At 52°N summer solstice noon elev ≈ 90-52+23.4 ≈ 61°
        self.assertGreater(elev, 50.0)
        self.assertLess(elev, 70.0)
        ghi = clearsky_ghi_ineichen(
            pos["solar_zenith_deg"].to_numpy(),
            np.array([t.dayofyear], dtype=float),
        )
        self.assertGreater(float(ghi[0]), 600.0)
        self.assertLess(float(ghi[0]), 1200.0)

    def test_winter_noon_lower_than_summer(self):
        summer = solar_position([pd.Timestamp("2024-06-21 13:00:00")], LAT, LON)
        winter = solar_position([pd.Timestamp("2024-12-21 12:30:00")], LAT, LON)
        self.assertGreater(
            float(summer["solar_elevation_deg"].iloc[0]),
            float(winter["solar_elevation_deg"].iloc[0]),
        )

    def test_k_obs_null_at_night(self):
        df = pd.DataFrame(
            {
                "obs_time": pd.to_datetime(
                    ["2024-12-21 01:00:00", "2024-06-21 13:00:00"]
                ),
                "radiation_wm2": [0.0, 800.0],
            }
        )
        out = attach_solar_and_clearsky(df, latitude_deg=LAT, longitude_deg=LON)
        self.assertEqual(int(out.loc[0, "is_daytime"]), 0)
        self.assertTrue(pd.isna(out.loc[0, "k_obs"]))
        self.assertEqual(float(out.loc[0, "G_cs"]), 0.0)
        self.assertEqual(int(out.loc[1, "is_daytime"]), 1)
        self.assertFalse(pd.isna(out.loc[1, "k_obs"]))
        self.assertGreater(float(out.loc[1, "G_cs"]), 0.0)


class TestHandbookBref(unittest.TestCase):
    def test_interpolate_matches_node(self):
        from handbook_bref import interpolate_lat

        pts = {48.0: 100.0, 52.0: 200.0, 56.0: 300.0}
        self.assertAlmostEqual(interpolate_lat(52.0, pts), 200.0)
        mid = interpolate_lat(50.0, pts)
        self.assertGreater(mid, 100.0)
        self.assertLess(mid, 200.0)

    def test_horizontal_bref_nonneg(self):
        from handbook_bref import horizontal_bref_hourly_wm2

        handbook = Path(__file__).resolve().parents[2] / "data" / "raw" / "handbook"
        if not handbook.is_dir():
            self.skipTest("handbook dir missing")
        hourly = horizontal_bref_hourly_wm2(handbook, LAT)
        self.assertTrue(len(hourly) > 0)
        self.assertTrue(all(v >= 0 for v in hourly.values()))
        self.assertGreater(sum(hourly.values()), 0.0)


if __name__ == "__main__":
    unittest.main()
