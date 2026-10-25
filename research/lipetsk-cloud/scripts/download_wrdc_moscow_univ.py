#!/usr/bin/env python3
"""Download WRDC MOSCOW UNIV. daily GHI and DHI tables and parse them to CSV.

Source tree (no login required):
  http://wrdc.mgo.rssi.ru/wrdccgi/protect.exe?data_list_full_protected/...

Units in the original tables: J/cm²/day.
  1 MJ/m² = 100 J/cm²
  1 kWh/m² = 360 J/cm²
Quality flag F=0 is the WRDC 'OK' mark, not a missing value.
Missing cells are '-' (or WRDC sentinel -32768).
"""

from __future__ import annotations

import csv
import html as html_lib
import re
import sys
import time
import urllib.error
import urllib.request
from calendar import monthrange
from pathlib import Path

BASE = "http://wrdc.mgo.rssi.ru/wrdccgi/protect.exe?data_list_full_protected"
STATION = "moscow_univ_"
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "wrdc" / "moscow_univ" / "raw"
CSV_DIR = ROOT / "data" / "wrdc" / "moscow_univ" / "csv"

MONTHS = [
    "JAN",
    "FEB",
    "MAR",
    "APR",
    "MAY",
    "JUN",
    "JUL",
    "AUG",
    "SEP",
    "OCT",
    "NOV",
    "DEC",
]
MONTH_INDEX = {name: i + 1 for i, name in enumerate(MONTHS)}
UA = "Mozilla/5.0 (compatible; wrdc-moscow-univ-archive/1.0)"


def year_url(product: str, year: int) -> str:
    if product == "dhi":
        return f"{BASE}/d/russia/{STATION}/{STATION}_{year}_d.html"
    if product == "ghi":
        return f"{BASE}/t6/russia/{STATION}/{STATION}_{year}_t6.html"
    raise ValueError(product)


def raw_path(product: str, year: int) -> Path:
    sub = "d" if product == "dhi" else "t6"
    suffix = "d" if product == "dhi" else "t6"
    return RAW / sub / f"{STATION}_{year}_{suffix}.html"


def fetch(url: str, dest: Path, retries: int = 5) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 800:
        return
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=45) as resp:
                body = resp.read()
            if len(body) < 400:
                raise RuntimeError(f"short response ({len(body)} bytes) from {url}")
            dest.write_bytes(body)
            return
        except (urllib.error.URLError, TimeoutError, RuntimeError, OSError) as err:
            last_err = err
            time.sleep(min(2 ** attempt, 16))
    raise RuntimeError(f"failed {url}: {last_err}")


def strip_tags(cell: str) -> str:
    text = re.sub(r"<[^>]+>", "", cell)
    return html_lib.unescape(text).replace("\xa0", " ").strip()


def parse_year_html(text: str, year: int, product: str) -> tuple[list[dict], list[dict]]:
    """Return (daily_rows, monthly_rows)."""
    tables = re.findall(r"<TABLE[^>]*>(.*?)</TABLE>", text, flags=re.I | re.S)
    if not tables:
        raise ValueError(f"no TABLE in {product} {year}")

    daily_map: dict[tuple[int, int, int], dict] = {}
    monthly_map: dict[int, dict] = {}

    for table in tables:
        rows = re.findall(r"<TR[^>]*>(.*?)</TR>", table, flags=re.I | re.S)
        if not rows:
            continue
        header_cells = [strip_tags(c) for c in re.findall(r"<TD[^>]*>(.*?)</TD>", rows[0], flags=re.I | re.S)]
        month_cols: list[tuple[int, int]] = []
        i = 1
        while i < len(header_cells):
            name = header_cells[i].upper()
            if name in MONTH_INDEX:
                month_cols.append((MONTH_INDEX[name], i))
                i += 2 if i + 1 < len(header_cells) and header_cells[i + 1].upper() in {"F", ""} else 1
            else:
                i += 1
        if not month_cols:
            continue

        for row in rows[1:]:
            cells = [strip_tags(c) for c in re.findall(r"<TD[^>]*>(.*?)</TD>", row, flags=re.I | re.S)]
            if not cells:
                continue
            label = cells[0].upper()
            if label in {"SUM", "MEAN"}:
                for month, col in month_cols:
                    value = parse_number(cells[col] if col < len(cells) else "")
                    flag = parse_flag(cells[col + 1] if col + 1 < len(cells) else "")
                    rec = monthly_map.setdefault(
                        month,
                        {
                            "year": year,
                            "month": month,
                            "product": product,
                            "sum_j_cm2": "",
                            "mean_j_cm2": "",
                            "flag": "",
                        },
                    )
                    rec["flag"] = flag if flag != "" else rec["flag"]
                    if label == "SUM":
                        rec["sum_j_cm2"] = value
                    else:
                        rec["mean_j_cm2"] = value
                continue
            if not label.isdigit():
                continue
            day = int(label)
            for month, col in month_cols:
                value = parse_number(cells[col] if col < len(cells) else "")
                flag = parse_flag(cells[col + 1] if col + 1 < len(cells) else "")
                max_day = monthrange(year, month)[1]
                if day > max_day:
                    continue
                if value == "" and flag == "":
                    continue
                daily_map[(year, month, day)] = {
                    "date": f"{year:04d}-{month:02d}-{day:02d}",
                    "year": year,
                    "month": month,
                    "day": day,
                    "product": product,
                    "value_j_cm2": value,
                    "flag": flag,
                }

    daily = [daily_map[k] for k in sorted(daily_map)]
    monthly = [monthly_map[k] for k in sorted(monthly_map)]
    return daily, monthly


def parse_number(raw: str) -> str:
    raw = raw.strip().replace(" ", "")
    if raw in {"", "-", "—", "-32768"}:
        return ""
    try:
        return str(int(raw))
    except ValueError:
        try:
            return str(float(raw))
        except ValueError:
            return ""


def parse_flag(raw: str) -> str:
    raw = raw.strip()
    if raw in {"", "-", "—"}:
        return ""
    return raw


def jcm2_to_mj(value: str) -> str:
    if value == "":
        return ""
    return f"{int(value) / 100:.2f}"


def jcm2_to_kwh(value: str) -> str:
    if value == "":
        return ""
    return f"{int(value) / 360:.3f}"


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_climatology(monthly_all: list[dict], annual: list[dict]) -> None:
    """WMO-style monthly means over complete calendar years."""
    complete_ghi = {int(r["year"]) for r in annual if r["ghi_year_j_cm2"] != ""}
    complete_both = {int(r["year"]) for r in annual if r["kd_year"] != ""}
    periods = {
        "ghi_1971_2024": ("ghi", {y for y in complete_ghi if 1971 <= y <= 2024}),
        "ghi_dhi_1991_2020": ("both", {y for y in complete_both if 1991 <= y <= 2020}),
        "ghi_dhi_1991_2024": ("both", {y for y in complete_both if 1991 <= y <= 2024}),
    }
    rows: list[dict] = []
    for period, (mode, years) in periods.items():
        if not years:
            continue
        for month in range(1, 13):
            ghi_vals = [
                int(r["sum_j_cm2"])
                for r in monthly_all
                if r["product"] == "ghi"
                and r["month"] == month
                and r["year"] in years
                and r["sum_j_cm2"] != ""
            ]
            rec = {
                "period": period,
                "n_years": len(years),
                "year_from": min(years),
                "year_to": max(years),
                "month": month,
            }
            if ghi_vals:
                ghi_mean = sum(ghi_vals) / len(ghi_vals)
                rec["ghi_mean_j_cm2"] = f"{ghi_mean:.0f}"
                rec["ghi_mean_mj_m2"] = f"{ghi_mean / 100:.2f}"
                rec["ghi_mean_kwh_m2"] = f"{ghi_mean / 360:.1f}"
            else:
                rec["ghi_mean_j_cm2"] = rec["ghi_mean_mj_m2"] = rec["ghi_mean_kwh_m2"] = ""
            if mode == "both":
                dhi_vals = [
                    int(r["sum_j_cm2"])
                    for r in monthly_all
                    if r["product"] == "dhi"
                    and r["month"] == month
                    and r["year"] in years
                    and r["sum_j_cm2"] != ""
                ]
                if dhi_vals:
                    dhi_mean = sum(dhi_vals) / len(dhi_vals)
                    rec["dhi_mean_j_cm2"] = f"{dhi_mean:.0f}"
                    rec["dhi_mean_mj_m2"] = f"{dhi_mean / 100:.2f}"
                    rec["dhi_mean_kwh_m2"] = f"{dhi_mean / 360:.1f}"
                    beam = ghi_mean - dhi_mean
                    rec["beam_mean_j_cm2"] = f"{beam:.0f}"
                    rec["beam_mean_mj_m2"] = f"{beam / 100:.2f}"
                    rec["beam_mean_kwh_m2"] = f"{beam / 360:.1f}"
                    rec["kd"] = f"{dhi_mean / ghi_mean:.3f}" if ghi_mean else ""
                else:
                    rec["dhi_mean_j_cm2"] = rec["dhi_mean_mj_m2"] = rec["dhi_mean_kwh_m2"] = ""
                    rec["beam_mean_j_cm2"] = rec["beam_mean_mj_m2"] = rec["beam_mean_kwh_m2"] = ""
                    rec["kd"] = ""
            else:
                rec["dhi_mean_j_cm2"] = rec["dhi_mean_mj_m2"] = rec["dhi_mean_kwh_m2"] = ""
                rec["beam_mean_j_cm2"] = rec["beam_mean_mj_m2"] = rec["beam_mean_kwh_m2"] = ""
                rec["kd"] = ""
            rows.append(rec)
    write_csv(
        CSV_DIR / "climatology_monthly.csv",
        rows,
        [
            "period",
            "n_years",
            "year_from",
            "year_to",
            "month",
            "ghi_mean_j_cm2",
            "ghi_mean_mj_m2",
            "ghi_mean_kwh_m2",
            "dhi_mean_j_cm2",
            "dhi_mean_mj_m2",
            "dhi_mean_kwh_m2",
            "beam_mean_j_cm2",
            "beam_mean_mj_m2",
            "beam_mean_kwh_m2",
            "kd",
        ],
    )


def catalog_years(product: str) -> list[int]:
    name = "catalog_d.html" if product == "dhi" else "catalog_t6.html"
    text = (RAW / name).read_text(encoding="latin-1", errors="replace")
    suffix = "_d.html" if product == "dhi" else "_t6.html"
    years = sorted({int(y) for y in re.findall(rf"{STATION}_(\d{{4}}){re.escape(suffix)}", text)})
    return years


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    CSV_DIR.mkdir(parents=True, exist_ok=True)

    catalogs = {
        "dhi": f"{BASE}/d/russia/{STATION}/{STATION}.html",
        "ghi": f"{BASE}/t6/russia/{STATION}/{STATION}.html",
    }
    fetch(catalogs["dhi"], RAW / "catalog_d.html")
    fetch(catalogs["ghi"], RAW / "catalog_t6.html")

    jobs: list[tuple[str, int]] = []
    for product in ("dhi", "ghi"):
        years = catalog_years(product)
        print(f"{product}: {len(years)} years ({years[0]}–{years[-1]})", flush=True)
        jobs.extend((product, y) for y in years)

    daily_all: list[dict] = []
    monthly_all: list[dict] = []
    failures: list[str] = []

    for i, (product, year) in enumerate(jobs, 1):
        dest = raw_path(product, year)
        url = year_url(product, year)
        try:
            fetch(url, dest)
            text = dest.read_text(encoding="latin-1", errors="replace")
            daily, monthly = parse_year_html(text, year, product)
            if not daily:
                raise ValueError("parsed 0 daily rows")
            daily_all.extend(daily)
            monthly_all.extend(monthly)
            print(f"[{i:03d}/{len(jobs)}] {product} {year}: {len(daily)} days", flush=True)
        except Exception as err:  # noqa: BLE001 — keep going, report at the end
            failures.append(f"{product} {year}: {err}")
            print(f"[{i:03d}/{len(jobs)}] FAIL {product} {year}: {err}", flush=True)
        time.sleep(0.15)

    for row in daily_all:
        row["value_mj_m2"] = jcm2_to_mj(row["value_j_cm2"])
        row["value_kwh_m2"] = jcm2_to_kwh(row["value_j_cm2"])
    for row in monthly_all:
        row["sum_mj_m2"] = jcm2_to_mj(row["sum_j_cm2"])
        row["sum_kwh_m2"] = jcm2_to_kwh(row["sum_j_cm2"])
        row["mean_mj_m2"] = jcm2_to_mj(row["mean_j_cm2"])
        row["mean_kwh_m2"] = jcm2_to_kwh(row["mean_j_cm2"])

    daily_fields = [
        "date",
        "year",
        "month",
        "day",
        "product",
        "value_j_cm2",
        "value_mj_m2",
        "value_kwh_m2",
        "flag",
    ]
    monthly_fields = [
        "year",
        "month",
        "product",
        "sum_j_cm2",
        "sum_mj_m2",
        "sum_kwh_m2",
        "mean_j_cm2",
        "mean_mj_m2",
        "mean_kwh_m2",
        "flag",
    ]
    write_csv(CSV_DIR / "daily.csv", daily_all, daily_fields)
    write_csv(CSV_DIR / "daily_ghi.csv", [r for r in daily_all if r["product"] == "ghi"], daily_fields)
    write_csv(CSV_DIR / "daily_dhi.csv", [r for r in daily_all if r["product"] == "dhi"], daily_fields)
    write_csv(CSV_DIR / "monthly.csv", monthly_all, monthly_fields)

    ghi_by_date = {r["date"]: r for r in daily_all if r["product"] == "ghi"}
    dhi_by_date = {r["date"]: r for r in daily_all if r["product"] == "dhi"}
    merged: list[dict] = []
    for date in sorted(set(ghi_by_date) & set(dhi_by_date)):
        g = ghi_by_date[date]
        d = dhi_by_date[date]
        beam = ""
        if g["value_j_cm2"] != "" and d["value_j_cm2"] != "":
            beam = str(int(g["value_j_cm2"]) - int(d["value_j_cm2"]))
        merged.append(
            {
                "date": date,
                "year": g["year"],
                "month": g["month"],
                "day": g["day"],
                "ghi_j_cm2": g["value_j_cm2"],
                "dhi_j_cm2": d["value_j_cm2"],
                "beam_j_cm2": beam,
                "ghi_mj_m2": g["value_mj_m2"],
                "dhi_mj_m2": d["value_mj_m2"],
                "beam_mj_m2": jcm2_to_mj(beam),
                "ghi_kwh_m2": g["value_kwh_m2"],
                "dhi_kwh_m2": d["value_kwh_m2"],
                "beam_kwh_m2": jcm2_to_kwh(beam),
                "ghi_flag": g["flag"],
                "dhi_flag": d["flag"],
                "kd": (
                    f"{int(d['value_j_cm2']) / int(g['value_j_cm2']):.4f}"
                    if g["value_j_cm2"] not in {"", "0"} and d["value_j_cm2"] != ""
                    else ""
                ),
            }
        )
    write_csv(
        CSV_DIR / "daily_ghi_dhi.csv",
        merged,
        [
            "date",
            "year",
            "month",
            "day",
            "ghi_j_cm2",
            "dhi_j_cm2",
            "beam_j_cm2",
            "ghi_mj_m2",
            "dhi_mj_m2",
            "beam_mj_m2",
            "ghi_kwh_m2",
            "dhi_kwh_m2",
            "beam_kwh_m2",
            "ghi_flag",
            "dhi_flag",
            "kd",
        ],
    )

    annual: list[dict] = []
    years = sorted({r["year"] for r in monthly_all})
    monthly_index = {(r["year"], r["month"], r["product"]): r for r in monthly_all}
    daily_index: dict[tuple[int, str], list[dict]] = {}
    for row in daily_all:
        daily_index.setdefault((row["year"], row["product"]), []).append(row)

    for year in years:
        rec: dict = {"year": year, "station": "MOSCOW UNIV.", "lat": "55.70", "lon": "37.50"}
        for product, prefix in (("ghi", "ghi"), ("dhi", "dhi")):
            months = [monthly_index.get((year, m, product)) for m in range(1, 13)]
            present = [m for m in months if m and m["sum_j_cm2"] != ""]
            rec[f"{prefix}_months"] = len(present)
            if len(present) == 12:
                total = sum(int(m["sum_j_cm2"]) for m in present)
                rec[f"{prefix}_year_j_cm2"] = total
                rec[f"{prefix}_year_mj_m2"] = f"{total / 100:.2f}"
                rec[f"{prefix}_year_kwh_m2"] = f"{total / 360:.1f}"
            else:
                rec[f"{prefix}_year_j_cm2"] = ""
                rec[f"{prefix}_year_mj_m2"] = ""
                rec[f"{prefix}_year_kwh_m2"] = ""
            days = daily_index.get((year, product), [])
            rec[f"{prefix}_days"] = sum(1 for d in days if d["value_j_cm2"] != "")
            rec[f"{prefix}_missing_days"] = sum(1 for d in days if d["value_j_cm2"] == "")
            flags = {d["flag"] for d in days if d["flag"] not in {"", "0"}}
            rec[f"{prefix}_other_flags"] = ";".join(sorted(flags))
        if rec["ghi_year_j_cm2"] != "" and rec["dhi_year_j_cm2"] != "":
            beam = int(rec["ghi_year_j_cm2"]) - int(rec["dhi_year_j_cm2"])
            rec["beam_year_j_cm2"] = beam
            rec["beam_year_mj_m2"] = f"{beam / 100:.2f}"
            rec["beam_year_kwh_m2"] = f"{beam / 360:.1f}"
            rec["kd_year"] = f"{int(rec['dhi_year_j_cm2']) / int(rec['ghi_year_j_cm2']):.3f}"
        else:
            rec["beam_year_j_cm2"] = ""
            rec["beam_year_mj_m2"] = ""
            rec["beam_year_kwh_m2"] = ""
            rec["kd_year"] = ""
        annual.append(rec)

    write_csv(
        CSV_DIR / "annual.csv",
        annual,
        [
            "year",
            "station",
            "lat",
            "lon",
            "ghi_months",
            "ghi_days",
            "ghi_missing_days",
            "ghi_year_j_cm2",
            "ghi_year_mj_m2",
            "ghi_year_kwh_m2",
            "ghi_other_flags",
            "dhi_months",
            "dhi_days",
            "dhi_missing_days",
            "dhi_year_j_cm2",
            "dhi_year_mj_m2",
            "dhi_year_kwh_m2",
            "dhi_other_flags",
            "beam_year_j_cm2",
            "beam_year_mj_m2",
            "beam_year_kwh_m2",
            "kd_year",
        ],
    )

    write_climatology(monthly_all, annual)

    complete_ghi = [r for r in annual if r["ghi_year_kwh_m2"] != ""]
    complete_dhi = [r for r in annual if r["dhi_year_kwh_m2"] != ""]
    complete_both = [r for r in annual if r["kd_year"] != ""]
    print()
    print(f"daily rows: {len(daily_all)}")
    print(f"merged GHI+DHI days: {len(merged)}")
    print(f"complete GHI years: {len(complete_ghi)}")
    print(f"complete DHI years: {len(complete_dhi)}")
    print(f"complete overlap years: {len(complete_both)}")
    if complete_ghi:
        ghi_vals = [float(r["ghi_year_kwh_m2"]) for r in complete_ghi]
        print(
            f"GHI annual kWh/m²: min {min(ghi_vals):.0f}, "
            f"mean {sum(ghi_vals)/len(ghi_vals):.0f}, max {max(ghi_vals):.0f}"
        )
    if complete_both:
        kd_vals = [float(r["kd_year"]) for r in complete_both]
        print(f"annual kd=DHI/GHI: min {min(kd_vals):.3f}, mean {sum(kd_vals)/len(kd_vals):.3f}, max {max(kd_vals):.3f}")
    if failures:
        print("FAILURES:")
        for item in failures:
            print(" ", item)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
