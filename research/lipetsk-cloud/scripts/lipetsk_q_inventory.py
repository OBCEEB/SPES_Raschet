#!/usr/bin/env python3
"""Инвентаризация сырых минутных CSV суммарной радиации Конь-Колодезя.

Файлы: data/lipetsk/obs/q/YYYY/YYYYMM/yymmdd.csv
Заголовок: Время;Q, Вт/м2;T, °C;Q, мВ;SSD, c
Пустой слот: токен `/`. Дни overflow (32-е) — заглушки. День `00` часто
держит **предыдущие** календарные сутки (живой Q), не пустышку.
"""

from __future__ import annotations

import csv
import json
from calendar import monthrange
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
Q_DIR = ROOT / "data" / "lipetsk" / "obs" / "q"
OUT = ROOT / "data" / "lipetsk" / "csv"


def parse_q(cell: str) -> float | None:
    s = (cell or "").strip().replace(",", ".")
    if not s or s == "/":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def classify_name(name: str) -> dict:
    stem = Path(name).stem
    if len(stem) != 6 or not stem.isdigit():
        return {"kind": "bad_name", "stem": stem}
    yy, mm, dd = int(stem[:2]), int(stem[2:4]), int(stem[4:6])
    year = 2000 + yy
    if not 1 <= mm <= 12:
        return {"kind": "bad_month", "year": year, "month": mm, "day": dd, "stem": stem}
    if dd == 0:
        return {"kind": "stub_day00", "year": year, "month": mm, "day": 0, "stem": stem}
    last = monthrange(year, mm)[1]
    if dd > last:
        return {"kind": "stub_overflow", "year": year, "month": mm, "day": dd, "stem": stem}
    return {
        "kind": "calendar",
        "year": year,
        "month": mm,
        "day": dd,
        "stem": stem,
        "date": f"{year:04d}-{mm:02d}-{dd:02d}",
    }


def scan_file(path: Path, meta: dict) -> dict:
    text = path.read_bytes().decode("cp1251", errors="replace")
    rows = list(csv.reader(text.splitlines(), delimiter=";"))
    rec = {
        **meta,
        "bytes": path.stat().st_size,
        "n_rows": 0,
        "q_slash": 0,
        "q_num": 0,
        "q_other": 0,
        "q_min": None,
        "q_max": None,
        "first_ts": None,
        "last_ts": None,
    }
    if not rows:
        return rec
    start = 1 if rows[0] and "Q" in (rows[0][0] + (rows[0][1] if len(rows[0]) > 1 else "")) else 0
    for row in rows[start:]:
        if len(row) < 2:
            continue
        rec["n_rows"] += 1
        if rec["first_ts"] is None:
            rec["first_ts"] = row[0]
        rec["last_ts"] = row[0]
        v = parse_q(row[1])
        if v is None:
            if (row[1] or "").strip() == "/":
                rec["q_slash"] += 1
            else:
                rec["q_other"] += 1
        else:
            rec["q_num"] += 1
            rec["q_min"] = v if rec["q_min"] is None else min(rec["q_min"], v)
            rec["q_max"] = v if rec["q_max"] is None else max(rec["q_max"], v)
    return rec


def main() -> None:
    files = sorted(Q_DIR.glob("**/??????.csv"))
    per_file = []
    kinds = defaultdict(int)
    monthly = defaultdict(
        lambda: {
            "calendar_files": 0,
            "stub_files": 0,
            "rows": 0,
            "q_slash": 0,
            "q_num": 0,
            "q_other": 0,
        }
    )
    for p in files:
        meta = classify_name(p.name)
        rec = scan_file(p, meta)
        per_file.append(rec)
        kinds[meta["kind"]] += 1
        y, m = meta.get("year"), meta.get("month")
        if y and m:
            b = monthly[(y, m)]
            if meta["kind"] == "calendar":
                b["calendar_files"] += 1
            else:
                b["stub_files"] += 1
            b["rows"] += rec["n_rows"]
            b["q_slash"] += rec["q_slash"]
            b["q_num"] += rec["q_num"]
            b["q_other"] += rec["q_other"]

    OUT.mkdir(parents=True, exist_ok=True)
    fields = [
        "year",
        "month",
        "calendar_files",
        "stub_files",
        "rows",
        "q_slash",
        "q_num",
        "q_other",
        "q_num_frac",
    ]
    month_rows = []
    tot = defaultdict(int)
    for y, m in sorted(monthly):
        b = monthly[(y, m)]
        rec = {"year": y, "month": m, **b}
        rec["q_num_frac"] = round(b["q_num"] / b["rows"], 6) if b["rows"] else 0
        month_rows.append(rec)
        for k, v in b.items():
            tot[k] += v

    with (OUT / "q_raw_monthly.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(month_rows)

    years = sorted({r["year"] for r in month_rows})
    n_num = tot["q_num"]
    n_rows = tot["rows"] or 1
    summary = {
        "years_on_disk": years,
        "files": len(files),
        "kinds": dict(kinds),
        "rows": tot["rows"],
        "q_slash": tot["q_slash"],
        "q_num": n_num,
        "q_other": tot["q_other"],
        "q_num_frac": round(n_num / n_rows, 6),
        "q_min": min((r["q_min"] for r in per_file if r["q_min"] is not None), default=None),
        "q_max": max((r["q_max"] for r in per_file if r["q_max"] is not None), default=None),
        "first_live": next(
            (
                f"{r.get('stem')} {r['first_ts']}"
                for r in per_file
                if r["q_num"]
            ),
            None,
        ),
        "note": (
            "Minute CSV. Token '/' is empty. Day 00 and overflow dates are station stubs. "
            "2022 is entirely '/'. Live Q from 2023-02-28 sits in 230300.csv "
            "(day-00), not in the empty 230228.csv template. Raw files gitignored."
        ),
    }
    (OUT / "q_raw_inventory.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
