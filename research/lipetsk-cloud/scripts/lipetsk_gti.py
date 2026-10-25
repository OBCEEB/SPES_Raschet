#!/usr/bin/env python3
"""Получасовки Конь-Колодезя → kt, kcs (Hottel), Эрбс, GTI юг β=φ.

Только слоты с сырым Q (hh_q_only). Суточный МГУ-Рейндл сюда не кормим.
δ — Cooper, как в msu_kd. Hottel 1976, midlatitude, A=0.15 км.
Наклон: юг, β = широта, ρg = 0.2. Часы 8–17 — как дублёр ВСН 52-86.
"""

from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HH = ROOT / "data" / "lipetsk" / "csv" / "hh_q_only.csv"
DAILY = ROOT / "data" / "lipetsk" / "csv" / "daily_obs_q_only.csv"
HREF = ROOT / "data" / "lipetsk" / "csv" / "sp131_href_cs.csv"
OUT = ROOT / "data" / "lipetsk" / "csv"

LAT = 52.135409
LON = 39.163510
MSK_H = 3.0
GSC = 1367.0
ALT_KM = 0.15
BETA = math.radians(LAT)  # юг, наклон = широта
RHO = 0.2
DT_S = 1800.0
MIN_COSZ = 0.05


def decl_e0(doy: int) -> tuple[float, float]:
    decl = math.radians(23.45) * math.sin(math.radians(360.0 * (284 + doy) / 365.0))
    e0 = 1.0 + 0.033 * math.cos(math.radians(360.0 * doy / 365.0))
    return decl, e0


def omega_rad(dt: datetime, lon_deg: float) -> float:
    """Часовой угол в середине слота, рад. Стенка MSK=UTC+3."""
    n = dt.timetuple().tm_yday
    decl, _ = decl_e0(n)
    # середина 30-мин слота
    hour_loc = dt.hour + dt.minute / 60.0 + 0.25
    hour_utc = hour_loc - MSK_H
    gamma = 2.0 * math.pi / 365.0 * (n - 1.0 + (hour_utc - 12.0) / 24.0)
    eqtime = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2.0 * gamma)
        - 0.040849 * math.sin(2.0 * gamma)
    )
    tst = hour_loc * 60.0 + eqtime + 4.0 * lon_deg - 60.0 * MSK_H
    return math.radians(tst / 4.0 - 180.0)


def i0_wm2(dt: datetime) -> tuple[float, float, float]:
    """Средний I0 Вт/м² за 30 мин, cosθz и ω середины."""
    n = dt.timetuple().tm_yday
    decl, e0 = decl_e0(n)
    phi = math.radians(LAT)
    # границы слота
    w1 = omega_rad(dt, LON)
    # ω растёт ~15°/ч → 7.5° за 30 мин
    dw = math.radians(7.5)
    w0, w2 = w1 - dw / 2.0, w1 + dw / 2.0
    geo = math.cos(phi) * math.cos(decl) * (math.sin(w2) - math.sin(w0)) + (w2 - w0) * math.sin(
        phi
    ) * math.sin(decl)
    i0_j = (12.0 * 3600.0 / math.pi) * GSC * e0 * geo
    i0 = i0_j / DT_S
    if i0 < 0:
        i0 = 0.0
    cosz = math.sin(phi) * math.sin(decl) + math.cos(phi) * math.cos(decl) * math.cos(w1)
    return i0, max(-1.0, min(1.0, cosz)), w1


def hottel_tau(cosz: float, month: int) -> tuple[float, float]:
    a = ALT_KM
    a0s = 0.4237 - 0.00821 * (6.0 - a) ** 2
    a1s = 0.5055 + 0.00595 * (6.5 - a) ** 2
    ks = 0.2711 + 0.01858 * (2.5 - a) ** 2
    if 4 <= month <= 9:
        r0, r1, rk = 0.97, 0.99, 1.02
    else:
        r0, r1, rk = 1.03, 1.01, 1.00
    a0, a1, k = r0 * a0s, r1 * a1s, rk * ks
    if cosz <= MIN_COSZ:
        return 0.0, 0.0
    tb = a0 + a1 * math.exp(-k / cosz)
    tb = min(max(tb, 0.0), 1.0)
    td = 0.2710 - 0.2939 * tb
    td = min(max(td, 0.0), 1.0)
    return tb, td


def erbs_hourly(kt: float) -> float:
    if kt <= 0.22:
        kd = 1.0 - 0.09 * kt
    elif kt <= 0.80:
        kd = (
            0.9511
            - 0.1604 * kt
            + 4.388 * kt**2
            - 16.638 * kt**3
            + 12.336 * kt**4
        )
    else:
        kd = 0.165
    return min(max(kd, 0.0), 1.0)


def reindl2_hourly(kt: float, sin_a: float) -> float:
    """Reindl-2 hour, §7.3. sin_a = cos θz = sin α."""
    if kt <= 0.3:
        kd = 1.020 - 0.254 * kt + 0.0123 * sin_a
    elif kt < 0.78:
        kd = 1.400 - 1.749 * kt + 0.177 * sin_a
    else:
        kd = 0.486 * kt - 0.182 * sin_a
    return min(max(kd, 0.0), 1.0)


def rb_south_lat(decl: float, omega: float, cosz: float) -> float:
    """Юг, β=φ → cosθ = cosδ cosω."""
    if cosz <= MIN_COSZ:
        return 0.0
    cost = math.cos(decl) * math.cos(omega)
    if cost <= 0:
        return 0.0
    return cost / cosz


def liu_jordan(bh: float, dh: float, ghi: float, rb: float) -> float:
    cb = math.cos(BETA)
    return bh * rb + dh * (1.0 + cb) / 2.0 + ghi * RHO * (1.0 - cb) / 2.0


def main() -> None:
    complete = set()
    with DAILY.open(encoding="utf-8") as f:
        for rec in csv.DictReader(f):
            if rec["complete_daylight"] == "1":
                complete.add(rec["date"])
    href = {}
    with HREF.open(encoding="utf-8") as f:
        for rec in csv.DictReader(f):
            href[int(rec["month"])] = float(rec["href_cs_52135_mjm2"])

    day = defaultdict(
        lambda: {
            "H": 0.0,
            "Hd": 0.0,
            "Bh": 0.0,
            "IT": 0.0,
            "IT817": 0.0,
            "I0": 0.0,
            "Gcs": 0.0,
            "n": 0,
            "n_kt": 0,
            "sum_kt": 0.0,
            "sum_kcs": 0.0,
            "n_kcs": 0,
        }
    )
    with HH.open(encoding="utf-8") as f:
        for rec in csv.DictReader(f):
            t = datetime.strptime(rec["obs_time"], "%Y-%m-%d %H:%M:%S")
            q = float(rec["q_wm2"])
            i0, cosz, w = i0_wm2(t)
            n = t.timetuple().tm_yday
            decl, _ = decl_e0(n)
            tb, td = hottel_tau(cosz, t.month)
            gcs = i0 * (tb + td) if i0 > 0 else 0.0
            kt = q / i0 if i0 > 20 else None
            kcs = q / gcs if gcs > 20 else None
            if kt is None:
                kd = None
                bh = dh = 0.0
            else:
                kd = erbs_hourly(min(max(kt, 0.0), 1.2))
                dh = kd * q
                bh = max(q - dh, 0.0)
            rb = rb_south_lat(decl, w, cosz)
            it = liu_jordan(bh, dh, q, rb) if kt is not None else 0.0
            d = t.strftime("%Y-%m-%d")
            b = day[d]
            mj = q * DT_S / 1e6
            b["H"] += mj
            b["Hd"] += dh * DT_S / 1e6
            b["Bh"] += bh * DT_S / 1e6
            b["IT"] += it * DT_S / 1e6
            if 8 <= t.hour < 17:
                b["IT817"] += it * DT_S / 1e6
            b["I0"] += i0 * DT_S / 1e6
            b["Gcs"] += gcs * DT_S / 1e6
            b["n"] += 1
            if kt is not None and 0 <= kt <= 1.2:
                b["sum_kt"] += kt
                b["n_kt"] += 1
            if kcs is not None and 0 <= kcs <= 1.5:
                b["sum_kcs"] += kcs
                b["n_kcs"] += 1
    daily_rows = []
    for d in sorted(day):
        if d not in complete:
            continue
        b = day[d]
        y, m = int(d[:4]), int(d[5:7])
        daily_rows.append(
            {
                "date": d,
                "year": y,
                "month": m,
                "H_mjm2": round(b["H"], 4),
                "Hd_erbs_mjm2": round(b["Hd"], 4),
                "Bh_erbs_mjm2": round(b["Bh"], 4),
                "IT_south_lat_mjm2": round(b["IT"], 4),
                "IT_8_17_mjm2": round(b["IT817"], 4),
                "I0_mjm2": round(b["I0"], 4),
                "Gcs_hottel_mjm2": round(b["Gcs"], 4),
                "Kt": round(b["sum_kt"] / b["n_kt"], 4) if b["n_kt"] else "",
                "kcs_mean": round(b["sum_kcs"] / b["n_kcs"], 4) if b["n_kcs"] else "",
                "IT_over_H": round(b["IT"] / b["H"], 4) if b["H"] else "",
            }
        )

    ym_d = defaultdict(list)
    for r in daily_rows:
        ym_d[(r["year"], r["month"])].append(r)

    monthly = []
    for y, m in sorted(ym_d):
        rows = ym_d[(y, m)]
        n = len(rows)
        n_cal = sum(1 for k in day if k.startswith(f"{y}-{m:02d}"))
        full = n == n_cal and n_cal >= 28
        s = lambda key: sum(r[key] for r in rows)
        h, it = s("H_mjm2"), s("IT_south_lat_mjm2")
        monthly.append(
            {
                "year": y,
                "month": m,
                "n_complete": n,
                "complete_month": int(full),
                "H_mjm2": round(h, 3),
                "Hd_erbs_mjm2": round(s("Hd_erbs_mjm2"), 3),
                "Bh_erbs_mjm2": round(s("Bh_erbs_mjm2"), 3),
                "IT_south_lat_mjm2": round(it, 3),
                "IT_8_17_mjm2": round(s("IT_8_17_mjm2"), 3),
                "Gcs_hottel_mjm2": round(s("Gcs_hottel_mjm2"), 3),
                "href_cs_mjm2": round(href[m], 3),
                "C_vs_sp": round(h / href[m], 4) if full else "",
                "IT_over_H": round(it / h, 4) if h else "",
                "IT_over_href": round(it / href[m], 4) if full else "",
            }
        )

    by_m = defaultdict(list)
    for r in daily_rows:
        by_m[r["month"]].append(r)
    clim = []
    ndays = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    for m in range(1, 13):
        rows = by_m[m]
        n = len(rows)
        h_mean = sum(r["H_mjm2"] for r in rows) / n
        it_mean = sum(r["IT_south_lat_mjm2"] for r in rows) / n
        it817_mean = sum(r["IT_8_17_mjm2"] for r in rows) / n
        hd_mean = sum(r["Hd_erbs_mjm2"] for r in rows) / n
        gcs_mean = sum(r["Gcs_hottel_mjm2"] for r in rows) / n
        h_eq = h_mean * ndays[m - 1]
        it_eq = it_mean * ndays[m - 1]
        clim.append(
            {
                "month": m,
                "n_complete_days": n,
                "H_mean_mjm2": round(h_mean, 3),
                "IT_mean_mjm2": round(it_mean, 3),
                "IT_8_17_mean_mjm2": round(it817_mean, 3),
                "H_eq_month_mjm2": round(h_eq, 3),
                "IT_eq_month_mjm2": round(it_eq, 3),
                "Hd_erbs_mean_mjm2": round(hd_mean, 3),
                "Gcs_hottel_mean_mjm2": round(gcs_mean, 3),
                "href_cs_mjm2": round(href[m], 3),
                "C_vs_sp": round(h_eq / href[m], 4),
                "IT_over_H": round(it_mean / h_mean, 4),
                "IT_over_href": round(it_eq / href[m], 4),
            }
        )

    h_year = sum(r["H_eq_month_mjm2"] for r in clim)
    it_year = sum(r["IT_eq_month_mjm2"] for r in clim)
    href_year = sum(href[m] for m in range(1, 13))
    it817_year = sum(r["IT_8_17_mean_mjm2"] * ndays[r["month"] - 1] for r in clim)
    gcs_year = sum(r["Gcs_hottel_mean_mjm2"] * ndays[r["month"] - 1] for r in clim)

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "daily_gti.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(daily_rows[0].keys()))
        w.writeheader()
        w.writerows(daily_rows)
    with (OUT / "monthly_gti.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(monthly[0].keys()))
        w.writeheader()
        w.writerows(monthly)
    with (OUT / "climatology_gti.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(clim[0].keys()))
        w.writeheader()
        w.writerows(clim)

    summary = {
        "beta_deg": LAT,
        "azimuth": "south",
        "rho_g": RHO,
        "split": "Erbs hourly on 30-min kt",
        "clear_sky": "Hottel 1976 midlatitude A=0.15 km",
        "n_complete_days": len(daily_rows),
        "H_year_eq_mjm2": round(h_year, 1),
        "H_year_kwhm2": round(h_year / 3.6, 1),
        "IT_year_eq_mjm2": round(it_year, 1),
        "IT_year_kwhm2": round(it_year / 3.6, 1),
        "IT817_year_eq_mjm2": round(it817_year, 1),
        "href_year_mjm2": round(href_year, 1),
        "Gcs_hottel_year_mjm2": round(gcs_year, 1),
        "kcs_year_H_over_Hottel": round(h_year / gcs_year, 4),
        "C_year": round(h_year / href_year, 4),
        "IT_over_H_year": round(it_year / h_year, 4),
        "IT_over_href_year": round(it_year / href_year, 4),
        "note": (
            "Composite of complete daylight days, not one calendar year. "
            "IT is isotropic Liu-Jordan south at latitude tilt. "
            "Hours 8-17 MSK as VSN 52-86 south dummy collector."
        ),
    }
    (OUT / "gti_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("month H IT IT/H C IT/Href")
    for r in clim:
        print(
            f"  {r['month']:2d} H={r['H_eq_month_mjm2']:7.1f} "
            f"IT={r['IT_eq_month_mjm2']:7.1f} "
            f"IT/H={r['IT_over_H']:.3f} C={r['C_vs_sp']:.3f} "
            f"IT/Href={r['IT_over_href']:.3f}"
        )


if __name__ == "__main__":
    main()
