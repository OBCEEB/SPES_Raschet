"""Numbers for article A after the time-basis fix.

Reads data/lipetsk/csv (daily_actualize.csv, daily_obs_q_only.csv, actualize_summary.json).
Writes reports/article_A_numbers.json.

1. Year-wise check of the daily log-Kt model by test year and season, for Kt and H.
2. The same model without the SSD feature (refit on the same folds).
3. Physical check of the clear-sky reference: daily H / Href,cs share of the day
   (smeared SP profile) by month; the upper percentiles approximate clear days.
4. Days dropped between the complete-day set and the model set.
"""
import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from lipetsk_actualize import fit_predict_daily, sina_noon  # noqa: E402

CSV = ROOT / "data" / "lipetsk" / "csv"
OUT = ROOT / "reports" / "article_A_numbers.json"
SEASONS = {"all": None, "winter": {11, 12, 1, 2, 3}, "summer": {5, 6, 7, 8, 9}, "shoulder": {4, 10}}


def metrics(obs, hat):
    obs, hat = np.asarray(obs), np.asarray(hat)
    e = hat - obs
    ss_tot = float(np.sum((obs - obs.mean()) ** 2))
    return {
        "n": int(len(obs)),
        "rmse": round(float(np.sqrt(np.mean(e ** 2))), 4),
        "mae": round(float(np.mean(np.abs(e))), 4),
        "mbe": round(float(np.mean(e)), 4),
        "r2": round(1.0 - float(np.sum(e ** 2)) / ss_tot, 4) if ss_tot else None,
    }


def load_daily():
    rows = []
    with (CSV / "daily_actualize.csv").open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            from datetime import datetime

            doy = datetime.strptime(r["date"], "%Y-%m-%d").timetuple().tm_yday
            kt, h = float(r["Kt"]), float(r["H_mjm2"])
            rows.append({
                "date": r["date"], "year": int(r["year"]), "month": int(r["month"]),
                "Kt": kt, "Kref": float(r["Kref_sp_smear"]), "s": float(r["s_ssd"]),
                "logH": float(r["log_Hcloud"]), "sina": max(0.0, sina_noon(doy)),
                "H": h, "H0": h / kt, "Href": float(r["Href_smear_mjm2"]),
                "Kt_hat_stored": float(r["Kt_hat_oos"]) if r["Kt_hat_oos"] else None,
            })
    return rows


def yearwise(rows, use_s):
    hats = {}
    for ty in sorted({r["year"] for r in rows}):
        tr = [r for r in rows if r["year"] != ty]
        te = [r for r in rows if r["year"] == ty]
        _, hat, _, _ = fit_predict_daily(tr, te, use_s=use_s)
        for r, h in zip(te, hat):
            hats[r["date"]] = float(h)
    return hats


def table(rows, hats):
    out = {}
    for ty in ["pooled"] + sorted({r["year"] for r in rows}):
        sub_y = rows if ty == "pooled" else [r for r in rows if r["year"] == ty]
        block = {}
        for label, ms in SEASONS.items():
            sub = [r for r in sub_y if ms is None or r["month"] in ms]
            if len(sub) < 5:
                continue
            kt_o = [r["Kt"] for r in sub]
            kt_h = [hats[r["date"]] for r in sub]
            h_o = [r["H"] for r in sub]
            h_h = [hats[r["date"]] * r["H0"] for r in sub]
            block[label] = {"Kt": metrics(kt_o, kt_h), "H_mjm2": metrics(h_o, h_h)}
        out[str(ty)] = block
    return out


def clear_sky_check(rows):
    by_m = defaultdict(list)
    for r in rows:
        if r["Href"] > 0:
            by_m[r["month"]].append(r["H"] / r["Href"])
    out = {}
    for m in range(1, 13):
        v = np.array(by_m[m])
        if not len(v):
            continue
        out[m] = {
            "n": int(len(v)),
            "p50": round(float(np.percentile(v, 50)), 3),
            "p90": round(float(np.percentile(v, 90)), 3),
            "p95": round(float(np.percentile(v, 95)), 3),
            "max": round(float(v.max()), 3),
        }
    allv = np.array([x for m in by_m for x in by_m[m]])
    out["all"] = {"n": int(len(allv)), "p95": round(float(np.percentile(allv, 95)), 3),
                  "p99": round(float(np.percentile(allv, 99)), 3), "max": round(float(allv.max()), 3)}
    return out


def dropped_days(rows):
    model = {r["date"] for r in rows}
    with (CSV / "daily_obs_q_only.csv").open(encoding="utf-8") as f:
        comp = [r["date"] for r in csv.DictReader(f) if r["complete_daylight"] == "1"]
    return sorted(set(comp) - model)


def main():
    rows = load_daily()
    hats = yearwise(rows, use_s=True)
    diff = max(abs(hats[r["date"]] - r["Kt_hat_stored"]) for r in rows if r["Kt_hat_stored"] is not None)
    hats_no_s = yearwise(rows, use_s=False)
    out = {
        "n_model_days": len(rows),
        "by_year_n": {y: sum(1 for r in rows if r["year"] == y) for y in sorted({r["year"] for r in rows})},
        "reproduces_stored_Kt_hat_max_abs_diff": round(diff, 6),
        "log_model_with_ssd": table(rows, hats),
        "log_model_no_ssd": table(rows, hats_no_s),
        "clear_sky_check_H_over_Href_daily": clear_sky_check(rows),
        "complete_days_not_in_model": dropped_days(rows),
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    p = out["log_model_with_ssd"]["pooled"]
    q = out["log_model_no_ssd"]["pooled"]
    print("days", out["n_model_days"], out["by_year_n"], "repro", out["reproduces_stored_Kt_hat_max_abs_diff"])
    for s in SEASONS:
        if s in p:
            print(s, "with", p[s]["Kt"], p[s]["H_mjm2"])
            print(s, "noS ", q[s]["Kt"], q[s]["H_mjm2"])
    for y in ("2023", "2024", "2025"):
        print(y, {s: (v["Kt"]["rmse"], v["Kt"]["mbe"], v["Kt"]["r2"], v["H_mjm2"]["rmse"]) for s, v in out["log_model_with_ssd"][y].items()})
    print("clear", json.dumps(out["clear_sky_check_H_over_Href_daily"]))
    print("dropped", out["complete_days_not_in_model"])


if __name__ == "__main__":
    main()
