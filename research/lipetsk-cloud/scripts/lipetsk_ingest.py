#!/usr/bin/env python3
"""Получасовой ряд Конь-Колодезя → сутки H, Kt, C-день, МГУ-Рейндл.

Не заполняет пропуски нулями. Сутки годны для энергии, только если среди
слотов с высотой Солнца > 5° доля дыр ≤ max_missing_fraction (по умолчанию 0.2).

Ищет по очереди:
  1) data/lipetsk/raw/spes_meteo.sqlite
  2) LIPETSK_SQLITE
  3) CSV с колонками obs_time,q_mjm2  (q_mjm2 = Вт/м², имя врёт)
  4) data/lipetsk/qc/merged_halfhourly_sample.csv — только проверка логики

Метки sqlite и сырого минутного CSV (колонка «Время») — шкала файла логгера,
переводятся в MSK; CSV с колонкой obs_time считаются уже в MSK.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from msu_kd import h0_mj, msu_reindl, sin_alpha_noon  # noqa: E402
from lipetsk_time import pyranometer_to_msk  # noqa: E402

LAT = 52.135409
LON = 39.163510
MSK_OFFSET_H = 3.0
DT_H = 0.5
WM2_HALFHOUR_TO_MJ = DT_H * 3600.0 / 1_000_000.0  # 0.0018
MIN_ELEV_DEG = 5.0
MAX_MISSING_FRAC = 0.2
CADENCE = timedelta(minutes=30)


def solar_elevation_deg(dt: datetime, lat_deg: float, lon_deg: float) -> float:
    """Приближённая высота Солнца; стенка Europe/Moscow как UTC+3 без DST."""
    n = dt.timetuple().tm_yday
    hour_utc = (dt.hour + dt.minute / 60.0 + dt.second / 3600.0) - MSK_OFFSET_H
    gamma = 2.0 * math.pi / 365.0 * (n - 1.0 + (hour_utc - 12.0) / 24.0)
    decl = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2.0 * gamma)
        + 0.000907 * math.sin(2.0 * gamma)
        - 0.002697 * math.cos(3.0 * gamma)
        + 0.00148 * math.sin(3.0 * gamma)
    )
    eqtime = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2.0 * gamma)
        - 0.040849 * math.sin(2.0 * gamma)
    )
    time_offset = eqtime + 4.0 * lon_deg - 60.0 * MSK_OFFSET_H
    tst = dt.hour * 60.0 + dt.minute + dt.second / 60.0 + time_offset
    ha = math.radians(tst / 4.0 - 180.0)
    lat = math.radians(lat_deg)
    cos_zen = math.sin(lat) * math.sin(decl) + math.cos(lat) * math.cos(decl) * math.cos(ha)
    cos_zen = max(-1.0, min(1.0, cos_zen))
    return math.degrees(math.asin(cos_zen))


def parse_ts(s: str) -> datetime:
    s = s.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"не разобрать время: {s!r}")


def load_sqlite(path: Path) -> list[dict]:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    rows = list(
        con.execute(
            "SELECT obs_time, q_mjm2, t_deg_c, ngo_m, ssd_s "
            "FROM meteo_observation ORDER BY obs_time"
        )
    )
    con.close()
    out = []
    for r in rows:
        out.append(
            {
                "ts": pyranometer_to_msk(parse_ts(r["obs_time"])),
                "q": r["q_mjm2"],
                "t": r["t_deg_c"],
                "ngo": r["ngo_m"],
                "ssd": r["ssd_s"],
            }
        )
    return out


def load_csv(path: Path) -> list[dict]:
    text = path.read_bytes()
    for enc in ("utf-8", "cp1251"):
        try:
            lines = text.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise RuntimeError(path)
    sample = lines[:4000]
    dialect = csv.Sniffer().sniff(sample, delimiters=",;")
    f = csv.DictReader(lines.splitlines(), dialect=dialect)
    rows = []
    for rec in f:
        keys = {k.strip(): k for k in rec}
        tkey = keys.get("obs_time") or keys.get("Время")
        qkey = (
            keys.get("q_wm2")
            or keys.get("q_mjm2")
            or keys.get("Q, Вт/м2")
            or keys.get("Q, Вт/м²")
        )
        if not tkey:
            continue
        ts_s = (rec.get(tkey) or "").strip()
        if not ts_s:
            continue
        q_s = (rec.get(qkey) or "").strip() if qkey else ""
        t_s = (rec.get(keys.get("t_deg_c") or keys.get("T, °C") or "") or "").strip()
        ngo_s = (rec.get(keys.get("ngo_m") or "") or "").strip()
        ssd_s = (rec.get(keys.get("ssd_s") or keys.get("SSD, c") or "") or "").strip()

        def num(x: str):
            if x in ("", "/", "None"):
                return None
            return float(x.replace(",", "."))

        ts = parse_ts(ts_s)
        if tkey.strip() == "Время":
            ts = pyranometer_to_msk(ts)
        rows.append(
            {
                "ts": ts,
                "q": num(q_s),
                "t": num(t_s) if t_s else None,
                "ngo": num(ngo_s) if ngo_s else None,
                "ssd": num(ssd_s) if ssd_s else None,
            }
        )
    return rows


def floor_slot(dt: datetime) -> datetime:
    minute = 0 if dt.minute < 30 else 30
    return dt.replace(minute=minute, second=0, microsecond=0)


def aggregate(obs: list[dict], max_missing: float) -> tuple[list[dict], list[dict]]:
    by_ts = {}
    for r in obs:
        by_ts[floor_slot(r["ts"])] = r
    if not by_ts:
        return [], []
    start = min(by_ts).replace(hour=0, minute=0, second=0, microsecond=0)
    end_day = max(by_ts).replace(hour=0, minute=0, second=0, microsecond=0)
    grid_end = end_day + timedelta(days=1) - CADENCE

    days: dict = defaultdict(
        lambda: {
            "n_slots": 0,
            "n_present_q": 0,
            "n_daylight": 0,
            "n_daylight_q": 0,
            "sum_q_mj": 0.0,
            "sum_ssd_s": 0.0,
            "n_ssd": 0,
            "sum_t": 0.0,
            "n_t": 0,
            "sum_ngo": 0.0,
            "n_ngo": 0,
            "n_night_q_pos": 0,
        }
    )
    t = start
    while t <= grid_end:
        d = t.date()
        elev = solar_elevation_deg(t, LAT, LON)
        bucket = days[d]
        bucket["n_slots"] += 1
        daylight = elev > MIN_ELEV_DEG
        if daylight:
            bucket["n_daylight"] += 1
        rec = by_ts.get(t)
        q = rec["q"] if rec else None
        if rec and q is not None:
            bucket["n_present_q"] += 1
            if daylight:
                bucket["n_daylight_q"] += 1
            bucket["sum_q_mj"] += q * WM2_HALFHOUR_TO_MJ
            if not daylight and q > 0:
                bucket["n_night_q_pos"] += 1
            if rec["ssd"] is not None:
                bucket["sum_ssd_s"] += rec["ssd"]
                bucket["n_ssd"] += 1
            if rec["t"] is not None:
                bucket["sum_t"] += rec["t"]
                bucket["n_t"] += 1
            if rec["ngo"] is not None:
                bucket["sum_ngo"] += rec["ngo"]
                bucket["n_ngo"] += 1
        t += CADENCE

    daily = []
    for d in sorted(days):
        b = days[d]
        miss = (
            1.0 - b["n_daylight_q"] / b["n_daylight"] if b["n_daylight"] else 1.0
        )
        usable = b["n_daylight"] > 0 and miss <= max_missing
        doy = d.timetuple().tm_yday
        h0 = h0_mj(doy, LAT)
        sina = sin_alpha_noon(doy, LAT)
        h = b["sum_q_mj"]
        kt = h / h0 if (usable and h0 > 0) else None
        kd = msu_reindl(kt, sina) if kt is not None else None
        hd = kd * h if kd is not None else None
        bh = (1.0 - kd) * h if kd is not None else None
        daily.append(
            {
                "date": d.isoformat(),
                "year": d.year,
                "month": d.month,
                "n_slots": b["n_slots"],
                "n_present_q": b["n_present_q"],
                "n_daylight": b["n_daylight"],
                "n_daylight_q": b["n_daylight_q"],
                "daylight_missing_frac": f"{miss:.4f}",
                "usable": int(usable),
                "H_obs_mjm2": f"{h:.4f}" if usable else "",
                "H0_mjm2": f"{h0:.4f}",
                "Kt": f"{kt:.4f}" if kt is not None else "",
                "sin_alpha_noon": f"{sina:.4f}",
                "Kd_msu_reindl": f"{kd:.4f}" if kd is not None else "",
                "Hd_mjm2": f"{hd:.4f}" if hd is not None else "",
                "Bh_mjm2": f"{bh:.4f}" if bh is not None else "",
                "ssd_s_sum": f"{b['sum_ssd_s']:.1f}" if b["n_ssd"] else "",
                "t_mean_c": f"{b['sum_t'] / b['n_t']:.2f}" if b["n_t"] else "",
                "ngo_m_mean": f"{b['sum_ngo'] / b['n_ngo']:.1f}" if b["n_ngo"] else "",
                "n_night_q_pos": b["n_night_q_pos"],
                "note": ""
                if usable
                else "incomplete_daylight; H not reported (gaps not zero-filled)",
            }
        )
    return daily, []


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def monthly_from_daily(daily: list[dict], href_csv: Path) -> list[dict]:
    href = {}
    if href_csv.exists():
        with href_csv.open(encoding="utf-8") as f:
            for rec in csv.DictReader(f):
                href[int(rec["month"])] = float(rec["href_cs_52135_mjm2"])
    groups: dict = defaultdict(lambda: {"n": 0, "n_usable": 0, "H": 0.0, "Hd": 0.0, "Bh": 0.0})
    for rec in daily:
        key = (int(rec["year"]), int(rec["month"]))
        g = groups[key]
        g["n"] += 1
        if rec["usable"] == 1 or rec["usable"] == "1":
            g["n_usable"] += 1
            g["H"] += float(rec["H_obs_mjm2"])
            g["Hd"] += float(rec["Hd_mjm2"])
            g["Bh"] += float(rec["Bh_mjm2"])
    out = []
    for year, month in sorted(groups):
        g = groups[(year, month)]
        h_cs = href.get(month)
        # Сумма годных суток ≠ месячная климатология, если месяц дырявый.
        c = (g["H"] / h_cs) if (h_cs and g["n_usable"] == g["n"] and g["n"] > 0) else None
        out.append(
            {
                "year": year,
                "month": month,
                "n_days": g["n"],
                "n_usable_days": g["n_usable"],
                "complete_month": int(g["n_usable"] == g["n"] and g["n"] > 0),
                "H_obs_usable_days_mjm2": f"{g['H']:.3f}" if g["n_usable"] else "",
                "Hd_msu_reindl_mjm2": f"{g['Hd']:.3f}" if g["n_usable"] else "",
                "Bh_msu_reindl_mjm2": f"{g['Bh']:.3f}" if g["n_usable"] else "",
                "href_cs_mjm2": f"{h_cs:.3f}" if h_cs else "",
                "C_Hobs_over_sp131": f"{c:.4f}" if c is not None else "",
                "note": ""
                if c is not None
                else "month incomplete — do not quote C as climatology",
            }
        )
    return out


def resolve_source(cli: str | None) -> tuple[str, Path]:
    if cli:
        p = Path(cli)
        return ("sqlite" if p.suffix.lower() in {".sqlite", ".db"} else "csv", p)
    env = os.environ.get("LIPETSK_SQLITE")
    if env and Path(env).exists():
        return "sqlite", Path(env)
    cand = [
        ROOT / "data" / "lipetsk" / "raw" / "spes_meteo.sqlite",
        Path("/tmp/SPES_Raschet/Data/spes_meteo.sqlite"),
        Path("D:/dev/SPES_Raschet/Data/spes_meteo.sqlite"),
    ]
    for p in cand:
        if p.exists():
            return "sqlite", p
    sample = ROOT / "data" / "lipetsk" / "qc" / "merged_halfhourly_sample.csv"
    return "csv", sample


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=None, help="sqlite или csv")
    ap.add_argument("--max-missing", type=float, default=MAX_MISSING_FRAC)
    args = ap.parse_args()
    kind, path = resolve_source(args.source)
    if not path.exists():
        print(f"нет файла наблюдений: {path}", file=sys.stderr)
        sys.exit(2)
    print(f"source={kind} path={path}")
    obs = load_sqlite(path) if kind == "sqlite" else load_csv(path)
    print(f"rows={len(obs)}")
    daily, _ = aggregate(obs, args.max_missing)
    sample = "sample" in path.name.lower()
    out_dir = ROOT / "data" / "lipetsk" / ("qc" if sample else "csv")
    daily_name = "ingest_sample_daily.csv" if sample else "daily_obs.csv"
    monthly_name = "ingest_sample_monthly.csv" if sample else "monthly_obs.csv"
    write_csv(out_dir / daily_name, daily)
    n_ok = sum(1 for r in daily if str(r["usable"]) == "1")
    print(f"days={len(daily)} usable={n_ok} -> {out_dir / daily_name}")
    href = ROOT / "data" / "lipetsk" / "csv" / "sp131_href_cs.csv"
    monthly = monthly_from_daily(daily, href)
    write_csv(out_dir / monthly_name, monthly)
    for r in daily[:3]:
        print(r["date"], "usable=", r["usable"], r.get("note", ""), "H=", r["H_obs_mjm2"])


if __name__ == "__main__":
    main()
