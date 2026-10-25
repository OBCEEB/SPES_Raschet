#!/usr/bin/env python3
"""Таблицы Href,cs (СП 13.1) и all-sky NASA POWER для Конь-Колодезя.

Не подменяет ряд станции. C_nasa = H_nasa / Href,cs — спутник, не пиранометр.
Координаты: 52.135409 N, 39.163510 E (analysis/configs/main.yaml в SPES_Raschet).
"""

from __future__ import annotations

import csv
import json
import math
import urllib.request
from calendar import monthrange
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "lipetsk"
RAW = OUT / "raw"
CSV = OUT / "csv"

LAT = 52.135409
LON = 39.163510
MONTHS = list(range(1, 13))
MONTH_NAMES = "I II III IV V VI VII VIII IX X XI XII".split()
# Невисокосный год для климатологии NASA (kWh/m²·сут → МДж/м²·мес).
CLIM_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
KWH_TO_MJ = 3.6

# СП 131.13330.2025 табл. 13.1, МДж/м², безоблачное небо (фрагмент рабочего материала).
SP131 = {
    40: (280, 401, 645, 775, 892, 913, 884, 800, 661, 522, 303, 237),
    48: (196, 308, 545, 712, 874, 911, 898, 753, 575, 409, 220, 158),
    56: (112, 215, 445, 648, 855, 903, 879, 707, 489, 295, 138, 79),
    60: (70, 169, 396, 617, 846, 910, 877, 684, 446, 239, 97, 39),
}


def lerp_lat(phi: float, table: dict[int, tuple[float, ...]]) -> list[float]:
    keys = sorted(table)
    if phi <= keys[0] or phi >= keys[-1]:
        raise ValueError(f"широта {phi} вне сетки СП 13.1")
    lo = max(k for k in keys if k <= phi)
    hi = min(k for k in keys if k >= phi)
    if lo == hi:
        return list(table[lo])
    t = (phi - lo) / (hi - lo)
    return [a + t * (b - a) for a, b in zip(table[lo], table[hi])]


def sp131_annual(monthly: list[float]) -> float:
    return sum(monthly)


def fetch_json(url: str, dest: Path) -> dict:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 200:
        return json.loads(dest.read_text(encoding="utf-8"))
    with urllib.request.urlopen(url, timeout=90) as resp:
        blob = resp.read()
    dest.write_bytes(blob)
    return json.loads(blob.decode("utf-8"))


def nasa_clim() -> dict:
    url = (
        "https://power.larc.nasa.gov/api/temporal/climatology/point"
        "?parameters=ALLSKY_SFC_SW_DWN,CLRSKY_SFC_SW_DWN,"
        "ALLSKY_SFC_SW_DIFF,ALLSKY_SFC_SW_DNI"
        f"&community=RE&longitude={LON}&latitude={LAT}&format=JSON"
    )
    return fetch_json(url, RAW / "nasa_power_climatology.json")


def nasa_monthly() -> dict:
    url = (
        "https://power.larc.nasa.gov/api/temporal/monthly/point"
        "?parameters=ALLSKY_SFC_SW_DWN,CLRSKY_SFC_SW_DWN,ALLSKY_SFC_SW_DIFF"
        f"&community=RE&longitude={LON}&latitude={LAT}"
        "&start=2023&end=2025&format=JSON"
    )
    return fetch_json(url, RAW / "nasa_power_monthly_2023_2025.json")


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow(row)


def handbook_daily_total_at(phi: float) -> float:
    path = OUT / "handbook" / "DailyTotalData.csv"
    xs, ys = [], []
    text = path.read_bytes().decode("utf-8", errors="replace")
    for line in text.strip().splitlines()[1:]:
        lat_s, val_s = line.strip().split(";")
        xs.append(float(lat_s))
        ys.append(float(val_s))
    for i in range(len(xs) - 1):
        if xs[i] <= phi <= xs[i + 1]:
            t = 0.0 if xs[i] == xs[i + 1] else (phi - xs[i]) / (xs[i + 1] - xs[i])
            return ys[i] + t * (ys[i + 1] - ys[i])
    raise ValueError("DailyTotalData: широта вне сетки")


def south_facade_wh(phi_grid: int = 52) -> tuple[float, float, float]:
    raw = (OUT / "handbook" / "IrradianceData.csv").read_bytes()
    text = raw.decode("cp1251")
    beam = diff = 0.0
    n_hours = 0
    for line in text.strip().splitlines()[1:]:
        parts = line.split(";")
        if int(float(parts[0])) != phi_grid:
            continue
        beam += float(parts[6])
        diff += float(parts[7])
        n_hours += 1
    return beam, diff, beam + diff


def main() -> None:
    href = lerp_lat(LAT, SP131)
    href48 = list(SP131[48])
    href56 = list(SP131[56])
    href_year = sp131_annual(href)

    clim = nasa_clim()
    geom = clim["geometry"]["coordinates"]
    params = clim["properties"]["parameter"]
    keys = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

    def clim_daily(name: str) -> list[float]:
        p = params[name]
        return [float(p[k]) for k in keys]

    ghi_d = clim_daily("ALLSKY_SFC_SW_DWN")
    clr_d = clim_daily("CLRSKY_SFC_SW_DWN")
    dhi_d = clim_daily("ALLSKY_SFC_SW_DIFF")
    dni_d = clim_daily("ALLSKY_SFC_SW_DNI")

    rows_href = []
    rows_cmp = []
    nasa_year_mj = 0.0
    clr_year_mj = 0.0
    dhi_year_mj = 0.0
    for m, name, days, h_cs, g, c, d, n in zip(
        MONTHS, MONTH_NAMES, CLIM_DAYS, href, ghi_d, clr_d, dhi_d, dni_d
    ):
        ghi_mj = g * days * KWH_TO_MJ
        clr_mj = c * days * KWH_TO_MJ
        dhi_mj = d * days * KWH_TO_MJ
        bh_mj = ghi_mj - dhi_mj
        nasa_year_mj += ghi_mj
        clr_year_mj += clr_mj
        dhi_year_mj += dhi_mj
        c_sp = ghi_mj / h_cs if h_cs else math.nan
        kcs = g / c if c else math.nan
        kd = d / g if g else math.nan
        rows_href.append(
            {
                "month": m,
                "month_rom": name,
                "days": days,
                "href_cs_48_mjm2": f"{href48[m - 1]:.1f}",
                "href_cs_56_mjm2": f"{href56[m - 1]:.1f}",
                "href_cs_52135_mjm2": f"{h_cs:.3f}",
                "href_cs_kwhm2": f"{h_cs / KWH_TO_MJ:.3f}",
            }
        )
        rows_cmp.append(
            {
                "month": m,
                "month_rom": name,
                "href_cs_mjm2": f"{h_cs:.3f}",
                "nasa_allsky_kwh_d": f"{g:.4f}",
                "nasa_clrsky_kwh_d": f"{c:.4f}",
                "nasa_dhi_kwh_d": f"{d:.4f}",
                "nasa_dni_kwh_d": f"{n:.4f}",
                "nasa_allsky_mjm2": f"{ghi_mj:.3f}",
                "nasa_clrsky_mjm2": f"{clr_mj:.3f}",
                "nasa_dhi_mjm2": f"{dhi_mj:.3f}",
                "nasa_bh_mjm2": f"{bh_mj:.3f}",
                "C_nasa_over_sp131": f"{c_sp:.4f}",
                "kcs_nasa_all_over_clr": f"{kcs:.4f}",
                "kd_nasa": f"{kd:.4f}",
            }
        )

    write_csv(
        CSV / "sp131_href_cs.csv",
        rows_href,
        [
            "month",
            "month_rom",
            "days",
            "href_cs_48_mjm2",
            "href_cs_56_mjm2",
            "href_cs_52135_mjm2",
            "href_cs_kwhm2",
        ],
    )
    write_csv(
        CSV / "nasa_vs_sp131.csv",
        rows_cmp,
        [
            "month",
            "month_rom",
            "href_cs_mjm2",
            "nasa_allsky_kwh_d",
            "nasa_clrsky_kwh_d",
            "nasa_dhi_kwh_d",
            "nasa_dni_kwh_d",
            "nasa_allsky_mjm2",
            "nasa_clrsky_mjm2",
            "nasa_dhi_mjm2",
            "nasa_bh_mjm2",
            "C_nasa_over_sp131",
            "kcs_nasa_all_over_clr",
            "kd_nasa",
        ],
    )

    monthly = nasa_monthly()
    mp = monthly["properties"]["parameter"]
    rows_m = []
    for y in (2023, 2024, 2025):
        for m in MONTHS:
            key = f"{y}{m:02d}"
            days = monthrange(y, m)[1]
            g = float(mp["ALLSKY_SFC_SW_DWN"][key])
            c = float(mp["CLRSKY_SFC_SW_DWN"][key])
            d = float(mp["ALLSKY_SFC_SW_DIFF"][key])
            h_cs = href[m - 1]
            # Месячная сумма СП — климатологическая, не зависит от числа дней года.
            ghi_mj = g * days * KWH_TO_MJ
            rows_m.append(
                {
                    "year": y,
                    "month": m,
                    "days": days,
                    "nasa_allsky_kwh_d": f"{g:.4f}",
                    "nasa_clrsky_kwh_d": f"{c:.4f}",
                    "nasa_dhi_kwh_d": f"{d:.4f}",
                    "nasa_allsky_mjm2": f"{ghi_mj:.3f}",
                    "href_cs_mjm2": f"{h_cs:.3f}",
                    "C_nasa_over_sp131": f"{ghi_mj / h_cs:.4f}",
                    "kcs_nasa": f"{g / c:.4f}" if c else "",
                    "kd_nasa": f"{d / g:.4f}" if g else "",
                }
            )
    write_csv(
        CSV / "nasa_monthly_2023_2025.csv",
        rows_m,
        [
            "year",
            "month",
            "days",
            "nasa_allsky_kwh_d",
            "nasa_clrsky_kwh_d",
            "nasa_dhi_kwh_d",
            "nasa_allsky_mjm2",
            "href_cs_mjm2",
            "C_nasa_over_sp131",
            "kcs_nasa",
            "kd_nasa",
        ],
    )

    dt52 = handbook_daily_total_at(52.0)
    dt_phi = handbook_daily_total_at(LAT)
    s_pr, s_r, s_tot = south_facade_wh(52)
    nasa_ann_kwh_d = float(params["ALLSKY_SFC_SW_DWN"]["ANN"])
    clr_ann_kwh_d = float(params["CLRSKY_SFC_SW_DWN"]["ANN"])
    dhi_ann_kwh_d = float(params["ALLSKY_SFC_SW_DIFF"]["ANN"])
    nasa_ann_kwh = nasa_ann_kwh_d * 365.0
    clr_ann_kwh = clr_ann_kwh_d * 365.0
    summary = {
        "site": "Kon-Kolodez",
        "latitude_deg": LAT,
        "longitude_deg": LON,
        "nasa_dem_elevation_m": geom[2],
        "sp131_href_cs_year_mjm2": round(href_year, 3),
        "sp131_href_cs_year_kwhm2": round(href_year / KWH_TO_MJ, 3),
        "nasa_allsky_year_from_months_mjm2": round(nasa_year_mj, 3),
        "nasa_allsky_year_ann_kwhm2": round(nasa_ann_kwh, 3),
        "nasa_clrsky_year_ann_kwhm2": round(clr_ann_kwh, 3),
        "nasa_clrsky_year_from_months_mjm2": round(clr_year_mj, 3),
        "nasa_dhi_year_from_months_mjm2": round(dhi_year_mj, 3),
        "C_nasa_over_sp131_year": round(nasa_year_mj / href_year, 4),
        "kcs_nasa_year": round(nasa_ann_kwh_d / clr_ann_kwh_d, 4),
        "kd_nasa_year": round(dhi_ann_kwh_d / nasa_ann_kwh_d, 4),
        "handbook_DailyTotal_52_Wh_m2": dt52,
        "handbook_DailyTotal_interp_Wh_m2": round(dt_phi, 3),
        "handbook_south_facade_52_beam_Wh_m2": s_pr,
        "handbook_south_facade_52_diff_Wh_m2": s_r,
        "handbook_south_facade_52_sum_Wh_m2": s_tot,
        "scale_note": (
            "DailyTotal ~329 Wh/m²·сут при наивном чтении как суточный GHI "
            "на порядок меньше NASA all-sky и СП 13.1; не считать % улучшения. "
            "IrradianceData на 52° — фасад (Ю пр+р = 2930 Wh/m² за табличные часы), не горизонталь."
        ),
    }
    (CSV / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
