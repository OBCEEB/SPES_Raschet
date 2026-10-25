#!/usr/bin/env python3
"""Render docs/rabochii-material.md → solnechnaya-radiaciya-kollektory.pdf."""

from __future__ import annotations

import re
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Image as RLImage,
    KeepTogether,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parent

JOBS = {
    "paper": {
        "md": ROOT / "docs" / "rabochii-material.md",
        "out": ROOT / "solnechnaya-radiaciya-kollektory.pdf",
        "kicker": "РАБОЧИЙ МАТЕРИАЛ К СТАТЬЕ · 15 ОКТЯБРЯ 2026",
        "header": "Рабочий материал к статье · солнечная радиация и коллекторы",
        "footer": "Не рукопись — база формул, данных и ссылок",
        "title": "Солнечная радиация для расчёта коллекторов — рабочий материал",
        "author": "Рабочий материал к статье",
    },
    "otchet": {
        "md": ROOT / "docs" / "otchet-raschety.md",
        "out": ROOT / "otchet-raschety-kon-kolodez.pdf",
        "kicker": "ОТЧЁТ ПО РАСЧЁТАМ · продолжение рабочего материала · 15 октября 2026",
        "header": "Отчёт по расчётам · Конь-Колодезь, МГУ, коллектор",
        "footer": "Цифры из CSV/JSON репозитория · сверка для рецензии",
        "title": "Отчёт по расчётам: Конь-Колодезь, МГУ, ISO 9806",
        "author": "Отчёт по расчётам",
    },
}

JOB = JOBS["paper"]
MD = JOB["md"]
OUT = JOB["out"]

FONT_DIR = "/usr/share/fonts/truetype/dejavu/"
pdfmetrics.registerFont(TTFont("DejaVu", FONT_DIR + "DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DejaVuBold", FONT_DIR + "DejaVuSans-Bold.ttf"))
pdfmetrics.registerFont(TTFont("DejaVuMono", FONT_DIR + "DejaVuSansMono.ttf"))

INK = colors.HexColor("#1a1a1a")
MUTED = colors.HexColor("#4a4a4a")
RULE = colors.HexColor("#c8c8c8")
HEAD_BG = colors.HexColor("#f2f2f2")
ACCENT = colors.HexColor("#1f4e79")
NOTE_BG = colors.HexColor("#f7f4ea")
WARN_BG = colors.HexColor("#f7ece6")
CODE_BG = colors.HexColor("#f4f4f4")
PAGE_W = 170 * mm


def styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle("CoverKicker", fontName="DejaVu", fontSize=9, textColor=ACCENT, spaceAfter=8))
    s.add(ParagraphStyle("CoverTitle", fontName="DejaVuBold", fontSize=18, leading=24, textColor=INK, spaceAfter=8))
    s.add(ParagraphStyle("H1", fontName="DejaVuBold", fontSize=13, leading=17, textColor=ACCENT, spaceBefore=14, spaceAfter=7))
    s.add(ParagraphStyle("H2", fontName="DejaVuBold", fontSize=11, leading=14.5, textColor=INK, spaceBefore=11, spaceAfter=5))
    s.add(ParagraphStyle("H3", fontName="DejaVuBold", fontSize=10, leading=13, textColor=INK, spaceBefore=8, spaceAfter=4))
    s.add(
        ParagraphStyle(
            "Body",
            fontName="DejaVu",
            fontSize=9.3,
            leading=13.2,
            textColor=INK,
            alignment=TA_JUSTIFY,
            spaceAfter=6,
        )
    )
    s.add(
        ParagraphStyle(
            "BulletBody",
            fontName="DejaVu",
            fontSize=9,
            leading=12.6,
            textColor=INK,
            leftIndent=12,
            spaceAfter=2.5,
        )
    )
    s.add(ParagraphStyle("Callout", fontName="DejaVu", fontSize=9, leading=12.6, textColor=INK, alignment=TA_LEFT))
    s.add(
        ParagraphStyle(
            "Formula",
            fontName="DejaVuMono",
            fontSize=8.2,
            leading=12,
            textColor=INK,
            alignment=TA_CENTER,
            spaceBefore=3,
            spaceAfter=6,
        )
    )
    s.add(
        ParagraphStyle(
            "CodeBlock",
            fontName="DejaVuMono",
            fontSize=7.4,
            leading=10.5,
            textColor=INK,
            leftIndent=4,
            spaceBefore=2,
            spaceAfter=6,
        )
    )
    s.add(ParagraphStyle("Th", fontName="DejaVuBold", fontSize=6.6, leading=8.6, textColor=INK, alignment=TA_CENTER))
    s.add(ParagraphStyle("Td", fontName="DejaVu", fontSize=6.6, leading=8.6, textColor=INK))
    s.add(ParagraphStyle("TdR", fontName="DejaVu", fontSize=6.6, leading=8.6, textColor=INK, alignment=TA_RIGHT))
    s.add(ParagraphStyle("Caption", fontName="DejaVu", fontSize=8, leading=11, textColor=MUTED, spaceAfter=8))
    return s


S = styles()


def inline(text: str) -> str:
    slots: list[str] = []

    def hold(html: str) -> str:
        slots.append(html)
        return f"\x00{len(slots) - 1}\x00"

    def links(m: re.Match[str]) -> str:
        label, url = m.group(1), m.group(2)
        return hold(f'<link href="{escape(url, {chr(34): "&quot;"})}" color="#1f4e79"><u>{escape(label)}</u></link>')

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", links, text)

    def code(m: re.Match[str]) -> str:
        return hold(f'<font face="DejaVuMono" size="8">{escape(m.group(1))}</font>')

    text = re.sub(r"`([^`]+)`", code, text)

    def bold(m: re.Match[str]) -> str:
        return hold(f"<b>{escape(m.group(1))}</b>")

    text = re.sub(r"\*\*([^*]+)\*\*", bold, text)

    def italic(m: re.Match[str]) -> str:
        return hold(escape(m.group(1)))

    text = re.sub(r"\*([^*]+)\*", italic, text)
    text = escape(text)
    text = re.sub(r"\x00(\d+)\x00", lambda m: slots[int(m.group(1))], text)
    return text


def P(text: str, style: str = "Body"):
    return Paragraph(inline(text), S[style])


def callout(text: str, bg=NOTE_BG):
    inner = Paragraph(inline(text), S["Callout"])
    t = Table([[inner]], colWidths=[PAGE_W])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), bg),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("BOX", (0, 0), (-1, -1), 0.4, RULE),
            ]
        )
    )
    return t


def make_table(headers: list[str], rows: list[list[str]]):
    n = len(headers)
    first = min(38 * mm, PAGE_W * 0.28) if n >= 6 else min(55 * mm, PAGE_W * 0.4)
    rest = (PAGE_W - first) / max(n - 1, 1)
    widths = [first] + [rest] * (n - 1)
    if n <= 4:
        widths = [PAGE_W / n] * n

    def is_num(cell: str) -> bool:
        compact = cell.replace(" ", "").replace(",", ".").replace("+", "").replace("−", "-").replace("–", "-")
        compact = compact.replace("**", "")
        return bool(re.fullmatch(r"-?\d+(\.\d+)?", compact)) or cell in {"—", "–", "-"}

    numeric_from = None
    if n > 1 and rows and all(is_num(c) or c == "" for c in rows[0][1:]):
        numeric_from = 1

    head = [Paragraph(inline(h), S["Th"]) for h in headers]
    body = []
    for row in rows:
        cells = []
        for i, cell in enumerate(row):
            st = S["TdR"] if numeric_from is not None and i >= numeric_from else S["Td"]
            cells.append(Paragraph(inline(cell), st))
        body.append(cells)
    data = [head] + body
    t = Table(data, colWidths=widths, repeatRows=1)
    cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
        ("GRID", (0, 0), (-1, -1), 0.25, RULE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2.2),
        ("TOPPADDING", (0, 0), (-1, -1), 2.6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.6),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            cmds.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#fafafa")))
    t.setStyle(TableStyle(cmds))
    return t


def header_footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.4)
    canvas.line(18 * mm, 287 * mm, 192 * mm, 287 * mm)
    canvas.setFont("DejaVu", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 290 * mm, JOB["header"])
    canvas.drawRightString(192 * mm, 290 * mm, "15 октября 2026")
    canvas.line(18 * mm, 12 * mm, 192 * mm, 12 * mm)
    canvas.drawString(18 * mm, 7 * mm, JOB["footer"])
    canvas.drawRightString(192 * mm, 7 * mm, str(doc.page))
    canvas.restoreState()


def split_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def is_sep(line: str) -> bool:
    cells = split_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", c.replace(" ", "")) for c in cells if c)


def parse_md(text: str) -> list:
    lines = text.replace("\r\n", "\n").split("\n")
    story: list = []
    i = 0
    para: list[str] = []
    first_h1 = True

    def flush_para():
        nonlocal para
        if not para:
            return
        raw = " ".join(para).strip()
        para = []
        if not raw:
            return
        story.append(P(raw))

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            flush_para()
            i += 1
            buf = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            block = "\n".join(buf)
            pre = Preformatted(block, S["CodeBlock"])
            box = Table([[pre]], colWidths=[PAGE_W])
            box.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), CODE_BG),
                        ("BOX", (0, 0), (-1, -1), 0.3, RULE),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ]
                )
            )
            story.append(box)
            continue

        img = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", stripped)
        if img:
            flush_para()
            cap, rel = img.group(1), img.group(2)
            path = Path(rel)
            if not path.is_absolute():
                path = ROOT / rel
            if path.exists():
                ir = ImageReader(str(path))
                iw, ih = ir.getSize()
                w, h = PAGE_W, PAGE_W * ih / iw
                max_h = 105 * mm
                if h > max_h:
                    h = max_h
                    w = h * iw / ih
                pic = RLImage(str(path), width=w, height=h)
                chunk = [Spacer(1, 3), pic]
                if cap:
                    chunk.append(P("Рис. " + cap, "Caption"))
                story.append(KeepTogether(chunk))
                story.append(Spacer(1, 4))
            i += 1
            continue

        if stripped.startswith("$$") and stripped.endswith("$$") and len(stripped) > 4:
            flush_para()
            story.append(Paragraph(escape(stripped[2:-2].strip()), S["Formula"]))
            i += 1
            continue

        if stripped.startswith("|") and i + 1 < len(lines) and is_sep(lines[i + 1]):
            flush_para()
            headers = split_row(stripped)
            i += 2
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(split_row(lines[i].strip()))
                i += 1
            story.append(Spacer(1, 2))
            story.append(make_table(headers, rows))
            story.append(Spacer(1, 6))
            continue

        if stripped == "---":
            flush_para()
            story.append(Spacer(1, 4))
            i += 1
            continue

        if stripped.startswith("> "):
            flush_para()
            buf = [stripped[2:]]
            i += 1
            while i < len(lines) and lines[i].strip().startswith("> "):
                buf.append(lines[i].strip()[2:])
                i += 1
            bg = WARN_BG if any("нельзя" in x.lower() or "не заменяет" in x.lower() for x in buf) else NOTE_BG
            story.append(callout(" ".join(buf), bg))
            story.append(Spacer(1, 4))
            continue

        if stripped.startswith("# "):
            flush_para()
            title = stripped[2:].strip()
            if first_h1:
                story.append(P(JOB["kicker"], "CoverKicker"))
                story.append(P(title, "CoverTitle"))
                first_h1 = False
            else:
                story.append(P(title, "H1"))
            i += 1
            continue

        if stripped.startswith("## "):
            flush_para()
            story.append(P(stripped[3:].strip(), "H1"))
            i += 1
            continue

        if stripped.startswith("### "):
            flush_para()
            story.append(P(stripped[4:].strip(), "H2"))
            i += 1
            continue

        if re.match(r"^[-*] ", stripped):
            flush_para()
            story.append(P("•  " + stripped[2:].strip(), "BulletBody"))
            i += 1
            continue

        if re.match(r"^\d+\.\s", stripped):
            flush_para()
            story.append(P(stripped, "BulletBody"))
            i += 1
            continue

        if stripped == "":
            flush_para()
            i += 1
            continue

        para.append(stripped)
        i += 1

    flush_para()
    return story


def build(job_name: str = "paper"):
    global JOB, MD, OUT
    if job_name not in JOBS:
        raise SystemExit(f"unknown job {job_name!r}; expected {list(JOBS)}")
    JOB = JOBS[job_name]
    MD = JOB["md"]
    OUT = JOB["out"]
    md = MD.read_text(encoding="utf-8")
    story = parse_md(md)
    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=16 * mm,
        title=JOB["title"],
        author=JOB["author"],
    )
    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes, {doc.page} pages)")


if __name__ == "__main__":
    import sys

    build(sys.argv[1] if len(sys.argv) > 1 else "paper")
