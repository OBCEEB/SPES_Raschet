#!/usr/bin/env python3
"""Сколько измеренной энергии теряет фильтр I0 > 20 при текущих метках и при сдвиге +3 ч.

Гипотеза: obs_time в hh_station.csv — фактически UTC, а пайплайн считает его MSK.
Проверка: (1) центр тяжести суточного хода GHI относительно расчётного ясного неба
при сдвиге 0 и +3 ч; (2) доля измеренной энергии в слотах, которые пайплайн
считает ночными (I0 ≤ 20 Вт/м²); (3) суточный Kt при обоих вариантах.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import lipetsk_gti as gti  # noqa: E402

CSV = ROOT / "data" / "lipetsk" / "csv"
WINTER = {11, 12, 1, 2, 3}
DE = gti.DT_S / 1e6

daily = {r["date"]: r for r in csv.DictReader((CSV / "daily_actualize.csv").open(encoding="utf-8"))}
slots = []
for rec in csv.DictReader((CSV / "hh_station.csv").open(encoding="utf-8")):
    if rec["quality_flag"] != "complete" or rec["GHI"] == "":
        continue
    if rec["obs_time_msk"][:10] not in daily:
        continue
    slots.append((datetime.strptime(rec["obs_time_msk"], "%Y-%m-%d %H:%M:%S"), float(rec["GHI"])))

out = {}
for shift_h in (0, 3):
    by_day = defaultdict(lambda: {"all": 0.0, "used": 0.0, "h0": 0.0, "w_g": 0.0, "g": 0.0, "w_cs": 0.0, "cs": 0.0})
    for t, g in slots:
        tt = t + timedelta(hours=shift_h)
        i0, cosz, w = gti.i0_wm2(tt)
        tb, td = gti.hottel_tau(cosz, tt.month)
        gcs = i0 * (tb + td) if i0 > 0 else 0.0
        b = by_day[t.strftime("%Y-%m-%d")]
        b["all"] += g * DE
        if i0 > 20:
            b["used"] += g * DE
            b["h0"] += i0 * DE
        b["w_g"] += g * w
        b["g"] += g
        b["w_cs"] += gcs * w
        b["cs"] += gcs
    res = {}
    for label, months in (("winter", WINTER), ("other", None)):
        days = [d for d in by_day if (int(d[5:7]) in WINTER) == (label == "winter")]
        tot = sum(by_day[d]["all"] for d in days)
        used = sum(by_day[d]["used"] for d in days)
        kt = [by_day[d]["used"] / by_day[d]["h0"] for d in days if by_day[d]["h0"] > 0]
        shifts = [np.degrees(by_day[d]["w_g"] / by_day[d]["g"] - by_day[d]["w_cs"] / by_day[d]["cs"]) * 4
                  for d in days if by_day[d]["g"] > 0 and by_day[d]["cs"] > 0]
        res[label] = {
            "n_days": len(days),
            "measured_energy_mjm2": round(tot, 1),
            "energy_in_slots_with_I0_gt20_mjm2": round(used, 1),
            "share_of_measured_energy_dropped": round(1 - used / tot, 4),
            "mean_daily_Kt": round(float(np.mean(kt)), 4),
            "median_centroid_shift_min": round(float(np.median(shifts)), 1),
        }
    out[f"shift_{shift_h}h"] = res
out["stored_mean_Kt_winter"] = round(float(np.mean([float(r["Kt"]) for r in daily.values() if int(r["month"]) in WINTER])), 4)
out["stored_mean_Kt_other"] = round(float(np.mean([float(r["Kt"]) for r in daily.values() if int(r["month"]) not in WINTER])), 4)
(Path(__file__).resolve().parent / "timing_impact.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps(out, indent=1, ensure_ascii=False))
