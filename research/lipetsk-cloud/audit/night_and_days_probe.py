"""After the time fix: GHI by solar elevation band and why complete days changed.

Reads data/lipetsk/csv (new) and data/lipetsk/csv_v1_time_bug (old).
Writes audit/night_and_days_probe.json.
"""
import csv
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from lipetsk_ingest import LAT, LON, solar_elevation_deg  # noqa: E402

NEW = ROOT / "data" / "lipetsk" / "csv"
OLD = ROOT / "data" / "lipetsk" / "csv_v1_time_bug"


def bands():
    edges = [(-90, -6), (-6, 0), (0, 5), (5, 90)]
    acc = {f"{a}..{b}": [] for a, b in edges}
    with (NEW / "hh_q_only.csv").open(encoding="utf-8") as f:
        for rec in csv.DictReader(f):
            t = datetime.strptime(rec["obs_time"], "%Y-%m-%d %H:%M:%S")
            e = solar_elevation_deg(t, LAT, LON)
            q = float(rec["q_wm2"])
            for a, b in edges:
                if a <= e < b:
                    acc[f"{a}..{b}"].append(q)
    out = {}
    for k, v in acc.items():
        v.sort()
        n = len(v)
        out[k] = {
            "n": n,
            "share_q_gt_0": round(sum(1 for x in v if x > 0) / n, 4) if n else None,
            "share_q_gt_5": round(sum(1 for x in v if x > 5) / n, 4) if n else None,
            "p50": round(v[n // 2], 2) if n else None,
            "p99": round(v[int(n * 0.99)], 2) if n else None,
        }
    return out


def complete_days(path):
    with path.open(encoding="utf-8") as f:
        return {r["date"]: r for r in csv.DictReader(f)}


def main():
    new, old = complete_days(NEW / "daily_obs_q_only.csv"), complete_days(OLD / "daily_obs_q_only.csv")
    cn = {d for d, r in new.items() if r["complete_daylight"] == "1"}
    co = {d for d, r in old.items() if r["complete_daylight"] == "1"}
    lost = sorted(co - cn)
    gained = sorted(cn - co)
    lost_detail = {d: {"n_daylight": new[d]["n_daylight"], "n_daylight_q": new[d]["n_daylight_q"]} for d in lost}
    out = {
        "ghi_by_elevation_band_new": bands(),
        "complete_old": len(co),
        "complete_new": len(cn),
        "lost": len(lost),
        "gained": len(gained),
        "lost_by_month": dict(Counter(d[:7] for d in lost)),
        "lost_missing_slots_hist": dict(Counter(int(v["n_daylight"]) - int(v["n_daylight_q"]) for v in lost_detail.values())),
        "lost_days": lost_detail,
        "gained_days": gained,
    }
    (Path(__file__).with_name("night_and_days_probe.json")).write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "lost_days"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
