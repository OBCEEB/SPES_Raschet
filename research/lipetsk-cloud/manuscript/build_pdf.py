#!/usr/bin/env python3
"""Article A manuscript (article_A.md + article_A_refs.md) → PDF via HTML and headless Edge/Chrome.

    python scripts/plot_article_a_figures.py
    python manuscript/build_pdf.py

Markup handled here (see the header comment of article_A.md): inline and numbered
display formulas (LaTeX → MathML), @eq/@tab/@fig cross-references, table captions,
figures from docs/figures, [@key] citations numbered by first mention.
"""

from __future__ import annotations

import re
import subprocess
from datetime import date
from pathlib import Path

import markdown
from latex2mathml.converter import convert as tex2mml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FIG = ROOT / "docs" / "figures"
OUT_DIR = HERE / "build"
SOURCE = HERE / "article_A.md"
REFS = HERE / "article_A_refs.md"
BROWSERS = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
]

CSS = """
@page { size: A4; margin: 20mm 18mm 20mm 22mm; }
body { font-family: "Times New Roman", Times, serif; font-size: 12pt; line-height: 1.35; color: #000; }
h1 { font-size: 14pt; text-align: center; text-transform: uppercase; margin: 6pt 0 10pt; line-height: 1.25; }
h2 { font-size: 12pt; margin: 14pt 0 6pt; }
h3 { font-size: 12pt; font-style: italic; margin: 10pt 0 4pt; }
p { text-align: justify; text-indent: 1.25cm; margin: 0 0 4pt; }
p.udk, p.authors, p.affil { text-indent: 0; }
p.authors, p.affil { text-align: center; }
p.affil { font-style: italic; margin-bottom: 10pt; }
p.abstract, p.keywords { text-indent: 0; font-size: 11pt; }
table { border-collapse: collapse; margin: 2pt auto 10pt; font-size: 10pt; page-break-inside: avoid; }
th, td { border: 0.6pt solid #000; padding: 1.5pt 4pt; vertical-align: middle; }
th { font-weight: bold; }
p.tcap { text-indent: 0; text-align: left; margin: 8pt 0 2pt; font-size: 11pt; }
figure { page-break-inside: avoid; margin: 8pt 0 10pt; text-align: center; }
figure img { max-width: 100%; max-height: 95mm; }
figcaption { font-size: 11pt; text-align: center; margin-top: 3pt; }
.eq { display: flex; align-items: center; margin: 6pt 0; page-break-inside: avoid; }
.eq .body { flex: 1; text-align: center; }
.eq .num { width: 3em; text-align: right; }
math { font-family: "Cambria Math", "Times New Roman", serif; font-size: 1.05em; }
ol.refs { padding-left: 1.6em; font-size: 11pt; }
ol.refs li { text-align: left; margin-bottom: 2pt; }
.eq + p { text-indent: 0; }
.banner { border: 0.8pt solid #000; padding: 4pt 8pt; font-size: 9.5pt; margin-bottom: 10pt; }
hr { border: 0; page-break-after: always; }
"""


def load_refs() -> dict[str, str]:
    refs = {}
    for line in REFS.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^- (\w+): (.+)$", line)
        if m:
            refs[m.group(1)] = m.group(2).strip()
    return refs


class Doc:
    def __init__(self, text: str) -> None:
        self.text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
        self.math: list[str] = []
        self.labels: dict[str, int] = {}
        self.cites: list[str] = []

    def stash(self, html: str) -> str:
        self.math.append(html)
        return f"MATHSTASH{len(self.math) - 1}X"

    def number_labels(self) -> None:
        counters = {"eq": 0, "tab": 0, "fig": 0}
        for kind, label in re.findall(r"\{#(eq|tab|fig):([\w-]+)\}", self.text):
            counters[kind] += 1
            self.labels[f"{kind}:{label}"] = counters[kind]

    def display_math(self) -> None:
        def repl(m: re.Match) -> str:
            mml = tex2mml(m.group(1).strip(), display="block")
            num = self.labels[f"eq:{m.group(2)}"]
            return "\n\n" + self.stash(
                f'<div class="eq"><div class="body">{mml}</div><div class="num">({num})</div></div>'
            ) + "\n\n"

        self.text = re.sub(r"^\$\$(.+?)\$\$\s*\{#eq:([\w-]+)\}\s*$", repl, self.text, flags=re.M | re.S)

    def inline_math(self) -> None:
        self.text = re.sub(r"\$([^$\n]+?)\$", lambda m: self.stash(tex2mml(m.group(1))), self.text)

    def crossrefs(self) -> None:
        self.text = re.sub(r"@(eq|tab|fig):([\w-]+)", lambda m: str(self.labels[f"{m.group(1)}:{m.group(2)}"]),
                           self.text)

    def captions(self) -> None:
        def tab(m: re.Match) -> str:
            n = self.labels[f"tab:{m.group(1)}"]
            return self.stash(f'<p class="tcap">Таблица {n}. {self.inline(m.group(2))}</p>')

        self.text = re.sub(r"^Таблица \{#tab:([\w-]+)\}\. (.+)$", tab, self.text, flags=re.M)

        def fig(m: re.Match) -> str:
            n = self.labels[f"fig:{m.group(3)}"]
            path = FIG / m.group(2)
            if not path.exists():
                raise FileNotFoundError(f"{path}: run scripts/plot_article_a_figures.py")
            return self.stash(
                f'<figure><img src="{path.as_uri()}" alt="Рис. {n}">'
                f"<figcaption>Рис. {n}. {self.inline(m.group(1))}</figcaption></figure>"
            )

        self.text = re.sub(r"^!\[(.+?)\]\(([\w.-]+)\)\{#fig:([\w-]+)\}\s*$", fig, self.text, flags=re.M)

    def inline(self, s: str) -> str:
        s = re.sub(r"\$([^$\n]+?)\$", lambda m: self.stash(tex2mml(m.group(1))), s)
        return re.sub(r"^<p>|</p>$", "", markdown.markdown(s))

    def citations(self, refs: dict[str, str]) -> None:
        def repl(m: re.Match) -> str:
            parts = []
            for item in m.group(1).split(";"):
                km = re.match(r"\s*@(\w+)(.*)$", item)
                key, tail = km.group(1), km.group(2).strip()
                if key not in refs:
                    raise KeyError(f"no reference {key}")
                if key not in self.cites:
                    self.cites.append(key)
                parts.append(str(self.cites.index(key) + 1) + (f", {tail.lstrip(',').strip()}" if tail else ""))
            return "[" + "; ".join(parts) + "]"

        self.text = re.sub(r"\[(@\w+[^\]]*)\]", repl, self.text)

    def bibliography(self, refs: dict[str, str]) -> None:
        items = "".join(f"<li>{refs[k]}</li>" for k in self.cites)
        self.text = self.text.replace("{{bibliography}}", self.stash(f'<ol class="refs">{items}</ol>'))

    def render(self, refs: dict[str, str]) -> str:
        self.number_labels()
        self.display_math()
        self.captions()
        self.inline_math()
        self.crossrefs()
        self.citations(refs)
        self.bibliography(refs)
        html = markdown.markdown(self.text, extensions=["tables", "sane_lists"])
        html = re.sub(r"<p>(MATHSTASH\d+X)</p>", r"\1", html)
        for i in range(len(self.math) - 1, -1, -1):
            html = html.replace(f"MATHSTASH{i}X", self.math[i])
        return html


def front_matter_classes(html: str) -> str:
    html = re.sub(r"<p>(УДК [^<]+)</p>", r'<p class="udk">\1</p>', html, count=1)
    html = re.sub(r"<p>(<strong>Д\. Р\..*?)</p>", r'<p class="authors">\1</p>', html, count=1, flags=re.S)
    html = re.sub(r"<p>(Липецкий государственный.*?)</p>", r'<p class="affil">\1</p>', html, count=1, flags=re.S)
    html = re.sub(r"<p>(<strong>(Аннотация|Abstract)\.</strong>)", r'<p class="abstract">\1', html)
    html = re.sub(r"<p>(<strong>(Ключевые слова|Keywords):</strong>)", r'<p class="keywords">\1', html)
    html = re.sub(r"<p>(<strong>D\. R\..*?)</p>", r'<p class="authors">\1</p>', html, count=1, flags=re.S)
    return html


def build_html() -> str:
    refs = load_refs()
    body = front_matter_classes(Doc(SOURCE.read_text(encoding="utf-8")).render(refs))
    banner = (
        f'<div class="banner">Рукопись, версия 3 от {date.today():%d.%m.%Y}. Не для распространения. '
        "Пометки [ТРЕБУЕТСЯ …] — данные, которые должен предоставить автор.</div>"
    )
    return (
        f'<!doctype html><html lang="ru"><head><meta charset="utf-8"><style>{CSS}</style></head>'
        f"<body>{banner}{body}</body></html>"
    )


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    html_path = OUT_DIR / "article_A.html"
    pdf_path = OUT_DIR / "article_A.pdf"
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
