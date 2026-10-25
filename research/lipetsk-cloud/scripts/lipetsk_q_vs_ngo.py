#!/usr/bin/env python3
"""Стыковка сырых минуток Q Конь-Колодезя с НГО аэропорта и sqlite.

Берёт :00 и :30 из минуток (если минуты нет — среднее по получасу).
День `yymm00.csv` часто держит **предыдущие** календарные сутки, не пустышку.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
Q_DIR = ROOT / "data" / "lipetsk" / "obs" / "q"
NGO_DIR = ROOT / "data" / "lipetsk" / "obs" / "ngo"
SQLITE = ROOT / "data" / "lipetsk" / "obs" / "kon_kolodez_halfhourly.csv"
OUT = ROOT / "data" / "lipetsk" / "csv"
STEP = timedelta(minutes=30)


def parse_q(cell: str) -> float | None:
    s = (cell or "").strip().replace(",", ".")
    if not s or s == "/":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_ts(raw: str) -> datetime | None:
    raw = (raw or "").strip()
    for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def load_minutes() -> dict[datetime, float]:
    by_min: dict[datetime, float] = {}
    for p in sorted(Q_DIR.glob("**/*.csv")):
        text = p.read_bytes().decode("cp1251", errors="replace")
        for row in csv.reader(text.splitlines(), delimiter=";"):
            if len(row) < 2 or not row[0][:1].isdigit():
                continue
            v = parse_q(row[1])
            if v is None:
                continue
            t = parse_ts(row[0])
            if t is not None:
                by_min[t] = v
    return by_min


def load_sqlite() -> dict[datetime, float]:
    out: dict[datetime, float] = {}
    if not SQLITE.exists():
        return out
    with SQLITE.open(encoding="utf-8") as f:
        for rec in csv.DictReader(f):
            t = datetime.strptime(rec["obs_time"][:19], "%Y-%m-%d %H:%M:%S")
            out[t] = float(rec["q_wm2"])
    return out


def load_ngo(start: datetime, end: datetime) -> tuple[set[datetime], set[datetime], dict]:
    ts, valid, val = set(), set(), {}
    for p in sorted(NGO_DIR.glob("c_*.csv")):
        text = p.read_bytes().decode("cp1251", errors="replace")
        for row in csv.reader(text.splitlines(), delimiter=";"):
            if len(row) < 30:
                continue
            try:
                t = datetime(int(row[3]), int(row[4]), int(row[5]), int(row[6]), int(row[7]))
            except Exception:
                continue
            if t < start or t > end:
                continue
            ts.add(t)
            s = (row[29] or "").strip().replace(",", ".")
            try:
                v = float(s) if s else None
            except ValueError:
                v = None
            val[t] = v
            if v is not None and v < 9000:
                valid.add(t)
    return ts, valid, val


def slot_q(minutes: dict[datetime, float], t0: datetime) -> float | None:
    if t0 in minutes:
        return minutes[t0]
    # exact :00/:30 missing: mean of minutes that exist in this half-hour (O(30))
    vals = [minutes[t0 + timedelta(minutes=i)] for i in range(30) if (t0 + timedelta(minutes=i)) in minutes]
    if not vals:
        return None
    return sum(vals) / len(vals)


def main() -> None:
    minutes = load_minutes()
    if not minutes:
        print("no live Q minutes")
        return
    start = min(minutes).replace(minute=0 if min(minutes).minute < 30 else 30, second=0, microsecond=0)
    last = max(minutes)
    end = last.replace(minute=0 if last.minute < 30 else 30, second=0, microsecond=0)
    station_end = datetime(2025, 12, 31, 23, 30)
    if end > station_end:
        end = station_end
    if start < datetime(2023, 2, 28):
        start = datetime(2023, 2, 28)
    sql = load_sqlite()
    ngo_ts, ngo_ok, _ = load_ngo(start, end)

    buckets: dict = defaultdict(
        lambda: {
            "grid": 0,
            "q_raw": 0,
            "q_and_ngo_ok": 0,
            "q_on_sentinel": 0,
            "q_on_sentinel_gt20": 0,
            "q_no_ngo_ts": 0,
            "sqlite": 0,
            "sqlite_and_raw": 0,
            "raw_not_sqlite": 0,
            "sqlite_not_raw": 0,
        }
    )
    hh_rows = []
    t = start
    while t <= end:
        b = buckets[(t.year, t.month)]
        b["grid"] += 1
        q = slot_q(minutes, t)
        has_sql = t in sql
        if t in ngo_ok:
            ngo_cls = "ok"
        elif t in ngo_ts:
            ngo_cls = "sentinel"
        else:
            ngo_cls = "no_ts"
        if q is not None:
            b["q_raw"] += 1
            if ngo_cls == "ok":
                b["q_and_ngo_ok"] += 1
            elif ngo_cls == "sentinel":
                b["q_on_sentinel"] += 1
                if q > 20:
                    b["q_on_sentinel_gt20"] += 1
            else:
                b["q_no_ngo_ts"] += 1
            hh_rows.append(
                {
                    "obs_time": t.strftime("%Y-%m-%d %H:%M:%S"),
                    "q_wm2": round(q, 2),
                    "ngo": ngo_cls,
                    "in_sqlite": int(has_sql),
                }
            )
        if has_sql:
            b["sqlite"] += 1
            if q is not None:
                b["sqlite_and_raw"] += 1
            else:
                b["sqlite_not_raw"] += 1
        elif q is not None:
            b["raw_not_sqlite"] += 1
        t += STEP

    fields = [
        "year",
        "month",
        "grid",
        "q_raw",
        "q_and_ngo_ok",
        "q_on_sentinel",
        "q_on_sentinel_gt20",
        "q_no_ngo_ts",
        "sqlite",
        "sqlite_and_raw",
        "raw_not_sqlite",
        "sqlite_not_raw",
        "frac_raw_dropped_sentinel",
    ]
    monthly = []
    tot = defaultdict(int)
    for y, m in sorted(buckets):
        b = buckets[(y, m)]
        rec = {"year": y, "month": m, **b}
        rec["frac_raw_dropped_sentinel"] = (
            round(b["q_on_sentinel"] / b["q_raw"], 4) if b["q_raw"] else ""
        )
        monthly.append(rec)
        for k, v in b.items():
            tot[k] += v

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "q_raw_vs_ngo_monthly.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(monthly)

    def season(months: set[int]) -> dict:
        s = defaultdict(int)
        for rec in monthly:
            if rec["month"] in months:
                for k in ("grid", "q_raw", "q_on_sentinel", "sqlite", "q_on_sentinel_gt20"):
                    s[k] += rec[k]
        qr = s["q_raw"] or 1
        return {
            "q_raw": s["q_raw"],
            "sqlite": s["sqlite"],
            "drop_sentinel": s["q_on_sentinel"],
            "frac_drop": round(s["q_on_sentinel"] / qr, 4),
            "drop_Qgt20": s["q_on_sentinel_gt20"],
        }

    with (OUT / "hh_q_only.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["obs_time", "q_wm2", "ngo", "in_sqlite"])
        w.writeheader()
        w.writerows(hh_rows)

    gq = tot["q_raw"] or 1
    summary = {
        "live_minute_slots": len(minutes),
        "range": [str(start), str(end)],
        "hh_grid": tot["grid"],
        "hh_with_raw_q": tot["q_raw"],
        "hh_q_and_valid_ngo": tot["q_and_ngo_ok"],
        "hh_q_on_sentinel": tot["q_on_sentinel"],
        "hh_q_on_sentinel_Qgt20": tot["q_on_sentinel_gt20"],
        "hh_sqlite": tot["sqlite"],
        "hh_sqlite_and_raw": tot["sqlite_and_raw"],
        "hh_raw_not_in_sqlite": tot["raw_not_sqlite"],
        "hh_sqlite_not_in_raw": tot["sqlite_not_raw"],
        "frac_q_dropped_because_sentinel": round(tot["q_on_sentinel"] / gq, 4),
        "mjjjas": season({5, 6, 7, 8, 9}),
        "ndj": season({11, 12, 1}),
        "hh_q_only_csv": "data/lipetsk/csv/hh_q_only.csv",
        "note": (
            "All sqlite Q rows are in the raw minutes. Importer drops Q when NGO>=9000. "
            "March 2024 is a real Q outage (~96 half-hours); Sep 2024 is Q-complete but 97.5% sentinel. "
            "hh_q_only.csv is the 30-min Q series without the NGO inner join."
        ),
    }
    (OUT / "q_raw_vs_ngo_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
