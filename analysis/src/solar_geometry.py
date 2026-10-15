"""
Solar position and clear-sky GHI for Kon’-Kolodez’ / Lipetsk analysis.

Clear-sky model: Ineichen–Perez (2002) as commonly implemented in pvlib
(``pvlib.clearsky.ineichen``). ``pvlib`` was not installable in this environment
(TLS/proxy to PyPI failed); the formulas below are transcribed from the
published model / pvlib reference equations and documented in the model report.

Solar position: NOAA-style algorithm (Spencer declination + equation of time),
with timestamps interpreted as Europe/Moscow wall time at fixed UTC+3
(DST handling UNKNOWN for the raw archive — same assumption as QC).
"""
from __future__ import annotations

import math
from typing import Iterable, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

# Solar constant (W/m²) used for extraterrestrial irradiance
SOLAR_CONSTANT_WM2 = 1367.0

# Default Linke turbidity (dimensionless). Site-specific TL UNKNOWN.
DEFAULT_LINKE_TURBIDITY = 3.0

# Fallback site elevation when config elevation_m is null (Lipetsk plateau ~160 m).
DEFAULT_ELEVATION_M = 160.0


def _as_utc_from_msk(dt: pd.Timestamp) -> pd.Timestamp:
    """Treat naive/local timestamp as MSK (UTC+3), return naive UTC timestamp."""
    if dt.tzinfo is not None:
        return dt.tz_convert("UTC").tz_localize(None)
    return dt - pd.Timedelta(hours=3)


def solar_position(
    times: Union[pd.Timestamp, Sequence[pd.Timestamp], pd.DatetimeIndex, pd.Series],
    latitude_deg: float,
    longitude_deg: float,
    msk_offset_h: float = 3.0,
) -> pd.DataFrame:
    """
    Approximate solar elevation / zenith / azimuth (degrees).

    Parameters
    ----------
    times : timestamps in local Europe/Moscow wall time (naive)
    latitude_deg, longitude_deg : site coordinates
    msk_offset_h : fixed offset from UTC (default +3); DST UNKNOWN
    """
    idx = pd.DatetimeIndex(pd.Series(times))
    # Vectorized NOAA-like geometry
    utc = idx - pd.Timedelta(hours=msk_offset_h)
    n = utc.dayofyear.astype(float).to_numpy()
    hour_utc = (
        utc.hour.to_numpy(dtype=float)
        + utc.minute.to_numpy(dtype=float) / 60.0
        + utc.second.to_numpy(dtype=float) / 3600.0
    )
    gamma = 2.0 * math.pi / 365.0 * (n - 1.0 + (hour_utc - 12.0) / 24.0)

    decl = (
        0.006918
        - 0.399912 * np.cos(gamma)
        + 0.070257 * np.sin(gamma)
        - 0.006758 * np.cos(2.0 * gamma)
        + 0.000907 * np.sin(2.0 * gamma)
        - 0.002697 * np.cos(3.0 * gamma)
        + 0.00148 * np.sin(3.0 * gamma)
    )
    eqtime = 229.18 * (
        0.000075
        + 0.001868 * np.cos(gamma)
        - 0.032077 * np.sin(gamma)
        - 0.014615 * np.cos(2.0 * gamma)
        - 0.040849 * np.sin(2.0 * gamma)
    )
    time_offset = eqtime + 4.0 * longitude_deg - 60.0 * msk_offset_h
    tst = (
        idx.hour.to_numpy(dtype=float) * 60.0
        + idx.minute.to_numpy(dtype=float)
        + idx.second.to_numpy(dtype=float) / 60.0
        + time_offset
    )
    ha = np.radians(tst / 4.0 - 180.0)
    lat = math.radians(latitude_deg)
    sin_elev = np.sin(lat) * np.sin(decl) + np.cos(lat) * np.cos(decl) * np.cos(ha)
    sin_elev = np.clip(sin_elev, -1.0, 1.0)
    elev = np.degrees(np.arcsin(sin_elev))
    zenith = 90.0 - elev

    # Azimuth (deg from north, clockwise) — diagnostic only
    cos_az = (
        (np.sin(decl) - np.sin(lat) * sin_elev)
        / (np.cos(lat) * np.cos(np.radians(elev)) + 1e-12)
    )
    cos_az = np.clip(cos_az, -1.0, 1.0)
    az = np.degrees(np.arccos(cos_az))
    az = np.where(ha > 0, 360.0 - az, az)

    return pd.DataFrame(
        {
            "solar_elevation_deg": elev,
            "solar_zenith_deg": zenith,
            "solar_azimuth_deg": az,
        },
        index=idx,
    )


def relative_airmass(zenith_deg: np.ndarray) -> np.ndarray:
    """Kasten & Young (1989) relative optical air mass; NaN when sun below horizon."""
    z = np.asarray(zenith_deg, dtype=float)
    am = np.full_like(z, np.nan, dtype=float)
    day = z < 90.0
    z_day = z[day]
    am[day] = 1.0 / (
        np.cos(np.radians(z_day))
        + 0.50572 * np.power(96.07995 - z_day, -1.6364)
    )
    return am


def pressure_corrected_airmass(relative_am: np.ndarray, elevation_m: float) -> np.ndarray:
    """Absolute airmass ≈ relative * P/P0 with barometric approximation."""
    p_ratio = math.exp(-elevation_m / 8434.5)  # simple scale height
    return np.asarray(relative_am, dtype=float) * p_ratio


def extraterrestrial_dni(day_of_year: np.ndarray, solar_constant: float = SOLAR_CONSTANT_WM2) -> np.ndarray:
    """Approximate extraterrestrial DNI (W/m²) with eccentricity correction."""
    doy = np.asarray(day_of_year, dtype=float)
    return solar_constant * (1.0 + 0.033 * np.cos(2.0 * math.pi * doy / 365.0))


def clearsky_ghi_ineichen(
    zenith_deg: np.ndarray,
    day_of_year: np.ndarray,
    elevation_m: float = DEFAULT_ELEVATION_M,
    linke_turbidity: float = DEFAULT_LINKE_TURBIDITY,
) -> np.ndarray:
    """
    Horizontal clear-sky GHI (W/m²), Ineichen–Perez (2002).

    Night / below-horizon samples return 0.
    """
    z = np.asarray(zenith_deg, dtype=float)
    doy = np.asarray(day_of_year, dtype=float)
    ghi = np.zeros_like(z, dtype=float)

    day = z < 90.0
    if not np.any(day):
        return ghi

    z_day = z[day]
    am_rel = relative_airmass(z_day)
    am_abs = pressure_corrected_airmass(am_rel, elevation_m)
    dni_extra = extraterrestrial_dni(doy[day])

    fh1 = math.exp(-elevation_m / 8000.0)
    fh2 = math.exp(-elevation_m / 1250.0)
    cg1 = 5.09e-5 * elevation_m + 0.868
    cg2 = 3.92e-5 * elevation_m + 0.0387

    cos_zen = np.cos(np.radians(z_day))
    cos_zen = np.maximum(cos_zen, 0.0)

    ghi_day = (
        cg1
        * dni_extra
        * cos_zen
        * np.exp(-cg2 * am_abs * (fh1 + fh2 * (linke_turbidity - 1.0)))
        * np.exp(0.01 * np.power(am_abs, 1.8))
    )
    ghi_day = np.maximum(ghi_day, 0.0)
    ghi[day] = ghi_day
    return ghi


def attach_solar_and_clearsky(
    df: pd.DataFrame,
    time_col: str = "obs_time",
    latitude_deg: float = 52.135409,
    longitude_deg: float = 39.163510,
    elevation_m: Optional[float] = None,
    linke_turbidity: float = DEFAULT_LINKE_TURBIDITY,
    min_solar_elevation_deg: float = 5.0,
    g_cs_min_wm2: float = 5.0,
) -> pd.DataFrame:
    """
    Add solar geometry, G_cs, daytime flag, and clear-sky index columns.

    Night / low-sun: ``G_cs=0``, ``k_obs`` null.
    """
    out = df.copy()
    elev_m = float(elevation_m) if elevation_m is not None else DEFAULT_ELEVATION_M
    pos = solar_position(out[time_col], latitude_deg, longitude_deg)
    out["solar_elevation_deg"] = pos["solar_elevation_deg"].to_numpy()
    out["solar_zenith_deg"] = pos["solar_zenith_deg"].to_numpy()
    out["solar_azimuth_deg"] = pos["solar_azimuth_deg"].to_numpy()

    doy = pd.DatetimeIndex(out[time_col]).dayofyear.to_numpy(dtype=float)
    out["G_cs"] = clearsky_ghi_ineichen(
        out["solar_zenith_deg"].to_numpy(),
        doy,
        elevation_m=elev_m,
        linke_turbidity=linke_turbidity,
    )

    daytime = out["solar_elevation_deg"] >= float(min_solar_elevation_deg)
    out["is_daytime"] = daytime.astype(np.int8)
    # Zero G_cs at night / below threshold for index safety
    out.loc[~daytime, "G_cs"] = 0.0

    g_obs = out["radiation_wm2"] if "radiation_wm2" in out.columns else out.get("q_mjm2")
    k = pd.Series(np.nan, index=out.index, dtype=float)
    valid_cs = daytime & (out["G_cs"] >= float(g_cs_min_wm2)) & g_obs.notna()
    k.loc[valid_cs] = g_obs.loc[valid_cs] / out.loc[valid_cs, "G_cs"]
    out["k_obs"] = k
    out["clearsky_model"] = "ineichen_perez_2002"
    out["linke_turbidity"] = float(linke_turbidity)
    out["elevation_m_used"] = elev_m
    return out
