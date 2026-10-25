#!/usr/bin/env python3
"""Figures 1, 2, 4 and 8 of article A (the rest come from plot_otchet_figures.py).

Writes docs/figures/a_fig1_scheme.png, a_fig2_reference.png, a_fig4_c_ratio.png,
a_fig8_clear_sky_check.png.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from plot_otchet_figures import ACCENT, GRID, INK, MUTED, SECOND  # noqa: E402

CSV = ROOT / "data" / "lipetsk" / "csv"
FIG = ROOT / "docs" / "figures"
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]
SP_48 = [196, 308, 545, 712, 874, 911, 898, 753, 575, 409, 220, 158]
SP_56 = [112, 215, 445, 648, 855, 903, 879, 707, 489, 295, 138, 79]


def rows(name: str) -> list[dict]:
    with (CSV / name).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fig1_scheme() -> None:
    steps = [
        "Таблица СП:\nHref,cs(φ, m)",
        "Интерполяция\nпо широте пункта",
        "Профиль Хоттела,\nприведённый к Href,cs",
        "Минутки пиранометра\n→ MSK, средние за 30 мин",
        "Полные световые\nсутки (QC)",
        "C = H/Href,cs и\nмодель приведения Kt",
        "Проверка\nпо годам",
    ]
    fig, ax = plt.subplots(figsize=(8.6, 2.6))
    ax.set_xlim(0, 7)
    ax.set_ylim(0, 2)
    ax.axis("off")
    for i, s in enumerate(steps):
        y = 1.25 if i < 3 else 0.35
        x = 0.2 + (i if i < 3 else i - 3) * 1.7
        box = FancyBboxPatch((x, y), 1.45, 0.55, boxstyle="round,pad=0.03", fc="#eef3f8", ec=ACCENT, lw=1.0)
        ax.add_patch(box)
        ax.text(x + 0.725, y + 0.275, s, ha="center", va="center", fontsize=7.5, color=INK)
    arrows = [((1.65, 1.525), (1.9, 1.525)), ((3.35, 1.525), (3.6, 1.525)),
              ((1.65, 0.625), (1.9, 0.625)), ((3.35, 0.625), (3.6, 0.625)), ((5.05, 0.625), (5.3, 0.625)),
              ((4.325, 1.22), (4.325, 0.93))]
    for a, b in arrows:
        ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=9, color=MUTED, lw=1.0))
    ax.text(4.4, 1.05, "Gref, Kref", fontsize=7, color=MUTED)
    fig.tight_layout()
    fig.savefig(FIG / "a_fig1_scheme.png", dpi=200)
    plt.close(fig)


def fig2_reference() -> None:
    sp = rows("sp131_href_cs.csv")
    nasa = rows("nasa_vs_sp131.csv")
    x = range(12)
    fig, ax = plt.subplots(figsize=(7.6, 3.6))
    ax.plot(x, SP_48, ls=":", c=MUTED, marker=".", label="СП, 48° с. ш.")
    ax.plot(x, SP_56, ls="--", c=MUTED, marker=".", label="СП, 56° с. ш.")
    ax.plot(x, [float(r["href_cs_52135_mjm2"]) for r in sp], c=ACCENT, lw=2, marker="o", ms=4,
            label="СП, 52,135° (интерполяция)")
    ax.plot(x, [float(r["nasa_clrsky_mjm2"]) for r in nasa], c=SECOND, lw=1.4, marker="s", ms=3,
            label="NASA POWER, безоблачное")
    ax.plot(x, [float(r["nasa_allsky_mjm2"]) for r in nasa], c=SECOND, lw=1.4, ls="--", marker="^", ms=3,
            label="NASA POWER, все условия")
    ax.set_xticks(list(x))
    ax.set_xticklabels(ROMAN)
    ax.set_ylabel("МДж/м² за месяц")
    ax.grid(True, color=GRID, lw=0.5)
    ax.legend(frameon=False, fontsize=7.5)
    fig.tight_layout()
    fig.savefig(FIG / "a_fig2_reference.png", dpi=200)
    plt.close(fig)


def fig4_c_ratio() -> None:
    clim = rows("climatology_q_only.csv")
    x = list(range(12))
    fig, ax = plt.subplots(figsize=(7.6, 3.4))
    ax.bar([i - 0.2 for i in x], [float(r["C_vs_sp"]) for r in clim], width=0.4, color=ACCENT,
           label="Станция Конь-Колодезь (полные сутки 2023–2025)")
    ax.bar([i + 0.2 for i in x], [float(r["C_nasa_clim"]) for r in clim], width=0.4, color=SECOND, alpha=0.8,
           label="NASA POWER (климатология)")
    ax.set_xticks(x)
    ax.set_xticklabels(ROMAN)
    ax.set_ylabel("C = H / Href,cs")
    ax.set_ylim(0, 1)
    ax.grid(True, axis="y", color=GRID, lw=0.5)
    ax.legend(frameon=False, fontsize=7.5, loc="upper left")
    fig.tight_layout()
    fig.savefig(FIG / "a_fig4_c_ratio.png", dpi=200)
    plt.close(fig)


def fig8_clear_sky() -> None:
    d = json.loads((ROOT / "reports" / "article_A_numbers.json").read_text(encoding="utf-8"))
    c = d["clear_sky_check_H_over_Href_daily"]
    x = list(range(12))
    get = lambda k: [c[str(m)][k] for m in range(1, 13)]  # noqa: E731
    fig, ax = plt.subplots(figsize=(7.6, 3.4))
    ax.plot(x, get("p50"), c=MUTED, marker="o", ms=3, label="медиана")
    ax.plot(x, get("p90"), c=ACCENT, marker="o", ms=3, ls="--", label="90-й процентиль")
    ax.plot(x, get("p95"), c=ACCENT, marker="s", ms=3.5, lw=1.8, label="95-й процентиль")
    ax.scatter(x, get("max"), c=SECOND, s=14, zorder=3, label="максимум")
    ax.axhline(1.0, c=INK, lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(ROMAN)
    ax.set_ylabel("H / Href,cs за сутки")
    ax.set_ylim(0, 1.3)
    ax.grid(True, color=GRID, lw=0.5)
    ax.legend(frameon=False, fontsize=7.5, loc="lower center", ncol=4)
    fig.tight_layout()
    fig.savefig(FIG / "a_fig8_clear_sky_check.png", dpi=200)
    plt.close(fig)


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    fig1_scheme()
    fig2_reference()
    fig4_c_ratio()
    fig8_clear_sky()
    print("ok")


if __name__ == "__main__":
    main()
