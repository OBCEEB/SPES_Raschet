# -*- coding: utf-8 -*-
"""
Сканирование CSV в каталоге метеорология:
- при наличии удаляет папки с именем 2021;
- по всем строкам с датой/временем в первой колонке (разделитель ;) считает сутки;
- полностью пустой день: есть хотя бы одна строка за этот календарный день, но ни в одной строке
  нет числовых измерений (только /, \\, пусто и т.д.) — такие дни нельзя безопасно усреднять;
- частичный пропуск: за сутки есть и строки с данными, и без — для усреднения по месяцу/году обычно допустимо.
"""
from __future__ import annotations

import csv
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path


def find_project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def is_date_token(s: str) -> bool:
    s = s.strip().strip('"').strip("'")
    if not s:
        return False
    if re.match(r"^\d{1,2}\.\d{1,2}\.\d{4}(\s|$)", s):
        return True
    if re.match(r"^\d{4}-\d{2}-\d{2}(\s|$)", s):
        return True
    return False


def calendar_date_from_first_cell(s: str) -> str | None:
    s = s.strip().strip('"').strip("'")
    m = re.match(r"^(\d{1,2}\.\d{1,2}\.\d{4})", s)
    if m:
        return m.group(1)
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        y, mo, d = m.group(1), m.group(2), m.group(3)
        return f"{int(d)}.{int(mo)}.{y}"
    return None


def row_has_numeric_data(fields: list[str]) -> bool:
    for cell in fields[1:]:
        t = cell.strip().strip('"').strip("'")
        if not t or t in {"\\", "/", "-", "—", "–", "...", ";"}:
            continue
        t2 = t.replace(",", ".").replace(" ", "")
        if re.search(r"\d", t2):
            return True
    return False


def decode_csv_text(path: Path) -> str | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    for enc in ("utf-8-sig", "cp1251", "utf-8"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return None


def iter_data_rows(text: str):
    reader = csv.reader(text.splitlines(), delimiter=";")
    for i, row in enumerate(reader, start=1):
        if not row:
            continue
        first = row[0].strip() if row else ""
        if i == 1 and not is_date_token(first):
            continue
        if not is_date_token(first):
            continue
        cal = calendar_date_from_first_cell(first)
        if not cal:
            continue
        yield cal, row_has_numeric_data(row)


def collect_year_2021_dirs(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_dir() and p.name == "2021")


def _sort_key_date(s: str) -> tuple:
    s = s.strip()
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", s)
    if m:
        d, mo, y = map(int, m.groups())
        return (y, mo, d)
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if m:
        y, mo, d = map(int, m.groups())
        return (y, mo, d)
    return (0, 0, 0)


def main() -> int:
    root = find_project_root() / "метеорология"
    if not root.is_dir():
        print("Folder not found:", root, file=sys.stderr)
        return 1

    dirs_2021 = collect_year_2021_dirs(root)
    if dirs_2021:
        print(f"Found {len(dirs_2021)} folder(s) named 2021:")
        for d in dirs_2021:
            print(" ", d.relative_to(root))
            shutil.rmtree(d, ignore_errors=False)
            print("  deleted.")
    else:
        print("No folder named 2021 (already removed or absent).")

    csv_files = sorted(
        (p for p in root.rglob("*.csv") if "2021" not in p.parts),
        key=lambda p: str(p).lower(),
    )

    rows_total: dict[str, int] = defaultdict(int)
    rows_with_data: dict[str, int] = defaultdict(int)

    decode_errors: list[str] = []

    for csv_path in csv_files:
        rel = csv_path.relative_to(root).as_posix()
        text = decode_csv_text(csv_path)
        if text is None:
            decode_errors.append(rel)
            continue
        for cal, has_num in iter_data_rows(text):
            rows_total[cal] += 1
            if has_num:
                rows_with_data[cal] += 1

    fully_empty: list[str] = []
    partial: list[str] = []
    complete: int = 0

    for cal in sorted(rows_total.keys(), key=_sort_key_date):
        tot = rows_total[cal]
        num = rows_with_data.get(cal, 0)
        if num == 0:
            fully_empty.append(cal)
        elif num < tot:
            partial.append(cal)
        else:
            complete += 1

    empty_path = root / "полностью_пустые_дни.txt"
    empty_lines = [
        "# Календарные сутки, за которые в архиве нет ни одного числового измерения "
        "(усреднять/суммировать выработку за эти дни нельзя без других источников).",
        f"# Всего таких дней: {len(fully_empty)}. Файлов CSV обработано: {len(csv_files)}.",
        "# Ниже — одна дата dd.mm.yyyy на строку:",
        "",
    ]
    empty_lines.extend(fully_empty)
    empty_path.write_text("\n".join(empty_lines), encoding="utf-8")

    summary_path = root / "сводка_качества_данных_метеостанции.txt"
    sum_lines = [
        "# Сводка по суткам (липецкая метеостанция, CSV с разделителем «;»).",
        f"# Файлов CSV: {len(csv_files)}.",
        f"# Суток с метками времени в данных: {len(rows_total)}.",
        f"# Полностью без чисел (исключить из средних за период): {len(fully_empty)}.",
        f"# С частичными пропусками по минутам (для месячных/годовых средних обычно допустимо): {len(partial)}.",
        f"# Без пропусков по минутам: {complete}.",
        "",
        "## Полностью пустые календарные даты",
        "",
    ]
    sum_lines.extend(fully_empty)
    sum_lines.extend(["", "## Календарные даты только с частичными пропусками (есть и данные, и «пустые» строки)", ""])
    sum_lines.extend(partial)
    if decode_errors:
        sum_lines.extend(["", "## Ошибки чтения файлов", ""])
        sum_lines.extend(decode_errors)
    summary_path.write_text("\n".join(sum_lines), encoding="utf-8")

    legacy = root / "пропуски_данных_по_датам.txt"
    if legacy.is_file():
        legacy.unlink()

    print(f"\nScanned {len(csv_files)} CSV files.")
    print(f"Fully empty calendar days: {len(fully_empty)}  -> {empty_path.name}")
    print(f"Partial-gap days: {len(partial)}")
    print(f"Summary: {summary_path.name}")
    if decode_errors:
        print(f"Decode errors: {len(decode_errors)} file(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
