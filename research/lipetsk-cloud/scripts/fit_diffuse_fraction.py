#!/usr/bin/env python3
"""Fit Moscow Univ. daily diffuse-fraction models (Erbs / Reindl analogs).

WRDC MOSCOW UNIV. tables are daily sums, so this is a daily Kd(Kt[, α]) model,
not an hourly Erbs/Reindl replacement. Published hourly formulas are scored
on the same daily Kt only as a baseline.

Station: 55.70 N, 37.50 E, 192 m.
Solar constant: 1367 W/m² (Duffie & Beckman).
"""

from __future__ import annotations

import csv
import json
import math
from calendar import monthrange
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "wrdc" / "moscow_univ" / "csv" / "daily_ghi_dhi.csv"
OUT = ROOT / "data" / "wrdc" / "moscow_univ" / "models"
LAT_DEG = 55.70
LON_DEG = 37.50
GSC = 1367.0  # W/m²
LAT = math.radians(LAT_DEG)

TRAIN_YEARS = set(range(1991, 2013))
VAL_YEARS = set(range(2013, 2019))
TEST_YEARS = {2019, 2020, 2021, 2023, 2024}


def day_of_year(year: int, month: int, day: int) -> int:
    n = day
    for m in range(1, month):
        n += monthrange(year, m)[1]
    return n


def declination(n: int) -> float:
    return math.radians(23.45) * math.sin(math.radians(360.0 * (284 + n) / 365.0))


def eccentricity(n: int) -> float:
    return 1.0 + 0.033 * math.cos(math.radians(360.0 * n / 365.0))


def sunset_hour_angle(dec: float) -> float:
    arg = -math.tan(LAT) * math.tan(dec)
    arg = min(1.0, max(-1.0, arg))
    return math.acos(arg)


def h0_mj(n: int) -> float:
    dec = declination(n)
    e0 = eccentricity(n)
    ws = sunset_hour_angle(dec)
    geo = math.cos(LAT) * math.cos(dec) * math.sin(ws) + ws * math.sin(LAT) * math.sin(dec)
    return (24.0 * 3600.0 / math.pi) * GSC * e0 * geo / 1_000_000.0


def sin_alpha_noon(dec: float) -> float:
    return min(1.0, max(0.0, math.sin(LAT) * math.sin(dec) + math.cos(LAT) * math.cos(dec)))


def sin_alpha_daylight_mean(dec: float, ws: float) -> float:
    if ws <= 1e-9:
        return 0.0
    return min(
        1.0,
        max(
            0.0,
            math.sin(LAT) * math.sin(dec) + math.cos(LAT) * math.cos(dec) * math.sin(ws) / ws,
        ),
    )


def load_rows() -> list[dict]:
    rows = []
    with SRC.open(encoding="utf-8") as fh:
        for rec in csv.DictReader(fh):
            if rec["ghi_j_cm2"] == "" or rec["dhi_j_cm2"] == "":
                continue
            if rec["ghi_flag"] not in {"0", ""} or rec["dhi_flag"] not in {"0", ""}:
                continue
            ghi = int(rec["ghi_j_cm2"])
            dhi = int(rec["dhi_j_cm2"])
            if ghi < 50 or dhi < 0 or dhi > ghi:
                continue
            year, month, day = int(rec["year"]), int(rec["month"]), int(rec["day"])
            n = day_of_year(year, month, day)
            h0 = h0_mj(n)
            if h0 < 1.0:
                continue
            h = ghi / 100.0
            hd = dhi / 100.0
            kt = h / h0
            kd = hd / h
            if not (0.03 <= kt <= 0.85 and 0.0 <= kd <= 1.0):
                continue
            dec = declination(n)
            ws = sunset_hour_angle(dec)
            rec_out = {
                "date": rec["date"],
                "year": year,
                "month": month,
                "day": day,
                "doy": n,
                "h_mj": h,
                "hd_mj": hd,
                "h0_mj": round(h0, 4),
                "kt": kt,
                "kd": kd,
                "ws_deg": math.degrees(ws),
                "sin_alpha_noon": sin_alpha_noon(dec),
                "sin_alpha_mean": sin_alpha_daylight_mean(dec, ws),
                "alpha_noon_deg": math.degrees(math.asin(sin_alpha_noon(dec))),
            }
            rec_out["split"] = split_of(year)
            rows.append(rec_out)
    return rows


def split_of(year: int) -> str:
    if year in TRAIN_YEARS:
        return "train"
    if year in VAL_YEARS:
        return "val"
    if year in TEST_YEARS:
        return "test"
    return "other"


def clip01(x: np.ndarray | float) -> np.ndarray | float:
    return np.clip(x, 0.0, 1.0)


def erbs_hourly(kt: np.ndarray) -> np.ndarray:
    kd = np.empty_like(kt, dtype=float)
    lo = kt <= 0.22
    mid = (kt > 0.22) & (kt <= 0.80)
    hi = kt > 0.80
    kd[lo] = 1.0 - 0.09 * kt[lo]
    k = kt[mid]
    kd[mid] = 0.9511 - 0.1604 * k + 4.388 * k**2 - 16.638 * k**3 + 12.336 * k**4
    kd[hi] = 0.165
    return clip01(kd)


def erbs_daily(kt: np.ndarray, ws_deg: np.ndarray) -> np.ndarray:
    kd = np.empty_like(kt, dtype=float)
    short = ws_deg <= 81.4
    k = kt[short]
    kd[short] = np.where(
        k < 0.715,
        1.0 - 0.2727 * k + 2.4495 * k**2 - 11.9514 * k**3 + 9.3879 * k**4,
        0.143,
    )
    k = kt[~short]
    kd[~short] = np.where(
        k < 0.722,
        1.0 + 0.2832 * k - 2.5557 * k**2 + 0.8448 * k**3,
        0.175,
    )
    return clip01(kd)


def reindl1(kt: np.ndarray) -> np.ndarray:
    kd = np.empty_like(kt, dtype=float)
    lo = kt <= 0.3
    mid = (kt > 0.3) & (kt < 0.78)
    hi = kt >= 0.78
    kd[lo] = clip01(1.020 - 0.248 * kt[lo])
    kd[mid] = clip01(1.45 - 1.67 * kt[mid])
    kd[hi] = 0.147
    return kd


def reindl2(kt: np.ndarray, sin_a: np.ndarray) -> np.ndarray:
    kd = np.empty_like(kt, dtype=float)
    lo = kt <= 0.3
    mid = (kt > 0.3) & (kt < 0.78)
    hi = kt >= 0.78
    kd[lo] = clip01(1.020 - 0.254 * kt[lo] + 0.0123 * sin_a[lo])
    kd[mid] = clip01(1.400 - 1.749 * kt[mid] + 0.177 * sin_a[mid])
    kd[hi] = clip01(0.486 * kt[hi] - 0.182 * sin_a[hi])
    return kd


def lstsq_fit(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    return beta


def predict_piecewise_kt(kt: np.ndarray, k1: float, k2: float, pieces: dict) -> np.ndarray:
    kd = np.empty_like(kt, dtype=float)
    lo = kt <= k1
    mid = (kt > k1) & (kt <= k2)
    hi = kt > k2
    a = pieces["lo"]
    kd[lo] = a[0] + a[1] * kt[lo]
    b = pieces["mid"]
    k = kt[mid]
    kd[mid] = b[0] + b[1] * k + b[2] * k**2 + b[3] * k**3
    c = pieces["hi"]
    kd[hi] = c[0] + c[1] * kt[hi]
    return clip01(kd)


def fit_msu_kt(kt: np.ndarray, kd: np.ndarray, k1: float, k2: float) -> dict:
    lo = kt <= k1
    mid = (kt > k1) & (kt <= k2)
    hi = kt > k2
    pieces = {}
    xlo = np.column_stack([np.ones(lo.sum()), kt[lo]])
    pieces["lo"] = lstsq_fit(xlo, kd[lo]).tolist()
    k = kt[mid]
    xmid = np.column_stack([np.ones(mid.sum()), k, k**2, k**3])
    pieces["mid"] = lstsq_fit(xmid, kd[mid]).tolist()
    xhi = np.column_stack([np.ones(hi.sum()), kt[hi]])
    pieces["hi"] = lstsq_fit(xhi, kd[hi]).tolist()
    return {"k1": k1, "k2": k2, "pieces": pieces}


def predict_msu_alpha(kt: np.ndarray, sin_a: np.ndarray, k1: float, k2: float, pieces: dict) -> np.ndarray:
    kd = np.empty_like(kt, dtype=float)
    masks = {
        "lo": kt <= k1,
        "mid": (kt > k1) & (kt <= k2),
        "hi": kt > k2,
    }
    for name, mask in masks.items():
        a = pieces[name]
        kd[mask] = a[0] + a[1] * kt[mask] + a[2] * sin_a[mask]
    return clip01(kd)


def fit_msu_alpha(kt: np.ndarray, sin_a: np.ndarray, kd: np.ndarray, k1: float, k2: float) -> dict:
    pieces = {}
    masks = {
        "lo": kt <= k1,
        "mid": (kt > k1) & (kt <= k2),
        "hi": kt > k2,
    }
    for name, mask in masks.items():
        x = np.column_stack([np.ones(mask.sum()), kt[mask], sin_a[mask]])
        pieces[name] = lstsq_fit(x, kd[mask]).tolist()
    return {"k1": k1, "k2": k2, "pieces": pieces}


def metrics(y: np.ndarray, yhat: np.ndarray, h: np.ndarray | None = None) -> dict:
    err = yhat - y
    rmse = float(np.sqrt(np.mean(err**2)))
    mae = float(np.mean(np.abs(err)))
    mbe = float(np.mean(err))
    ss_res = float(np.sum(err**2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    out = {
        "n": int(len(y)),
        "rmse_kd": round(rmse, 4),
        "mae_kd": round(mae, 4),
        "mbe_kd": round(mbe, 4),
        "r2_kd": round(r2, 4),
    }
    if h is not None:
        dhi_err = err * h
        out["rmse_dhi_mj"] = round(float(np.sqrt(np.mean(dhi_err**2))), 3)
        out["mbe_dhi_mj"] = round(float(np.mean(dhi_err)), 3)
    return out


def fmt_poly(coeffs: list[float], names: list[str]) -> str:
    parts = []
    for c, name in zip(coeffs, names, strict=True):
        if abs(c) < 5e-5:
            continue
        if not parts:
            parts.append(f"{c:.4f}" if name == "1" else f"{c:.4f} {name}")
        else:
            sign = "+" if c >= 0 else "−"
            parts.append(f"{sign} {abs(c):.4f}" if name == "1" else f"{sign} {abs(c):.4f} {name}")
    return " ".join(parts) if parts else "0"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = load_rows()
    print(f"usable days: {len(rows)}")
    by_split = {s: sum(1 for r in rows if r["split"] == s) for s in ("train", "val", "test", "other")}
    print("splits", by_split)

    def pack(split: str | None = None):
        subset = rows if split is None else [r for r in rows if r["split"] == split]
        return {
            "kt": np.array([r["kt"] for r in subset]),
            "kd": np.array([r["kd"] for r in subset]),
            "h": np.array([r["h_mj"] for r in subset]),
            "ws": np.array([r["ws_deg"] for r in subset]),
            "sin_n": np.array([r["sin_alpha_noon"] for r in subset]),
            "sin_m": np.array([r["sin_alpha_mean"] for r in subset]),
            "month": np.array([r["month"] for r in subset]),
            "year": np.array([r["year"] for r in subset]),
        }

    train, val = pack("train"), pack("val")

    best = None
    for k1 in np.arange(0.18, 0.34, 0.01):
        for k2 in np.arange(0.62, 0.82, 0.01):
            if k2 <= k1 + 0.15:
                continue
            if (train["kt"] <= k1).sum() < 80 or ((train["kt"] > k1) & (train["kt"] <= k2)).sum() < 200:
                continue
            if (train["kt"] > k2).sum() < 40:
                continue
            model = fit_msu_kt(train["kt"], train["kd"], float(k1), float(k2))
            pred = predict_piecewise_kt(val["kt"], model["k1"], model["k2"], model["pieces"])
            rmse = float(np.sqrt(np.mean((pred - val["kd"]) ** 2)))
            if best is None or rmse < best[0]:
                model["k1"] = round(float(k1), 2)
                model["k2"] = round(float(k2), 2)
                best = (rmse, model)
    msu_kt = best[1]
    print("best msu_kt", round(best[0], 4), msu_kt["k1"], msu_kt["k2"])

    best_a = None
    k1, k2 = msu_kt["k1"], msu_kt["k2"]
    for sin_name in ("sin_n", "sin_m"):
        model = fit_msu_alpha(train["kt"], train[sin_name], train["kd"], k1, k2)
        pred = predict_msu_alpha(val["kt"], val[sin_name], k1, k2, model["pieces"])
        rmse = float(np.sqrt(np.mean((pred - val["kd"]) ** 2)))
        if best_a is None or rmse < best_a[0]:
            best_a = (rmse, model, sin_name)
    msu_a = best_a[1]
    sin_key = best_a[2]
    print("best msu_alpha", round(best_a[0], 4), sin_key)

    # refit chosen forms on train+val, score on test (and report all-data)
    fitset = pack()
    # only train+val for final coefficients
    tv_mask = np.array([r["split"] in {"train", "val"} for r in rows])
    kt_tv, kd_tv = fitset["kt"][tv_mask], fitset["kd"][tv_mask]
    sin_tv = fitset[sin_key][tv_mask]
    msu_kt = fit_msu_kt(kt_tv, kd_tv, msu_kt["k1"], msu_kt["k2"])
    msu_a = fit_msu_alpha(kt_tv, sin_tv, kd_tv, msu_a["k1"], msu_a["k2"])

    models_pred = {
        "Erbs hourly (на суточный Kt)": lambda d: erbs_hourly(d["kt"]),
        "Erbs daily": lambda d: erbs_daily(d["kt"], d["ws"]),
        "Reindl-1 (kt)": lambda d: reindl1(d["kt"]),
        "Reindl-2 (kt, α noon)": lambda d: reindl2(d["kt"], d["sin_n"]),
        "МГУ-Эрбс (kt)": lambda d: predict_piecewise_kt(d["kt"], msu_kt["k1"], msu_kt["k2"], msu_kt["pieces"]),
        "МГУ-Рейндл (kt, α)": lambda d: predict_msu_alpha(
            d["kt"], d[sin_key], msu_a["k1"], msu_a["k2"], msu_a["pieces"]
        ),
    }

    metric_rows = []
    for split in ("train", "val", "test", "all"):
        data = pack() if split == "all" else pack(split)
        if split == "all":
            data = pack()
        for name, fn in models_pred.items():
            m = metrics(data["kd"], fn(data), data["h"])
            m["model"] = name
            m["split"] = split
            metric_rows.append(m)
            if split in {"test", "all"}:
                print(f"{split:5s} {name:32s} RMSE kd={m['rmse_kd']:.4f}  DHI={m['rmse_dhi_mj']:.3f}  MBE={m['mbe_kd']:+.4f}  R2={m['r2_kd']:.3f}")

    # empirical bins on test
    test = pack("test")
    edges = np.arange(0.05, 0.81, 0.05)
    binned = []
    for i in range(len(edges) - 1):
        mask = (test["kt"] >= edges[i]) & (test["kt"] < edges[i + 1])
        if mask.sum() < 8:
            continue
        kt_mid = float(0.5 * (edges[i] + edges[i + 1]))
        kd_mean = float(np.mean(test["kd"][mask]))
        kd_p25 = float(np.percentile(test["kd"][mask], 25))
        kd_p75 = float(np.percentile(test["kd"][mask], 75))
        row = {
            "kt": round(kt_mid, 3),
            "n": int(mask.sum()),
            "kd_mean": round(kd_mean, 4),
            "kd_p25": round(kd_p25, 4),
            "kd_p75": round(kd_p75, 4),
        }
        dummy_kt = np.array([kt_mid])
        dummy_ws = np.array([float(np.mean(test["ws"][mask]))])
        dummy_sin_n = np.array([float(np.mean(test["sin_n"][mask]))])
        dummy_sin_m = np.array([float(np.mean(test["sin_m"][mask]))])
        dummy = {
            "kt": dummy_kt,
            "ws": dummy_ws,
            "sin_n": dummy_sin_n,
            "sin_m": dummy_sin_m,
        }
        for name, fn in models_pred.items():
            row[name] = round(float(fn(dummy)[0]), 4)
        binned.append(row)

    by_month = []
    for month in range(1, 13):
        mask = test["month"] == month
        if mask.sum() < 20:
            continue
        d = {k: v[mask] for k, v in test.items()}
        rec = {"month": month, "n": int(mask.sum())}
        for name, fn in models_pred.items():
            rec[name] = metrics(d["kd"], fn(d), d["h"])["rmse_kd"]
        by_month.append(rec)

    curve_kt = np.round(np.linspace(0.05, 0.80, 76), 3)
    # curves at mean test geometry vs kt
    mean_ws = float(np.mean(test["ws"]))
    mean_sin_n = float(np.mean(test["sin_n"]))
    mean_sin_m = float(np.mean(test["sin_m"]))
    curves = {"kt": curve_kt.tolist()}
    dummy = {
        "kt": curve_kt,
        "ws": np.full_like(curve_kt, mean_ws),
        "sin_n": np.full_like(curve_kt, mean_sin_n),
        "sin_m": np.full_like(curve_kt, mean_sin_m),
    }
    for name, fn in models_pred.items():
        curves[name] = [round(float(x), 4) for x in fn(dummy)]

    # winter / summer curves for MSU-Reindl
    for label, months in (("winter", {11, 12, 1, 2}), ("summer", {5, 6, 7, 8})):
        mask = np.isin(test["month"], list(months))
        dummy_s = {
            "kt": curve_kt,
            "ws": np.full_like(curve_kt, float(np.mean(test["ws"][mask]))),
            "sin_n": np.full_like(curve_kt, float(np.mean(test["sin_n"][mask]))),
            "sin_m": np.full_like(curve_kt, float(np.mean(test["sin_m"][mask]))),
        }
        curves[f"МГУ-Рейндл {label}"] = [
            round(float(x), 4)
            for x in predict_msu_alpha(
                dummy_s["kt"], dummy_s[sin_key], msu_a["k1"], msu_a["k2"], msu_a["pieces"]
            )
        ]

    alpha_name = "sin(α_noon)" if sin_key == "sin_n" else "sin(α_daylight mean)"
    formulas = {
        "msu_erbs": {
            "name": "МГУ-Эрбс",
            "type": "daily Kd(Kt)",
            "k1": msu_kt["k1"],
            "k2": msu_kt["k2"],
            "pieces": msu_kt["pieces"],
            "text": [
                f"Kt ≤ {msu_kt['k1']:.2f}:  Kd = {fmt_poly(msu_kt['pieces']['lo'], ['1', 'Kt'])}",
                f"{msu_kt['k1']:.2f} < Kt ≤ {msu_kt['k2']:.2f}:  Kd = {fmt_poly(msu_kt['pieces']['mid'], ['1', 'Kt', 'Kt²', 'Kt³'])}",
                f"Kt > {msu_kt['k2']:.2f}:  Kd = {fmt_poly(msu_kt['pieces']['hi'], ['1', 'Kt'])}",
                "затем 0 ≤ Kd ≤ 1",
            ],
        },
        "msu_reindl": {
            "name": "МГУ-Рейндл",
            "type": "daily Kd(Kt, α)",
            "k1": msu_a["k1"],
            "k2": msu_a["k2"],
            "sin_alpha": sin_key,
            "sin_alpha_label": alpha_name,
            "pieces": msu_a["pieces"],
            "text": [
                f"α — высота Солнца в полдень; используем {alpha_name}",
                f"Kt ≤ {msu_a['k1']:.2f}:  Kd = {fmt_poly(msu_a['pieces']['lo'], ['1', 'Kt', alpha_name])}",
                f"{msu_a['k1']:.2f} < Kt ≤ {msu_a['k2']:.2f}:  Kd = {fmt_poly(msu_a['pieces']['mid'], ['1', 'Kt', alpha_name])}",
                f"Kt > {msu_a['k2']:.2f}:  Kd = {fmt_poly(msu_a['pieces']['hi'], ['1', 'Kt', alpha_name])}",
                "затем 0 ≤ Kd ≤ 1",
            ],
        },
    }

    payload = {
        "station": "MOSCOW UNIV.",
        "lat": LAT_DEG,
        "lon": LON_DEG,
        "gsc_w_m2": GSC,
        "note": "Daily analog of Erbs/Reindl fitted on WRDC MOSCOW UNIV. GHI+DHI. Not an hourly model.",
        "filters": "F=0, GHI≥50 J/cm², 0≤DHI≤GHI, 0.03≤Kt≤0.85, H0≥1 MJ/m²",
        "splits": {
            "train": "1991–2012",
            "val": "2013–2018",
            "test": "2019–2021, 2023–2024",
        },
        "n": by_split,
        "n_total": len(rows),
        "formulas": formulas,
        "metrics": metric_rows,
        "binned_test": binned,
        "rmse_by_month_test": by_month,
        "curves": curves,
    }

    (OUT / "msu_diffuse_fraction.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    with (OUT / "metrics.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["model", "split", "n", "rmse_kd", "mae_kd", "mbe_kd", "r2_kd", "rmse_dhi_mj", "mbe_dhi_mj"],
        )
        writer.writeheader()
        writer.writerows(metric_rows)

    with (OUT / "daily_kt_kd.csv").open("w", newline="", encoding="utf-8") as fh:
        fieldnames = [
            "date",
            "year",
            "month",
            "split",
            "h_mj",
            "hd_mj",
            "h0_mj",
            "kt",
            "kd",
            "ws_deg",
            "alpha_noon_deg",
            "sin_alpha_noon",
            "sin_alpha_mean",
            "kd_erbs_daily",
            "kd_reindl2",
            "kd_msu_erbs",
            "kd_msu_reindl",
        ]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        all_d = pack()
        preds = {
            "kd_erbs_daily": erbs_daily(all_d["kt"], all_d["ws"]),
            "kd_reindl2": reindl2(all_d["kt"], all_d["sin_n"]),
            "kd_msu_erbs": predict_piecewise_kt(all_d["kt"], msu_kt["k1"], msu_kt["k2"], msu_kt["pieces"]),
            "kd_msu_reindl": predict_msu_alpha(all_d["kt"], all_d[sin_key], msu_a["k1"], msu_a["k2"], msu_a["pieces"]),
        }
        for i, r in enumerate(rows):
            writer.writerow(
                {
                    "date": r["date"],
                    "year": r["year"],
                    "month": r["month"],
                    "split": r["split"],
                    "h_mj": f"{r['h_mj']:.2f}",
                    "hd_mj": f"{r['hd_mj']:.2f}",
                    "h0_mj": f"{r['h0_mj']:.4f}",
                    "kt": f"{r['kt']:.4f}",
                    "kd": f"{r['kd']:.4f}",
                    "ws_deg": f"{r['ws_deg']:.2f}",
                    "alpha_noon_deg": f"{r['alpha_noon_deg']:.2f}",
                    "sin_alpha_noon": f"{r['sin_alpha_noon']:.4f}",
                    "sin_alpha_mean": f"{r['sin_alpha_mean']:.4f}",
                    "kd_erbs_daily": f"{preds['kd_erbs_daily'][i]:.4f}",
                    "kd_reindl2": f"{preds['kd_reindl2'][i]:.4f}",
                    "kd_msu_erbs": f"{preds['kd_msu_erbs'][i]:.4f}",
                    "kd_msu_reindl": f"{preds['kd_msu_reindl'][i]:.4f}",
                }
            )

    md = []
    md.append("# МГУ-Эрбс и МГУ-Рейндл")
    md.append("")
    md.append("Суточный аналог формул Erbs (1982) и Reindl-2 (1990) по актинометрии WRDC **MOSCOW UNIV.**")
    md.append("Не замена часовому Эрбсу: у WRDC сутки, а не часы. Для поминутной/почасовой станции МГУ формулу нужно переподобрать.")
    md.append("")
    md.append("Kt = H / H0,  Kd = Hd / H,  H0 по Duffie & Beckman, Gsc = 1367 Вт/м², φ = 55.70°.")
    md.append("Обучение 1991–2012, подбор порогов 2013–2018, проверка 2019–2021 и 2023–2024. Коэффициенты финально на train+val.")
    md.append("")
    md.append("## МГУ-Эрбс")
    md.append("")
    for line in formulas["msu_erbs"]["text"]:
        md.append(f"- {line}")
    md.append("")
    md.append("## МГУ-Рейндл")
    md.append("")
    for line in formulas["msu_reindl"]["text"]:
        md.append(f"- {line}")
    md.append("")
    md.append("Прямая на горизонталь: `Bh = (1 − Kd) · H`.")
    (OUT / "FORMULAS.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
