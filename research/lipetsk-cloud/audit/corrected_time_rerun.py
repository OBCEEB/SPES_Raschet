#!/usr/bin/env python3
"""Пересчёт ключевых величин статей A/B при исправленном времени пиранометра.

Гипотеза аудита: метки пиранометра в hh_station.csv — UTC, а пайплайн считает их MSK.
Сценарий shift=0 воспроизводит пайплайн (контроль), shift=3 — исправленная геометрия.
Склейка с ASMG/SSD/T сохраняется как в hh_station (по одной строке), т. е. предполагается,
что пайплайн склеил ряды в одной шкале. Код пайплайна не изменяется.

Выход: audit/corrected_time_rerun.json
"""

from __future__ import annotations

import csv
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import lipetsk_actualize as act  # noqa: E402

CSV = ROOT / "data" / "lipetsk" / "csv"
WINTER = {11, 12, 1, 2, 3}
DE = act.DT_S / 1e6

daily_old = {r["date"]: r for r in csv.DictReader((CSV / "daily_actualize.csv").open(encoding="utf-8"))}
recs = [r for r in csv.DictReader((CSV / "hh_station.csv").open(encoding="utf-8"))
        if r["quality_flag"] == "complete" and r["GHI"] != "" and r["obs_time_msk"][:10] in daily_old]
href = act.load_href()


def run(shift_h: int) -> dict:
    factors = act.smear_factors(href)
    slots = []
    day = defaultdict(lambda: {"H": 0.0, "H0": 0.0, "Href": 0.0, "ssd": 0.0, "nmin": 0, "logH": 0.0, "nH": 0})
    for r in recs:
        lab = datetime.strptime(r["obs_time_msk"], "%Y-%m-%d %H:%M:%S")
        t = lab + timedelta(hours=shift_h)
        d = r["obs_time_msk"][:10]  # сутки как в пайплайне: для сравнимости тот же набор дней
        opt = act.optics(t)
        if opt["i0"] <= 20:
            continue
        fac = factors.get((t.year, t.month), factors[(lab.year, lab.month)])["smear"]
        q = float(r["GHI"])
        ta = float(r["T_c"]) if r["T_c"] else None
        ssd = float(r["sunshine_minutes"]) * 60.0 if r["sunshine_minutes"] else 0.0
        cb = float(r["cloud_base_m"]) if r["cloud_base_m"] else None
        he = act.heff(cb)
        b = day[d]
        b["H"] += q * DE
        b["H0"] += opt["i0"] * DE
        b["Href"] += opt["gcs"] * fac * DE
        b["ssd"] += ssd
        b["nmin"] += 30
        if he is not None:
            b["logH"] += math.log(he + act.H0_FLOOR)
            b["nH"] += 1
        slots.append({"d": d, "month": lab.month, "opt": opt, "q": q, "ta": ta, "gref": opt["gcs"] * fac})

    rows = []
    for d, b in day.items():
        if b["H0"] <= 0 or b["Href"] <= 0 or b["nH"] == 0:
            continue
        dt = datetime.strptime(d, "%Y-%m-%d")
        rows.append({"date": d, "year": dt.year, "month": dt.month, "Kt": b["H"] / b["H0"],
                     "Kref": b["Href"] / b["H0"], "s": min(max(b["ssd"] / (b["nmin"] * 60.0), 0.0), 1.0),
                     "logH": b["logH"] / b["nH"], "sina": max(0.0, act.sina_noon(dt.timetuple().tm_yday))})

    def X(rs):
        return np.array([[1.0, math.log(r["Kref"]), r["sina"], r["s"], r["logH"]]
                         + [1.0 if r["month"] == m else 0.0 for m in range(1, 12)] for r in rs])

    hat = {}
    for ty in sorted({r["year"] for r in rows}):
        tr = [r for r in rows if r["year"] != ty]
        te = [r for r in rows if r["year"] == ty]
        y = np.log(np.array([r["Kt"] for r in tr]))
        bcoef = np.linalg.lstsq(X(tr), y, rcond=None)[0]
        sm = float(np.mean(np.exp(y - X(tr) @ bcoef)))
        for r, h in zip(te, np.clip(np.exp(X(te) @ bcoef) * sm, 0.0, 1.1)):
            hat[r["date"]] = float(h)

    def kt_m(months=None):
        sel = [r for r in rows if months is None or r["month"] in months]
        e = np.array([hat[r["date"]] - r["Kt"] for r in sel])
        return {"n": len(sel), "mean_Kt": round(float(np.mean([r["Kt"] for r in sel])), 4),
                "rmse": round(float(np.sqrt(np.mean(e ** 2))), 4), "mbe": round(float(np.mean(e)), 4)}

    kref_d = {r["date"]: r["Kref"] for r in rows}
    kt_obs = {r["date"]: r["Kt"] for r in rows}

    def q_slot(ghi, opt, ta):
        bh, dh, it = act.erbs_it(ghi, ghi / opt["i0"], opt)
        return act.iso_q(bh, dh, ghi, it, opt, ta)

    res = {}
    for label in ("S1_measured", "S2_oracle_smooth", "S4_baseline_smooth"):
        acc = defaultdict(lambda: {"q": 0.0, "n": 0, "zero": 0, "it": 0.0})
        per_day = defaultdict(float)
        for s in slots:
            if s["d"] not in kref_d:
                continue
            if label == "S1_measured":
                ghi = s["q"]
            else:
                k = kt_obs[s["d"]] if label == "S2_oracle_smooth" else hat[s["d"]]
                ghi = s["gref"] * k / kref_d[s["d"]]
            q = q_slot(ghi, s["opt"], s["ta"])
            se = "winter" if s["month"] in WINTER else "other"
            a = acc[se]
            a["q"] += q * DE
            a["n"] += 1
            a["zero"] += q <= 0
            per_day[s["d"]] += q * DE
        res[label] = {se: {"Q_sum_mjm2": round(a["q"], 1), "share_slots_Q_zero": round(a["zero"] / a["n"], 4),
                           "n_slots": a["n"]} for se, a in acc.items()}
        res[label]["_per_day"] = per_day
    winter_days = [r["date"] for r in rows if r["month"] in WINTER]
    q1 = np.array([res["S1_measured"]["_per_day"][d] for d in winter_days])
    out = {"n_days": len(rows), "Kt_all": kt_m(), "Kt_winter": kt_m(WINTER)}
    for label in ("S2_oracle_smooth", "S4_baseline_smooth"):
        qx = np.array([res[label]["_per_day"][d] for d in winter_days])
        res[label]["winter_vs_S1"] = {"Q_ratio": round(float(qx.sum() / q1.sum()), 4),
                                      "rmse_daily_Q_mjm2": round(float(np.sqrt(np.mean((qx - q1) ** 2))), 4),
                                      "mbe_daily_Q_mjm2": round(float(np.mean(qx - q1)), 4)}
    for label in res:
        res[label].pop("_per_day")
    out["Q"] = res
    return out


out = {"control_shift_0h": run(0), "corrected_shift_3h": run(3),
       "stored_winter_Kt_baseline": {"rmse": 0.0856, "mbe": -0.0058}}
(Path(__file__).resolve().parent / "corrected_time_rerun.json").write_text(
    json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps(out, indent=1, ensure_ascii=False))
