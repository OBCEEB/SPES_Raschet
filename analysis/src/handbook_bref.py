"""
Handbook baseline B_ref — Python reimplementation of C# lat interpolation.

Equivalence to product:
- ``MathTools.Interpolate``: linear between nearest latitude nodes; clamp at edges;
  result floored at 0 (``Math.Max(0, …)``).
- ``ClimatologyCalculationService.CalculateHourlyIrradiance``: per hour × direction.
- ``DailyTotalData``: single horizontal daily total per latitude (no month).

Limits vs product UI:
- Product Table 1 is **façade directions** (пр/р), not horizontal half-hourly GHI.
- Product labels DailyTotal as МДж/м² in the UI while ``SolarData`` comments say
  Вт·ч/м² — analysis follows **code comments (Вт·ч/м²)** per research decision.
- Tables are climatological (no calendar day/month): one diurnal profile per latitude.

Horizontal half-hourly B_ref used for M0/M1:
1. Interpolate ``DAILY_TOTAL_HORIZONTAL`` → E_day [W·h/m²].
2. Interpolate handbook sun altitude vs hour at site latitude.
3. Distribute E_day across hours with weights max(sin(alt), 0).
4. Hourly energy Wh/m² over a 1 h slot ⇒ mean irradiance W/m² of equal magnitude;
   both 30-min slots in that hour inherit the same mean W/m².
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd


def interpolate_lat(target_x: float, points: Dict[float, float]) -> float:
    """Match ``MathTools.Interpolate`` (nearest-neighbour linear, non-negative)."""
    if not points:
        return 0.0
    sorted_lats = sorted(points.keys())
    if len(sorted_lats) == 1:
        return max(0.0, float(points[sorted_lats[0]]))
    if target_x in points:
        return max(0.0, float(points[target_x]))

    x1 = None
    x2 = None
    for lat in sorted_lats:
        if lat < target_x:
            x1 = lat
        else:
            x2 = lat
            break
    if x1 is None:
        return max(0.0, float(points[sorted_lats[0]]))
    if x2 is None:
        return max(0.0, float(points[sorted_lats[-1]]))
    y1 = float(points[x1])
    y2 = float(points[x2])
    result = y1 + (target_x - x1) * (y2 - y1) / (x2 - x1)
    return max(0.0, result)


def _read_csv_lines(path: Path) -> List[str]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
        if text and "\ufffd" in text.splitlines()[0]:
            text = raw.decode("cp1251")
    except UnicodeDecodeError:
        text = raw.decode("cp1251")
    return text.splitlines()


def load_daily_total(handbook_dir: Path) -> Dict[float, float]:
    lines = _read_csv_lines(handbook_dir / "DailyTotalData.csv")
    points: Dict[float, float] = {}
    for line in lines[1:]:
        parts = line.split(";")
        if len(parts) < 2:
            continue
        try:
            lat = float(parts[0].replace(",", "."))
            val = float(parts[1].replace(",", "."))
        except ValueError:
            continue
        if val < 0:
            continue
        points[lat] = val
    return points


def load_irradiance_table(handbook_dir: Path) -> pd.DataFrame:
    lines = _read_csv_lines(handbook_dir / "IrradianceData.csv")
    header = [h.strip() for h in lines[0].split(";")]
    rows = []
    for line in lines[1:]:
        parts = line.split(";")
        if len(parts) < 3:
            continue
        try:
            lat = float(parts[0].replace(",", "."))
            hour = int(parts[1].strip())
        except ValueError:
            continue
        rec = {"latitude": lat, "start_hour": hour}
        for i, key in enumerate(header[2:]):
            if i + 2 >= len(parts):
                break
            try:
                val = float(parts[i + 2].replace(",", "."))
            except ValueError:
                val = -1.0
            rec[key] = val
        rows.append(rec)
    return pd.DataFrame(rows)


def load_sun_altitude_table(handbook_dir: Path) -> pd.DataFrame:
    """SunPosition_Altitude.csv: rows=hour, columns=latitude grid."""
    lines = _read_csv_lines(handbook_dir / "SunPosition_Altitude.csv")
    header = lines[0].split(";")
    lats = []
    for h in header[1:]:
        try:
            lats.append(float(h.replace(",", ".")))
        except ValueError:
            lats.append(float("nan"))
    rows = []
    for line in lines[1:]:
        parts = line.split(";")
        if not parts:
            continue
        try:
            hour = int(parts[0].strip())
        except ValueError:
            continue
        for j, lat in enumerate(lats):
            if j + 1 >= len(parts) or np.isnan(lat):
                continue
            try:
                val = float(parts[j + 1].replace(",", "."))
            except ValueError:
                continue
            if val < 0:
                continue
            rows.append({"start_hour": hour, "latitude": lat, "altitude_deg": val})
    return pd.DataFrame(rows)


def interpolate_hourly_altitude(handbook_dir: Path, latitude_deg: float) -> Dict[int, float]:
    table = load_sun_altitude_table(handbook_dir)
    out: Dict[int, float] = {}
    for hour, grp in table.groupby("start_hour"):
        pts = {float(r.latitude): float(r.altitude_deg) for r in grp.itertuples()}
        out[int(hour)] = interpolate_lat(latitude_deg, pts)
    return out


def horizontal_bref_hourly_wm2(
    handbook_dir: Path,
    latitude_deg: float,
) -> Dict[int, float]:
    """
    Climatological hourly horizontal B_ref as mean W/m² over each clock hour.

    Handbook daily total is W·h/m² (code comment). Distributing by handbook
    sun-altitude weights yields hourly W·h/m²; for a 1-hour interval that equals
    mean W/m².
    """
    daily_pts = load_daily_total(handbook_dir)
    e_day = interpolate_lat(latitude_deg, daily_pts)  # W·h/m² per day
    alt = interpolate_hourly_altitude(handbook_dir, latitude_deg)
    weights = {h: max(float(np.sin(np.radians(a))), 0.0) for h, a in alt.items()}
    wsum = sum(weights.values())
    if wsum <= 0:
        return {h: 0.0 for h in sorted(alt)}
    return {h: e_day * (w / wsum) for h, w in weights.items()}


def attach_bref(
    df: pd.DataFrame,
    handbook_dir: Path,
    latitude_deg: float,
    time_col: str = "obs_time",
) -> pd.DataFrame:
    """Add ``B_ref`` (W/m² mean over the half-hour) and diagnostic columns."""
    out = df.copy()
    hourly = horizontal_bref_hourly_wm2(handbook_dir, latitude_deg)
    e_day = interpolate_lat(latitude_deg, load_daily_total(handbook_dir))
    hours = pd.DatetimeIndex(out[time_col]).hour
    out["B_ref"] = np.array([float(hourly.get(int(h), 0.0)) for h in hours], dtype=float)
    out["B_ref_daily_total_wh_m2"] = float(e_day)
    out["B_ref_method"] = "daily_total_x_handbook_sin_altitude"

    # Diagnostic: south façade пр+р (Wh/m² per hour ⇒ W/m² mean)
    try:
        irr = load_irradiance_table(handbook_dir)
        pr = next((c for c in irr.columns if c.strip() == "Ю пр"), None)
        dif = next((c for c in irr.columns if c.strip() == "Ю р"), None)
        if pr and dif:
            south: Dict[int, float] = {}
            for hour, grp in irr.groupby("start_hour"):
                pts_pr = {
                    float(lat): float(val)
                    for lat, val in zip(grp["latitude"], grp[pr])
                    if float(val) >= 0
                }
                pts_dif = {
                    float(lat): float(val)
                    for lat, val in zip(grp["latitude"], grp[dif])
                    if float(val) >= 0
                }
                south[int(hour)] = interpolate_lat(latitude_deg, pts_pr) + interpolate_lat(
                    latitude_deg, pts_dif
                )
            out["B_ref_south_facade_wm2"] = np.array(
                [float(south.get(int(h), 0.0)) for h in hours], dtype=float
            )
        else:
            out["B_ref_south_facade_wm2"] = np.nan
    except Exception:  # noqa: BLE001 — diagnostic only
        out["B_ref_south_facade_wm2"] = np.nan
    return out
