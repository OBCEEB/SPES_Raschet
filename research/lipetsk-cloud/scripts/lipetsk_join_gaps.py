#!/usr/bin/env python3
"""Стыковка сырого НГО аэропорта 27930 и Q Конь-Колодезя (уже из sqlite).

Q-файл — после prune sqlite, поэтому Q ⊆ NGO_valid. Дыры сетки раскладываются на:
  no_ngo_ts      — нет строки ASMG
  ngo_sentinel   — НГО ≥9000 (импортёр → null → слот выкинут даже если Q был в сырье)
  ngo_ok_no_q    — валидное НГО, в базе нет Q (радиации в sqlite нет)
  both           — то, что в kon_kolodez_halfhourly.csv
"""

from __future__ import annotations

import csv
import json
import sys
from calendar import monthrange
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from lipetsk_time import asmg_to_msk, pyranometer_to_msk  # noqa: E402
NGO_DIR = ROOT / "data" / "lipetsk" / "obs" / "ngo"
Q_CSV = ROOT / "data" / "lipetsk" / "obs" / "kon_kolodez_halfhourly.csv"
OUT = ROOT / "data" / "lipetsk" / "csv"
START = datetime(2023, 2, 28, 0, 0)
END = datetime(2025, 12, 31, 23, 30)
STEP = timedelta(minutes=30)


def load_q() -> set[str]:
    keys = set()
    with Q_CSV.open(encoding="utf-8") as f:
        for rec in csv.DictReader(f):
            t = datetime.strptime(rec["obs_time"][:16], "%Y-%m-%d %H:%M")
            keys.add(pyranometer_to_msk(t).strftime("%Y-%m-%d %H:%M"))
    return keys


def load_ngo() -> tuple[set[str], set[str]]:
    ts, valid = set(), set()
    for p in sorted(NGO_DIR.glob("c_202[3-5]*.csv")):
        text = p.read_bytes().decode("cp1251", errors="replace")
        for row in csv.reader(text.splitlines(), delimiter=";"):
            if len(row) < 30:
                continue
            try:
                t = asmg_to_msk(datetime(int(row[3]), int(row[4]), int(row[5]), int(row[6]), int(row[7])))
            except Exception:
                continue
            if t < START or t > END:
                continue
            key = t.strftime("%Y-%m-%d %H:%M")
            ts.add(key)
            s = (row[29] or "").strip().replace(",", ".")
            try:
                v = float(s) if s else None
            except ValueError:
                v = None
            if v is not None and v < 9000:
                valid.add(key)
    return ts, valid


def main() -> None:
    q = load_q()
    ngo_ts, ngo_ok = load_ngo()
    rows = []
    t = START
    buckets: dict = defaultdict(
        lambda: {
            "grid": 0,
            "both": 0,
            "ngo_ok_no_q": 0,
            "ngo_sentinel": 0,
            "no_ngo_ts": 0,
            "q_without_valid_ngo": 0,
        }
    )
    while t <= END:
        key = t.strftime("%Y-%m-%d %H:%M")
        ym = (t.year, t.month)
        b = buckets[ym]
        b["grid"] += 1
        has_q = key in q
        has_ts = key in ngo_ts
        has_ok = key in ngo_ok
        if has_q and has_ok:
            b["both"] += 1
        elif has_ok and not has_q:
            b["ngo_ok_no_q"] += 1
        elif has_ts and not has_ok:
            b["ngo_sentinel"] += 1
            if has_q:
                b["q_without_valid_ngo"] += 1
        else:
            b["no_ngo_ts"] += 1
            if has_q:
                b["q_without_valid_ngo"] += 1
        t += STEP

    monthly = []
    tot = defaultdict(int)
    for y, m in sorted(buckets):
        b = buckets[(y, m)]
        rec = {"year": y, "month": m, **b}
        rec["join_keep_frac"] = round(b["both"] / b["grid"], 4) if b["grid"] else 0
        rec["airport_valid_frac"] = round((b["both"] + b["ngo_ok_no_q"]) / b["grid"], 4)
        rec["q_given_valid_ngo_frac"] = (
            round(b["both"] / (b["both"] + b["ngo_ok_no_q"]), 4)
            if (b["both"] + b["ngo_ok_no_q"])
            else ""
        )
        monthly.append(rec)
        for k, v in b.items():
            tot[k] += v

    OUT.mkdir(parents=True, exist_ok=True)
    fields = [
        "year",
        "month",
        "grid",
        "both",
        "ngo_ok_no_q",
        "ngo_sentinel",
        "no_ngo_ts",
        "q_without_valid_ngo",
        "join_keep_frac",
        "airport_valid_frac",
        "q_given_valid_ngo_frac",
    ]
    with (OUT / "join_q_ngo_monthly.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(monthly)

    def season_frac(months: set[int]) -> dict:
        s = defaultdict(int)
        for rec in monthly:
            if rec["month"] in months:
                for k in (
                    "grid",
                    "both",
                    "ngo_ok_no_q",
                    "ngo_sentinel",
                    "no_ngo_ts",
                ):
                    s[k] += rec[k]
        g_s = s["grid"] or 1
        return {
            "grid": s["grid"],
            "frac_both": round(s["both"] / g_s, 4),
            "frac_sentinel": round(s["ngo_sentinel"] / g_s, 4),
            "frac_ngo_ok_no_q": round(s["ngo_ok_no_q"] / g_s, 4),
        }

    g = tot["grid"]
    summary = {
        "period": "2023-02-28 .. 2025-12-31",
        "airport_files": "60/60 months 2021-01..2025-12 (join uses 2023-02..2025-12)",
        "grid_slots": g,
        "both_in_sqlite": tot["both"],
        "ngo_ok_but_no_Q_in_sqlite": tot["ngo_ok_no_q"],
        "ngo_sentinel_ge_9000": tot["ngo_sentinel"],
        "no_airport_timestamp": tot["no_ngo_ts"],
        "Q_without_valid_NGO": tot["q_without_valid_ngo"],
        "frac_both": round(tot["both"] / g, 4),
        "frac_ngo_ok_no_q": round(tot["ngo_ok_no_q"] / g, 4),
        "frac_sentinel": round(tot["ngo_sentinel"] / g, 4),
        "frac_no_ts": round(tot["no_ngo_ts"] / g, 4),
        "mjjjas": season_frac({5, 6, 7, 8, 9}),
        "ndj": season_frac({11, 12, 1}),
        "note": (
            "Q CSV is post-join sqlite so Q should sit inside valid NGO. "
            "Sentinel slots would drop raw Q if it existed. "
            "ngo_ok_no_q means airport cloud base is usable but radiation is not in sqlite. "
            "Raw airport files are complete; the summer hole is NGO≥9000, not missing CSVs."
        ),
    }
    (OUT / "join_q_ngo_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("worst months (lowest both/grid):")
    for rec in sorted(monthly, key=lambda r: r["join_keep_frac"])[:8]:
        print(
            f"  {rec['year']}-{rec['month']:02d} both={rec['both']}/{rec['grid']} "
            f"sentinel={rec['ngo_sentinel']} ngo_ok_no_q={rec['ngo_ok_no_q']} no_ts={rec['no_ngo_ts']}"
        )


if __name__ == "__main__":
    main()
