# Data dictionary — Lipetsk radiation study

Unknown fields are marked **UNKNOWN**. Do not invent units or semantics beyond what code/headers/inventory provide.

## Locked stations

| Role | Site | Latitude | Longitude | Source notes |
|------|------|---------:|----------:|--------------|
| Total solar radiation + SSD | Kon’-Kolodez’ (Конь-Колодезь) | 52.135409 | 39.163510 | Raw files under `метеорология\липецкая область\Суммарная солнечная радиация\`; site name **not** in filenames |
| Cloud base (НГО) | Lipetsk airport ASMG | 52.697862 | 39.524295 | `метеорология\липецкая область\НГО\`; station code **27930** |
| Modeling | Co-located (assumed) | — | — | Treat NGO as if at radiation site; document ~spatial mismatch as limitation |

Elevation for both sites: **UNKNOWN**.

Timezone used by DB schema default / config: `Europe/Moscow`. Whether raw CSV timestamps are already local winter/summer or fixed offset: **UNKNOWN** (importer uses `DateTimeStyles.AssumeLocal` for radiation).

---

## A. Handbook tables (`data/raw/handbook/`)

Provenance: copied from `bin\Debug\net6.0-windows7.0\` (hashes verified; see `data/raw/README.md`).

### A.1 `IrradianceData.csv` — `B_ref` hourly by direction

| Item | Value |
|------|--------|
| Separator | `;` |
| Encoding | Windows-1251 (Cyrillic headers) with UTF-8 fallback in `DataImporter` |
| Key columns | `LATITUDE`, `STARTHOUR`, then direction pairs (С/В/Ю/З and diagonals; `пр` / `р`) |
| Latitude grid | 0…68 °, step 4 |
| Physical meaning | Handbook / reference insolation table used by product interpolation |
| Units (code comment) | Вт·ч/м² |
| Surface / tilt | Directional façade-style columns (product Table 1); exact handbook definition (clear-sky vs climate mean vs design day): **UNKNOWN** |
| Temporal meaning of `STARTHOUR` | Local hour index in table; calendar date not present (climatological table) |
| Missing sentinel | `-1` in parser |

### A.2 `DailyTotalData.csv`

| Item | Value |
|------|--------|
| Columns | `LATITUDE`, `DAILY_TOTAL_HORIZONTAL` |
| Units (code comment) | Вт·ч/м² per day (horizontal) |
| Period / season represented | **UNKNOWN** (single value per latitude; no month column) |

### A.3 `SunPosition_Altitude.csv` / `SunPosition_Azimuth.csv`

| Item | Value |
|------|--------|
| Layout | First column hour; other columns numeric grid 0…68 step 4 |
| Units | Degrees (altitude / azimuth) |
| Column-axis meaning | Numeric labels match latitude grid; C# property name is `Longitude` but calculation interpolates with target **latitude** |
| Missing sentinel | `-1` |
| Calendar day of year | **UNKNOWN** / not in file (climatological hour×lat matrix) |

### A.4 `settlements.csv`

National settlement list (many administrative columns). Used for UI geocoding, not as meteo station metadata. Kon’-Kolodez’ absent. Example Lipetsk city coords in file: ~52.6103, 39.5946 (distinct from locked research sites).

### A.5 `regions_bounds.json`

RF region polygons for map hit-testing. Not a radiation source.

---

## B. Raw radiation CSVs (`метеорология\…\Суммарная солнечная радиация\`)

| Item | Value |
|------|--------|
| Layout | `регион/параметр/YYYY/YYYYMM/ddmmyyH.csv` day files |
| Encoding | Windows-1251 |
| Header sample | `Время;Q, Вт/м2;T, °C;Q, мВ;SSD, c` |
| `Время` | Timestamp; sample `28.02.2023 0:00:00` |
| `Q, Вт/м2` | Observed total solar irradiance; header unit **Вт/м²** |
| `T, °C` | Air temperature °C |
| `Q, мВ` | Sensor millivolt channel (instrument raw) |
| `SSD, c` | Sunshine duration; header unit **c** (seconds) |
| Empty / missing token | `/` in early files; numeric start ~2023-02-28 |
| Years on disk | Folders 2022–2025; usable numeric radiation aligns with SQLite from 2023-02-28 |
| Station id in file | **UNKNOWN** (region folder only) |

---

## C. Raw НГО / ASMG CSVs (`метеорология\…\НГО\`)

| Item | Value |
|------|--------|
| Files | `c_YYYYMM.csv`, 2021-01 … 2025-12 |
| Header | none |
| Station code field | **27930** |
| Time | year, month, day, hour, minute → 30-minute steps |
| NGO meters | Importer column index **29**; values ≥9000 → null (censored / no cloud / instrument limit) |
| Other ASMG columns | **UNKNOWN** (not mapped by importer) |
| Units of NGO | meters (column name `ngo_m`) |

---

## D. SQLite `Data/spes_meteo.sqlite` (analysis primary)

Gitignored. SHA256 at inventory: `CBBD355F405B501A07EF78A11D4D5DB449EDFE76BA5882A128928712EDA1E353` (~359 MB).

### D.1 `meteo_station`

| Column | Type | Observed / notes |
|--------|------|------------------|
| `id` | INTEGER PK | `1` |
| `code` | TEXT | hashed station code from region name |
| `display_name` | TEXT | `липецкая область` |
| `region_subject` | TEXT | same |
| `latitude` | REAL | **NULL** (use config coords, not DB) |
| `longitude` | REAL | **NULL** |
| `timezone_iana` | TEXT | `Europe/Moscow` |

### D.2 `meteo_dataset`

| Column | Type | Observed / notes |
|--------|------|------------------|
| `id` | INTEGER PK | `1` |
| `station_id` | INTEGER | `1` |
| `code` | TEXT | dataset hash |
| `display_name` | TEXT | `Суммарная солнечная радиация` |
| `parameter_kind` | TEXT | same string |
| `schema_version` | INTEGER | `1` |

### D.3 `meteo_observation` (fields used in analysis)

| Column | Type | Meaning | Units / caveats |
|--------|------|---------|-----------------|
| `id` | INTEGER PK | Row id | — |
| `station_id` | INTEGER | FK station | — |
| `dataset_id` | INTEGER | FK dataset | — |
| `obs_time` | TEXT | Timestamp `yyyy-MM-dd HH:mm:ss` | Local assumed; cadence **30 min** after merge |
| `q_mjm2` | REAL | Radiation from CSV col `Q, Вт/м2` | **Unit name mismatch**: raw header Вт/м², column name suggests МДж/м² — treat numeric values as stored from W/m² parser until reconciled (**UNKNOWN** which physical energy unit was intended by column name) |
| `t_deg_c` | REAL | Temperature | °C |
| `q_mj` | REAL | From CSV `Q, мВ` | Millivolts in source; column name `q_mj` is misleading |
| `ngo_m` | REAL | Cloud base height | meters; null if missing/censored |
| `ssd_s` | REAL | Sunshine duration | seconds (from `SSD, c`) |

Constraints for current DB: importer deletes rows where `q_mjm2` IS NULL OR `ngo_m` IS NULL → all 21 799 rows have both Q and NGO non-null.

Period: **2023-02-28 00:00:00** → **2025-12-31 23:30:00**.

Sample first row: `q_mjm2=0`, `t_deg_c=-3.6`, `q_mj=0`, `ngo_m=631`, `ssd_s=0`.

---

## E. Not yet available

| Source | Status |
|--------|--------|
| Cloudiness amount (баллы / oktas) archive | Missing |
| `cfo_settlements.csv` | Missing |
| Instrument calibration / height / surface tilt for Q | **UNKNOWN** |
| Official station passport linking radiation CSVs to Kon’-Kolodez’ | External confirmation (locked by project decision); not encoded in files |

---

## F. Analysis path summary

1. Primary series: `Data/spes_meteo.sqlite` → `meteo_observation`.
2. Reference handbook: `data/raw/handbook/*.csv`.
3. Site coordinates / ASMG id: `analysis/configs/main.yaml` (not SQLite lat/lon).
4. Raw CSVs under `метеорология\` only for re-import / QC audits — do not commit.
