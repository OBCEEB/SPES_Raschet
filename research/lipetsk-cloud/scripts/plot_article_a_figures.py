#!/usr/bin/env python3
"""Figures of article A for black-and-white print.

Series differ by line style, marker and hatching only (black on white, no grey
ramps). Notation follows the manuscript: H_сп, H_н, K_я, K̂_я.
Writes docs/figures/a_fig1_scheme.png … a_fig7_residuals.png.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "data" / "lipetsk" / "csv"
FIG = ROOT / "docs" / "figures"
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]
SP_48 = [196, 308, 545, 712, 874, 911, 898, 753, 575, 409, 220, 158]
SP_56 = [112, 215, 445, 648, 855, 903, 879, 707, 489, 295, 138, 79]
K = "black"
YEAR_MARK = {2023: dict(marker="o", facecolors="none", edgecolors=K),
             2024: dict(marker="+", c=K),
             2025: dict(marker="^", facecolors="none", edgecolors=K)}

plt.rcParams.update({
    "font.family": "Times New Roman",
    "mathtext.fontset": "custom",
    "mathtext.rm": "Times New Roman",
    "mathtext.it": "Times New Roman:italic",
    "mathtext.bf": "Times New Roman:bold",
    "font.size": 10,
    "axes.edgecolor": K,
    "axes.linewidth": 0.8,
    "axes.grid": False,
    "xtick.direction": "in",
    "ytick.direction": "in",
    "legend.frameon": False,
    "savefig.dpi": 300,
})


def rows(name: str) -> list[dict]:
    with (CSV / name).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save(fig, name: str) -> None:
    fig.tight_layout()
    fig.savefig(FIG / name, facecolor="white")
    plt.close(fig)


def months_axis(ax) -> None:
    ax.set_xticks(range(12))
    ax.set_xticklabels(ROMAN)
    ax.set_xlim(-0.5, 11.5)
    ax.set_xlabel("Месяц")


def fig1_scheme() -> None:
    steps = [
        "Таблица СП:\n$H_{\\mathrm{сп}}(\\varphi_i,\\ м)$",
        "Интерполяция\nпо широте, (1)",
        "Профиль Хоттела,\nприведённый к $H_{\\mathrm{сп}}$, (2)–(7)",
        "Минутные данные\n→ МСК, средние за 30 мин",
        "Полные световые\nсутки",
        "$C$, (8); модель\nприведения $K_{\\mathrm{я}}$, (9)–(12)",
        "Проверка\nпо годам, (13)",
    ]
    fig, ax = plt.subplots(figsize=(6.7, 2.2))
    ax.set_xlim(0, 7)
    ax.set_ylim(0, 2)
    ax.axis("off")
    for i, s in enumerate(steps):
        y = 1.25 if i < 3 else 0.3
        x = 0.1 + (i if i < 3 else i - 3) * 1.72
        ax.add_patch(FancyBboxPatch((x, y), 1.5, 0.6, boxstyle="round,pad=0.03", fc="white", ec=K, lw=0.9))
        ax.text(x + 0.75, y + 0.3, s, ha="center", va="center", fontsize=8)
    for a, b in [((1.63, 1.55), (1.82, 1.55)), ((3.35, 1.55), (3.54, 1.55)),
                 ((1.63, 0.6), (1.82, 0.6)), ((3.35, 0.6), (3.54, 0.6)), ((5.07, 0.6), (5.26, 0.6)),
                 ((4.29, 1.22), (4.29, 0.93))]:
        ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=9, color=K, lw=0.9))
    ax.text(4.36, 1.04, "$G_{\\mathrm{сп}},\\ K_{\\mathrm{сп}}$", fontsize=8)
    save(fig, "a_fig1_scheme.png")


def fig2_reference() -> None:
    sp = [float(r["href_cs_52135_mjm2"]) for r in rows("sp131_href_cs.csv")]
    nasa = rows("nasa_vs_sp131.csv")
    x = range(12)
    fig, ax = plt.subplots(figsize=(6.3, 3.4))
    ax.plot(x, SP_48, ls=":", c=K, lw=1.0, label="СП, 48° с. ш.")
    ax.plot(x, SP_56, ls="-.", c=K, lw=1.0, label="СП, 56° с. ш.")
    ax.plot(x, sp, ls="-", c=K, lw=1.8, marker="o", ms=4, mfc=K, label="СП, 52,135° с. ш. (интерполяция)")
    ax.plot(x, [float(r["nasa_clrsky_mjm2"]) for r in nasa], ls="-", c=K, lw=0.9, marker="s", ms=4, mfc="white",
            label="NASA POWER, безоблачное небо")
    ax.plot(x, [float(r["nasa_allsky_mjm2"]) for r in nasa], ls="--", c=K, lw=0.9, marker="^", ms=4, mfc="white",
            label="NASA POWER, все условия")
    months_axis(ax)
    ax.set_ylabel("Месячная сумма, МДж/м²")
    ax.legend(fontsize=8, loc="upper right")
    save(fig, "a_fig2_reference.png")


def fig3_c_ratio() -> None:
    clim = rows("climatology_q_only.csv")
    x = np.arange(12)
    fig, ax = plt.subplots(figsize=(6.3, 3.2))
    ax.bar(x - 0.2, [float(r["C_vs_sp"]) for r in clim], width=0.38, color=K, edgecolor=K, lw=0.6,
           label="Станция Конь-Колодезь, полные сутки 2023–2025 гг.")
    ax.bar(x + 0.2, [float(r["C_nasa_clim"]) for r in clim], width=0.38, color="white", edgecolor=K, lw=0.6,
           hatch="////", label="NASA POWER, климатология")
    months_axis(ax)
    ax.set_ylabel("$C = H_{\\mathrm{н}}\\,/\\,H_{\\mathrm{сп}}$")
    ax.set_ylim(0, 1.0)
    ax.legend(fontsize=8, loc="upper left")
    save(fig, "a_fig3_c_ratio.png")


def fig4_clear_sky() -> None:
    c = json.loads((ROOT / "reports" / "article_A_numbers.json").read_text(encoding="utf-8"))[
        "clear_sky_check_H_over_Href_daily"]
    get = lambda k: [c[str(m)][k] for m in range(1, 13)]  # noqa: E731
    x = range(12)
    fig, ax = plt.subplots(figsize=(6.3, 3.2))
    ax.plot(x, get("p50"), ls=":", c=K, lw=1.0, marker="o", ms=3.5, mfc="white", label="медиана")
    ax.plot(x, get("p90"), ls="--", c=K, lw=1.0, label="90-й процентиль")
    ax.plot(x, get("p95"), ls="-", c=K, lw=1.6, marker="s", ms=3.5, mfc=K, label="95-й процентиль")
    ax.scatter(x, get("max"), marker="x", c=K, s=22, lw=0.9, zorder=3, label="максимум")
    ax.axhline(1.0, c=K, lw=0.6)
    months_axis(ax)
    ax.set_ylabel("$H_{\\mathrm{н}}\\,/\\,H_{\\mathrm{сп.с}}$")
    ax.set_ylim(0, 1.3)
    ax.legend(fontsize=8, loc="lower left", ncol=2)
    save(fig, "a_fig4_clear_sky_check.png")


def fig5_diurnal() -> None:
    daily = rows("daily_actualize.csv")
    by_m = defaultdict(list)
    for r in daily:
        by_m[int(r["month"])].append(r)

    def typical(month: int) -> str:
        med = float(np.median([float(r["Kt"]) for r in by_m[month]]))
        return min(by_m[month], key=lambda r: abs(float(r["Kt"]) - med))["date"]

    jan, jul = typical(1), typical(7)
    series = {jan: [], jul: []}
    djf, jja = defaultdict(list), defaultdict(list)
    for rec in rows("hh_station.csv"):
        if rec["quality_flag"] != "complete" or rec["GHI"] == "":
            continue
        t = datetime.strptime(rec["obs_time_msk"], "%Y-%m-%d %H:%M:%S")
        h = t.hour + t.minute / 60.0 + 0.25
        q = float(rec["GHI"])
        if t.month in (12, 1, 2):
            djf[h].append(q)
        if t.month in (6, 7, 8):
            jja[h].append(q)
        if rec["obs_time_msk"][:10] in series:
            series[rec["obs_time_msk"][:10]].append((h, q))
    fig, ax = plt.subplots(figsize=(6.3, 3.4))
    for bucket, ls, lab in ((jja, "-", "лето (VI–VIII), среднее"), (djf, "--", "зима (XII–II), среднее")):
        xs = sorted(bucket)
        ax.plot(xs, [np.mean(bucket[v]) for v in xs], ls=ls, c=K, lw=1.6, label=lab)
    for d, mk, lab in ((jul, "o", f"типичные сутки {datetime.strptime(jul, '%Y-%m-%d'):%d.%m.%Y}"),
                       (jan, "s", f"типичные сутки {datetime.strptime(jan, '%Y-%m-%d'):%d.%m.%Y}")):
        xs, ys = zip(*sorted(series[d]))
        ax.plot(xs, ys, ls=":", c=K, lw=0.8, marker=mk, ms=2.8, mfc="white", label=lab)
    ax.set_xlim(0, 24)
    ax.set_xticks(range(0, 25, 3))
    ax.set_xlabel("Время, ч (МСК; середина получасового интервала)")
    ax.set_ylabel("$G$, Вт/м²")
    ax.legend(fontsize=8, loc="upper right")
    save(fig, "a_fig5_diurnal.png")


def model_rows() -> tuple[np.ndarray, np.ndarray, np.ndarray, list[datetime]]:
    d = [r for r in rows("daily_actualize.csv") if r["Kt_hat_oos"]]
    return (np.array([float(r["Kt"]) for r in d]), np.array([float(r["Kt_hat_oos"]) for r in d]),
            np.array([int(r["year"]) for r in d]), [datetime.strptime(r["date"], "%Y-%m-%d") for r in d])


def fig6_kt() -> None:
    obs, hat, years, _ = model_rows()
    fig, ax = plt.subplots(figsize=(4.4, 4.2))
    for y, kw in YEAR_MARK.items():
        m = years == y
        ax.scatter(hat[m], obs[m], s=10, lw=0.6, label=f"{y} г.", **kw)
    ax.plot((0, 1.1), (0, 1.1), c=K, lw=0.8, ls="--")
    ax.set_xlim(0, 1.1)
    ax.set_ylim(0, 1.1)
    ax.set_aspect("equal")
    ax.set_xlabel("Прогноз $\\hat{K}_{\\mathrm{я}}$")
    ax.set_ylabel("Наблюдение $K_{\\mathrm{я}}$")
    ax.legend(fontsize=8, loc="upper left", markerscale=1.4)
    save(fig, "a_fig6_kt_obs_pred.png")


def fig7_residuals() -> None:
    obs, hat, years, dates = model_rows()
    resid = hat - obs
    import matplotlib.dates as mdates

    fig, axes = plt.subplots(1, 2, figsize=(6.7, 3.3), gridspec_kw={"width_ratios": [1, 1.4]})
    darr = np.array(dates)
    for y, kw in YEAR_MARK.items():
        m = years == y
        axes[0].scatter(hat[m], resid[m], s=8, lw=0.5, label=f"{y} г.", **kw)
        axes[1].scatter(darr[m], resid[m], s=8, lw=0.5, **kw)
    for ax in axes:
        ax.axhline(0, c=K, lw=0.7)
        ax.set_ylim(-0.45, 0.45)
    axes[0].set_xlabel("$\\hat{K}_{\\mathrm{я}}$")
    axes[0].set_ylabel("$\\hat{K}_{\\mathrm{я}} - K_{\\mathrm{я}}$")
    axes[0].text(0.03, 0.04, "а", transform=axes[0].transAxes, fontsize=11)
    axes[1].set_xlabel("Дата")
    axes[1].xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 7)))
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%m.%Y"))
    axes[1].text(0.03, 0.04, "б", transform=axes[1].transAxes, fontsize=11)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=3, fontsize=8, markerscale=1.4)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(FIG / "a_fig7_residuals.png", facecolor="white")
    plt.close(fig)


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    for old in ("a_fig4_c_ratio.png", "a_fig8_clear_sky_check.png"):
        (FIG / old).unlink(missing_ok=True)
    fig1_scheme()
    fig2_reference()
    fig3_c_ratio()
    fig4_clear_sky()
    fig5_diurnal()
    fig6_kt()
    fig7_residuals()
    print("ok")


if __name__ == "__main__":
    main()
