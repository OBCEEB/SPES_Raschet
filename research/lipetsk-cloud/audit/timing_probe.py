#!/usr/bin/env python3
"""Проверка меток времени: где пик измеренного GHI относительно расчётного полдня."""

from __future__ import annotations

import csv
import math
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import lipetsk_gti as gti  # noqa: E402

rows = defaultdict(list)
with (ROOT / "data" / "lipetsk" / "csv" / "hh_station.csv").open(encoding="utf-8") as f:
    for rec in csv.DictReader(f):
        if rec["GHI"] == "":
            continue
        rows[rec["obs_time_msk"][:10]].append(rec)


def solar_noon_msk(day: datetime) -> float:
    """Час MSK, когда ω = 0 (по формулам пайплайна)."""
    best, best_t = 1e9, 0.0
    for k in range(0, 24 * 60, 2):
        t = day + timedelta(minutes=k)
        # omega_rad добавляет +15 мин (середина слота); здесь нужен сам момент
        w = gti.omega_rad(t - timedelta(minutes=15), gti.LON)
        if abs(w) < best:
            best, best_t = abs(w), k / 60.0
    return best_t


def peak_and_centroid(recs) -> tuple[float, float, float]:
    g = [(datetime.strptime(r["obs_time_msk"], "%Y-%m-%d %H:%M:%S"), float(r["GHI"])) for r in recs]
    tot = sum(v for _, v in g)
    cen = sum((t.hour + t.minute / 60 + 0.25) * v for t, v in g) / tot
    pk = max(g, key=lambda x: x[1])[0]
    first = min(t for t, v in g if v > 5)
    return pk.hour + pk.minute / 60 + 0.25, cen, first.hour + first.minute / 60


print("date        noon_MSK  peak_MSK  centroid  first_GHI>5  maxGHI")
for d in ("2023-06-21", "2023-07-10", "2024-06-15", "2024-08-01", "2024-12-20", "2025-03-21", "2025-06-21", "2025-09-10"):
    if d not in rows:
        continue
    day = datetime.strptime(d, "%Y-%m-%d")
    pk, cen, first = peak_and_centroid(rows[d])
    mx = max(float(r["GHI"]) for r in rows[d])
    print(f"{d}  {solar_noon_msk(day):7.2f}  {pk:8.2f}  {cen:8.2f}  {first:9.2f}  {mx:7.0f}")

# Средний суточный ход за лето: по часам MSK
acc = defaultdict(lambda: [0.0, 0])
for d, recs in rows.items():
    if d[5:7] not in ("06", "07"):
        continue
    for r in recs:
        t = datetime.strptime(r["obs_time_msk"], "%Y-%m-%d %H:%M:%S")
        a = acc[t.hour + t.minute / 60]
        a[0] += float(r["GHI"])
        a[1] += 1
print("\nJune-July mean GHI by slot start (MSK):")
print(" ".join(f"{h:04.1f}:{acc[h][0] / acc[h][1]:4.0f}" for h in sorted(acc) if acc[h][1]))
