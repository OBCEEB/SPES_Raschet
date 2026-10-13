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

- `analysis/configs/main.yaml` — sites, paths, period, QC thresholds, model placeholders
- Primary series: `Data/spes_meteo.sqlite` (gitignored; must exist locally)
- Outputs: `data/processed/`, `tables/`, `figures/`, `reports/`

## Run (export + QC)

From repo root:

```bat
analysis\.venv\Scripts\python.exe analysis\src\run_pipeline.py
```

Equivalent:

```bat
analysis\.venv\Scripts\python.exe analysis\src\export_qc.py
```

Or, if dependencies are available for system `py -3`:

```bat
py -3 analysis\src\run_pipeline.py
```

## Outputs

| Path | Contents |
|------|----------|
| `data/processed/merged_halfhourly.parquet` | Full half-hourly grid + values + QC flags (gitignored if large) |
| `data/processed/qc_flags.parquet` | Flag columns only |
| `tables/qc_*.csv` | Completeness and flag-count summaries (committed) |
| `tables/merged_halfhourly_sample.csv` | First 48 rows sample |
| `figures/qc_*.png` | Completeness heatmap / monthly valid-Q fraction |
| `reports/qc_report.md` | Human-readable QC summary |

Rows are **not** dropped for QC failures; flags are columns.

## Units caveat

`q_mjm2` is populated from raw `Q, Вт/м2`. Confirm physical units before modeling.
