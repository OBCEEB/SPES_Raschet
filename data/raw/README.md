# Raw data sources

This tree holds **immutable** research inputs. Do not overwrite files here after copy; write cleaned outputs under `data/interim/` or `data/processed/`.

## Handbook / reference tables (`handbook/`)

Canonical research copies of the SPES climatology lookup tables. Source used for this checkout:

| File | Copied from | Size (bytes) | SHA256 |
|------|-------------|-------------:|--------|
| `IrradianceData.csv` | `bin\Debug\net6.0-windows7.0\` | 14228 | `16D70E5241EA451C349C66B5B1DAE61FA1EA57DF74A034A8A65DD0CF28A6B9B7` |
| `DailyTotalData.csv` | same | 174 | `B12B95B12A7D4527D91FC85977C1A54EA7EBEED2FB310799632D56439FC1BE53` |
| `SunPosition_Altitude.csv` | same | 1179 | `B754180990875D23A71BE472D1A5E447EFA825FC30758A70B01E9BFC207C9CCE` |
| `SunPosition_Azimuth.csv` | same | 1321 | `956F1D215668BAB0AD7084C782AE7DD4E88EFE068EC0EF2081725700FA6C940F` |
| `settlements.csv` | same | 254587 | `EEFA7F8E9943FCD6247B08E9CC03CA0D209B7598DA00FB91C55F79E21255F841` |
| `regions_bounds.json` | same | 541837 | `9914016312B28C4A767A0D30957898C3C328C8F9C0E1DC85FCA6B35077A2F9E2` |

Notes:

- At inventory time these files existed only under build output (prefer `net6.0-windows7.0` over `net10.0-windows`); they were not tracked at repo root.
- Runtime C# still loads the same filenames from `AppContext.BaseDirectory` (next to the exe). Research analysis should prefer `data/raw/handbook/`.
- `regions_bounds_cfo.json` remains at repo root (separate CFO map package); not duplicated here.
- `cfo_settlements.csv` is missing on this machine.

## Analysis series (not committed)

Primary merged observational series for the Lipetsk radiation study:

- Path: `Data\spes_meteo.sqlite` (gitignored)
- Content: 30-minute rows with both radiation (`q_mjm2`) and cloud-base (`ngo_m`) after import prune
- Period (current DB): 2023-02-28 00:00:00 → 2025-12-31 23:30:00
- Row count: 21 799

## Raw meteorology archive (not committed)

- Path: `метеорология\` at repo root (gitignored)
- Radiation+SSD day CSVs under `метеорология\липецкая область\Суммарная солнечная радиация\`
- NGO / ASMG monthly CSVs under `метеорология\липецкая область\НГО\` (station code **27930**)

Do **not** add `метеорология\`, `Data\*.sqlite`, `bin\`, or `obj\` to git.
