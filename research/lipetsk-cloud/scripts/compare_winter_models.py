#!/usr/bin/env python3
"""Сравнение зимних моделей Kt по приказу Claude (winter_models_complete).

Одни и те же 972 complete-дня, year-wise, QC не трогаем.
Qadj — тот же ISO 9806 и профиль Gref, что в lipetsk_actualize.py.
XGBoost: train на одном чужом годе, early stopping на втором, тест — третий.
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
from sklearn.linear_model import LinearRegression, LogisticRegression, QuantileRegressor, Ridge
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from lipetsk_actualize import (  # noqa: E402
    DT_S,
    LAT,
    erbs_it,
    iso_q,
    load_href,
    optics,
    sina_noon,
    smear_factors,
)
from plot_otchet_figures import ACCENT, GRID, INK, MUTED, SECOND, SUMMER, WINTER  # noqa: E402
import matplotlib.pyplot as plt

CSV = ROOT / "data" / "lipetsk" / "csv"
FIG = ROOT / "docs" / "figures"
OUT = CSV

WINTER_M = {11, 12, 1, 2, 3}
SUMMER_M = {5, 6, 7, 8, 9}
SHOULDER_M = {4, 10}
SEASONS = {"all": None, "winter": WINTER_M, "summer": SUMMER_M, "shoulder": SHOULDER_M}


def load_daily() -> list[dict]:
    rows = []
    with (CSV / "daily_actualize.csv").open(encoding="utf-8") as f:
        for rec in csv.DictReader(f):
            dt = datetime.strptime(rec["date"], "%Y-%m-%d")
            kt = float(rec["Kt"])
            h = float(rec["H_mjm2"])
            rows.append(
                {
                    "date": rec["date"],
                    "year": int(rec["year"]),
                    "month": int(rec["month"]),
                    "Kt": kt,
                    "Kref": float(rec["Kref_sp_smear"]),
                    "s": float(rec["s_ssd"]),
                    "logH": float(rec["log_Hcloud"]),
                    "sina": max(0.0, sina_noon(dt.timetuple().tm_yday)),
                    "H": h,
                    "H0": h / kt if kt else 0.0,
                    "Href": float(rec["Href_smear_mjm2"]),
                    "Qobs": float(rec["Qu_obs_mjm2"]),
                    "Qref": float(rec["Qu_ref_mjm2"]),
                    "Qadj_log": float(rec["Qu_adj_mjm2"]),
                }
            )
    return rows


def month_dummies(m: int) -> list[float]:
    return [1.0 if m == i else 0.0 for i in range(1, 12)]


def ols(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    xtx = x.T @ x
    try:
        return np.linalg.solve(xtx, x.T @ y)
    except np.linalg.LinAlgError:
        return np.linalg.pinv(xtx) @ x.T @ y


def X_log(rows: list[dict]) -> np.ndarray:
    return np.array(
        [[1.0, math.log(r["Kref"]), r["sina"], r["s"], r["logH"]] + month_dummies(r["month"]) for r in rows]
    )


def X_lin(rows: list[dict], kref: bool = True) -> np.ndarray:
    cols = []
    for r in rows:
        row = [1.0, r["sina"], r["s"], r["logH"]] + month_dummies(r["month"])
        if kref:
            row.insert(1, r["Kref"])
        cols.append(row)
    return np.array(cols)


def clip_kt(a: np.ndarray) -> np.ndarray:
    return np.clip(a, 0.0, 1.1)


def pred_baseline_log(tr: list[dict], te: list[dict]) -> np.ndarray:
    xtr, xte = X_log(tr), X_log(te)
    y = np.log(np.array([r["Kt"] for r in tr]))
    b = ols(xtr, y)
    smear = float(np.mean(np.exp(y - xtr @ b)))
    return clip_kt(np.exp(xte @ b) * smear)


def pred_ols_linear(tr, te):
    y = np.array([r["Kt"] for r in tr])
    return clip_kt(X_lin(te) @ ols(X_lin(tr), y))


def pred_ols_no_kref(tr, te):
    y = np.array([r["Kt"] for r in tr])
    return clip_kt(X_lin(te, kref=False) @ ols(X_lin(tr, kref=False), y))


def pred_s_only(tr, te):
    y = np.array([r["Kt"] for r in tr])
    xtr = np.column_stack([np.ones(len(tr)), [r["s"] for r in tr]])
    xte = np.column_stack([np.ones(len(te)), [r["s"] for r in te]])
    return clip_kt(xte @ ols(xtr, y))


def sk_mat(rows: list[dict]) -> np.ndarray:
    return np.array([[r["Kref"], r["sina"], r["s"], r["logH"], r["month"]] for r in rows])


def pred_quantile(tr, te):
    xtr = np.column_stack([X_lin(tr), [r["Kref"] for r in tr]])  # already has Kref
    # X_lin already includes Kref
    y = np.array([r["Kt"] for r in tr])
    m = QuantileRegressor(quantile=0.5, alpha=0.0, solver="highs")
    m.fit(X_lin(tr), y)
    return clip_kt(m.predict(X_lin(te)))


def pred_ensemble(tr, te):
    feats = ["Kref", "sina", "s", "logH"]
    winter_m = [11, 12, 1, 2, 3]
    wtr = [r for r in tr if r["month"] in winter_m]
    str_ = [r for r in tr if r["month"] in (5, 6, 7, 8, 9)]
    if len(wtr) < 20 or len(str_) < 20:
        return pred_ols_linear(tr, te)
    scw, scs = StandardScaler(), StandardScaler()
    Xw = scw.fit_transform([[r[k] for k in feats] for r in wtr])
    Xs = scs.fit_transform([[r[k] for k in feats] for r in str_])
    mw = Ridge(alpha=1.0).fit(Xw, [r["Kt"] for r in wtr])
    ms = Ridge(alpha=1.0).fit(Xs, [r["Kt"] for r in str_])
    Xt = [[r[k] for k in feats] for r in te]
    kw = clip_kt(mw.predict(scw.transform(Xt)))
    ks = clip_kt(ms.predict(scs.transform(Xt)))
    wmap = {12: 1.0, 1: 1.0, 2: 1.0, 11: 0.7, 3: 0.7, 10: 0.3, 4: 0.3}
    w = np.array([wmap.get(r["month"], 0.0) for r in te])
    return clip_kt(w * kw + (1.0 - w) * ks)


def pred_hurdle(tr, te, gq=0.05):
    yb = np.array([1 if r["Qobs"] > gq else 0 for r in tr])
    Xb = np.column_stack([X_lin(tr, kref=False)[:, [0, 2, 3]], [r["sina"] for r in tr]])  # 1,s,logH,sina + months from lin
    # simpler: s, logH, sina, month dummies
    def Xh(rows):
        return np.array([[1.0, r["s"], r["logH"], r["sina"]] + month_dummies(r["month"]) for r in rows])

    logit = LogisticRegression(max_iter=2000, random_state=42)
    logit.fit(Xh(tr), yb)
    p = logit.predict_proba(Xh(te))[:, 1]
    pos = [r for r in tr if r["Qobs"] > gq]
    if len(pos) < 30:
        return pred_ols_linear(tr, te)
    kt_pos = clip_kt(X_lin(te) @ ols(X_lin(pos), np.array([r["Kt"] for r in pos])))
    return clip_kt(p * kt_pos)


def pred_xgb(tr, te):
    import xgboost as xgb

    feats = lambda rows: np.array([[r["month"], r["Kref"], r["sina"], r["s"], r["logH"]] for r in rows])
    years = sorted({r["year"] for r in tr})
    if len(years) < 2:
        return pred_ols_linear(tr, te)
    inner_tr = [r for r in tr if r["year"] == years[0]]
    inner_va = [r for r in tr if r["year"] == years[1]]
    w = np.array([3.0 if r["month"] in WINTER_M else 1.0 for r in inner_tr])
    dtr = xgb.DMatrix(feats(inner_tr), label=[r["Kt"] for r in inner_tr], weight=w)
    dva = xgb.DMatrix(feats(inner_va), label=[r["Kt"] for r in inner_va])
    dte = xgb.DMatrix(feats(te))
    params = {
        "objective": "reg:squarederror",
        "max_depth": 4,
        "eta": 0.08,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "eval_metric": "rmse",
        "seed": 42,
    }
    model = xgb.train(
        params,
        dtr,
        num_boost_round=400,
        evals=[(dva, "val")],
        early_stopping_rounds=25,
        verbose_eval=False,
    )
    return clip_kt(model.predict(dte))


def pred_oracle(tr, te):
    """Not a forecast. Upper bound of the Gref-shape disaggregation given true daily Kt."""
    return np.array([r["Kt"] for r in te])


MODELS = {
    "baseline_log": pred_baseline_log,
    "ols_linear": pred_ols_linear,
    "ols_no_kref": pred_ols_no_kref,
    "s_only": pred_s_only,
    "quantile_50": pred_quantile,
    "ensemble": pred_ensemble,
    "hurdle": pred_hurdle,
    "xgb_nested": pred_xgb,
    "oracle_obs_Kt": pred_oracle,
}


def metrics_block(obs: np.ndarray, hat: np.ndarray, months: np.ndarray) -> dict:
    out = {}
    for label, mset in SEASONS.items():
        m = np.ones(len(obs), bool) if mset is None else np.isin(months, list(mset))
        if m.sum() < 3:
            continue
        e = hat[m] - obs[m]
        ss_res = float(np.sum(e**2))
        ss_tot = float(np.sum((obs[m] - obs[m].mean()) ** 2))
        out[label] = {
            "n": int(m.sum()),
            "rmse": round(float(np.sqrt(ss_res / m.sum())), 4),
            "mae": round(float(np.mean(np.abs(e))), 4),
            "mbe": round(float(np.mean(e)), 4),
            "r2": round(1.0 - ss_res / ss_tot, 4) if ss_tot else None,
        }
    return out


def precompute_slots(daily: list[dict]) -> list[dict]:
    href = load_href()
    factors = smear_factors(href)
    by_d = {r["date"]: r for r in daily}
    slots = []
    with (CSV / "hh_station.csv").open(encoding="utf-8") as f:
        for rec in csv.DictReader(f):
            if rec["quality_flag"] != "complete" or rec["GHI"] == "":
                continue
            t = datetime.strptime(rec["obs_time_msk"], "%Y-%m-%d %H:%M:%S")
            d = rec["obs_time_msk"][:10]
            if d not in by_d:
                continue
            opt = optics(t)
            if opt["i0"] <= 20:
                continue
            fac = factors[(t.year, t.month)]["smear"]
            ta = float(rec["T_c"]) if rec["T_c"] else None
            slots.append(
                {
                    "d": d,
                    "month": t.month,
                    "opt": opt,
                    "fac": fac,
                    "gref": opt["gcs"] * fac,
                    "ta": ta,
                    "kref_d": by_d[d]["Kref"],
                }
            )
    return slots


def qadj_days(slots: list[dict], kt_hat: dict[str, float]) -> tuple[dict[str, float], dict]:
    q = defaultdict(float)
    n_day = n_zero = n_win = n_win_zero = 0
    for s in slots:
        kthat = kt_hat.get(s["d"])
        if kthat is None or s["kref_d"] <= 0:
            continue
        opt = s["opt"]
        ghi_a = s["gref"] * (kthat / s["kref_d"])
        kt_a = ghi_a / opt["i0"]
        bh, dh, it = erbs_it(ghi_a, kt_a, opt)
        qa = iso_q(bh, dh, ghi_a, it, opt, s["ta"])
        q[s["d"]] += qa * DT_S / 1e6
        n_day += 1
        zero = qa <= 0
        if zero:
            n_zero += 1
        if s["month"] in WINTER_M:
            n_win += 1
            if zero:
                n_win_zero += 1
    stat = {
        "frac_G_le_Gcrit_all": round(n_zero / n_day, 4) if n_day else None,
        "frac_G_le_Gcrit_winter": round(n_win_zero / n_win, 4) if n_win else None,
        "n_hh": n_day,
        "n_hh_winter": n_win,
    }
    return dict(q), stat


def plot_winter_q(daily, hats: dict[str, dict[str, float]], best: str) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    winter = [r for r in daily if r["month"] in WINTER_M]
    dates = [datetime.strptime(r["date"], "%Y-%m-%d") for r in winter]
    obs = [r["Qobs"] for r in winter]
    base = [hats["baseline_log"].get(r["date"], 0.0) for r in winter]
    alt = [hats[best].get(r["date"], 0.0) for r in winter]
    fig, ax = plt.subplots(figsize=(8.2, 3.8))
    ax.scatter(dates, obs, s=14, c=INK, alpha=0.75, label="Qobs", zorder=3)
    ax.scatter(dates, base, s=12, c=SECOND, alpha=0.7, label="Qadj baseline log", zorder=2)
    ax.scatter(dates, alt, s=12, c=ACCENT, alpha=0.75, marker="D", label=f"Qadj {best}", zorder=2)
    ax.set_ylabel("Q, МДж/м²·сут")
    ax.set_title("Зима XI–III: суточная полезная теплота")
    ax.grid(True, color=GRID, lw=0.5)
    ax.legend(frameon=False, fontsize=8)
    fig.autofmt_xdate(rotation=30, ha="right")
    fig.tight_layout()
    fig.savefig(FIG / "winter_q_obs_vs_models.png", dpi=160)
    plt.close(fig)


def plot_bars(rows_by_model: dict) -> None:
    names = list(rows_by_model)
    winter_rmse = [rows_by_model[n]["Kt"]["winter"]["rmse"] for n in names]
    winter_q = [rows_by_model[n]["Q"]["winter"]["rmse"] for n in names]
    fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.6))
    colors = [SECOND if n == "baseline_log" else ACCENT for n in names]
    axes[0].barh(names, winter_rmse, color=colors)
    axes[0].set_xlabel("RMSE Kt, зима")
    axes[0].set_title("Зимний Kt")
    axes[0].grid(True, axis="x", color=GRID, lw=0.5)
    axes[1].barh(names, winter_q, color=colors)
    axes[1].set_xlabel("RMSE Q, МДж/м²·сут, зима")
    axes[1].set_title("Зимняя полезная теплота")
    axes[1].grid(True, axis="x", color=GRID, lw=0.5)
    fig.tight_layout()
    fig.savefig(FIG / "winter_models_rmse.png", dpi=160)
    plt.close(fig)


def main() -> None:
    daily = load_daily()
    print(f"days {len(daily)}", flush=True)
    years = sorted({r["year"] for r in daily})
    oos_hat: dict[str, dict[str, float]] = {name: {} for name in MODELS}
    kt_blocks = defaultdict(lambda: {"obs": [], "hat": [], "month": [], "Hobs": [], "Hhat": [], "Qobs": [], "year": []})

    for ty in years:
        tr = [r for r in daily if r["year"] != ty]
        te = [r for r in daily if r["year"] == ty]
        print(f"  test {ty} n_train={len(tr)} n_test={len(te)}", flush=True)
        for name, fn in MODELS.items():
            hat = fn(tr, te)
            for r, h in zip(te, hat):
                oos_hat[name][r["date"]] = float(h)
                kt_blocks[name]["obs"].append(r["Kt"])
                kt_blocks[name]["hat"].append(float(h))
                kt_blocks[name]["month"].append(r["month"])
                kt_blocks[name]["Hobs"].append(r["H"])
                kt_blocks[name]["Hhat"].append(float(h) * r["H0"])
                kt_blocks[name]["Qobs"].append(r["Qobs"])
                kt_blocks[name]["year"].append(r["year"])

    print("ISO on predicted Kt...", flush=True)
    slots = precompute_slots(daily)
    qmaps = {}
    qstat = {}
    for name in MODELS:
        qmaps[name], qstat[name] = qadj_days(slots, oos_hat[name])
        print(f"  {name} winter G<=Gcrit {qstat[name]['frac_G_le_Gcrit_winter']}", flush=True)

    comparison = []
    packed = {}
    for name in MODELS:
        b = kt_blocks[name]
        obs = np.array(b["obs"])
        hat = np.array(b["hat"])
        months = np.array(b["month"])
        hobs = np.array(b["Hobs"])
        hhat = np.array(b["Hhat"])
        qobs = np.array([next(r["Qobs"] for r in daily if r["date"] == d) for d in oos_hat[name]])
        # align Q with daily order of blocks — blocks appended in year-wise te order
        qhat = np.array(
            [
                qmaps[name].get(r["date"], 0.0)
                for ty in years
                for r in daily
                if r["year"] == ty
            ]
        )
        qobs_ord = np.array(
            [r["Qobs"] for ty in years for r in daily if r["year"] == ty]
        )
        months_ord = np.array(
            [r["month"] for ty in years for r in daily if r["year"] == ty]
        )
        rec = {
            "model": name,
            "Kt": metrics_block(obs, hat, months),
            "H": metrics_block(hobs, hhat, months),
            "Q": metrics_block(qobs_ord, qhat, months_ord),
            "gcrit": qstat[name],
        }
        packed[name] = rec
        flat = {"model": name}
        for kind in ("Kt", "H", "Q"):
            for season, vals in rec[kind].items():
                for k, v in vals.items():
                    if k == "n":
                        continue
                    flat[f"{kind}_{season}_{k}"] = v
        flat["frac_Gcrit_winter"] = rec["gcrit"]["frac_G_le_Gcrit_winter"]
        flat["frac_Gcrit_all"] = rec["gcrit"]["frac_G_le_Gcrit_all"]
        # winter monthly Q sums (mean day * n is in clim later)
        winter_obs = qobs_ord[np.isin(months_ord, list(WINTER_M))].sum()
        winter_hat = qhat[np.isin(months_ord, list(WINTER_M))].sum()
        flat["Q_winter_sum_obs"] = round(float(winter_obs), 2)
        flat["Q_winter_sum_hat"] = round(float(winter_hat), 2)
        flat["Q_winter_hat_over_obs"] = round(float(winter_hat / winter_obs), 4) if winter_obs else None
        comparison.append(flat)

    # pick best by winter Q RMSE, not overall Kt
    scored = [n for n in packed if n != "oracle_obs_Kt"]
    best = min(scored, key=lambda n: packed[n]["Q"]["winter"]["rmse"])
    plot_winter_q(daily, qmaps, best)
    plot_bars(packed)

    # monthly Q table for baseline vs best vs obs
    ndays = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    monthly = []
    for m in range(1, 13):
        rs = [r for r in daily if r["month"] == m]
        n = len(rs)
        if not n:
            continue
        qo = sum(r["Qobs"] for r in rs) / n
        qb = sum(qmaps["baseline_log"].get(r["date"], 0.0) for r in rs) / n
        qbest = sum(qmaps[best].get(r["date"], 0.0) for r in rs) / n
        monthly.append(
            {
                "month": m,
                "n": n,
                "Qobs_eq_mjm2": round(qo * ndays[m - 1], 2),
                "Qadj_baseline_eq_mjm2": round(qb * ndays[m - 1], 2),
                f"Qadj_{best}_eq_mjm2": round(qbest * ndays[m - 1], 2),
                "baseline_over_obs": round(qb / qo, 4) if qo else "",
                "best_over_obs": round(qbest / qo, 4) if qo else "",
            }
        )

    fields = list(comparison[0].keys())
    with (OUT / "winter_models_comparison.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(comparison)
    with (OUT / "winter_models_monthly_q.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(monthly[0].keys()))
        w.writeheader()
        w.writerows(monthly)

    summary = {
        "n_days": len(daily),
        "same_complete_days_as_log_model": True,
        "gcrit_approx_Wm2": 210,
        "xgb_validation": "early stopping on the other non-test year, not on the test year",
        "ensemble_weights": "manual: XII–II=1, XI/III=0.7, X/IV=0.3, V–IX=0",
        "best_by_winter_Q_rmse": best,
        "models": packed,
        "winter_Q_sum_obs_mjm2": comparison[0]["Q_winter_sum_obs"],
        "notes": [
            "hurdle is a Kt model, not a collector model",
            "SSD is the same logger as Q, not an independent Campbell-Stokes",
            "do not transfer to other regions",
        ],
    }
    (OUT / "winter_models_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: packed[k]["Q"]["winter"] for k in MODELS}, indent=2))
    print("best", best)


if __name__ == "__main__":
    main()
