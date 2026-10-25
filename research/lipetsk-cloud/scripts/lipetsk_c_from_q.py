#!/usr/bin/env python3
"""Месячный C = Hobs/Href,cs и Kd по полным световым суткам сырого Q (без prune НГО)."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DAILY = ROOT / "data" / "lipetsk" / "csv" / "daily_obs_q_only.csv"
HREF = ROOT / "data" / "lipetsk" / "csv" / "sp131_href_cs.csv"
NASA = ROOT / "data" / "lipetsk" / "csv" / "nasa_monthly_2023_2025.csv"
NASA_CLIM = ROOT / "data" / "lipetsk" / "csv" / "nasa_vs_sp131.csv"
OUT = ROOT / "data" / "lipetsk" / "csv"


def main() -> None:
    href = {}
    with HREF.open(encoding="utf-8") as f:
        for rec in csv.DictReader(f):
            href[int(rec["month"])] = {
                "mjm2": float(rec["href_cs_52135_mjm2"]),
                "days": int(rec["days"]),
            }
    nasa_ym = {}
    with NASA.open(encoding="utf-8") as f:
        for rec in csv.DictReader(f):
            nasa_ym[(int(rec["year"]), int(rec["month"]))] = float(rec["nasa_allsky_mjm2"])
    nasa_clim = {}
    with NASA_CLIM.open(encoding="utf-8") as f:
        for rec in csv.DictReader(f):
            nasa_clim[int(rec["month"])] = {
                "all": float(rec["nasa_allsky_mjm2"]),
                "c": float(rec["C_nasa_over_sp131"]),
                "kd": float(rec["kd_nasa"]),
            }

    days = []
    with DAILY.open(encoding="utf-8") as f:
        for rec in csv.DictReader(f):
            rec["complete"] = rec["complete_daylight"] in ("1", "true", "True")
            rec["year"] = int(rec["year"])
            rec["month"] = int(rec["month"])
            rec["H"] = float(rec["H_obs_mjm2"]) if rec["H_obs_mjm2"] else None
            rec["Kt"] = float(rec["Kt"]) if rec["Kt"] else None
            rec["Kd"] = float(rec["Kd_msu_reindl"]) if rec["Kd_msu_reindl"] else None
            rec["Hd"] = float(rec["Hd_mjm2"]) if rec["Hd_mjm2"] else None
            rec["Bh"] = float(rec["Bh_mjm2"]) if rec["Bh_mjm2"] else None
            days.append(rec)

    complete = [r for r in days if r["complete"] and r["H"] is not None]
    ym: dict = defaultdict(list)
    for r in complete:
        ym[(r["year"], r["month"])].append(r)

    monthly = []
    for y, m in sorted(ym):
        rows = ym[(y, m)]
        n_cal = sum(1 for r in days if r["year"] == y and r["month"] == m)
        n = len(rows)
        h = sum(r["H"] for r in rows)
        hd = sum(r["Hd"] for r in rows)
        bh = sum(r["Bh"] for r in rows)
        kt = sum(r["Kt"] for r in rows) / n
        kd = sum(r["Kd"] for r in rows) / n
        href_m = href[m]["mjm2"]
        nd = href[m]["days"]
        # leap Feb 2024: 29 calendar days, SP table is 28
        full = n == n_cal and n_cal >= 28
        # C from complete days vs SP: scale SP to n days if month incomplete
        href_for_n = href_m * (n / nd)
        c_vs_sp_scaled = h / href_for_n if href_for_n else None
        c_month = (h / href_m) if full else None
        nasa = nasa_ym.get((y, m))
        c_nasa_year = (h / nasa) if (full and nasa) else None
        monthly.append(
            {
                "year": y,
                "month": m,
                "n_calendar": n_cal,
                "n_complete": n,
                "complete_month": int(full),
                "H_complete_mjm2": round(h, 3),
                "Hd_msu_mjm2": round(hd, 3),
                "Bh_msu_mjm2": round(bh, 3),
                "Kt_mean": round(kt, 4),
                "Kd_msu_mean": round(kd, 4),
                "href_cs_mjm2": round(href_m, 3),
                "C_vs_sp_if_complete_month": round(c_month, 4) if c_month else "",
                "C_vs_sp_scaled_ndays": round(c_vs_sp_scaled, 4),
                "nasa_allsky_mjm2": round(nasa, 3) if nasa else "",
                "C_vs_nasa_if_complete_month": round(c_nasa_year, 4) if c_nasa_year else "",
            }
        )

    clim = []
    by_m = defaultdict(list)
    for r in complete:
        by_m[r["month"]].append(r)
    for m in range(1, 13):
        rows = by_m[m]
        n = len(rows)
        href_m = href[m]["mjm2"]
        nd = href[m]["days"]
        h_mean = sum(r["H"] for r in rows) / n
        h_month_eq = h_mean * nd
        c = h_month_eq / href_m
        kd = sum(r["Kd"] for r in rows) / n
        kt = sum(r["Kt"] for r in rows) / n
        clim.append(
            {
                "month": m,
                "n_complete_days": n,
                "H_mean_mjm2": round(h_mean, 3),
                "H_eq_month_mjm2": round(h_month_eq, 3),
                "href_cs_mjm2": round(href_m, 3),
                "C_vs_sp": round(c, 4),
                "C_nasa_clim": nasa_clim[m]["c"],
                "nasa_allsky_mjm2": nasa_clim[m]["all"],
                "Kt_mean": round(kt, 4),
                "Kd_msu_mean": round(kd, 4),
                "kd_nasa_clim": nasa_clim[m]["kd"],
            }
        )

    href_year = sum(href[m]["mjm2"] for m in range(1, 13))
    h_eq_year = sum(r["H_eq_month_mjm2"] for r in clim)
    c_year = h_eq_year / href_year
    kd_year = sum(
        r["Kd_msu_mean"] * href[r["month"]]["mjm2"] for r in clim
    ) / href_year  # energy-weight by Href is wrong; weight by H
    h_w = sum(r["H_eq_month_mjm2"] for r in clim)
    kd_year = sum(r["Kd_msu_mean"] * r["H_eq_month_mjm2"] for r in clim) / h_w

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "monthly_q_only.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(monthly[0].keys()))
        w.writeheader()
        w.writerows(monthly)
    with (OUT / "climatology_q_only.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(clim[0].keys()))
        w.writeheader()
        w.writerows(clim)

    full = [r for r in monthly if r["complete_month"]]
    summary = {
        "n_complete_days": len(complete),
        "n_complete_calendar_months": len(full),
        "C_year_from_monthly_means": round(c_year, 4),
        "C_nasa_clim_year": 0.696,
        "Kd_year_Hweighted": round(kd_year, 4),
        "kd_nasa_clim_year": 0.45,
        "C_complete_months": {
            f"{r['year']}-{r['month']:02d}": r["C_vs_sp_if_complete_month"] for r in full
        },
        "climatology_C_vs_sp": {r["month"]: r["C_vs_sp"] for r in clim},
        "climatology_Kd_msu": {r["month"]: r["Kd_msu_mean"] for r in clim},
        "note": (
            "C from complete-day means × SP month length / Href,cs. Not sqlite. "
            "Annual C is a 12-month composite of complete days, not one station year. "
            "March 2024 has only 2 complete days in the March mean."
        ),
    }
    (OUT / "c_q_only_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("climatology C and Kd by month:")
    for r in clim:
        print(
            f"  {r['month']:2d} n={r['n_complete_days']:3d} "
            f"H={r['H_mean_mjm2']:6.2f} C={r['C_vs_sp']:.3f} "
            f"(NASA {r['C_nasa_clim']:.3f}) Kd={r['Kd_msu_mean']:.3f} "
            f"(NASA {r['kd_nasa_clim']:.3f})"
        )


if __name__ == "__main__":
    main()
