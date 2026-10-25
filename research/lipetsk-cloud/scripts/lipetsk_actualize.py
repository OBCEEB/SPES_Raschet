#!/usr/bin/env python3
"""Этапы 2, 4, 7 как в §11.4 — без sqlite.

2: размазка Href,cs(m) весами Hottel Gcs внутри календарного месяца.
4: log(Kt,d) и log(kt,h) year-wise; 9999 → 3000 м (нет низкой кромки).
7: Qref по размазанному СП; Qadj по oos-прогнозу суточного Kt, профиль Gref.
Часовой AR(1) — диагностика, в Qadj не идёт (это был бы nowcast по Q).
Split на актуализированном ряде — часовой Эрбс; Reindl-2 на наблюдаемом IT — сверка.
"""

from __future__ import annotations

import calendar
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
from lipetsk_collector import (  # noqa: E402
    DT_COLL,
    END,
    START,
    STEP,
    keff_iam,
    load_complete,
    load_hh_q,
    load_ngo,
    load_t_ssd,
    qdot,
)
from lipetsk_gti import (  # noqa: E402
    DT_S,
    LAT,
    decl_e0,
    erbs_hourly,
    hottel_tau,
    i0_wm2,
    liu_jordan,
    rb_south_lat,
    reindl2_hourly,
)

HREF = ROOT / "data" / "lipetsk" / "csv" / "sp131_href_cs.csv"
OUT = ROOT / "data" / "lipetsk" / "csv"
H0_FLOOR = 10.0  # m, log(Hcloud + h0)
H_CLEAR = 3000.0  # NGO=9999 → нет измеренной кромки; подстановка, не измерение
H_CLEAR_SENSITIVITY = (1000.0, 2000.0, 3000.0, 5000.0, 10000.0)
KT_LO = 0.03


def load_href() -> dict[int, float]:
    out = {}
    with HREF.open(encoding="utf-8") as f:
        for rec in csv.DictReader(f):
            out[int(rec["month"])] = float(rec["href_cs_52135_mjm2"])
    return out


def month_slots(year: int, month: int) -> list[datetime]:
    nd = calendar.monthrange(year, month)[1]
    t = datetime(year, month, 1, 0, 0)
    end = datetime(year, month, nd, 23, 30)
    out = []
    while t <= end:
        out.append(t)
        t += STEP
    return out


def heff(ngo: float | None, h_clear: float = H_CLEAR) -> float | None:
    if ngo is None:
        return None
    if ngo >= 9000:
        return h_clear
    return max(ngo, 0.0)


def optics(t: datetime) -> dict:
    i0, cosz, w = i0_wm2(t)
    n = t.timetuple().tm_yday
    decl, _ = decl_e0(n)
    tb, td = hottel_tau(cosz, t.month)
    gcs = i0 * (tb + td) if i0 > 0 else 0.0
    rb = rb_south_lat(decl, w, cosz)
    cost = math.cos(decl) * math.cos(w)
    return {
        "i0": i0,
        "cosz": cosz,
        "cost": cost,
        "tb": tb,
        "td": td,
        "gcs": gcs,
        "rb": rb,
        "decl": decl,
        "w": w,
    }


def split_it(ghi: float, kt: float, opt: dict, fn) -> tuple[float, float, float]:
    kd = fn(min(max(kt, 0.0), 1.2), opt["cosz"])
    dh = kd * ghi
    bh = max(ghi - dh, 0.0)
    it = liu_jordan(bh, dh, ghi, opt["rb"])
    return bh, dh, it


def erbs_it(ghi: float, kt: float, opt: dict) -> tuple[float, float, float]:
    kd = erbs_hourly(min(max(kt, 0.0), 1.2))
    dh = kd * ghi
    bh = max(ghi - dh, 0.0)
    return bh, dh, liu_jordan(bh, dh, ghi, opt["rb"])


def iso_q(bh: float, dh: float, ghi: float, it: float, opt: dict, ta: float | None) -> float:
    if ta is None or it <= 0:
        return 0.0
    k = keff_iam(bh, dh, ghi, opt["rb"], it, opt["cost"])
    return qdot(it, k)


def ols(x: np.ndarray, y: np.ndarray) -> np.ndarray:
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
        "rmse": round(float(np.sqrt(ss_res / max(len(y), 1))), 4),
        "mae": round(float(np.mean(np.abs(e))), 4),
        "mbe": round(float(np.mean(e)), 4),
        "r2": round(1.0 - ss_res / ss_tot, 4) if ss_tot else None,
    }


def month_dummies(month: int) -> list[float]:
    return [1.0 if month == m else 0.0 for m in range(1, 12)]


def sina_noon(doy: int) -> float:
    decl = math.radians(23.45) * math.sin(math.radians(360.0 * (284 + doy) / 365.0))
    phi = math.radians(LAT)
    return math.sin(phi) * math.sin(decl) + math.cos(phi) * math.cos(decl)


def smear_factors(href: dict[int, float]) -> dict[tuple[int, int], dict]:
    """Full calendar month geometry → scale Hottel so Σ Gref Δt = Href,cs(m)."""
    out = {}
    years = sorted({START.year, END.year})
    for y in range(years[0], years[-1] + 1):
        for m in range(1, 13):
            if datetime(y, m, 1) > END:
                continue
            if calendar.monthrange(y, m)[1] and datetime(y, m, calendar.monthrange(y, m)[1]) < START.replace(
                hour=0, minute=0
            ):
                continue
            e = 0.0
            n_sun = 0
            for t in month_slots(y, m):
                gcs = optics(t)["gcs"]
                e += gcs * DT_S / 1e6
                if gcs > 0:
                    n_sun += 1
            href_m = href[m]
            fac = href_m / e if e > 0 else 0.0
            out[(y, m)] = {
                "year": y,
                "month": m,
                "E_hottel_mjm2": round(e, 3),
                "href_cs_mjm2": round(href_m, 3),
                "smear": round(fac, 4),
                "n_sun_slots": n_sun,
            }
    return out


def design_daily(rows: list[dict], use_s: bool = True, h_key: str = "logH") -> tuple[np.ndarray, list[str]]:
    names = ["intercept", "log_Kref", "sin_alpha"] + (["s_ssd"] if use_s else []) + ["log_Hcloud"]
    names += [f"m{m:02d}" for m in range(1, 12)]
    x = []
    for r in rows:
        row = [1.0, math.log(r["Kref"]), r["sina"]] + ([r["s"]] if use_s else []) + [r[h_key]]
        x.append(row + month_dummies(r["month"]))
    return np.array(x), names


def design_hour(rows: list[dict], ar: bool) -> tuple[np.ndarray, list[str]]:
    names = ["intercept", "log_kref", "s_h", "log_Hcloud", "cosz"] + [f"m{m:02d}" for m in range(1, 12)]
    if ar:
        names.append("log_kt_lag")
    x = []
    for r in rows:
        row = [1.0, r["log_kref"], r["sh"], r["logH"], r["cosz"]] + month_dummies(r["month"])
        if ar:
            row.append(r["log_kt_lag"])
        x.append(row)
    return np.array(x), names


def fit_predict_daily(
    train: list[dict], test: list[dict], use_s: bool = True, h_key: str = "logH"
) -> tuple[np.ndarray, np.ndarray, dict, float]:
    xtr, names = design_daily(train, use_s, h_key)
    ytr = np.log(np.array([r["Kt"] for r in train]))
    b = ols(xtr, ytr)
    resid = ytr - xtr @ b
    smear = float(np.mean(np.exp(resid)))
    xte, _ = design_daily(test, use_s, h_key)
    yhat_log = xte @ b
    kt_hat = np.clip(np.exp(yhat_log) * smear, 0.0, 1.1)
    kt_obs = np.array([r["Kt"] for r in test])
    coef = {n: round(float(v), 4) for n, v in zip(names, b)}
    coef["smear_exp_resid"] = round(smear, 4)
    return kt_obs, kt_hat, coef, smear


def main() -> None:
    print("loading station (Q, T, SSD, NGO)...", flush=True)
    complete = load_complete()
    qq = load_hh_q()
    ts = load_t_ssd()
    ngo = load_ngo()
    href = load_href()
    print("smear Href,cs onto Hottel month...", flush=True)
    factors = smear_factors(href)

    # unified half-hours on the station grid
    hh_rows = []
    t = START
    slots = []
    while t <= END:
        opt = optics(t)
        ym = (t.year, t.month)
        fac = factors[ym]["smear"]
        gref = opt["gcs"] * fac
        q = qq.get(t)
        met = ts.get(t, {})
        ng = ngo.get(t, {})
        hraw = ng.get("h")
        n_ok = ng.get("n")
        d = t.strftime("%Y-%m-%d")
        if d in complete and q is not None:
            flag = "complete"
        elif q is not None:
            flag = "incomplete_day"
        else:
            flag = "no_q"
        utc = t - timedelta(hours=3)
        ssd = met.get("ssd")
        sun_min = (ssd / 60.0) if ssd is not None else None
        hh_rows.append(
            {
                "timestamp_utc": utc.strftime("%Y-%m-%d %H:%M:%S"),
                "obs_time_msk": t.strftime("%Y-%m-%d %H:%M:%S"),
                "GHI": "" if q is None else round(q, 2),
                "sunshine_minutes": "" if sun_min is None else round(sun_min, 3),
                "cloud_base_m": "" if hraw is None else (int(hraw) if hraw == int(hraw) else hraw),
                "T_c": "" if met.get("t") is None else round(met["t"], 2),
                "n_oktas": "" if n_ok is None else n_ok,
                "quality_flag": flag,
            }
        )
        slots.append(
            {
                "t": t,
                "d": d,
                "year": t.year,
                "month": t.month,
                "q": q,
                "ta": met.get("t"),
                "ssd": ssd or 0.0,
                "ssd_ok": ssd is not None,
                "n_min": met.get("n_min") or 0,
                "hraw": hraw,
                "he": heff(hraw),
                "n_ok": n_ok,
                "opt": opt,
                "gref": gref,
                "fac": fac,
                "flag": flag,
            }
        )
        t += STEP

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "hh_station.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "timestamp_utc",
                "obs_time_msk",
                "GHI",
                "sunshine_minutes",
                "cloud_base_m",
                "T_c",
                "n_oktas",
                "quality_flag",
            ],
        )
        w.writeheader()
        w.writerows(hh_rows)
    with (OUT / "smear_href_monthly.csv").open("w", encoding="utf-8", newline="") as f:
        recs = [factors[k] for k in sorted(factors)]
        w = csv.DictWriter(f, fieldnames=list(recs[0].keys()))
        w.writeheader()
        w.writerows(recs)

    # daily features on complete days
    day = defaultdict(
        lambda: {
            "H": 0.0,
            "H0": 0.0,
            "Href": 0.0,
            "ssd": 0.0,
            "nmin": 0,
            "logH": 0.0,
            "nH": 0,
            "n9999": 0,
            "n_ngo": 0,
            "hraws": [],
        }
    )
    for s in slots:
        if s["flag"] != "complete" or s["opt"]["i0"] <= 20:
            continue
        b = day[s["d"]]
        dt_e = DT_S / 1e6
        if s["q"] is not None:
            b["H"] += s["q"] * dt_e
        b["H0"] += s["opt"]["i0"] * dt_e
        b["Href"] += s["gref"] * dt_e
        if s["ssd_ok"]:
            b["ssd"] += s["ssd"]
            b["nmin"] += 30
        if s["he"] is not None:
            b["logH"] += math.log(s["he"] + H0_FLOOR)
            b["nH"] += 1
            b["n_ngo"] += 1
            b["hraws"].append(s["hraw"])
            if s["hraw"] is not None and s["hraw"] >= 9000:
                b["n9999"] += 1

    daily = []
    for d, b in sorted(day.items()):
        if b["H0"] <= 0 or b["Href"] <= 0 or b["nH"] == 0 or b["nmin"] == 0:
            continue
        kt = b["H"] / b["H0"]
        kref = b["Href"] / b["H0"]
        if kt < KT_LO or kref <= 0:
            continue
        dt = datetime.strptime(d, "%Y-%m-%d")
        sbar = b["ssd"] / (b["nmin"] * 60.0)
        log_h_alt = {
            f"logH_{int(hc)}": sum(math.log(heff(h, hc) + H0_FLOOR) for h in b["hraws"]) / len(b["hraws"])
            for hc in H_CLEAR_SENSITIVITY
        }
        daily.append(
            {
                "date": d,
                "year": dt.year,
                "month": dt.month,
                "Kt": kt,
                "Kref": kref,
                "s": min(max(sbar, 0.0), 1.0),
                "logH": b["logH"] / b["nH"],
                **log_h_alt,
                "sina": max(0.0, sina_noon(dt.timetuple().tm_yday)),
                "H": b["H"],
                "H0": b["H0"],
                "Href": b["Href"],
                "f9999": b["n9999"] / b["n_ngo"] if b["n_ngo"] else 0.0,
            }
        )

    yearwise_d = {}
    kt_hat_oos = {}
    for ty in (2025, 2024, 2023):
        tr = [r for r in daily if r["year"] != ty]
        te = [r for r in daily if r["year"] == ty]
        if len(tr) < 50 or len(te) < 30:
            continue
        obs, hat, coef, smear = fit_predict_daily(tr, te)
        yearwise_d[str(ty)] = {
            "n_train": len(tr),
            "n_test": len(te),
            "coef": coef,
            "Kt": metrics(obs, hat),
            "baseline_mean": metrics(obs, np.full_like(obs, np.mean([r["Kt"] for r in tr]))),
        }
        for r, h in zip(te, hat):
            kt_hat_oos[r["date"]] = float(h)

    def yearwise_variant(use_s: bool, h_key: str) -> dict:
        out = {}
        for ty in (2025, 2024, 2023):
            tr = [r for r in daily if r["year"] != ty]
            te = [r for r in daily if r["year"] == ty]
            if len(tr) < 50 or len(te) < 30:
                continue
            obs, hat, _, _ = fit_predict_daily(tr, te, use_s, h_key)
            winter = np.array([r["month"] in (11, 12, 1, 2, 3) for r in te])
            out[str(ty)] = {"Kt": metrics(obs, hat), "Kt_winter": metrics(obs[winter], hat[winter])}
        return out

    variants_d = {"with_ssd": {}, "no_ssd": {}}
    for hc in H_CLEAR_SENSITIVITY:
        key = f"logH_{int(hc)}"
        variants_d["with_ssd"][f"h9999_{int(hc)}m"] = yearwise_variant(True, key)
        variants_d["no_ssd"][f"h9999_{int(hc)}m"] = yearwise_variant(False, key)

    xall, names_d = design_daily(daily)
    yall = np.log(np.array([r["Kt"] for r in daily]))
    ball = ols(xall, yall)
    smear_all = float(np.mean(np.exp(yall - xall @ ball)))
    kt_hat_all = np.clip(np.exp(xall @ ball) * smear_all, 0.0, 1.1)
    kt_obs_all = np.array([r["Kt"] for r in daily])

    # hourly log(kt), daylight complete slots
    hour_rows = []
    prev = None
    for s in slots:
        if s["flag"] != "complete" or s["opt"]["i0"] <= 20 or s["q"] is None:
            prev = None
            continue
        kt = s["q"] / s["opt"]["i0"]
        kref = s["gref"] / s["opt"]["i0"] if s["opt"]["i0"] > 0 else None
        if kref is None or kref <= 1e-6 or kt <= 0.01 or s["he"] is None:
            prev = {"d": s["d"], "logkt": math.log(max(kt, 0.01))}
            continue
        sh = min(max(s["ssd"] / 1800.0, 0.0), 1.0)
        rec = {
            "year": s["year"],
            "month": s["month"],
            "d": s["d"],
            "kt": min(kt, 1.2),
            "log_kref": math.log(kref),
            "sh": sh,
            "logH": math.log(s["he"] + H0_FLOOR),
            "cosz": s["opt"]["cosz"],
            "log_kt_lag": None,
        }
        if prev and prev["d"] == s["d"]:
            rec["log_kt_lag"] = prev["logkt"]
        hour_rows.append(rec)
        prev = {"d": s["d"], "logkt": math.log(max(kt, 0.01))}

    hour_ar = [r for r in hour_rows if r["log_kt_lag"] is not None]
    yearwise_h = {}
    yearwise_h_ar = {}
    for ty in (2025, 2024, 2023):
        tr = [r for r in hour_rows if r["year"] != ty]
        te = [r for r in hour_rows if r["year"] == ty]
        if len(tr) < 200 or len(te) < 100:
            continue
        xtr, nh = design_hour(tr, ar=False)
        ytr = np.log(np.array([r["kt"] for r in tr]))
        bh = ols(xtr, ytr)
        sm = float(np.mean(np.exp(ytr - xtr @ bh)))
        xte, _ = design_hour(te, ar=False)
        hat = np.clip(np.exp(xte @ bh) * sm, 0.0, 1.2)
        obs = np.array([r["kt"] for r in te])
        yearwise_h[str(ty)] = {
            "n_train": len(tr),
            "n_test": len(te),
            "coef": {**{n: round(float(v), 4) for n, v in zip(nh, bh)}, "smear_exp_resid": round(sm, 4)},
            "kt": metrics(obs, hat),
            "note": "meteo only, no AR(1); for actualization",
        }
        tr_a = [r for r in hour_ar if r["year"] != ty]
        te_a = [r for r in hour_ar if r["year"] == ty]
        xtr, na = design_hour(tr_a, ar=True)
        ytr = np.log(np.array([r["kt"] for r in tr_a]))
        ba = ols(xtr, ytr)
        sma = float(np.mean(np.exp(ytr - xtr @ ba)))
        xte, _ = design_hour(te_a, ar=True)
        hat_a = np.clip(np.exp(xte @ ba) * sma, 0.0, 1.2)
        obs_a = np.array([r["kt"] for r in te_a])
        yearwise_h_ar[str(ty)] = {
            "n_test": len(te_a),
            "coef_rho_log_kt_lag": round(float(ba[-1]), 4),
            "kt_one_step_obs_lag": metrics(obs_a, hat_a),
            "note": "AR(1) with observed lag = nowcast, not Qadj",
        }

    # Qref / Qadj / Qobs on complete days. Qadj: oos daily Kt, shape of Gref.
    qacc = defaultdict(lambda: {"obs": 0.0, "ref": 0.0, "adj": 0.0, "it_obs": 0.0, "it_ref": 0.0, "it_adj": 0.0, "it_r2": 0.0})
    n_q_slots = 0
    n_missing_hat = 0
    for s in slots:
        if s["flag"] != "complete" or s["opt"]["i0"] <= 20:
            continue
        drec = day[s["d"]]
        if drec["Href"] <= 0 or drec["H0"] <= 0:
            continue
        kref_d = drec["Href"] / drec["H0"]
        kt_hat = kt_hat_oos.get(s["d"])
        opt = s["opt"]
        ta = s["ta"]
        fac = s["fac"]
        # Qobs
        if s["q"] is not None:
            kt_o = s["q"] / opt["i0"]
            bh, dh, it = erbs_it(s["q"], kt_o, opt)
            qo = iso_q(bh, dh, s["q"], it, opt, ta)
            _, _, it_r2 = split_it(s["q"], kt_o, opt, lambda k, c: reindl2_hourly(k, c))
        else:
            qo, it, it_r2 = 0.0, 0.0, 0.0
        # Qref: smeared clear-sky beam+diffuse
        bh_r = opt["i0"] * opt["tb"] * fac
        dh_r = opt["i0"] * opt["td"] * fac
        ghi_r = s["gref"]
        it_r = liu_jordan(bh_r, dh_r, ghi_r, opt["rb"])
        qr = iso_q(bh_r, dh_r, ghi_r, it_r, opt, ta)
        # Qadj: G = Gref * (Kt_hat / Kref) — only oos days in the log model
        if kt_hat is None:
            n_missing_hat += 1
            qa, it_a = 0.0, 0.0
        else:
            ghi_a = ghi_r * (kt_hat / kref_d) if kref_d > 0 else 0.0
            kt_a = ghi_a / opt["i0"] if opt["i0"] > 0 else 0.0
            bh_a, dh_a, it_a = erbs_it(ghi_a, kt_a, opt)
            qa = iso_q(bh_a, dh_a, ghi_a, it_a, opt, ta)
        b = qacc[s["d"]]
        de = DT_S / 1e6
        b["obs"] += qo * de
        b["ref"] += qr * de
        b["adj"] += qa * de
        b["it_obs"] += it * de
        b["it_ref"] += it_r * de
        b["it_adj"] += it_a * de
        b["it_r2"] += it_r2 * de
        n_q_slots += 1

    daily_out = []
    for r in daily:
        q = qacc.get(r["date"], {})
        daily_out.append(
            {
                "date": r["date"],
                "year": r["year"],
                "month": r["month"],
                "Kt": round(r["Kt"], 4),
                "Kref_sp_smear": round(r["Kref"], 4),
                "Kt_hat_oos": round(kt_hat_oos[r["date"]], 4) if r["date"] in kt_hat_oos else "",
                "s_ssd": round(r["s"], 4),
                "log_Hcloud": round(r["logH"], 4),
                "H_mjm2": round(r["H"], 4),
                "Href_smear_mjm2": round(r["Href"], 4),
                "Qu_obs_mjm2": round(q.get("obs", 0.0), 4),
                "Q_from_measured_GHI_mjm2": round(q.get("obs", 0.0), 4),
                "Qu_ref_mjm2": round(q.get("ref", 0.0), 4),
                "Qu_adj_mjm2": round(q.get("adj", 0.0), 4),
                "IT_obs_mjm2": round(q.get("it_obs", 0.0), 4),
                "IT_ref_mjm2": round(q.get("it_ref", 0.0), 4),
                "IT_adj_mjm2": round(q.get("it_adj", 0.0), 4),
            }
        )

    ndays = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    by_m = defaultdict(list)
    for r in daily_out:
        by_m[r["month"]].append(r)
    clim = []
    for m in range(1, 13):
        rs = by_m[m]
        n = len(rs)
        if not n:
            continue

        def mean(key):
            return sum(r[key] for r in rs) / n

        qo, qr, qa = mean("Qu_obs_mjm2"), mean("Qu_ref_mjm2"), mean("Qu_adj_mjm2")
        clim.append(
            {
                "month": m,
                "n": n,
                "Qu_obs_mean": round(qo, 3),
                "Qu_ref_mean": round(qr, 3),
                "Qu_adj_mean": round(qa, 3),
                "Qu_obs_eq_mjm2": round(qo * ndays[m - 1], 2),
                "Qu_ref_eq_mjm2": round(qr * ndays[m - 1], 2),
                "Qu_adj_eq_mjm2": round(qa * ndays[m - 1], 2),
                "adj_over_ref": round(qa / qr, 4) if qr else "",
                "obs_over_ref": round(qo / qr, 4) if qr else "",
                "adj_over_obs": round(qa / qo, 4) if qo else "",
            }
        )

    def year_sum(key):
        return sum(r[key] for r in clim)

    # observed IT Erbs vs Reindl-2 on same complete slots
    it_e = sum(qacc[r["date"]]["it_obs"] for r in daily if r["date"] in qacc)
    it_r = sum(qacc[r["date"]]["it_r2"] for r in daily if r["date"] in qacc)

    with (OUT / "daily_actualize.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(daily_out[0].keys()))
        w.writeheader()
        w.writerows(daily_out)
    with (OUT / "climatology_qref_qadj.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(clim[0].keys()))
        w.writeheader()
        w.writerows(clim)

    smear_by_m = defaultdict(list)
    for rec in factors.values():
        smear_by_m[rec["month"]].append(rec["smear"])

    summary = {
        "sqlite": "not used",
        "n_hh_station": len(hh_rows),
        "n_complete_days_in_log_model": len(daily),
        "n_hh_iso": n_q_slots,
        "smear": {
            "rule": "Gref,h = Gcs,Hottel,h * Href,cs(m) / Σ_month Gcs,Hottel Δt",
            "mean_smear_by_month": {str(m): round(float(np.mean(v)), 4) for m, v in sorted(smear_by_m.items())},
        },
        "daily_log_Kt": {
            "formula": "log(Kt) = αm + β1 log(Kref_sp) + β2 sinαn + β3 s + β4 log(Hcloud+10)",
            "Hcloud": "NGO=9999 → 3000 m; else metres",
            "Kref": "daily sum of smeared SP Gref / H0",
            "full_sample_coef": {
                **{n: round(float(v), 4) for n, v in zip(names_d, ball)},
                "smear_exp_resid": round(smear_all, 4),
            },
            "full_sample_Kt": metrics(kt_obs_all, kt_hat_all),
            "yearwise": yearwise_d,
            "yearwise_variants": {
                "note": (
                    "Robustness check, not model selection: NGO=9999 substitute height "
                    "and with/without the logger SSD feature; same days and folds."
                ),
                **variants_d,
            },
        },
        "hourly_log_kt": {
            "formula": "log(kt) = αm + βref log(kref) + βs sh + βh log(H+10) + βz cosz",
            "yearwise_meteo": yearwise_h,
            "yearwise_AR1_obs_lag": yearwise_h_ar,
        },
        "iso9806": {
            "collector": "typical glazed flat-plate, same as lipetsk_collector.py",
            "dT_K": DT_COLL,
            "Qref": "ISO on smeared SP clear-sky GTI (Hottel beam/diffuse × smear)",
            "Qadj": "ISO on Gadj,h = Gref,h * Kt_hat_oos / Kref_d (Erbs + Liu-Jordan)",
            "Qobs": "Q_from_measured_GHI: ISO on measured GHI (Erbs + Liu-Jordan); not measured heat",
            "year_eq_mjm2": {
                "Qu_obs": round(year_sum("Qu_obs_eq_mjm2"), 1),
                "Qu_ref": round(year_sum("Qu_ref_eq_mjm2"), 1),
                "Qu_adj": round(year_sum("Qu_adj_eq_mjm2"), 1),
            },
            "year_kwhm2": {
                "Qu_obs": round(year_sum("Qu_obs_eq_mjm2") / 3.6, 1),
                "Qu_ref": round(year_sum("Qu_ref_eq_mjm2") / 3.6, 1),
                "Qu_adj": round(year_sum("Qu_adj_eq_mjm2") / 3.6, 1),
            },
            "Qu_obs_over_ref": round(year_sum("Qu_obs_eq_mjm2") / year_sum("Qu_ref_eq_mjm2"), 4),
            "Qu_adj_over_ref": round(year_sum("Qu_adj_eq_mjm2") / year_sum("Qu_ref_eq_mjm2"), 4),
            "Qu_adj_over_obs": round(year_sum("Qu_adj_eq_mjm2") / year_sum("Qu_obs_eq_mjm2"), 4),
        },
        "reindl2_vs_erbs_IT_complete_days_mjm2": {
            "IT_erbs_sum_of_daily": round(it_e, 1),
            "IT_reindl2_sum_of_daily": round(it_r, 1),
            "reindl2_over_erbs": round(it_r / it_e, 4) if it_e else None,
            "note": "same observed GHI; Q chain stays on Erbs",
        },
        "n_complete_slots_without_oos_Kt_hat": n_missing_hat,
    }
    (OUT / "actualize_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
