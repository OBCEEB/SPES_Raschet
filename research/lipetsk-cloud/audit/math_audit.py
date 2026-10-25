#!/usr/bin/env python3
"""Математический аудит расчётной цепочки перед написанием статей A и B.

Не меняет код пайплайна: импортирует его функции и проверяет допущения на
сохранённых рядах (hh_station.csv, daily_actualize.csv, smear_href_monthly.csv,
sp131_href_cs.csv, winter_models_summary.json). Сырые минутки и sqlite не нужны.

Результат: audit/math_audit_numbers.json (все числа для reports/math_audit_before_writing.md).
"""

from __future__ import annotations

import csv
import json
import math
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import lipetsk_collector as col  # noqa: E402
import lipetsk_gti as gti  # noqa: E402
from lipetsk_actualize import (  # noqa: E402
    H0_FLOOR,
    H_CLEAR,
    erbs_it,
    iso_q,
    load_href,
    optics,
    sina_noon,
    smear_factors,
)
from lipetsk_tables import SP131, lerp_lat  # noqa: E402
from msu_kd import h0_mj  # noqa: E402

CSV = ROOT / "data" / "lipetsk" / "csv"
OUT = Path(__file__).resolve().parent / "math_audit_numbers.json"
WINTER_M = {11, 12, 1, 2, 3}
SEASONS = {"winter": WINTER_M, "summer": {5, 6, 7, 8, 9}, "shoulder": {4, 10}}
AIRPORT = (52.697862, 39.524295)
DE = gti.DT_S / 1e6


def read_csv(name: str) -> list[dict]:
    with (CSV / name).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def season_of(m: int) -> str:
    for k, v in SEASONS.items():
        if m in v:
            return k
    return "other"


# ---------------------------------------------------------------- A. таблица СП
def audit_sp_table() -> dict:
    rows = read_csv("sp131_href_cs.csv")
    stored = [float(r["href_cs_52135_mjm2"]) for r in sorted(rows, key=lambda r: int(r["month"]))]
    recomputed = lerp_lat(gti.LAT, SP131)
    diff = max(abs(a - b) for a, b in zip(stored, recomputed))
    return {
        "grid_latitudes_deg": sorted(SP131),
        "interpolation": "linear in latitude between 48 and 56 deg; table has no longitude",
        "units": "MJ/m2 per month, clear sky, horizontal (as coded)",
        "max_abs_diff_stored_vs_recomputed_mjm2": round(diff, 4),
        "annual_sum_mjm2": round(sum(stored), 1),
        "annual_sum_kwhm2": round(sum(stored) / 3.6, 1),
        "edition_in_code_comment": "СП 131.13330.2025 табл. 13.1 — проверить редакцию",
    }


# ------------------------------------------------- B. внеатмосферная радиация
def slot_i0_clipped(t: datetime) -> float:
    """То же, что gti.i0_wm2, но интегрирование только при положительной высоте Солнца."""
    n = t.timetuple().tm_yday
    decl, e0 = gti.decl_e0(n)
    phi = math.radians(gti.LAT)
    w1 = gti.omega_rad(t, gti.LON)
    dw = math.radians(7.5)
    w0, w2 = w1 - dw / 2.0, w1 + dw / 2.0
    ws = math.acos(min(1.0, max(-1.0, -math.tan(phi) * math.tan(decl))))
    a, b = max(w0, -ws), min(w2, ws)
    if b <= a:
        return 0.0
    geo = math.cos(phi) * math.cos(decl) * (math.sin(b) - math.sin(a)) + (b - a) * math.sin(phi) * math.sin(decl)
    return max((12.0 * 3600.0 / math.pi) * gti.GSC * e0 * geo / gti.DT_S, 0.0)


def audit_h0() -> dict:
    half_width = math.radians(7.5) / 2.0
    rows = []
    for doy in range(1, 366):
        day = datetime(2023, 1, 1) + __import__("datetime").timedelta(days=doy - 1)
        s_code = s_clip = s_code_gt20 = s_clip_gt20 = 0.0
        for k in range(48):
            t = day.replace(hour=k // 2, minute=30 * (k % 2))
            i_code = gti.i0_wm2(t)[0]
            i_clip = slot_i0_clipped(t)
            s_code += i_code * DE
            s_clip += i_clip * DE
            if i_code > 20:
                s_code_gt20 += i_code * DE
                s_clip_gt20 += i_clip * DE
        rows.append((day.month, h0_mj(doy, gti.LAT), s_code, s_clip, s_code_gt20, s_clip_gt20))
    by_m = defaultdict(list)
    for r in rows:
        by_m[r[0]].append(r)
    monthly = {}
    for m, rs in sorted(by_m.items()):
        an = sum(r[1] for r in rs)
        monthly[str(m)] = {
            "code_over_analytic": round(sum(r[2] for r in rs) / an, 5),
            "clipped_over_analytic": round(sum(r[3] for r in rs) / an, 5),
            "code_over_clipped_slots_I0_gt20": round(sum(r[4] for r in rs) / sum(r[5] for r in rs), 5),
        }
    worst = min(monthly.items(), key=lambda kv: kv[1]["code_over_clipped_slots_I0_gt20"])
    return {
        "half_width_rad": round(half_width, 6),
        "pi_over_48": round(math.pi / 48.0, 6),
        "half_width_ok": abs(half_width - math.pi / 48.0) < 1e-12,
        "sunrise_sunset_clipping_in_code": False,
        "monthly": monthly,
        "worst_month_for_Kt_denominator": {"month": worst[0], **worst[1]},
    }


# --------------------------------------------------------- C. ребалансировка
def audit_smear() -> dict:
    href = load_href()
    factors = smear_factors(href)
    stored = {(int(r["year"]), int(r["month"])): r for r in read_csv("smear_href_monthly.csv")}
    max_err = 0.0
    for key, f in factors.items():
        # Σ Gref Δt за месяц = smear × E_hottel
        err = abs(f["smear"] * f["E_hottel_mjm2"] - f["href_cs_mjm2"])
        max_err = max(max_err, err)
    same = all(abs(factors[k]["smear"] - float(stored[k]["smear"])) < 1e-4 for k in stored)
    return {
        "n_months": len(factors),
        "max_abs_month_sum_error_mjm2": round(max_err, 4),
        "note": "smear rounded to 4 digits in output; error is rounding of the stored factor",
        "recomputed_equals_stored": same,
        "range_smear": [min(f["smear"] for f in factors.values()), max(f["smear"] for f in factors.values())],
    }


# -------------------------------------------- D/E. пересчёт суток и теплоты
def load_slots() -> tuple[list[dict], dict[str, dict]]:
    daily = {r["date"]: r for r in read_csv("daily_actualize.csv")}
    href = load_href()
    factors = smear_factors(href)
    slots = []
    for rec in read_csv("hh_station.csv"):
        if rec["quality_flag"] != "complete" or rec["GHI"] == "":
            continue
        d = rec["obs_time_msk"][:10]
        if d not in daily:
            continue
        t = datetime.strptime(rec["obs_time_msk"], "%Y-%m-%d %H:%M:%S")
        opt = optics(t)
        if opt["i0"] <= 20:
            continue
        slots.append({
            "t": t, "d": d, "month": t.month, "year": t.year, "opt": opt,
            "q": float(rec["GHI"]),
            "ta": float(rec["T_c"]) if rec["T_c"] != "" else None,
            "ssd_min": float(rec["sunshine_minutes"]) if rec["sunshine_minutes"] != "" else None,
            "cb": rec["cloud_base_m"],
            "gref": opt["gcs"] * factors[(t.year, t.month)]["smear"],
        })
    return slots, daily


def q_slot(ghi: float, opt: dict, ta) -> float:
    kt = ghi / opt["i0"]
    bh, dh, it = erbs_it(ghi, kt, opt)
    return iso_q(bh, dh, ghi, it, opt, ta)


def slot_k_eff(ghi: float, opt: dict) -> tuple[float, float]:
    kt = ghi / opt["i0"]
    bh, dh, it = erbs_it(ghi, kt, opt)
    if it <= 5:
        return it, col.IAM_DIFFUSE
    return it, col.keff_iam(bh, dh, ghi, opt["rb"], it, opt["cost"])


def audit_daily_energy_and_q(slots, daily) -> dict:
    H = defaultdict(float)
    H0 = defaultdict(float)
    Href = defaultdict(float)
    for s in slots:
        H[s["d"]] += s["q"] * DE
        H0[s["d"]] += s["opt"]["i0"] * DE
        Href[s["d"]] += s["gref"] * DE
    dh = [abs(H[d] - float(r["H_mjm2"])) for d, r in daily.items()]
    dkt = [abs(H[d] / H0[d] - float(r["Kt"])) for d, r in daily.items()]
    # oracle: Gadj = Gref * Kt_obs / Kref_d на тех же слотах
    oracle_err = []
    for d, r in daily.items():
        kt, kref = H[d] / H0[d], Href[d] / H0[d]
        e = sum(s["gref"] * kt / kref * DE for s in slots if s["d"] == d) if False else Href[d] * kt / kref
        oracle_err.append(abs(e - H[d]))

    # Q по измеренному GHI: воспроизведение и вклад пропусков Ta
    q_code = defaultdict(float)
    q_no_gate = defaultdict(float)
    n_slot = defaultdict(int)
    n_missing = defaultdict(int)
    n_missing_positive = defaultdict(int)
    for s in slots:
        qc = q_slot(s["q"], s["opt"], s["ta"])
        qn = q_slot(s["q"], s["opt"], 0.0)  # ΔT фиксирована; Ta в формулу не входит
        q_code[s["d"]] += qc * DE
        q_no_gate[s["d"]] += qn * DE
        se = season_of(s["month"])
        n_slot[se] += 1
        if s["ta"] is None:
            n_missing[se] += 1
            if qn > 0:
                n_missing_positive[se] += 1
    dq = [abs(q_code[d] - float(r["Qu_obs_mjm2"])) for d, r in daily.items()]
    by_season = {}
    for se in SEASONS:
        days = [d for d, r in daily.items() if season_of(int(r["month"])) == se]
        qc = sum(q_code[d] for d in days)
        qn = sum(q_no_gate[d] for d in days)
        by_season[se] = {
            "n_daylight_slots": n_slot[se],
            "slots_without_Ta": n_missing[se],
            "share_slots_without_Ta": round(n_missing[se] / n_slot[se], 4) if n_slot[se] else None,
            "slots_without_Ta_but_positive_Q_if_not_gated": n_missing_positive[se],
            "Q_code_sum_mjm2": round(qc, 2),
            "Q_without_Ta_gate_sum_mjm2": round(qn, 2),
            "Q_lost_to_Ta_gate_share": round(1 - qc / qn, 4) if qn else None,
        }
    return {
        "n_days": len(daily),
        "n_slots": len(slots),
        "max_abs_H_diff_vs_daily_actualize_mjm2": round(max(dh), 4),
        "max_abs_Kt_diff": round(max(dkt), 5),
        "oracle_daily_energy_max_abs_err_mjm2": round(max(oracle_err), 6),
        "Q_obs_reproduction_max_abs_diff_mjm2": round(max(dq), 4),
        "Ta_gate_by_season": by_season,
    }


# ---------------------------------------- F. доля «ниже Gcrit» и её состав
def fit_log_yearwise(rows: list[dict], key_logH: str = "logH") -> dict[str, float]:
    def X(rs):
        return np.array([[1.0, math.log(r["Kref"]), r["sina"], r["s"], r[key_logH]]
                         + [1.0 if r["month"] == m else 0.0 for m in range(1, 12)] for r in rs])
    hat = {}
    for ty in sorted({r["year"] for r in rows}):
        tr = [r for r in rows if r["year"] != ty]
        te = [r for r in rows if r["year"] == ty]
        xtr = X(tr)
        y = np.log(np.array([r["Kt"] for r in tr]))
        b = np.linalg.lstsq(xtr, y, rcond=None)[0]
        sm = float(np.mean(np.exp(y - xtr @ b)))
        for r, h in zip(te, np.clip(np.exp(X(te) @ b) * sm, 0.0, 1.1)):
            hat[r["date"]] = float(h)
    return hat


def daily_rows(daily: dict) -> list[dict]:
    out = []
    for d, r in daily.items():
        dt = datetime.strptime(d, "%Y-%m-%d")
        out.append({
            "date": d, "year": int(r["year"]), "month": int(r["month"]),
            "Kt": float(r["Kt"]), "Kref": float(r["Kref_sp_smear"]), "s": float(r["s_ssd"]),
            "logH": float(r["log_Hcloud"]), "sina": max(0.0, sina_noon(dt.timetuple().tm_yday)),
        })
    return out


def kt_metrics(rows, hat, months=None) -> dict:
    sel = [r for r in rows if r["date"] in hat and (months is None or r["month"] in months)]
    e = np.array([hat[r["date"]] - r["Kt"] for r in sel])
    return {"n": len(sel), "rmse": round(float(np.sqrt(np.mean(e ** 2))), 4), "mbe": round(float(np.mean(e)), 4)}


def zero_decomposition(slots, daily, kt_hat: dict[str, float]) -> dict:
    href_d, h0_d = defaultdict(float), defaultdict(float)
    for s in slots:
        href_d[s["d"]] += s["gref"] * DE
        h0_d[s["d"]] += s["opt"]["i0"] * DE
    acc = defaultdict(lambda: {"n": 0, "zero_code": 0, "zero_physical": 0, "zero_only_Ta": 0})
    for s in slots:
        kh = kt_hat.get(s["d"])
        if kh is None:
            continue
        kref = href_d[s["d"]] / h0_d[s["d"]]
        ghi = s["gref"] * kh / kref
        q_gated = q_slot(ghi, s["opt"], s["ta"])
        q_phys = q_slot(ghi, s["opt"], 0.0)
        se = "winter" if s["month"] in WINTER_M else "other"
        a = acc[se]
        a["n"] += 1
        a["zero_code"] += q_gated <= 0
        a["zero_physical"] += q_phys <= 0
        a["zero_only_Ta"] += (q_gated <= 0) and (q_phys > 0)
    return {se: {"n_slots": a["n"],
                 "share_Q_zero_as_in_code": round(a["zero_code"] / a["n"], 4),
                 "share_below_Gcrit_physical": round(a["zero_physical"] / a["n"], 4),
                 "share_zero_only_because_Ta_missing": round(a["zero_only_Ta"] / a["n"], 4)}
            for se, a in acc.items()}


def gcrit_distribution(slots) -> dict:
    base = (col.A1 * col.DT_COLL + col.A2 * col.DT_COLL ** 2) / col.ETA0
    out = {"Gcrit_K1_Wm2": round(base, 1)}
    for se, months in (("winter", WINTER_M), ("summer", SEASONS["summer"])):
        vals = []
        for s in slots:
            if s["month"] not in months:
                continue
            it, k = slot_k_eff(s["q"], s["opt"])
            if k > 0:
                vals.append(base / k)
        a = np.array(vals)
        out[se] = {"n": len(a), "p10": round(float(np.percentile(a, 10)), 1),
                   "median": round(float(np.median(a)), 1), "p90": round(float(np.percentile(a, 90)), 1)}
    return out


# ------------------------------------------------ G. НГО=9999 чувствительность
def ngo_sensitivity(slots, rows) -> dict:
    per_day = defaultdict(list)
    for s in slots:
        cb = s["cb"]
        if cb == "":
            continue
        per_day[s["d"]].append(float(cb))
    res = {}
    for h_clear in (1000.0, 2000.0, 3000.0, 5000.0, 10000.0):
        rr = []
        for r in rows:
            vals = per_day.get(r["date"], [])
            if not vals:
                continue
            he = [h_clear if v >= 9000 else max(v, 0.0) for v in vals]
            rr.append({**r, "logH_alt": float(np.mean([math.log(h + H0_FLOOR) for h in he]))})
        if h_clear == H_CLEAR:
            res["reproduces_stored_logH_max_abs_diff"] = round(max(abs(r["logH_alt"] - r["logH"]) for r in rr), 5)
        hat = fit_log_yearwise(rr, "logH_alt")
        res[f"h_clear_{int(h_clear)}"] = {"all": kt_metrics(rr, hat), "winter": kt_metrics(rr, hat, WINTER_M)}
    return res


# --------------------------------------------- H. время и I. SSD, J. расстояние
def timing_check(slots) -> dict:
    by_d = defaultdict(list)
    for s in slots:
        by_d[s["d"]].append(s)
    shifts, ratios = [], []
    for d, ss in by_d.items():
        g = np.array([s["q"] for s in ss])
        gcs = np.array([s["opt"]["gcs"] for s in ss])
        if gcs.sum() <= 0:
            continue
        ratios.append(g.sum() / gcs.sum())
        if g.sum() / gcs.sum() < 0.55:
            continue  # пасмурные дни: центр масс GHI определяется облаками, а не временем
        w = np.array([s["opt"]["w"] for s in ss])
        shifts.append(float(np.sum(g * w) / np.sum(g) - np.sum(gcs * w) / np.sum(gcs)))
    if ratios:
        print("  daily H/Hcs percentiles 50/90/99:", np.percentile(ratios, [50, 90, 99]).round(3))
    a = np.degrees(np.array(shifts)) * 4.0  # 1° часового угла = 4 минуты
    if len(a) == 0:
        return {"n_clear_days": 0, "note": "no days passed the clear-day filter"}
    return {"n_clear_days": len(a), "median_shift_min": round(float(np.median(a)), 1),
            "p25_p75_min": [round(float(np.percentile(a, 25)), 1), round(float(np.percentile(a, 75)), 1)],
            "note": "GHI-weighted vs clear-sky-weighted hour angle; 0 = timestamps are slot starts as coded"}


def ssd_diagnostics(slots) -> dict:
    x, y = [], []
    n_sun_dim = n_dark_bright = n = 0
    for s in slots:
        if s["ssd_min"] is None or s["opt"]["gcs"] < 50:
            continue
        kcs = s["q"] / s["opt"]["gcs"]
        n += 1
        x.append(s["ssd_min"] / 30.0)
        y.append(kcs)
        n_sun_dim += s["ssd_min"] >= 25 and kcs < 0.3
        n_dark_bright += s["ssd_min"] == 0 and kcs > 0.9
    return {"n_slots": n, "corr_sunshine_fraction_vs_kcs": round(float(np.corrcoef(x, y)[0, 1]), 3),
            "share_sunshine_ge25min_but_kcs_lt0.3": round(n_sun_dim / n, 4),
            "share_sunshine_0_but_kcs_gt0.9": round(n_dark_bright / n, 4),
            "conclusion": "statistics cannot establish whether SSD is a separate sensor or derived from Q"}


def haversine_km(a, b) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def main() -> None:
    out = {"generated": datetime.now().isoformat(timespec="seconds")}
    print("A. SP table"); out["A_sp_table"] = audit_sp_table()
    print("B. H0"); out["B_h0"] = audit_h0()
    print("C. smear"); out["C_smear"] = audit_smear()
    print("loading slots"); slots, daily = load_slots()
    print("D/E. daily energy, Q"); out["DE_daily_and_Q"] = audit_daily_energy_and_q(slots, daily)
    rows = daily_rows(daily)
    print("F. baseline reproduction and zero decomposition")
    hat_base = fit_log_yearwise(rows)
    stored = json.loads((CSV / "winter_models_summary.json").read_text(encoding="utf-8"))
    out["F_baseline_log"] = {
        "recomputed": {"all": kt_metrics(rows, hat_base), "winter": kt_metrics(rows, hat_base, WINTER_M)},
        "stored_winter_Kt": stored["models"]["baseline_log"]["Kt"]["winter"],
        "stored_gcrit": stored["models"]["baseline_log"]["gcrit"],
    }
    oracle = {r["date"]: r["Kt"] for r in rows}
    out["F_zero_decomposition"] = {"baseline_log": zero_decomposition(slots, daily, hat_base),
                                   "oracle_obs_Kt": zero_decomposition(slots, daily, oracle),
                                   "stored_oracle_gcrit": stored["models"]["oracle_obs_Kt"]["gcrit"]}
    out["F_gcrit_slot_specific"] = gcrit_distribution(slots)
    # S1: измеренный GHI; S2: тот же суточный Kt, гладкий профиль; S4: прогноз log-модели
    s1 = defaultdict(lambda: {"n": 0, "zero": 0, "q": 0.0})
    for s in slots:
        se = "winter" if s["month"] in WINTER_M else "other"
        q = q_slot(s["q"], s["opt"], s["ta"])
        s1[se]["n"] += 1
        s1[se]["zero"] += q <= 0
        s1[se]["q"] += q * DE
    out["F_S1_measured_GHI"] = {se: {"n_slots": a["n"], "share_Q_zero": round(a["zero"] / a["n"], 4),
                                     "Q_sum_mjm2": round(a["q"], 2)} for se, a in s1.items()}
    for label, hat in (("S2_oracle_smooth", oracle), ("S4_baseline_log_smooth", hat_base)):
        href_d, h0_d = defaultdict(float), defaultdict(float)
        for s in slots:
            href_d[s["d"]] += s["gref"] * DE
            h0_d[s["d"]] += s["opt"]["i0"] * DE
        acc = defaultdict(float)
        for s in slots:
            ghi = s["gref"] * hat[s["d"]] / (href_d[s["d"]] / h0_d[s["d"]])
            acc["winter" if s["month"] in WINTER_M else "other"] += q_slot(ghi, s["opt"], s["ta"]) * DE
        out[f"F_{label}_Q_sum_mjm2"] = {k: round(v, 2) for k, v in acc.items()}
    print("G. NGO sensitivity"); out["G_ngo_9999_sensitivity"] = ngo_sensitivity(slots, rows)
    print("H. timing"); out["H_timing"] = timing_check(slots)
    print("I. SSD"); out["I_ssd"] = ssd_diagnostics(slots)
    out["J_distance_pyranometer_airport_km"] = round(haversine_km((gti.LAT, gti.LON), AIRPORT), 1)
    out["K_split"] = {"years": sorted({r["year"] for r in rows}),
                      "scheme": "leave-one-year-out; test year never in train",
                      "days_per_year": {str(y): sum(1 for r in rows if r["year"] == y) for y in sorted({r["year"] for r in rows})}}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    print("->", OUT)


if __name__ == "__main__":
    main()
