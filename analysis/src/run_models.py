"""
Build clear-sky + B_ref features, fit M0/M1, write tables/figures/report.

Usage (repo root):
  analysis\\.venv\\Scripts\\python.exe analysis/src/run_models.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

_SRC = Path(__file__).resolve().parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from config_loader import REPO_ROOT, load_config, resolve_path  # noqa: E402
from export_qc import run as run_export_qc, try_write_parquet, write_table  # noqa: E402
from handbook_bref import attach_bref  # noqa: E402
from models_m0_m1 import (  # noqa: E402
    apply_models,
    energy_sums,
    fit_m1_monthly_scales,
    metrics_by_split,
)
from solar_geometry import attach_solar_and_clearsky  # noqa: E402


def _site_coords(cfg: Dict) -> Dict[str, float]:
    site = cfg.get("site") or {}
    rad = site.get("radiation") or {}
    elev = site.get("elevation_m")
    if elev is None:
        elev = rad.get("elevation_m")
    return {
        "lat": float(site.get("latitude_deg") or rad.get("latitude_deg") or 52.135409),
        "lon": float(site.get("longitude_deg") or rad.get("longitude_deg") or 39.163510),
        "elev": elev,
    }


def load_or_build_processed(cfg: Dict) -> pd.DataFrame:
    processed = resolve_path(cfg, "processed_dir") / "merged_halfhourly.parquet"
    if processed.is_file():
        df = pd.read_parquet(processed)
    else:
        run_export_qc(cfg.get("_config_path"))
        df = pd.read_parquet(processed)
    if "radiation_wm2" not in df.columns:
        df["radiation_wm2"] = df["q_mjm2"]
    return df


def make_figures(df: pd.DataFrame, figures_dir: Path) -> List[str]:
    figures_dir.mkdir(parents=True, exist_ok=True)
    written: List[str] = []
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # noqa: BLE001
        note = figures_dir / "MODEL_FIGURES_SKIPPED.txt"
        note.write_text("Plotting unavailable: {}\n".format(exc), encoding="utf-8")
        return [str(note)]

    # Sample days: high mean daytime G_obs with good coverage (avoid extreme k_obs outliers)
    day = df.copy()
    day["date"] = pd.DatetimeIndex(day["obs_time"]).date
    day_mask = (day["is_daytime"] == 1) & day["radiation_wm2"].notna() & day["G_cs"].notna()
    stats = (
        day.loc[day_mask]
        .groupby("date")
        .agg(
            n=("radiation_wm2", "size"),
            mean_k=("k_obs", "mean"),
            mean_g=("radiation_wm2", "mean"),
        )
        .reset_index()
    )
    stats = stats[(stats["n"] >= 12) & (stats["mean_k"].between(0.3, 1.2))]
    stats = stats.sort_values("mean_g", ascending=False)
    sample_dates = list(stats["date"].head(3))
    if len(sample_dates) < 3:
        fallback = (
            day.loc[day_mask]
            .groupby("date")
            .agg(n=("radiation_wm2", "size"), mean_g=("radiation_wm2", "mean"))
            .reset_index()
        )
        fallback = fallback[fallback["n"] >= 10].sort_values("mean_g", ascending=False)
        for d in fallback["date"]:
            if d not in sample_dates:
                sample_dates.append(d)
            if len(sample_dates) >= 3:
                break

    if sample_dates:
        fig, axes = plt.subplots(len(sample_dates), 1, figsize=(10, 3.2 * len(sample_dates)), sharex=False)
        if len(sample_dates) == 1:
            axes = [axes]
        for ax, d in zip(axes, sample_dates):
            sub = day[day["date"] == d].sort_values("obs_time")
            ax.plot(sub["obs_time"], sub["radiation_wm2"], label="G_obs", color="#1d3557", lw=1.4)
            ax.plot(sub["obs_time"], sub["G_cs"], label="G_cs", color="#e76f51", lw=1.2)
            ax.plot(sub["obs_time"], sub["B_ref"], label="B_ref", color="#2a9d8f", lw=1.0, ls="--")
            ax.set_ylabel("W/m²")
            ax.set_title("Sample day {}".format(d))
            ax.legend(loc="upper right", fontsize=8)
            ax.grid(True, alpha=0.3)
        fig.tight_layout()
        p = figures_dir / "m0m1_gobs_gcs_sample_days.png"
        fig.savefig(p, dpi=120)
        plt.close(fig)
        written.append(str(p))

    # k_obs histogram (daytime valid)
    fig, ax = plt.subplots(figsize=(7, 4))
    k = df.loc[(df["is_daytime"] == 1) & df["k_obs"].notna(), "k_obs"]
    ax.hist(k.clip(0, 1.5), bins=40, color="#457b9d", edgecolor="white")
    ax.set_xlabel("k_obs = G_obs / G_cs (clipped 0–1.5 for display)")
    ax.set_ylabel("Count")
    ax.set_title("Clear-sky index distribution (daytime)")
    fig.tight_layout()
    p = figures_dir / "m0m1_k_obs_hist.png"
    fig.savefig(p, dpi=120)
    plt.close(fig)
    written.append(str(p))

    # Scatter M0 / M1 on test daytime
    test = df[(df["split"] == "test") & (df["is_daytime"] == 1) & df["radiation_wm2"].notna()]
    if len(test):
        fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))
        for ax, col, title in zip(
            axes, ["G_hat_M0", "G_hat_M1"], ["M0: B_ref", "M1: c_month × B_ref"]
        ):
            ax.scatter(
                test["radiation_wm2"],
                test[col],
                s=6,
                alpha=0.25,
                color="#1d3557",
                edgecolors="none",
            )
            lim = max(test["radiation_wm2"].max(), test[col].max(), 1.0)
            ax.plot([0, lim], [0, lim], color="#e63946", lw=1)
            ax.set_xlabel("G_obs (W/m²)")
            ax.set_ylabel("G_hat (W/m²)")
            ax.set_title(title + " (test 2025)")
            ax.set_aspect("equal", adjustable="box")
            ax.grid(True, alpha=0.3)
        fig.tight_layout()
        p = figures_dir / "m0m1_scatter_test.png"
        fig.savefig(p, dpi=120)
        plt.close(fig)
        written.append(str(p))

    # Monthly error on val+test
    monthly = energy_sums(df, ["G_hat_M0", "G_hat_M1"], freq="monthly")
    monthly = monthly[monthly["split"].isin(["val", "test"])]
    if len(monthly):
        monthly["ym"] = monthly.apply(
            lambda r: "{}-{:02d}".format(int(r["year"]), int(r["month"])), axis=1
        )
        monthly["err_M0"] = monthly["G_hat_M0_Wh"] - monthly["radiation_wm2_Wh"]
        monthly["err_M1"] = monthly["G_hat_M1_Wh"] - monthly["radiation_wm2_Wh"]
        fig, ax = plt.subplots(figsize=(10, 4))
        x = np.arange(len(monthly))
        ax.bar(x - 0.2, monthly["err_M0"], width=0.4, label="M0 error", color="#e76f51")
        ax.bar(x + 0.2, monthly["err_M1"], width=0.4, label="M1 error", color="#2a9d8f")
        ax.axhline(0, color="black", lw=0.8)
        ax.set_ylabel("Monthly energy error (W·h/m²)")
        ax.set_title("Monthly daytime energy error (val+test; present slots only)")
        step = max(1, len(monthly) // 10)
        ax.set_xticks(x[::step])
        ax.set_xticklabels(monthly["ym"].iloc[::step], rotation=45, ha="right")
        ax.legend()
        fig.tight_layout()
        p = figures_dir / "m0m1_monthly_energy_error.png"
        fig.savefig(p, dpi=120)
        plt.close(fig)
        written.append(str(p))

    return written


def write_model_report(
    path: Path,
    cfg: Dict,
    metrics: pd.DataFrame,
    scales: Dict[int, float],
    figures: List[str],
    n_rows: int,
    notes: Dict[str, object],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    site = _site_coords(cfg)
    cs = (cfg.get("clear_sky") or {})
    val = (cfg.get("validation") or {})
    lines = []
    lines.append("# Model report — M0 / M1 (horizontal irradiance)")
    lines.append("")
    lines.append("Generated by `analysis/src/run_models.py`.")
    lines.append("")
    lines.append("## Site and units")
    lines.append("")
    lines.append("| Item | Value |")
    lines.append("|------|--------|")
    lines.append("| Radiation site | Kon’-Kolodez’ ({}, {}) |".format(site["lat"], site["lon"]))
    lines.append("| Observed irradiance | **W/m²** (raw CSV `Q, Вт/м2`; SQLite column `q_mjm2` is a misnomer) |")
    lines.append("| Analysis column | `radiation_wm2` (= `q_mjm2`) |")
    lines.append("| Cadence | 30 min; energy Wh/m² = W/m² × 0.5 h |")
    lines.append("| Elevation used for clear-sky | {} m (config null → default) |".format(notes.get("elevation_m_used")))
    lines.append("")
    lines.append("## Clear-sky model")
    lines.append("")
    lines.append("- **Model:** Ineichen–Perez (2002) horizontal GHI (`G_cs`).")
    lines.append("- **pvlib:** preferred, but not installable offline/online here (PyPI TLS/proxy failure); formulas match the usual `pvlib.clearsky.ineichen` implementation.")
    lines.append("- **Linke turbidity:** {} (config; site TL UNKNOWN).".format(cs.get("linke_turbidity", 3.0)))
    lines.append("- **Daytime:** solar elevation ≥ {}°; `k_obs = G_obs/G_cs` only when `G_cs` ≥ {} W/m²; night → `G_cs=0`, `k_obs` null.".format(
        (cfg.get("quality_control") or {}).get("min_solar_elevation_deg", 5),
        cs.get("g_cs_min_wm2", 5),
    ))
    lines.append("")
    lines.append("## Handbook baseline `B_ref`")
    lines.append("")
    lines.append("- C# UI not callable without WinForms; **Python reimplements** `MathTools.Interpolate` + table load.")
    lines.append("- Horizontal series: interpolate `DailyTotalData.csv` (Вт·ч/м² per code comments) at site lat, then distribute across hours with handbook `SunPosition_Altitude` weights `max(sin(alt),0)`.")
    lines.append("- Conversion: hourly Wh/m² over 1 h ⇒ mean W/m² of equal magnitude; half-hours inherit that mean.")
    lines.append("- **Limits:** climatological (no month/DOY in tables); Table 1 is façade-only — not used as horizontal GHI. UI labels DailyTotal as МДж/м² but analysis follows code comments (Вт·ч/м²). Interpolated daily total at site: **{:.2f}** W·h/m² (~0.33 kWh/m²/day).".format(
        float(notes.get("bref_daily_total_wh_m2") or 0)
    ))
    lines.append("- **Magnitude caveat:** that daily total is far below observed daytime energy (summer days often several kWh/m²), so raw M0 systematically under-predicts; M1 `c_month` (often ≫1 in summer) absorbs the scale mismatch. Possible handbook unit/label inconsistency remains open; we did not invent a rescaling beyond code comments.")
    lines.append("- Method tag: `daily_total_x_handbook_sin_altitude`.")
    lines.append("- **Timezone caveat:** timestamps treated as Europe/Moscow UTC+3 fixed; some high-`k_obs` mornings may indicate clock/offset issues (UNKNOWN).")
    lines.append("")
    lines.append("## Models")
    lines.append("")
    lines.append("| Model | Definition |")
    lines.append("|-------|------------|")
    lines.append("| M0 | `G_hat = B_ref` |")
    lines.append("| M1 | `G_hat = c_month(m) * B_ref` with `c_month` from train years only |")
    lines.append("")
    lines.append("Year split (only years with data): train {}, val {}, test {}.".format(
        val.get("train_years", [2023]),
        val.get("val_years", [2024]),
        val.get("test_years", [2025]),
    ))
    lines.append("")
    lines.append("### Monthly scales (M1, train)")
    lines.append("")
    lines.append("| Month | c_month |")
    lines.append("|------:|--------:|")
    for m in range(1, 13):
        lines.append("| {} | {:.4f} |".format(m, float(scales.get(m, 1.0))))
    lines.append("")
    lines.append("## Metrics (daytime valid hours)")
    lines.append("")
    lines.append("Valid = daytime, non-null `radiation_wm2`, non-negative Q, `B_ref > 0`.")
    lines.append("")
    lines.append("| Model | Split | n | MAE | RMSE | MBE | nRMSE | mean G_obs |")
    lines.append("|-------|-------|--:|----:|-----:|----:|------:|-----------:|")
    for r in metrics.itertuples():
        lines.append(
            "| {} | {} | {:,} | {:.2f} | {:.2f} | {:.2f} | {:.3f} | {:.2f} |".format(
                r.model.replace("G_hat_", ""),
                r.split,
                int(r.n),
                r.MAE,
                r.RMSE,
                r.MBE,
                r.nRMSE,
                r.mean_obs,
            )
        )
    lines.append("")
    lines.append("Units: MAE/RMSE/MBE in W/m²; nRMSE = RMSE / mean(G_obs).")
    lines.append("")
    lines.append("Daily/monthly energy tables: `tables/m0m1_energy_daily.csv`, `tables/m0m1_energy_monthly.csv` (W·h/m² over present daytime slots).")
    lines.append("")
    lines.append("## Figures")
    lines.append("")
    for f in figures:
        rel = Path(f)
        try:
            rel = rel.relative_to(REPO_ROOT)
        except ValueError:
            pass
        lines.append("- `{}`".format(rel.as_posix() if isinstance(rel, Path) else f))
    lines.append("")
    lines.append("## Rows")
    lines.append("")
    lines.append("Feature table rows: {:,}.".format(n_rows))
    lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(config_path: Optional[Path] = None) -> Dict[str, object]:
    cfg = load_config(config_path)
    coords = _site_coords(cfg)
    qc = cfg.get("quality_control") or {}
    cs = cfg.get("clear_sky") or {}
    val = cfg.get("validation") or {}
    train_years = [int(y) for y in (val.get("train_years") or [2023])]
    val_years = [int(y) for y in (val.get("val_years") or [2024])]
    test_years = [int(y) for y in (val.get("test_years") or [2025])]

    df = load_or_build_processed(cfg)
    df = attach_solar_and_clearsky(
        df,
        latitude_deg=coords["lat"],
        longitude_deg=coords["lon"],
        elevation_m=coords["elev"],
        linke_turbidity=float(cs.get("linke_turbidity", 3.0)),
        min_solar_elevation_deg=float(qc.get("min_solar_elevation_deg", 5)),
        g_cs_min_wm2=float(cs.get("g_cs_min_wm2", 5)),
    )
    handbook_dir = resolve_path(cfg, "handbook_dir")
    df = attach_bref(df, handbook_dir, coords["lat"])

    scales = fit_m1_monthly_scales(df, train_years=train_years)
    df = apply_models(df, scales)
    # re-assign split with config years
    from models_m0_m1 import assign_split

    df["split"] = assign_split(df["obs_time"], train_years, val_years, test_years)

    metrics = pd.concat(
        [
            metrics_by_split(df, "G_hat_M0"),
            metrics_by_split(df, "G_hat_M1"),
        ],
        ignore_index=True,
    )

    tables_dir = resolve_path(cfg, "tables_dir")
    figures_dir = resolve_path(cfg, "figures_dir")
    reports_dir = resolve_path(cfg, "reports_dir")
    processed_dir = resolve_path(cfg, "processed_dir")

    write_table(metrics, tables_dir / "m0m1_metrics.csv")
    scales_df = pd.DataFrame({"month": list(range(1, 13)), "c_month": [scales[m] for m in range(1, 13)]})
    write_table(scales_df, tables_dir / "m0m1_monthly_scales.csv")
    daily = energy_sums(df, ["G_hat_M0", "G_hat_M1", "B_ref", "G_cs"], freq="daily")
    monthly = energy_sums(df, ["G_hat_M0", "G_hat_M1", "B_ref", "G_cs"], freq="monthly")
    write_table(daily, tables_dir / "m0m1_energy_daily.csv")
    write_table(monthly, tables_dir / "m0m1_energy_monthly.csv")

    # Compact feature sample for repo
    sample_cols = [
        "obs_time",
        "radiation_wm2",
        "q_mjm2",
        "solar_elevation_deg",
        "G_cs",
        "k_obs",
        "B_ref",
        "G_hat_M0",
        "G_hat_M1",
        "c_month",
        "split",
        "is_daytime",
    ]
    sample_cols = [c for c in sample_cols if c in df.columns]
    write_table(df[sample_cols].head(96), tables_dir / "m0m1_features_sample.csv")

    try_write_parquet(df, processed_dir / "features_m0m1.parquet")

    figures = make_figures(df, figures_dir)
    notes = {
        "elevation_m_used": float(df["elevation_m_used"].iloc[0]) if len(df) else None,
        "bref_daily_total_wh_m2": float(df["B_ref_daily_total_wh_m2"].iloc[0]) if len(df) else None,
    }
    report_path = reports_dir / "model_report_m0_m1.md"
    write_model_report(report_path, cfg, metrics, scales, figures, len(df), notes)

    return {
        "report": str(report_path),
        "n_rows": len(df),
        "metrics": metrics.to_dict(orient="records"),
        "scales": scales,
        "figures": figures,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run clear-sky + M0/M1 baselines")
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args(argv)
    summary = run(args.config)
    print("Report:", summary["report"])
    print("Rows:", summary["n_rows"])
    for r in summary["metrics"]:
        if r["split"] in ("train", "val", "test"):
            print(
                "  {} {}: MAE={:.2f} RMSE={:.2f} MBE={:.2f} nRMSE={:.3f} n={}".format(
                    r["model"], r["split"], r["MAE"], r["RMSE"], r["MBE"], r["nRMSE"], r["n"]
                )
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
