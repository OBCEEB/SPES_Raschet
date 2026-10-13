# Repository inventory — SPES_Raschet

Baseline for the Lipetsk radiation research branch. Product calculation logic was not changed for this inventory.

## Identity

| Field | Value |
|-------|--------|
| Remote | `https://github.com/OBCEEB/SPES_Raschet.git` |
| Baseline commit (branch point / HEAD at setup) | `5925a2f39d7a18ce7d4790ae179b62c4bb57bd36` |
| Baseline subject | `release: ship meteo DB pipeline and climatology UX updates` |
| Research branch | `research/lipetsk-radiation` |
| App version (`SPES_Raschet.csproj`) | `0.4.0` |
| Target framework | `net6.0-windows7.0` (WinForms) |

Working tree at setup may also contain unrelated dirty edits on `main` (meteo services, map tools). Those are **not** part of the research-scaffolding commit unless explicitly staged.

## What the C# application does

WinForms shell (`ShellForm`) launches modular tools. The climatology module (`Form1`) lets the user:

1. Load RF/CFO offline maps and settlement lists.
2. Pick a settlement (or coordinates) and compute **handbook** insolation tables via latitude interpolation.
3. Show hourly irradiance by façade direction, sun altitude/azimuth, and daily horizontal totals.
4. Import/view local meteorology from CSV archive into SQLite (`Data/spes_meteo.sqlite`) and open Lipetsk meteo records UI.

There is **no automated unit-test project** in the repo (`*Test*` search empty). Validation is manual / UI-driven.

## Entry points

| Entry | Role |
|-------|------|
| `Program.Main` | Registers Windows-1251 code pages, theme, starts `ShellForm` |
| `ShellForm` | Module launcher; can trigger `MeteoArchiveImporter.ImportArchive` |
| `Form1` | Climatology UI: maps, handbook load (`DataImporter.LoadAllData`), settlement pick, calculation results, meteo import / Lipetsk records |
| `CalculationResultsForm` | Runs `ClimatologyCalculationService` + charts/PDF export |
| `DataImporter` (`SolarData.cs`) | Parses handbook CSVs into `DataStore` |
| `MathTools.Interpolate` | Linear interpolation between nearest tabular latitudes |
| `ClimatologyCalculationService` | Hourly irradiance + sun position tables for a target latitude |
| `GeoDataHandler` | Loads `settlements.csv`, `regions_bounds.json` |
| `MeteoArchiveImporter` | CSV → SQLite merge of radiation and НГО |
| `MeteoQueryService` | Reads observations / summaries for UI |
| `tools/import_meteo_sqlite.py` | Parallel offline importer → `Data/spes_meteo.sqlite` |
| `tools/scan_meteorology_csv.py` | Empty-day QC scan of raw radiation CSVs |

## Handbook formats (reference field `B_ref`)

Loaded from exe directory (`AppDomain.CurrentDomain.BaseDirectory` / `AppContext.BaseDirectory`). Research copies live under `data/raw/handbook/` (see `data/raw/README.md` for hashes).

| File | Role in code | Format notes |
|------|--------------|--------------|
| `IrradianceData.csv` | Table 1 — hourly irradiance by latitude & direction | `;` separator; header `LATITUDE;STARTHOUR;…` direction columns (С/В/Ю/З + diagonals, пр/р); latitudes 0…68 step 4; values treated as **Вт·ч/м²** in `IrradianceData` comments |
| `DailyTotalData.csv` | Table 3 — daily horizontal total by latitude | `LATITUDE;DAILY_TOTAL_HORIZONTAL`; code comment: sum **Вт·ч/м²** per day |
| `SunPosition_Altitude.csv` / `SunPosition_Azimuth.csv` | Table 2 — sun height / azimuth matrices | Row = hour, columns = numeric grid (0…68 step 4). Parsed into `SunPositionData.Longitude` but interpolated with **target latitude** in `ClimatologyCalculationService` (naming mismatch; treat column axis as latitude grid for analysis) |
| `settlements.csv` | Settlement picker | UTF-8-SIG national list; Lipetsk oblast cities present; **no** Kon’-Kolodez’ row |
| `regions_bounds.json` | Region polygons for RF map | JSON |

Missing for CFO mode: `cfo_settlements.csv`. Present separately: `regions_bounds_cfo.json`, `MapData/CFO/*`, `MapData/Russia/*` (mbtiles gitignored).

## Meteo import

Default archive path: `{AppBase}/метеорология` (`MeteoDbPaths.GetDefaultMeteorologyArchivePath`). On this checkout the archive also exists at **repo root** `метеорология\` (not under `bin\`).

Layout:

1. Preferred: `регион / категория / год / … / *.csv`
2. Category `НГО` → ASMG parser; other categories keep folder name as parameter (radiation folder `Суммарная солнечная радиация`)
3. Region names containing `Липецк` normalize to `липецкая область`
4. Radiation CSV: Windows-1251; header skipped; columns `Время; Q; T; Q; SSD` → stored as `q_mjm2`, `t_deg_c`, `q_mj`, `ssd_s`
5. НГО/ASMG CSV: no header; timestamp from cols 3–7 (Y,M,D,h,min); NGO meters from column index 29; sentinel ≥9000 → null
6. Post-import prune: delete rows missing `q_mjm2` **or** `ngo_m` → yields 30-minute merged series

SQLite path: `{AppBase}/Data/spes_meteo.sqlite` (also present at repo `Data\spes_meteo.sqlite`).

Schema (from `MeteoSchema` / live DB):

- `meteo_station(id, code, display_name, region_subject, latitude, longitude, timezone_iana)`
- `meteo_dataset(id, station_id, code, display_name, parameter_kind, schema_version)`
- `meteo_observation(id, station_id, dataset_id, obs_time, q_mjm2, t_deg_c, q_mj, ngo_m, ssd_s)`

Current DB probe: 21 799 observations, 2023-02-28 → 2025-12-31, station display `липецкая область`, lat/lon **NULL** in DB.

## Build / run commands

```bash
dotnet build SPES_Raschet.csproj
dotnet run --project SPES_Raschet.csproj
```

Python offline import (prefer `py -3` on this machine):

```bash
py -3 tools/import_meteo_sqlite.py
py -3 tools/scan_meteorology_csv.py
```

Map prep helpers: `tools/prepare-cfo-map.ps1`, `tools/prepare-russia-map.ps1`, related download scripts under `tools/`.

## Research scaffolding (this branch)

```text
data/raw/handbook/     # tracked handbook copies
data/interim/          # empty staging
data/processed/        # empty outputs
analysis/src/          # Python modules (to be filled)
analysis/configs/      # main.yaml
figures/ tables/ reports/
docs/repository_inventory.md
docs/data_dictionary.md
```

## Python analysis integration point

Recommended boundary (do **not** rewrite C# climatology math for the article pipeline):

1. Keep C# for handbook load/interpolation and optional CSV→SQLite ingestion.
2. Point Python configs at:
   - `Data/spes_meteo.sqlite` — primary observational series
   - `data/raw/handbook/` — reference tables for `B_ref` / sun geometry baselines
3. Export normalized tables to `data/interim/` / `data/processed/` (CSV/Parquet + metadata).
4. Implement QC, clear-sky index, models M0–M3, figures under `analysis/src/` driven by `analysis/configs/main.yaml`.
5. Optional later: call C# `MathTools` / `ClimatologyCalculationService` from a thin export CLI — not required for first Python path; can reimplement linear latitude interpolation independently for cross-check.

Locked site metadata for analysis is in `analysis/configs/main.yaml` (Kon’-Kolodez’ radiation; Lipetsk airport NGO 27930; co-located modeling with documented mismatch).
