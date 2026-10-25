#!/usr/bin/env python3
"""Рисунки для отчёта: Kt, остатки, суточный ход, полнота, IT/H, Qobs/Qref."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "data" / "lipetsk" / "csv"
OUT = ROOT / "docs" / "figures"

INK = "#1a1a1a"
ACCENT = "#1f4e79"
SECOND = "#b85c38"
MUTED = "#6a6a6a"
GRID = "#e4e4e4"
WINTER = "#3d5a80"
SUMMER = "#c45c26"

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "axes.titlesize": 10.5,
        "axes.titleweight": "bold",
        "axes.labelsize": 9,
        "axes.edgecolor": INK,
        "axes.labelcolor": INK,
        "axes.linewidth": 0.6,
        "xtick.color": INK,
        "ytick.color": INK,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
        "savefig.bbox": "tight",
        "savefig.dpi": 160,
    }
)


def load_csv(name: str) -> list[dict]:
    with (CSV / name).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save(fig: plt.Figure, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    fig.savefig(path, dpi=160)
    plt.close(fig)
    print(path, path.stat().st_size)


def fig_kt_obs_pred(daily: list[dict]) -> None:
    years = [int(r["year"]) for r in daily]
    obs = np.array([float(r["Kt"]) for r in daily])
    hat = np.array([float(r["Kt_hat_oos"]) for r in daily])
    palette = {2023: ACCENT, 2024: SECOND, 2025: "#2a9d8f"}
    fig, ax = plt.subplots(figsize=(5.6, 5.2))
    for y, c in palette.items():
        m = np.array(years) == y
        ax.scatter(hat[m], obs[m], s=12, alpha=0.7, c=c, linewidths=0, label=str(y), zorder=2)
    lim = (0.0, 0.85)
    ax.plot(lim, lim, color=INK, lw=0.8, ls="--", label="1 : 1", zorder=1)
    ax.set_xlim(*lim)
    ax.set_ylim(*lim)
    ax.set_aspect("equal")
    ax.set_xlabel("Kt̂, year-wise oos (log-модель §11.4)")
    ax.set_ylabel("Kt наблюдаемый = H / H0")
    ax.set_title("Суточный Kt: наблюдение vs прогноз")
    ax.grid(True, color=GRID, lw=0.5)
    ax.legend(frameon=False, loc="upper left")
    rmse = float(np.sqrt(np.mean((hat - obs) ** 2)))
    ax.text(0.97, 0.04, f"n = {len(obs)}\nRMSE = {rmse:.3f}", transform=ax.transAxes, ha="right", va="bottom", color=MUTED, fontsize=8)
    save(fig, "kt_obs_pred.png")


def fig_residuals(daily: list[dict]) -> None:
    dates = [datetime.strptime(r["date"], "%Y-%m-%d") for r in daily]
    obs = np.array([float(r["Kt"]) for r in daily])
    hat = np.array([float(r["Kt_hat_oos"]) for r in daily])
    resid = hat - obs
    years = np.array([int(r["year"]) for r in daily])
    palette = {2023: ACCENT, 2024: SECOND, 2025: "#2a9d8f"}
    fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.6))
    ax = axes[0]
    for y, c in palette.items():
        m = years == y
        ax.scatter(hat[m], resid[m], s=11, alpha=0.7, c=c, linewidths=0, label=str(y))
    ax.axhline(0, color=INK, lw=0.7)
    ax.set_xlabel("Kt̂ oos")
    ax.set_ylabel("остаток Kt̂ − Kt")
    ax.set_title("Остатки vs прогноз")
    ax.grid(True, color=GRID, lw=0.5)
    ax.legend(frameon=False, loc="upper right", fontsize=8)
    ax = axes[1]
    darr = np.array(dates)
    for y, c in palette.items():
        m = years == y
        ax.scatter(darr[m], resid[m], s=9, alpha=0.65, c=c, linewidths=0, label=str(y))
    ax.axhline(0, color=INK, lw=0.7)
    ax.set_xlabel("дата")
    ax.set_title("Остатки во времени")
    ax.grid(True, color=GRID, lw=0.5)
    fig.autofmt_xdate(rotation=30, ha="right")
    fig.tight_layout()
    save(fig, "kt_residuals.png")


def fig_diurnal() -> None:
    daily = load_csv("daily_actualize.csv")
    by_month = defaultdict(list)
    for r in daily:
        by_month[int(r["month"])].append(r)
    def nearest(month: int) -> str:
        rows = by_month[month]
        kts = [float(r["Kt"]) for r in rows]
        med = float(np.median(kts))
        return min(rows, key=lambda r: abs(float(r["Kt"]) - med))["date"]

    jan = nearest(1)
    jul = nearest(7)
    want = {jan, jul}
    series = {jan: [], jul: []}
    jja = defaultdict(list)
    djf = defaultdict(list)
    with (CSV / "hh_station.csv").open(encoding="utf-8") as f:
        for rec in csv.DictReader(f):
            if rec["quality_flag"] != "complete" or rec["GHI"] == "":
                continue
            t = datetime.strptime(rec["obs_time_msk"], "%Y-%m-%d %H:%M:%S")
            hour = t.hour + t.minute / 60.0
            q = float(rec["GHI"])
            d = rec["obs_time_msk"][:10]
            m = t.month
            if m in (6, 7, 8):
                jja[hour].append(q)
            if m in (12, 1, 2):
                djf[hour].append(q)
            if d in want:
                series[d].append((hour, q))

    def mean_curve(bucket: dict) -> tuple[np.ndarray, np.ndarray]:
        xs = sorted(bucket)
        ys = [float(np.mean(bucket[x])) for x in xs]
        return np.array(xs), np.array(ys)

    xj, yj = mean_curve(jja)
    xd, yd = mean_curve(djf)
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    ax.plot(xd, yd, color=WINTER, lw=2.0, label="зима DJF, среднее полных дней")
    ax.plot(xj, yj, color=SUMMER, lw=2.0, label="лето JJA, среднее полных дней")
    for d, col, ls, lab in (
        (jan, WINTER, "--", f"типичный январь {jan} (медиана Kt)"),
        (jul, SUMMER, "--", f"типичный июль {jul} (медиана Kt)"),
    ):
        pts = sorted(series[d])
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color=col, lw=0.9, ls=ls, alpha=0.85, label=lab)
    ax.set_xlim(0, 24)
    ax.set_xticks(range(0, 25, 3))
    ax.set_xlabel("час MSK")
    ax.set_ylabel("GHI, Вт/м²")
    ax.set_title("Суточный ход: зима vs лето")
    ax.grid(True, color=GRID, lw=0.5)
    ax.legend(frameon=False, fontsize=7.5, loc="upper right")
    save(fig, "diurnal_winter_summer.png")


def fig_heatmap() -> None:
    meta = json.loads((CSV / "q_only_days_summary.json").read_text(encoding="utf-8"))
    complete = meta["complete_ym"]
    years = [2023, 2024, 2025]
    months = list(range(1, 13))
    ndays = {1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30, 7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}
    frac = np.full((3, 12), np.nan)
    counts = np.full((3, 12), np.nan)
    for i, y in enumerate(years):
        for j, m in enumerate(months):
            key = f"{y}-{m:02d}"
            if key not in complete:
                continue
            n = complete[key]
            cal = ndays[m]
            if y == 2024 and m == 2:
                cal = 29
            if y == 2023 and m == 2:
                cal = 1  # ряд начинается 28.02
            frac[i, j] = n / cal
            counts[i, j] = n
    cmap = LinearSegmentedColormap.from_list("navy", ["#f7f4ea", "#c45c26", ACCENT])
    fig, ax = plt.subplots(figsize=(8.0, 2.8))
    im = ax.imshow(frac, vmin=0, vmax=1, cmap=cmap, aspect="auto")
    ax.set_xticks(range(12))
    ax.set_xticklabels(["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"])
    ax.set_yticks(range(3))
    ax.set_yticklabels(["2023", "2024", "2025"])
    for i in range(3):
        for j in range(12):
            if np.isnan(frac[i, j]):
                ax.text(j, i, "—", ha="center", va="center", color=MUTED, fontsize=8)
            else:
                ax.text(j, i, f"{int(counts[i, j])}", ha="center", va="center", color="white" if frac[i, j] > 0.55 else INK, fontsize=8)
    ax.set_title("Полные световые сутки (число в ячейке; цвет — доля месяца)")
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.02)
    cbar.set_label("доля полных дней")
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    save(fig, "completeness_heatmap.png")


def fig_it_over_h() -> None:
    rows = load_csv("climatology_gti.csv")
    months = [int(r["month"]) for r in rows]
    ratio = [float(r["IT_over_H"]) for r in rows]
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    ax.bar(months, ratio, color=ACCENT, width=0.72, zorder=2)
    ax.axhline(1.0, color=SECOND, lw=1.0, ls="--", label="IT = H", zorder=3)
    ax.set_xticks(range(1, 13))
    ax.set_xticklabels(["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"])
    ax.set_ylabel("IT / H")
    ax.set_ylim(0, 2.1)
    ax.set_title("Наклон юг β=φ к горизонтали, по месяцам")
    ax.grid(True, axis="y", color=GRID, lw=0.5, zorder=0)
    ax.legend(frameon=False)
    save(fig, "it_over_h.png")


def fig_qobs_qref() -> None:
    rows = load_csv("climatology_qref_qadj.csv")
    months = [int(r["month"]) for r in rows]
    ratio = [float(r["obs_over_ref"]) for r in rows]
    year_r = sum(float(r["Qu_obs_eq_mjm2"]) for r in rows) / sum(float(r["Qu_ref_eq_mjm2"]) for r in rows)
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    ax.bar(months, ratio, color=ACCENT, width=0.72, zorder=2)
    ax.axhline(year_r, color=SECOND, lw=1.0, ls="--", label=f"год (суммы) {year_r:.2f}", zorder=3)
    ax.set_xticks(range(1, 13))
    ax.set_xticklabels(["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"])
    ax.set_ylabel("Qobs / Qref")
    ax.set_ylim(0, 0.65)
    ax.set_title("Полезная теплота: измеренный ряд vs размазанный СП")
    ax.grid(True, axis="y", color=GRID, lw=0.5, zorder=0)
    ax.legend(frameon=False)
    save(fig, "qobs_over_qref.png")


def main() -> None:
    daily = load_csv("daily_actualize.csv")
    fig_kt_obs_pred(daily)
    fig_residuals(daily)
    fig_diurnal()
    fig_heatmap()
    fig_it_over_h()
    fig_qobs_qref()


if __name__ == "__main__":
    main()
