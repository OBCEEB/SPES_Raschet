#!/usr/bin/env python3
"""Этапы 4 и 7: регрессия Kt по метео (не по sqlite) и ISO 9806 Qobs vs Qcs.

Сияние и T — из минуток. НГО=9999 → флаг «нет низкой кромки», Q не выкидываем.
Параметры коллектора — типичный остеклённый плоский (не конкретное изделие):
  η0=0.78, a1=3.5 Вт/м²K, a2=0.015 Вт/м²K², b0=0.1, Tm−Ta=40 K (ГВС).
"""

from __future__ import annotations

import csv
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from lipetsk_gti import (  # noqa: E402
    BETA,
    DT_S,
    LAT,
    MIN_COSZ,
    RHO,
    decl_e0,
    erbs_hourly,
    hottel_tau,
    i0_wm2,
    liu_jordan,
    rb_south_lat,
)
from lipetsk_q_vs_ngo import MIN_MINUTES  # noqa: E402
from lipetsk_time import asmg_to_msk, pyranometer_to_msk  # noqa: E402

Q_DIR = ROOT / "data" / "lipetsk" / "obs" / "q"
NGO_DIR = ROOT / "data" / "lipetsk" / "obs" / "ngo"
HH_Q = ROOT / "data" / "lipetsk" / "csv" / "hh_q_only.csv"
DAILY = ROOT / "data" / "lipetsk" / "csv" / "daily_obs_q_only.csv"
DAILY_GTI = ROOT / "data" / "lipetsk" / "csv" / "daily_gti.csv"
OUT = ROOT / "data" / "lipetsk" / "csv"

# Typical glazed flat-plate, ISO 9806 quadratic. Not a named product.
ETA0 = 0.78
A1 = 3.5
A2 = 0.015
B0 = 0.10
DT_COLL = 40.0  # Tm - Ta, K
IAM_DIFF_DEG = 60.0

START = datetime(2023, 2, 28)
END = datetime(2025, 12, 31, 23, 30)
STEP = timedelta(minutes=30)


def num(s: str) -> float | None:
    s = (s or "").strip().replace(",", ".")
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


def floor30(t: datetime) -> datetime:
    return t.replace(minute=0 if t.minute < 30 else 30, second=0, microsecond=0)


def kb(cost: float) -> float:
    if cost <= 0.15:
        return 0.0
    return max(0.0, 1.0 - B0 * (1.0 / cost - 1.0))


IAM_DIFFUSE = kb(math.cos(math.radians(IAM_DIFF_DEG)))


def load_complete() -> set[str]:
    s = set()
    with DAILY.open(encoding="utf-8") as f:
        for rec in csv.DictReader(f):
            if rec["complete_daylight"] == "1":
                s.add(rec["date"])
    return s


def load_hh_q() -> dict[datetime, float]:
    out = {}
    with HH_Q.open(encoding="utf-8") as f:
        for rec in csv.DictReader(f):
            t = datetime.strptime(rec["obs_time"], "%Y-%m-%d %H:%M:%S")
            out[t] = float(rec["q_wm2"])
    return out


def load_t_ssd() -> dict[datetime, dict]:
    """Mean T and SSD seconds over each 30-min MSK slot from minute CSVs.

    SSD is scaled to 30 minutes when 24..29 minutes are present; slots with
    fewer minutes get ssd=None, matching the GHI completeness rule.
    """
    acc: dict = defaultdict(lambda: {"t_sum": 0.0, "t_n": 0, "ssd": 0.0, "ssd_n": 0, "n": 0})
    seen: set = set()
    for p in Q_DIR.glob("**/*.csv"):
        if p.stat().st_size <= 41200:
            continue
        text = p.read_bytes().decode("cp1251", errors="replace")
        for row in csv.reader(text.splitlines(), delimiter=";"):
            if len(row) < 5 or not row[0][:1].isdigit():
                continue
            t = parse_ts(row[0])
            if t is None or num(row[1]) is None:
                continue
            t = pyranometer_to_msk(t)
            if t < START or t > END or t in seen:
                continue
            seen.add(t)
            key = floor30(t)
            acc[key]["n"] += 1
            tv = num(row[2])
            if tv is not None:
                acc[key]["t_sum"] += tv
                acc[key]["t_n"] += 1
            sv = num(row[4])
            if sv is not None:
                acc[key]["ssd"] += sv
                acc[key]["ssd_n"] += 1
    out = {}
    for k, a in acc.items():
        ssd = a["ssd"] * 30.0 / a["ssd_n"] if a["ssd_n"] >= MIN_MINUTES else None
        out[k] = {
            "t": (a["t_sum"] / a["t_n"]) if a["t_n"] else None,
            "ssd": ssd,
            "n_min": a["n"],
        }
    return out


def load_ngo() -> dict[datetime, dict]:
    out = {}
    for p in NGO_DIR.glob("c_202[3-5]*.csv"):
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
            v = num(row[29])
            n = num(row[23])
            out[t] = {"h": v, "n": n, "clear": bool(v is not None and v >= 9000)}
    return out


def slot_optics(t: datetime, q: float) -> dict:
    i0, cosz, w = i0_wm2(t)
    n = t.timetuple().tm_yday
    decl, _ = decl_e0(n)
    tb, td = hottel_tau(cosz, t.month)
    gcs = i0 * (tb + td) if i0 > 0 else 0.0
    kt = q / i0 if i0 > 20 else None
    rb = rb_south_lat(decl, w, cosz)
    cost = math.cos(decl) * math.cos(w)  # south, β=φ
    if kt is None:
        kd = None
        bh = dh = 0.0
        it = 0.0
    else:
        kd = erbs_hourly(min(max(kt, 0.0), 1.2))
        dh = kd * q
        bh = max(q - dh, 0.0)
        it = liu_jordan(bh, dh, q, rb)
    # clear-sky tilted: Hottel beam+diffuse through Liu-Jordan
    bh_cs = i0 * tb if i0 > 0 else 0.0
    dh_cs = i0 * td if i0 > 0 else 0.0
    ghi_cs = bh_cs + dh_cs
    it_cs = liu_jordan(bh_cs, dh_cs, ghi_cs, rb) if i0 > 20 else 0.0
    return {
        "i0": i0,
        "cosz": cosz,
        "cost": cost,
        "gcs": gcs,
        "kt": kt,
        "it": it,
        "it_cs": it_cs,
        "bh": bh if kt is not None else 0.0,
        "dh": dh if kt is not None else 0.0,
        "bh_cs": bh_cs,
        "dh_cs": dh_cs,
        "ghi_cs": ghi_cs,
        "rb": rb,
    }


def keff_iam(bh: float, dh: float, ghi: float, rb: float, it: float, cost: float) -> float:
    ibt = bh * rb
    idt = dh * (1.0 + math.cos(BETA)) / 2.0
    ir = ghi * RHO * (1.0 - math.cos(BETA)) / 2.0
    kbe = kb(cost)
    if it <= 5:
        return IAM_DIFFUSE
    return min(max((ibt * kbe + (idt + ir) * IAM_DIFFUSE) / it, 0.0), 1.2)


def qdot(g: float, k: float) -> float:
    if g <= 5:
        return 0.0
    eta = ETA0 * k - A1 * DT_COLL / g - A2 * DT_COLL * DT_COLL / g
    return max(eta, 0.0) * g


def useful(opt: dict, q: float, ta: float | None) -> tuple[float, float]:
    """ISO 9806 useful W/m²: observed IT vs Hottel clear-sky IT. Same ΔT."""
    if ta is None:
        return 0.0, 0.0
    k_obs = keff_iam(opt["bh"], opt["dh"], q, opt["rb"], opt["it"], opt["cost"])
    k_cs = keff_iam(
        opt["bh_cs"], opt["dh_cs"], opt["ghi_cs"], opt["rb"], opt["it_cs"], opt["cost"]
    )
    return qdot(opt["it"], k_obs), qdot(opt["it_cs"], k_cs)


def ols_fit(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    xtx = x.T @ x
    try:
        return np.linalg.solve(xtx, x.T @ y)
    except np.linalg.LinAlgError:
        return np.linalg.pinv(xtx) @ x.T @ y


def metrics(y: np.ndarray, yhat: np.ndarray) -> dict:
    e = yhat - y
    ss_res = float(np.sum(e**2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    return {
        "n": int(len(y)),
        "rmse": round(float(np.sqrt(ss_res / len(y))), 4),
        "mae": round(float(np.mean(np.abs(e))), 4),
        "mbe": round(float(np.mean(e)), 4),
        "r2": round(1.0 - ss_res / ss_tot, 4) if ss_tot else None,
    }


def main() -> None:
    complete = load_complete()
    print("loading Q, T/SSD, NGO...", flush=True)
    qq = load_hh_q()
    ts = load_t_ssd()
    ngo = load_ngo()
    daily_gti = {}
    with DAILY_GTI.open(encoding="utf-8") as f:
        for rec in csv.DictReader(f):
            daily_gti[rec["date"]] = rec

    day_acc = defaultdict(
        lambda: {
            "ssd": 0.0,
            "daylight_min": 0,
            "n9999": 0,
            "n_ngo": 0,
            "n_n": 0,
            "sum_n": 0.0,
            "t_sum": 0.0,
            "t_n": 0,
            "q_u": 0.0,
            "q_cs": 0.0,
            "it": 0.0,
            "it_cs": 0.0,
        }
    )

    t = START
    n_slots = 0
    while t <= END:
        d = t.strftime("%Y-%m-%d")
        q = qq.get(t)
        if q is not None and d in complete:
            opt = slot_optics(t, q)
            met = ts.get(t, {})
            ng = ngo.get(t, {})
            ta = met.get("t")
            qu, qcs = useful(opt, q, ta)
            b = day_acc[d]
            b["q_u"] += qu * DT_S / 1e6
            b["q_cs"] += qcs * DT_S / 1e6
            b["it"] += opt["it"] * DT_S / 1e6
            b["it_cs"] += opt["it_cs"] * DT_S / 1e6
            if ta is not None:
                b["t_sum"] += ta
                b["t_n"] += 1
            if opt["i0"] > 20:
                if met.get("ssd") is not None:
                    b["ssd"] += met["ssd"]
                    b["daylight_min"] += 30
                if ng:
                    b["n_ngo"] += 1
                    if ng.get("clear"):
                        b["n9999"] += 1
                    if ng.get("n") is not None:
                        b["sum_n"] += ng["n"]
                        b["n_n"] += 1
            n_slots += 1
        t += STEP

    rows = []
    for d in sorted(complete):
        g = daily_gti.get(d)
        if not g:
            continue
        a = day_acc[d]
        h = float(g["H_mjm2"])
        hcs = float(g["Gcs_hottel_mjm2"])
        i0 = float(g["I0_mjm2"])
        kt = h / i0 if i0 > 0 else None
        kref = hcs / i0 if i0 > 0 else None
        s = a["ssd"] / (a["daylight_min"] * 60.0) if a["daylight_min"] else None
        fcl = a["n9999"] / a["n_ngo"] if a["n_ngo"] else None
        nbar = a["sum_n"] / a["n_n"] if a["n_n"] else None
        ta = a["t_sum"] / a["t_n"] if a["t_n"] else None
        y, m = int(d[:4]), int(d[5:7])
        doy = datetime.strptime(d, "%Y-%m-%d").timetuple().tm_yday
        sina = math.sin(math.radians(LAT)) * math.sin(
            math.radians(23.45) * math.sin(math.radians(360.0 * (284 + doy) / 365.0))
        ) + math.cos(math.radians(LAT)) * math.cos(
            math.radians(23.45) * math.sin(math.radians(360.0 * (284 + doy) / 365.0))
        )
        rows.append(
            {
                "date": d,
                "year": y,
                "month": m,
                "Kt": round(kt, 4) if kt is not None else "",
                "Kref": round(kref, 4) if kref is not None else "",
                "s_ssd": round(s, 4) if s is not None else "",
                "f_ngo9999": round(fcl, 4) if fcl is not None else "",
                "N_mean": round(nbar, 3) if nbar is not None else "",
                "sin_alpha_noon": round(max(0.0, sina), 4),
                "Ta_c": round(ta, 2) if ta is not None else "",
                "H_mjm2": round(h, 4),
                "IT_mjm2": round(a["it"], 4),
                "IT_cs_mjm2": round(a["it_cs"], 4),
                "Qu_mjm2": round(a["q_u"], 4),
                "Qcs_mjm2": round(a["q_cs"], 4),
            }
        )

    fit_rows = [
        r
        for r in rows
        if r["Kt"] != ""
        and r["Kref"] != ""
        and r["s_ssd"] != ""
        and r["f_ngo9999"] != ""
        and r["N_mean"] != ""
        and r["Ta_c"] != ""
    ]

    def pack(rs, months_dummy=True):
        y = np.array([float(r["Kt"]) for r in rs])
        cols = [
            np.ones(len(rs)),
            np.array([float(r["Kref"]) for r in rs]),
            np.array([float(r["s_ssd"]) for r in rs]),
            np.array([float(r["f_ngo9999"]) for r in rs]),
            np.array([float(r["N_mean"]) for r in rs]),
            np.array([float(r["sin_alpha_noon"]) for r in rs]),
        ]
        names = ["intercept", "Kref", "s_ssd", "f_ngo9999", "N_mean", "sin_alpha"]
        if months_dummy:
            for m in range(1, 12):  # drop December
                cols.append(np.array([1.0 if int(r["month"]) == m else 0.0 for r in rs]))
                names.append(f"m{m:02d}")
        x = np.column_stack(cols)
        return x, y, names

    tests = {}
    for train_years, test_year in (
        ([2023, 2024], 2025),
        ([2023, 2025], 2024),
        ([2024, 2025], 2023),
    ):
        tr = [r for r in fit_rows if r["year"] in train_years]
        te = [r for r in fit_rows if r["year"] == test_year]
        if len(tr) < 50 or len(te) < 30:
            continue
        xtr, ytr, names = pack(tr)
        b = ols_fit(xtr, ytr)
        xte, yte, _ = pack(te)
        yhat = xte @ b
        # baseline: Kt = mean(train)
        yhat0 = np.full_like(yte, ytr.mean())
        tests[str(test_year)] = {
            "train_years": train_years,
            "n_train": len(tr),
            "n_test": len(te),
            "coef": {n: round(float(v), 4) for n, v in zip(names, b)},
            "test": metrics(yte, yhat),
            "baseline_mean_Kt": metrics(yte, yhat0),
        }

    # full-sample: with months (same spec as year-wise) and without (readable coef)
    xall, yall, names = pack(fit_rows, months_dummy=True)
    ball = ols_fit(xall, yall)
    yhat_all = xall @ ball
    xphys, yphys, nphys = pack(fit_rows, months_dummy=False)
    bphys = ols_fit(xphys, yphys)

    def pack_cols(rs, cols):
        y = np.array([float(r["Kt"]) for r in rs])
        mats = [np.ones(len(rs))]
        labels = ["intercept"]
        for c in cols:
            mats.append(np.array([float(r[c]) for r in rs]))
            labels.append(c)
        return np.column_stack(mats), y, labels

    baselines = {}
    for label, cols in (
        ("mean", []),
        ("s_only", ["s_ssd"]),
        ("Kref_only", ["Kref"]),
        ("s_Kref_sina", ["s_ssd", "Kref", "sin_alpha_noon"]),
        ("s_Kref_airport", ["s_ssd", "Kref", "f_ngo9999", "N_mean", "sin_alpha_noon"]),
    ):
        xb, yb, nb = pack_cols(fit_rows, cols)
        bb = ols_fit(xb, yb)
        baselines[label] = {
            "coef": {n: round(float(v), 4) for n, v in zip(nb, bb)},
            **metrics(yb, xb @ bb),
        }

    # climatology useful heat
    by_m = defaultdict(list)
    for r in rows:
        if r["Qu_mjm2"] == "" or r["date"] not in complete:
            continue
        by_m[r["month"]].append(r)
    ndays = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    clim = []
    for m in range(1, 13):
        rs = by_m[m]
        n = len(rs)
        if not n:
            continue
        qu = sum(r["Qu_mjm2"] for r in rs) / n
        qcs = sum(r["Qcs_mjm2"] for r in rs) / n
        it = sum(r["IT_mjm2"] for r in rs) / n
        clim.append(
            {
                "month": m,
                "n": n,
                "Qu_mean_mjm2": round(qu, 3),
                "Qcs_mean_mjm2": round(qcs, 3),
                "IT_mean_mjm2": round(it, 3),
                "Qu_eq_month_mjm2": round(qu * ndays[m - 1], 2),
                "Qcs_eq_month_mjm2": round(qcs * ndays[m - 1], 2),
                "Qu_over_Qcs": round(qu / qcs, 4) if qcs else "",
            }
        )
    qu_y = sum(r["Qu_eq_month_mjm2"] for r in clim)
    qcs_y = sum(r["Qcs_eq_month_mjm2"] for r in clim)

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "daily_collector.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    with (OUT / "climatology_collector.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(clim[0].keys()))
        w.writeheader()
        w.writerows(clim)

    summary = {
        "collector": {
            "type": "typical glazed flat-plate, not a named product",
            "eta0": ETA0,
            "a1": A1,
            "a2": A2,
            "b0": B0,
            "dT_K": DT_COLL,
            "beta_deg": LAT,
            "orientation": "south",
        },
        "n_complete_days_with_T": len(fit_rows),
        "n_hh_processed": n_slots,
        "regression": {
            "formula": "Kt = b0 + b1 Kref + b2 s + b3 f_NGO9999 + b4 N̄ + b5 sinα + month",
            "Kref": "Hcs_Hottel / H0 (no observed Q)",
            "s": "SSD seconds / (daylight minutes × 60)",
            "f_NGO9999": "fraction of daylight slots with NGO=9999",
            "full_sample_coef_with_month": {n: round(float(v), 4) for n, v in zip(names, ball)},
            "full_sample_coef_no_month": {n: round(float(v), 4) for n, v in zip(nphys, bphys)},
            "full_sample": metrics(yall, yhat_all),
            "full_sample_no_month": metrics(yphys, xphys @ bphys),
            "nested_baselines": baselines,
            "yearwise": tests,
        },
        "iso9806_composite_year": {
            "Qu_mjm2": round(qu_y, 1),
            "Qu_kwhm2": round(qu_y / 3.6, 1),
            "Qcs_mjm2": round(qcs_y, 1),
            "Qcs_kwhm2": round(qcs_y / 3.6, 1),
            "Qu_over_Qcs": round(qu_y / qcs_y, 4) if qcs_y else None,
            "note": (
                "Qu here is Q_from_measured_GHI (ISO 9806 on measured GHI, not measured heat). "
                "Qu/Qcs is the cloud penalty on useful heat at ΔT=40 K. Not an error of SP 131."
            ),
        },
    }
    (OUT / "collector_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
