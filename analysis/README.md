# Analysis layer (Lipetsk radiation study)

Python QC / modeling pipeline. Does **not** modify product C# calculation logic.

## Setup

Prefer a local venv (no GUI required):

```bat
py -3 -m venv analysis\.venv
analysis\.venv\Scripts\python.exe -m pip install -r analysis\requirements.txt
```

If `pip` cannot reach PyPI (TLS/proxy errors on this machine), download wheels manually into `analysis\.wheels` and install with:

```bat
analysis\.venv\Scripts\python.exe -m pip install --no-index --find-links analysis\.wheels -r analysis\requirements.txt
```

`analysis/.venv/` and `analysis/.wheels/` are gitignored.

## Config

- `analysis/configs/main.yaml` — sites, paths, period, QC, clear-sky, year splits
- Primary series: `Data/spes_meteo.sqlite` (gitignored; must exist locally)
- Outputs: `data/processed/`, `tables/`, `figures/`, `reports/`

## Run

From repo root:

```bat
analysis\.venv\Scripts\python.exe analysis\src\run_pipeline.py
```

Stages: `export,qc,models` (default). Models only:

```bat
analysis\.venv\Scripts\python.exe analysis\src\run_models.py
```

Tests:

```bat
analysis\.venv\Scripts\python.exe -m unittest discover -s analysis\tests -v
```

## Units (confirmed)

Observed irradiance is **W/m²**. SQLite column `q_mjm2` is a misnomer; analysis column `radiation_wm2` (= `q_mjm2`). Do not convert from MJ/m².

Handbook tables: product comments use **Вт·ч/м²**; hourly Wh/m² over 1 h ≡ mean W/m² for comparison.

## Clear-sky / baselines

- Solar position + Ineichen–Perez (2002) horizontal `G_cs` (`analysis/src/solar_geometry.py`). `pvlib` preferred but not required.
- Handbook `B_ref`: lat interpolation + DailyTotal shaped by handbook sun altitude (`handbook_bref.py`).
- M0: `G_hat = B_ref`; M1: monthly scale on train year 2023 (`models_m0_m1.py`).

## Outputs

| Path | Contents |
|------|----------|
| `data/processed/merged_halfhourly.parquet` | Half-hourly grid + QC (gitignored) |
| `data/processed/features_m0m1.parquet` | Features + predictions (gitignored) |
| `tables/qc_*.csv`, `tables/m0m1_*.csv` | Summaries (committed) |
| `figures/qc_*.png`, `figures/m0m1_*.png` | Figures |
| `reports/qc_report.md`, `reports/model_report_m0_m1.md` | Reports |

Rows are **not** dropped for QC failures; flags are columns.
