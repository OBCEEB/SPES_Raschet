"""
Export SQLite meteo observations to a half-hourly series with QC flags.

Usage (from repo root):
  analysis\\.venv\\Scripts\\python.exe analysis/src/export_qc.py
  py -3 analysis/src/run_pipeline.py
"""
from __future__ import annotations

import argparse
import math
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Allow `py -3 analysis/src/export_qc.py` without installing the package.
_SRC = Path(__file__).resolve().parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from config_loader import load_config, resolve_path, REPO_ROOT  # noqa: E402


VALUE_COLS = ["q_mjm2", "t_deg_c", "q_mj", "ngo_m", "ssd_s"]
QC_FLAG_COLS = [
    "qc_missing_row",
    "qc_missing_q",
    "qc_missing_ssd",
    "qc_missing_ngo",
    "qc_missing_t",
    "qc_negative_q",
    "qc_night_suspect",
    "qc_ngo_censored",
    "qc_flatline_q",
]


def _solar_elevation_deg(dt: pd.Timestamp, lat_deg: float, lon_deg: float) -> float:
    """Approximate solar elevation (degrees). Local civil time treated as UTC+3 (MSK)."""
    # Treat timestamps as Europe/Moscow wall time without DST correction (UNKNOWN in data dict).
    msk_offset_h = 3.0
    utc = dt - pd.Timedelta(hours=msk_offset_h)
    n = float(utc.dayofyear)
    hour_utc = utc.hour + utc.minute / 60.0 + utc.second / 3600.0
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
    time_offset = eqtime + 4.0 * lon_deg - 60.0 * msk_offset_h
    tst = (
        dt.hour * 60.0
        + dt.minute
        + dt.second / 60.0
        + time_offset
    )
    ha = math.radians(tst / 4.0 - 180.0)
    lat = math.radians(lat_deg)
    cos_zen = math.sin(lat) * math.sin(decl) + math.cos(lat) * math.cos(decl) * math.cos(ha)
    cos_zen = max(-1.0, min(1.0, cos_zen))
    return math.degrees(math.asin(cos_zen))


def read_observations(sqlite_path: Path) -> pd.DataFrame:
    if not sqlite_path.is_file():
        raise FileNotFoundError("SQLite not found: {}".format(sqlite_path))
    query = """
        SELECT obs_time, q_mjm2, t_deg_c, q_mj, ngo_m, ssd_s
        FROM meteo_observation
        ORDER BY obs_time
    """
    with sqlite3.connect(str(sqlite_path)) as conn:
        df = pd.read_sql_query(query, conn)
    df["obs_time"] = pd.to_datetime(df["obs_time"], format="%Y-%m-%d %H:%M:%S")
    return df


def build_halfhourly_grid(df: pd.DataFrame, start: Optional[str], end: Optional[str]) -> pd.DataFrame:
    if start:
        t0 = pd.Timestamp(start)
    else:
        t0 = df["obs_time"].min().floor("30min")
    if end:
        t1 = pd.Timestamp(end) + pd.Timedelta(hours=23, minutes=30)
    else:
        t1 = df["obs_time"].max().ceil("30min")
    grid = pd.DataFrame({"obs_time": pd.date_range(t0, t1, freq="30min")})
    merged = grid.merge(df, on="obs_time", how="left")
    return merged


def apply_qc(df: pd.DataFrame, cfg: Dict) -> pd.DataFrame:
    out = df.copy()
    qc = cfg.get("quality_control") or {}
    site = cfg.get("site") or {}
    lat = float(site.get("latitude_deg") or site.get("radiation", {}).get("latitude_deg") or 52.135409)
    lon = float(site.get("longitude_deg") or site.get("radiation", {}).get("longitude_deg") or 39.163510)
    min_elev = float(qc.get("min_solar_elevation_deg", 5))
    flat_h = float(qc.get("flatline_window_hours", 6))
    flat_n = max(2, int(round(flat_h * 60 / 30)))

    out["qc_missing_row"] = out["q_mjm2"].isna() & out["ngo_m"].isna() & out["ssd_s"].isna() & out["t_deg_c"].isna()
    # Also treat any absent observation join as missing row when all value cols null
    out["qc_missing_row"] = out[VALUE_COLS].isna().all(axis=1)

    out["qc_missing_q"] = out["q_mjm2"].isna().astype(np.int8)
    out["qc_missing_ssd"] = out["ssd_s"].isna().astype(np.int8)
    out["qc_missing_ngo"] = out["ngo_m"].isna().astype(np.int8)
    out["qc_missing_t"] = out["t_deg_c"].isna().astype(np.int8)
    out["qc_missing_row"] = out["qc_missing_row"].astype(np.int8)

    out["qc_negative_q"] = ((~out["q_mjm2"].isna()) & (out["q_mjm2"] < 0)).astype(np.int8)

    # NGO ≥9000 already nulled by importer; still flag any residual censored values.
    out["qc_ngo_censored"] = ((~out["ngo_m"].isna()) & (out["ngo_m"] >= 9000)).astype(np.int8)

    elev = out["obs_time"].map(lambda t: _solar_elevation_deg(t, lat, lon))
    out["solar_elevation_deg"] = elev.astype(float)
    night = elev < min_elev
    q_pos = (~out["q_mjm2"].isna()) & (out["q_mjm2"] > 0)
    out["qc_night_suspect"] = (night & q_pos).astype(np.int8)

    # Flatline suspects: runs of identical non-null Q spanning >= flatline window.
    q = out["q_mjm2"]
    same_as_prev = q.notna() & q.eq(q.shift(1))
    # run ids change when value changes or null break
    run_break = (~same_as_prev) | q.isna()
    run_id = run_break.cumsum()
    run_len = out.groupby(run_id)["q_mjm2"].transform("size")
    # Only flag when the constant value is non-null and run is long enough
    out["qc_flatline_q"] = (
        q.notna() & (run_len >= flat_n) & same_as_prev.groupby(run_id).transform("any")
    ).astype(np.int8)
    # Include the first sample of a long flat run as well
    long_run = q.notna() & (run_len >= flat_n)
    out.loc[long_run, "qc_flatline_q"] = 1

    # Null residual censored NGO values for consistency (do not drop rows).
    if out["qc_ngo_censored"].any():
        out.loc[out["qc_ngo_censored"] == 1, "ngo_m"] = np.nan
        out.loc[out["qc_ngo_censored"] == 1, "qc_missing_ngo"] = 1

    return out


def write_table(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8")


def try_write_parquet(df: pd.DataFrame, path: Path) -> Tuple[bool, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(path, index=False)
        return True, str(path)
    except Exception as exc:  # noqa: BLE001 — fallback to CSV is intentional
        csv_path = path.with_suffix(".csv")
        df.to_csv(csv_path, index=False, encoding="utf-8")
        return False, "{} (parquet failed: {}; wrote {})".format(path, exc, csv_path)


def completeness_tables(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    tmp = df.copy()
    tmp["year"] = tmp["obs_time"].dt.year
    tmp["month"] = tmp["obs_time"].dt.month
    tmp["present"] = 1 - tmp["qc_missing_row"]
    tmp["valid_q"] = (
        (tmp["qc_missing_q"] == 0)
        & (tmp["qc_negative_q"] == 0)
    ).astype(int)

    by_ym = (
        tmp.groupby(["year", "month"], as_index=False)
        .agg(
            expected_slots=("obs_time", "size"),
            present_rows=("present", "sum"),
            missing_rows=("qc_missing_row", "sum"),
            valid_q=("valid_q", "sum"),
            night_suspect=("qc_night_suspect", "sum"),
            flatline_q=("qc_flatline_q", "sum"),
            negative_q=("qc_negative_q", "sum"),
            missing_ngo=("qc_missing_ngo", "sum"),
            missing_ssd=("qc_missing_ssd", "sum"),
        )
    )
    by_ym["present_fraction"] = by_ym["present_rows"] / by_ym["expected_slots"]
    by_ym["valid_q_fraction"] = by_ym["valid_q"] / by_ym["expected_slots"]

    by_y = (
        tmp.groupby(["year"], as_index=False)
        .agg(
            expected_slots=("obs_time", "size"),
            present_rows=("present", "sum"),
            missing_rows=("qc_missing_row", "sum"),
            valid_q=("valid_q", "sum"),
        )
    )
    by_y["present_fraction"] = by_y["present_rows"] / by_y["expected_slots"]
    by_y["valid_q_fraction"] = by_y["valid_q"] / by_y["expected_slots"]
    return by_ym, by_y


def reason_counts(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for col in QC_FLAG_COLS:
        rows.append({"flag": col, "count": int(df[col].sum()), "fraction": float(df[col].mean())})
    return pd.DataFrame(rows)


def make_figures(by_ym: pd.DataFrame, figures_dir: Path) -> List[str]:
    figures_dir.mkdir(parents=True, exist_ok=True)
    written: List[str] = []
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # noqa: BLE001
        note = figures_dir / "FIGURES_SKIPPED.txt"
        note.write_text("Plotting unavailable: {}\n".format(exc), encoding="utf-8")
        return [str(note)]

    # Completeness heatmap: year x month present_fraction
    pivot = by_ym.pivot(index="year", columns="month", values="present_fraction")
    for m in range(1, 13):
        if m not in pivot.columns:
            pivot[m] = np.nan
    pivot = pivot.reindex(columns=list(range(1, 13)))

    fig, ax = plt.subplots(figsize=(10, 3.2))
    im = ax.imshow(pivot.values, aspect="auto", vmin=0, vmax=1, cmap="viridis")
    ax.set_xticks(range(12))
    ax.set_xticklabels(list(range(1, 13)))
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels([str(y) for y in pivot.index])
    ax.set_xlabel("Month")
    ax.set_ylabel("Year")
    ax.set_title("Half-hourly completeness (present / expected)")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    path1 = figures_dir / "qc_completeness_heatmap.png"
    fig.tight_layout()
    fig.savefig(path1, dpi=120)
    plt.close(fig)
    written.append(str(path1))

    fig, ax = plt.subplots(figsize=(10, 3.8))
    labels = ["{}-{:02d}".format(int(r.year), int(r.month)) for r in by_ym.itertuples()]
    ax.bar(range(len(by_ym)), by_ym["valid_q_fraction"].values, color="#2a6f97")
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Valid Q fraction")
    ax.set_title("Monthly valid Q fraction (non-missing, non-negative)")
    step = max(1, len(labels) // 12)
    ax.set_xticks(range(0, len(labels), step))
    ax.set_xticklabels([labels[i] for i in range(0, len(labels), step)], rotation=45, ha="right")
    path2 = figures_dir / "qc_monthly_valid_q_fraction.png"
    fig.tight_layout()
    fig.savefig(path2, dpi=120)
    plt.close(fig)
    written.append(str(path2))
    return written


def write_report(
    path: Path,
    cfg: Dict,
    df: pd.DataFrame,
    by_ym: pd.DataFrame,
    by_y: pd.DataFrame,
    reasons: pd.DataFrame,
    parquet_note: str,
    figures: List[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    period = cfg.get("period") or {}
    site = cfg.get("site") or {}
    tmin = df["obs_time"].min()
    tmax = df["obs_time"].max()
    n_grid = len(df)
    n_present = int((df["qc_missing_row"] == 0).sum())
    n_db_like = n_present  # rows with at least one value after left-join fill

    lines = []
    lines.append("# QC report — Lipetsk half-hourly meteo series")
    lines.append("")
    lines.append("Generated by `analysis/src/export_qc.py`.")
    lines.append("")
    lines.append("## Source")
    lines.append("")
    lines.append("| Item | Value |")
    lines.append("|------|--------|")
    lines.append("| SQLite | `{}` |".format(resolve_path(cfg, "sqlite").as_posix()))
    lines.append("| Radiation site | {} ({}, {}) |".format(
        (site.get("radiation") or {}).get("name", "Kon-Kolodez"),
        site.get("latitude_deg"),
        site.get("longitude_deg"),
    ))
    lines.append("| NGO site | {} (ASMG {}) |".format(
        (site.get("ngo") or {}).get("name", "Lipetsk airport"),
        (site.get("ngo") or {}).get("asmg_station_code", "27930"),
    ))
    lines.append("| Config period | {} → {} |".format(period.get("start"), period.get("end")))
    lines.append("| Cadence | {} minutes |".format(period.get("cadence_minutes", 30)))
    lines.append("| Grid period (actual) | {} → {} |".format(tmin, tmax))
    lines.append("| Processed output | {} |".format(parquet_note))
    lines.append("")
    lines.append("## Units note (open question)")
    lines.append("")
    lines.append(
        "Column `q_mjm2` is filled from raw CSV header **`Q, Вт/м2`** (W/m²). "
        "The SQLite/column name suggests MJ/m². Until reconciled, numeric values are treated as "
        "**stored irradiance as parsed from W/m²** — do not convert for modeling without confirmation. "
        "`q_mj` similarly comes from **`Q, мВ`** (millivolts), not megajoules."
    )
    lines.append("")
    lines.append("## Counts")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|------:|")
    lines.append("| Half-hourly grid rows | {:,} |".format(n_grid))
    lines.append("| Present observation rows | {:,} |".format(n_present))
    lines.append("| Missing grid slots | {:,} |".format(n_grid - n_present))
    lines.append("| Present fraction | {:.3f} |".format(n_present / n_grid if n_grid else float("nan")))
    lines.append("")
    lines.append("Importer already drops rows lacking both Q and NGO before analysis; "
                 "missing slots below are gaps in the 30-minute timeline.")
    lines.append("")
    lines.append("## QC flag counts (no rows dropped)")
    lines.append("")
    lines.append("| Flag | Count | Fraction of grid |")
    lines.append("|------|------:|-----------------:|")
    for r in reasons.itertuples():
        lines.append("| `{}` | {:,} | {:.4f} |".format(r.flag, r.count, r.fraction))
    lines.append("")
    lines.append("### Flag definitions")
    lines.append("")
    lines.append("- `qc_missing_row` — no observation joined for the half-hour slot")
    lines.append("- `qc_missing_*` — named variable is null")
    lines.append("- `qc_negative_q` — `q_mjm2` < 0")
    lines.append("- `qc_night_suspect` — `q_mjm2` > 0 while approximate solar elevation "
                 "< `quality_control.min_solar_elevation_deg` ({}°)".format(
                     (cfg.get("quality_control") or {}).get("min_solar_elevation_deg", 5)
                 ))
    lines.append("- `qc_ngo_censored` — residual `ngo_m` ≥ 9000 (importer normally nulls these)")
    lines.append("- `qc_flatline_q` — identical non-null Q lasting ≥ {} h".format(
        (cfg.get("quality_control") or {}).get("flatline_window_hours", 6)
    ))
    lines.append("")
    lines.append("## Completeness by year")
    lines.append("")
    lines.append("| Year | Expected | Present | Present frac | Valid Q | Valid Q frac |")
    lines.append("|-----:|---------:|--------:|-------------:|--------:|-------------:|")
    for r in by_y.itertuples():
        lines.append(
            "| {} | {:,} | {:,} | {:.3f} | {:,} | {:.3f} |".format(
                int(r.year),
                int(r.expected_slots),
                int(r.present_rows),
                r.present_fraction,
                int(r.valid_q),
                r.valid_q_fraction,
            )
        )
    lines.append("")
    lines.append("## Completeness by year-month")
    lines.append("")
    lines.append("See `tables/qc_completeness_year_month.csv`.")
    lines.append("")
    lines.append("| Year | Month | Present frac | Valid Q frac | Missing rows | Night suspect | Flatline Q |")
    lines.append("|-----:|------:|-------------:|-------------:|-------------:|--------------:|-----------:|")
    for r in by_ym.itertuples():
        lines.append(
            "| {} | {:02d} | {:.3f} | {:.3f} | {:,} | {:,} | {:,} |".format(
                int(r.year),
                int(r.month),
                r.present_fraction,
                r.valid_q_fraction,
                int(r.missing_rows),
                int(r.night_suspect),
                int(r.flatline_q),
            )
        )
    lines.append("")
    lines.append("## Figures")
    lines.append("")
    if figures:
        for f in figures:
            rel = Path(f)
            try:
                rel = rel.relative_to(REPO_ROOT)
            except ValueError:
                pass
            lines.append("- `{}`".format(rel.as_posix() if isinstance(rel, Path) else f))
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("## Local large artefacts")
    lines.append("")
    lines.append(
        "`data/processed/*.parquet` is gitignored when large. Regenerate locally with "
        "`analysis\\.venv\\Scripts\\python.exe analysis/src/run_pipeline.py`."
    )
    lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(config_path: Optional[Path] = None) -> Dict[str, object]:
    cfg = load_config(config_path)
    sqlite_path = resolve_path(cfg, "sqlite")
    processed_dir = resolve_path(cfg, "processed_dir")
    tables_dir = resolve_path(cfg, "tables_dir")
    reports_dir = resolve_path(cfg, "reports_dir")
    figures_dir = resolve_path(cfg, "figures_dir")

    period = cfg.get("period") or {}
    raw = read_observations(sqlite_path)
    n_raw = len(raw)
    merged = build_halfhourly_grid(raw, period.get("start"), period.get("end"))
    qc = apply_qc(merged, cfg)

    # Combined processed table (values + flags)
    keep_cols = ["obs_time"] + VALUE_COLS + ["solar_elevation_deg"] + QC_FLAG_COLS
    combined = qc[keep_cols].copy()

    parquet_path = processed_dir / "merged_halfhourly.parquet"
    ok, parquet_note = try_write_parquet(combined, parquet_path)

    flags_only = qc[["obs_time"] + QC_FLAG_COLS].copy()
    flags_path = processed_dir / "qc_flags.parquet"
    ok_f, flags_note = try_write_parquet(flags_only, flags_path)

    # Always write a small CSV sample of the combined series for the repo
    sample = combined.head(48)
    write_table(sample, tables_dir / "merged_halfhourly_sample.csv")

    by_ym, by_y = completeness_tables(qc)
    reasons = reason_counts(qc)
    write_table(by_ym, tables_dir / "qc_completeness_year_month.csv")
    write_table(by_y, tables_dir / "qc_completeness_year.csv")
    write_table(reasons, tables_dir / "qc_flag_counts.csv")

    figures = make_figures(by_ym, figures_dir)
    report_path = reports_dir / "qc_report.md"
    write_report(
        report_path,
        cfg,
        qc,
        by_ym,
        by_y,
        reasons,
        parquet_note + "; flags: " + flags_note,
        figures,
    )

    summary = {
        "n_sqlite_rows": n_raw,
        "n_grid_rows": len(qc),
        "n_present": int((qc["qc_missing_row"] == 0).sum()),
        "t_min": str(qc["obs_time"].min()),
        "t_max": str(qc["obs_time"].max()),
        "parquet_ok": ok and ok_f,
        "report": str(report_path),
        "reasons": reasons.to_dict(orient="records"),
    }
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Export SQLite meteo series + QC flags")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to analysis config YAML (default: analysis/configs/main.yaml)",
    )
    args = parser.parse_args(argv)
    summary = run(args.config)
    print("SQLite rows: {}".format(summary["n_sqlite_rows"]))
    print("Grid rows:   {}".format(summary["n_grid_rows"]))
    print("Present:     {}".format(summary["n_present"]))
    print("Period:      {} -> {}".format(summary["t_min"], summary["t_max"]))
    print("Report:      {}".format(summary["report"]))
    for r in summary["reasons"]:
        print("  {}: {} ({:.4f})".format(r["flag"], r["count"], r["fraction"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
