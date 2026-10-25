"""Probe raw minute files: SSD vs GHI relation and minutes per 30-min slot.

Reads raw pyranometer CSVs read-only. Writes audit/ssd_minute_probe.json.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAW = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    r"D:\dev\SPES_Raschet\метеорология\липецкая область\Суммарная солнечная радиация")
OUT = Path(__file__).with_name("ssd_minute_probe.json")


def load(path):
    df = pd.read_csv(path, sep=";", decimal=",", encoding="cp1251")
    df.columns = ["t", "q", "temp", "mv", "ssd"]
    df["t"] = pd.to_datetime(df["t"], format="%d.%m.%Y %H:%M:%S", errors="coerce")
    for col in ["q", "temp", "mv", "ssd"]:
        df[col] = pd.to_numeric(df[col].astype(str).str.replace(",", ".", regex=False), errors="coerce")
    return df.dropna(subset=["t", "q", "ssd"])


LAT = 52.135409
LON = 39.163510


def sin_elev_utc(t):
    """Sine of solar elevation for UTC timestamps (NOAA approximations)."""
    doy = t.dt.dayofyear.values
    hr = (t.dt.hour + t.dt.minute / 60.0).values
    g = 2 * np.pi / 365 * (doy - 1 + (hr - 12) / 24)
    eot = 229.18 * (0.000075 + 0.001868 * np.cos(g) - 0.032077 * np.sin(g)
                    - 0.014615 * np.cos(2 * g) - 0.040849 * np.sin(2 * g))
    decl = (0.006918 - 0.399912 * np.cos(g) + 0.070257 * np.sin(g) - 0.006758 * np.cos(2 * g)
            + 0.000907 * np.sin(2 * g) - 0.002697 * np.cos(3 * g) + 0.00148 * np.sin(3 * g))
    tst = hr * 60 + eot + 4 * LON
    omega = np.radians(tst / 4 - 180)
    phi = np.radians(LAT)
    e0 = 1 + 0.033 * np.cos(2 * np.pi * doy / 365)
    return np.sin(phi) * np.sin(decl) + np.cos(phi) * np.cos(decl) * np.cos(omega), e0


def kt_separability(day):
    sh, e0 = sin_elev_utc(day["t"])
    sel = sh > np.sin(np.radians(3))
    q = day["q"].values[sel]
    ssd = day["ssd"].values[sel]
    kt = q / (1361 * e0[sel] * sh[sel])
    res = {}
    for name, x in (("ghi", q), ("kt", kt)):
        best = None
        for thr in np.quantile(x, np.linspace(0.05, 0.95, 181)):
            acc = float(((x > thr) == (ssd > 30)).mean())
            if best is None or acc > best[1]:
                best = (float(thr), acc)
        res[name] = {"best_threshold": round(best[0], 4), "accuracy_ssd_gt_30": round(best[1], 4)}
    res["n_minutes_elev_gt_3"] = int(sel.sum())
    return res


def main():
    files = sorted(RAW.rglob("*.csv"))
    frames = [load(p) for p in files]
    df = pd.concat(frames, ignore_index=True).drop_duplicates("t").sort_values("t")
    df = df[(df["q"] >= 0) & (df["ssd"] >= 0) & (df["ssd"] <= 60)]

    day = df[df["q"] > 5]
    sun = day[day["ssd"] > 0]
    nosun = day[day["ssd"] == 0]
    full = day[day["ssd"] == 60]
    partial = day[(day["ssd"] > 0) & (day["ssd"] < 60)]

    q_edges = [0, 50, 100, 120, 150, 200, 300, 500, 800, 2000]
    share_by_q = {}
    for lo, hi in zip(q_edges[:-1], q_edges[1:]):
        sel = day[(day["q"] > lo) & (day["q"] <= hi)]
        if len(sel):
            share_by_q[f"{lo}-{hi}"] = {
                "n": int(len(sel)),
                "share_ssd_pos": round(float((sel["ssd"] > 0).mean()), 4),
                "share_ssd_60": round(float((sel["ssd"] == 60).mean()), 4),
            }

    out_kt = kt_separability(day)

    slot = df["t"].dt.floor("30min")
    n_per_slot = slot.value_counts()
    month = df["t"].dt.month
    winter = df[month.isin([11, 12, 1, 2, 3])]
    out = {
        "files": len(files),
        "minutes": int(len(df)),
        "t_min": str(df["t"].min()),
        "t_max": str(df["t"].max()),
        "ssd_unique_values_count": int(df["ssd"].nunique()),
        "ssd_is_integer": bool(np.allclose(df["ssd"], df["ssd"].round())),
        "daylight_minutes_q_gt_5": int(len(day)),
        "share_ssd_pos": round(float(len(sun) / len(day)), 4),
        "share_ssd_partial_1_59": round(float(len(partial) / len(day)), 4),
        "q_quantiles_when_ssd_60": [round(float(x), 1) for x in full["q"].quantile([0.01, 0.05, 0.5]).values],
        "q_quantiles_when_ssd_0": [round(float(x), 1) for x in nosun["q"].quantile([0.5, 0.95, 0.99]).values],
        "share_by_q_bin": share_by_q,
        "slots_total": int(len(n_per_slot)),
        "slot_minutes_quantiles_p1_p5_p50": [int(x) for x in n_per_slot.quantile([0.01, 0.05, 0.5]).values],
        "share_slots_ge_24_min": round(float((n_per_slot >= 24).mean()), 4),
        "share_slots_eq_30_min": round(float((n_per_slot == 30).mean()), 4),
        "winter_minutes": int(len(winter)),
        "kt_separability_labels_as_utc": out_kt,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
