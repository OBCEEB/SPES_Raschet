#!/usr/bin/env python3
"""Сутки из получасового ряда сырого Q (hh_q_only.csv) → daily_obs_q_only.csv.

complete_daylight: нет ни одной дыры среди слотов с высотой Солнца > 5°.
usable_0_2: дыр ≤ 20 %; H, Kt и МГУ-Рейндл выводятся для таких суток.
Метки hh_q_only.csv — MSK (перевод из шкалы файла делает lipetsk_q_vs_ngo).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from lipetsk_ingest import aggregate, load_csv, write_csv  # noqa: E402

CSV_DIR = ROOT / "data" / "lipetsk" / "csv"


def build(hh_path: Path) -> list[dict]:
    daily, _ = aggregate(load_csv(hh_path), 0.2)
    out = []
    for rec in daily:
        complete = rec["n_daylight"] > 0 and rec["n_daylight_q"] == rec["n_daylight"]
        row = {
            "date": rec["date"],
            "year": rec["year"],
            "month": rec["month"],
            "complete_daylight": int(complete),
            "usable_0_2": rec["usable"],
        }
        row.update({k: v for k, v in rec.items() if k not in ("date", "year", "month", "usable")})
        out.append(row)
    return out


def summarize(rows: list[dict]) -> dict:
    comp = [r for r in rows if r["complete_daylight"] == 1]
    usab = [r for r in rows if str(r["usable_0_2"]) == "1"]
    by_ym_cal = Counter(r["date"][:7] for r in rows)
    by_ym_comp = Counter(r["date"][:7] for r in comp)
    by_ym_usab = Counter(r["date"][:7] for r in usab)
    season = lambda rs, ms: sum(1 for r in rs if int(r["month"]) in ms)  # noqa: E731
    mjjas, ndj = {5, 6, 7, 8, 9}, {11, 12, 1}
    return {
        "calendar_days": len(rows),
        "complete_daylight_maxmiss_0": len(comp),
        "usable_maxmiss_0.2": len(usab),
        "complete_by_month_all_years": dict(sorted(Counter(int(r["month"]) for r in comp).items())),
        "usable02_by_month_all_years": dict(sorted(Counter(int(r["month"]) for r in usab).items())),
        "complete_by_year": dict(sorted(Counter(int(r["year"]) for r in comp).items())),
        "usable02_by_year": dict(sorted(Counter(int(r["year"]) for r in usab).items())),
        "complete_calendar_months": [ym for ym in sorted(by_ym_cal) if by_ym_comp[ym] == by_ym_cal[ym]],
        "usable02_calendar_months": [ym for ym in sorted(by_ym_cal) if by_ym_usab[ym] == by_ym_cal[ym]],
        "MJJAS_complete": {"ok": season(comp, mjjas), "calendar": season(rows, mjjas)},
        "MJJAS_usable02": {"ok": season(usab, mjjas), "calendar": season(rows, mjjas)},
        "NDJ_complete": {"ok": season(comp, ndj), "calendar": season(rows, ndj)},
        "NDJ_usable02": {"ok": season(usab, ndj), "calendar": season(rows, ndj)},
        "complete_ym": {ym: by_ym_comp[ym] for ym in sorted(by_ym_cal)},
        "usable02_ym": {ym: f"{by_ym_usab[ym]}/{by_ym_cal[ym]}" for ym in sorted(by_ym_cal)},
        "n_night_q_pos_complete_days": sum(int(r["n_night_q_pos"]) for r in comp),
        "complete_days_with_night_q_pos": sum(1 for r in comp if int(r["n_night_q_pos"]) > 0),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hh", default=str(CSV_DIR / "hh_q_only.csv"))
    ap.add_argument("--out-dir", default=str(CSV_DIR))
    args = ap.parse_args()
    rows = build(Path(args.hh))
    out_dir = Path(args.out_dir)
    write_csv(out_dir / "daily_obs_q_only.csv", rows)
    summary = summarize(rows)
    (out_dir / "q_only_days_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: summary[k] for k in list(summary)[:3]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
