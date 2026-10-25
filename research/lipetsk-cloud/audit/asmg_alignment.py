#!/usr/bin/env python3
"""Взаимное выравнивание пиранометра и ASMG: корреляция октантов облачности аэропорта
с ослаблением GHI относительно ясного неба при сдвиге ряда аэропорта на k получасов.

Если обе метки в одной шкале (например, обе UTC), максимум корреляции (по модулю)
должен быть около k = 0. Геометрия ясного неба считается при гипотезе «метки = UTC».
"""

from __future__ import annotations

import csv
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import lipetsk_gti as gti  # noqa: E402

recs = list(csv.DictReader((ROOT / "data" / "lipetsk" / "csv" / "hh_station.csv").open(encoding="utf-8")))
t = [datetime.strptime(r["obs_time_msk"], "%Y-%m-%d %H:%M:%S") for r in recs]
kcs = np.full(len(recs), np.nan)
for i, r in enumerate(recs):
    if r["GHI"] == "":
        continue
    tt = t[i] + timedelta(hours=3)  # гипотеза: метки — UTC
    i0, cosz, _ = gti.i0_wm2(tt)
    tb, td = gti.hottel_tau(cosz, tt.month)
    gcs = i0 * (tb + td)
    if gcs > 150:
        kcs[i] = float(r["GHI"]) / gcs
okt = np.array([float(r["n_oktas"]) if r["n_oktas"] not in ("", None) else np.nan for r in recs])

print("shift of airport series (half-hours, + = airport later)  corr(oktas, kcs)  n")
best = None
for k in range(-10, 11):
    if k >= 0:
        a, b = okt[: len(okt) - k], kcs[k:]
    else:
        a, b = okt[-k:], kcs[: len(kcs) + k]
    m = ~np.isnan(a) & ~np.isnan(b)
    c = float(np.corrcoef(a[m], b[m])[0, 1])
    print(f"{k:+3d} ({k * 30:+5d} min)  {c:+.4f}  {int(m.sum())}")
    if best is None or c < best[1]:
        best = (k, c)
print("strongest negative correlation at shift", best[0], "half-hours =", best[0] * 30, "min")
