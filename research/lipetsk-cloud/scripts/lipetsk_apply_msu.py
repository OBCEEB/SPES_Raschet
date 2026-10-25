#!/usr/bin/env python3
"""Сутки Конь-Колодезя (частичные суммы) → Kt, МГУ-Рейндл.

H — сумма наличных дневных получасов, не климатологический день.
Месячный C = ΣH / Href,cs не публиковать как норму облачности.
"""

from __future__ import annotations

import csv
import json
import sys
from calendar import monthrange
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from msu_kd import h0_mj, msu_reindl, sin_alpha_noon  # noqa: E402

LAT = 52.135409
SRC = ROOT / "data" / "lipetsk" / "obs" / "m0m1_energy_daily.csv"
QC = ROOT / "data" / "lipetsk" / "qc" / "qc_completeness_year_month.csv"
HREF = ROOT / "data" / "lipetsk" / "csv" / "sp131_href_cs.csv"
OUT = ROOT / "data" / "lipetsk" / "csv"
WH_TO_MJ = 0.0036
KT_MIN, KT_MAX = 0.03, 0.85


def main() -> None:
    href = {}
    with HREF.open(encoding="utf-8") as f:
        for rec in csv.DictReader(f):
            href[int(rec["month"])] = float(rec["href_cs_52135_mjm2"])
    qc = {}
    with QC.open(encoding="utf-8") as f:
        for rec in csv.DictReader(f):
            qc[(int(rec["year"]), int(rec["month"]))] = float(rec["present_fraction"])

    daily = []
    with SRC.open(encoding="utf-8") as f:
        for rec in csv.DictReader(f):
            d = date.fromisoformat(rec["date"])
            wh = float(rec["radiation_wm2_Wh"])
            h = wh * WH_TO_MJ
            doy = d.timetuple().tm_yday
            h0 = h0_mj(doy, LAT)
            sina = sin_alpha_noon(doy, LAT)
            kt = h / h0 if h0 > 0 else None
            physical = kt is not None and KT_MIN <= kt <= KT_MAX
            kd = msu_reindl(kt, sina) if physical else None
            daily.append(
                {
                    "date": d.isoformat(),
                    "year": d.year,
                    "month": d.month,
                    "H_partial_Whm2": f"{wh:.4f}",
                    "H_partial_mjm2": f"{h:.4f}",
                    "H0_mjm2": f"{h0:.4f}",
                    "Kt_partial": f"{kt:.4f}" if kt is not None else "",
                    "sin_alpha_noon": f"{sina:.4f}",
                    "physical_kt": int(physical),
                    "Kd_msu_reindl": f"{kd:.4f}" if kd is not None else "",
                    "Hd_mjm2": f"{kd * h:.4f}" if kd is not None else "",
                    "Bh_mjm2": f"{(1.0 - kd) * h:.4f}" if kd is not None else "",
                    "note": ""
                    if physical
                    else (
                        "measured_zero"
                        if wh == 0.0
                        else "Kt_outside_MSU_filter_or_incomplete_day"
                    ),
                }
            )

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "daily_kt_kd.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(daily[0].keys()))
        w.writeheader()
        w.writerows(daily)

    groups: dict = defaultdict(
        lambda: {"n": 0, "H": 0.0, "n_phys": 0, "H_phys": 0.0, "Hd": 0.0, "Bh": 0.0}
    )
    for rec in daily:
        key = (int(rec["year"]), int(rec["month"]))
        g = groups[key]
        g["n"] += 1
        g["H"] += float(rec["H_partial_mjm2"])
        if rec["physical_kt"] in (1, "1"):
            g["n_phys"] += 1
            g["H_phys"] += float(rec["H_partial_mjm2"])
            g["Hd"] += float(rec["Hd_mjm2"])
            g["Bh"] += float(rec["Bh_mjm2"])

    monthly = []
    for year, month in sorted(groups):
        g = groups[(year, month)]
        h_cs = href[month]
        dim = monthrange(year, month)[1]
        pf = qc.get((year, month))
        monthly.append(
            {
                "year": year,
                "month": month,
                "calendar_days": dim,
                "n_days_with_any_daytime": g["n"],
                "n_physical_kt": g["n_phys"],
                "grid_present_frac_incl_night": f"{pf:.4f}" if pf is not None else "",
                "H_partial_mjm2": f"{g['H']:.3f}",
                "Hd_msu_reindl_physdays_mjm2": f"{g['Hd']:.3f}",
                "Bh_msu_reindl_physdays_mjm2": f"{g['Bh']:.3f}",
                "href_cs_mjm2": f"{h_cs:.3f}",
                "C_partial_over_sp131": f"{g['H'] / h_cs:.4f}",
                "note": "H is sum of present daytime slots only; not a climate C",
            }
        )
    with (OUT / "monthly_partial.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(monthly[0].keys()))
        w.writeheader()
        w.writerows(monthly)

    n_phys = sum(1 for r in daily if r["physical_kt"] in (1, "1"))
    kd_mean = (
        sum(float(r["Kd_msu_reindl"]) for r in daily if r["Kd_msu_reindl"]) / n_phys
        if n_phys
        else None
    )
    summary = {
        "source": "OBCEEB/SPES_Raschet cursor/solar-geometry-m0m1-9b6b tables/m0m1_energy_daily.csv",
        "site": "Kon-Kolodez 52.135409 N 39.163510 E",
        "n_days_in_file": len(daily),
        "n_physical_kt_for_msu_reindl": n_phys,
        "mean_Kd_msu_reindl_physical_days": round(kd_mean, 4) if kd_mean else None,
        "measured_zero_days": sum(1 for r in daily if r["note"] == "measured_zero"),
        "warning": (
            "Daily H underestimates cloudy-month energy because half-hour gaps "
            "are omitted rather than interpolated. Do not quote monthly C as climatology."
        ),
    }
    (OUT / "obs_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
