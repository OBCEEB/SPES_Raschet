#!/usr/bin/env python3
"""Article A draft → one PDF (text, tables, figures) via HTML and headless Edge/Chrome.

    python scripts/plot_otchet_figures.py
    python scripts/plot_article_a_figures.py
    python manuscript/build_pdf.py
"""

from __future__ import annotations

import re
import subprocess
from datetime import date
from pathlib import Path

import markdown

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FIG = ROOT / "docs" / "figures"
OUT_DIR = HERE / "build"
BROWSERS = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
]

FIGURES = [
    ("a_fig1_scheme.png", "Схема расчётной цепочки."),
    ("a_fig2_reference.png", "Справочная месячная сумма суммарной радиации при безоблачном небе для табличных широт "
     "48° и 56° и для широты станции (интерполяция), а также климатология NASA POWER для безоблачного неба "
     "и всех условий."),
    ("completeness_heatmap.png", "Полные световые сутки по месяцам и годам (963 суток)."),
    ("a_fig4_c_ratio.png", "Отношение наблюдаемой и справочной безоблачной сумм C по месяцам: станция "
     "Конь-Колодезь (совокупность полных суток 2023–2025 гг.) и NASA POWER."),
    ("kt_obs_pred.png", "Суточный индекс ясности: наблюдение и прогноз модели приведения при поочерёдном "
     "исключении лет (956 суток)."),
    ("kt_residuals.png", "Остатки модели приведения суточного индекса ясности."),
    ("diurnal_winter_summer.png", "Средний суточный ход суммарной облучённости зимой и летом по полным суткам "
     "(часы московского времени, начало получасового интервала)."),
    ("a_fig8_clear_sky_check.png", "Отношение наблюдаемой суточной суммы к суточной доле справочной безоблачной "
     "суммы по месяцам: медиана, 90-й и 95-й процентили, максимум."),
]

CSS = """
@page { size: A4; margin: 20mm 18mm 20mm 22mm; }
body { font-family: "Times New Roman", Times, serif; font-size: 12pt; line-height: 1.4; color: #111; }
h1 { font-size: 16pt; text-align: center; margin: 0 0 10pt; }
h2 { font-size: 13.5pt; margin: 16pt 0 6pt; }
h3 { font-size: 12.5pt; margin: 12pt 0 4pt; }
p { text-align: justify; margin: 0 0 6pt; }
code { font-family: Consolas, monospace; font-size: 9.5pt; color: #444; }
table { border-collapse: collapse; margin: 6pt 0 10pt; font-size: 10pt; page-break-inside: avoid; }
th, td { border: 0.6pt solid #888; padding: 2pt 5pt; vertical-align: top; }
th { background: #eef1f5; }
ul, ol { margin: 0 0 6pt 18pt; padding: 0; }
.banner { border: 0.8pt solid #b85c38; color: #7a3a20; padding: 5pt 8pt; font-size: 10pt; margin-bottom: 12pt; }
.part { page-break-before: always; }
figure { page-break-inside: avoid; margin: 0 0 16pt; text-align: center; }
figure img { max-width: 100%; max-height: 105mm; }
figcaption { font-size: 10.5pt; text-align: justify; margin-top: 4pt; }
"""


def md_to_html(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    return markdown.markdown(text, extensions=["tables", "sane_lists"])


def tables_html() -> str:
    text = (HERE / "article_A_tables.md").read_text(encoding="utf-8")
    text = re.sub(r"^# .*\n", "", text, count=1)
    text = re.sub(r"^Числа скопированы.*\n", "", text, count=1, flags=re.M)
    return md_to_html(text)


def figures_html() -> str:
    parts = []
    for i, (name, caption) in enumerate(FIGURES, 1):
        path = FIG / name
        if not path.exists():
            raise FileNotFoundError(f"{path}: run the plotting scripts first")
        parts.append(
            f'<figure><img src="{path.as_uri()}" alt="Рис. {i}">'
            f"<figcaption><b>Рис. {i}.</b> {caption}</figcaption></figure>"
        )
    return "\n".join(parts)


def build_html() -> str:
    article = md_to_html((HERE / "article_A_draft_v1.md").read_text(encoding="utf-8"))
    banner = (
        f'<div class="banner">Черновик v2 от {date.today():%d.%m.%Y}. Не для распространения. '
        "Пометки [ТРЕБУЕТСЯ …] — данные, которые должен предоставить автор.</div>"
    )
    return (
        f'<!doctype html><html lang="ru"><head><meta charset="utf-8"><style>{CSS}</style></head><body>'
        f"{banner}{article}"
        f'<div class="part"><h2>Таблицы</h2>{tables_html()}</div>'
        f'<div class="part"><h2>Рисунки</h2>{figures_html()}</div>'
        "</body></html>"
    )


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    html_path = OUT_DIR / "article_A_draft.html"
    pdf_path = OUT_DIR / "article_A_draft.pdf"
    html_path.write_text(build_html(), encoding="utf-8")
    browser = next((b for b in BROWSERS if b.exists()), None)
    if browser is None:
        raise SystemExit(f"HTML written to {html_path}; no Edge/Chrome found for PDF")
    subprocess.run(
        [str(browser), "--headless", "--disable-gpu", "--no-pdf-header-footer",
         f"--print-to-pdf={pdf_path}", html_path.as_uri()],
        check=True, capture_output=True, timeout=120,
    )
    print(pdf_path, pdf_path.stat().st_size)


if __name__ == "__main__":
    main()
