# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
METEO_DIR = ROOT / "метеорология"
DB_PATH = ROOT / "Data" / "spes_meteo.sqlite"


def stable_code(label: str, prefix: str) -> str:
    h = hashlib.sha256(label.encode("utf-8")).digest()[:8].hex()
    return prefix + h


def normalize_region(name: str) -> str:
    if "липецк" in name.lower():
        return "липецкая область"
    return name.strip()


def to_float(s: str):
    t = (s or "").strip().strip('"')
    if not t or t in {"/", "\\", "-", "—", "–"}:
        return None
    t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def to_ngo(s: str):
    v = to_float(s)
    if v is None:
        return None
    # Сентинел "нет НГО"
    if v >= 9000:
        return None
    return v


def ensure_schema(con: sqlite3.Connection):
    con.executescript(
        """
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;
        CREATE TABLE IF NOT EXISTS meteo_station (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          code TEXT NOT NULL UNIQUE,
          display_name TEXT NOT NULL,
          region_subject TEXT,
          latitude REAL,
          longitude REAL,
          timezone_iana TEXT NOT NULL DEFAULT 'Europe/Moscow'
        );
        CREATE TABLE IF NOT EXISTS meteo_dataset (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          station_id INTEGER NOT NULL,
          code TEXT NOT NULL,
          display_name TEXT NOT NULL,
          parameter_kind TEXT,
          schema_version INTEGER NOT NULL DEFAULT 1,
          UNIQUE(station_id, code)
        );
        CREATE TABLE IF NOT EXISTS meteo_observation (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          station_id INTEGER NOT NULL,
          dataset_id INTEGER NOT NULL,
          obs_time TEXT NOT NULL,
          q_mjm2 REAL,
          t_deg_c REAL,
          q_mj REAL,
          ngo_m REAL,
          ssd_s REAL,
          UNIQUE(station_id, dataset_id, obs_time)
        );
        CREATE INDEX IF NOT EXISTS ix_meteo_obs_station_time ON meteo_observation(station_id, obs_time);
        CREATE INDEX IF NOT EXISTS ix_meteo_obs_dataset_time ON meteo_observation(dataset_id, obs_time);
        CREATE INDEX IF NOT EXISTS ix_meteo_obs_time ON meteo_observation(obs_time);
        """
    )
    cols = {r[1] for r in con.execute("PRAGMA table_info(meteo_observation)")}
    if "ngo_m" not in cols:
        con.execute("ALTER TABLE meteo_observation ADD COLUMN ngo_m REAL")


def upsert_station(con: sqlite3.Connection, region: str) -> int:
    code = stable_code("region:" + region, "st_")
    con.execute(
        """
        INSERT INTO meteo_station(code, display_name, region_subject)
        VALUES(?, ?, ?)
        ON CONFLICT(code) DO UPDATE SET
            display_name=excluded.display_name,
            region_subject=excluded.region_subject
        """,
        (code, region, region),
    )
    return con.execute("SELECT id FROM meteo_station WHERE code=?", (code,)).fetchone()[0]


def upsert_dataset(con: sqlite3.Connection, station_id: int, name: str) -> int:
    code = stable_code(f"dataset:{station_id}:{name}", "ds_")
    con.execute(
        """
        INSERT INTO meteo_dataset(station_id, code, display_name, parameter_kind)
        VALUES(?, ?, ?, ?)
        ON CONFLICT(station_id, code) DO UPDATE SET
            display_name=excluded.display_name,
            parameter_kind=excluded.parameter_kind
        """,
        (station_id, code, name, name),
    )
    return con.execute(
        "SELECT id FROM meteo_dataset WHERE station_id=? AND code=?", (station_id, code)
    ).fetchone()[0]


def iter_records(path: Path, is_asmg: bool):
    with path.open("r", encoding="cp1251", errors="replace", newline="") as f:
        reader = csv.reader(f, delimiter=";")
        if not is_asmg:
            next(reader, None)  # header
        for row in reader:
            if not row:
                continue
            if is_asmg:
                if len(row) < 30:
                    continue
                try:
                    y = int(row[3].strip())
                    m = int(row[4].strip())
                    d = int(row[5].strip())
                    hh = int(row[6].strip())
                    mm = int(row[7].strip())
                    ts = datetime(y, m, d, hh, mm).strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    continue
                ngo = to_ngo(row[29])  # AD / 30-я колонка
                yield (ts, None, None, None, ngo, None)
            else:
                try:
                    ts = datetime.strptime(row[0].strip().strip('"'), "%d.%m.%Y %H:%M:%S").strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                except Exception:
                    continue
                q1 = to_float(row[1]) if len(row) > 1 else None
                t = to_float(row[2]) if len(row) > 2 else None
                q = to_float(row[3]) if len(row) > 3 else None
                ssd = to_float(row[4]) if len(row) > 4 else None
                yield (ts, q1, t, q, None, ssd)


def resolve_target(path: Path):
    rel = path.relative_to(METEO_DIR)
    parts = rel.parts
    # Обратная совместимость: старый плоский формат АМСГ.
    if len(parts) == 2 and parts[1].lower().startswith("c_"):
        region = normalize_region(parts[0])
        return region, "Суммарная солнечная радиация", True
    if len(parts) >= 3:
        region = normalize_region(parts[0])
        category = parts[1].strip()
        is_ngo = category.lower() == "нго"
        dataset_name = "Суммарная солнечная радиация" if is_ngo else category
        return region, dataset_name, is_ngo
    return None


def main():
    if not METEO_DIR.exists():
        raise SystemExit(f"Folder not found: {METEO_DIR}")

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    try:
        ensure_schema(con)
        con.execute("BEGIN")
        con.execute("DELETE FROM meteo_observation")

        files = sorted(METEO_DIR.rglob("*.csv"))
        files_done = 0
        rows = 0
        station_cache: dict[str, int] = {}
        dataset_cache: dict[tuple[str, str], int] = {}

        upsert_sql = """
        INSERT INTO meteo_observation(station_id,dataset_id,obs_time,q_mjm2,t_deg_c,q_mj,ngo_m,ssd_s)
        VALUES(?,?,?,?,?,?,?,?)
        ON CONFLICT(station_id, dataset_id, obs_time) DO UPDATE SET
            q_mjm2=COALESCE(excluded.q_mjm2, meteo_observation.q_mjm2),
            t_deg_c=COALESCE(excluded.t_deg_c, meteo_observation.t_deg_c),
            q_mj=COALESCE(excluded.q_mj, meteo_observation.q_mj),
            ngo_m=COALESCE(excluded.ngo_m, meteo_observation.ngo_m),
            ssd_s=COALESCE(excluded.ssd_s, meteo_observation.ssd_s)
        """

        for p in files:
            target = resolve_target(p)
            if not target:
                continue
            region, dataset_name, is_asmg = target
            sid = station_cache.get(region)
            if sid is None:
                sid = upsert_station(con, region)
                station_cache[region] = sid
            dkey = (region, dataset_name)
            did = dataset_cache.get(dkey)
            if did is None:
                did = upsert_dataset(con, sid, dataset_name)
                dataset_cache[dkey] = did

            batch = []
            for ts, q1, t, q, ngo, ssd in iter_records(p, is_asmg):
                batch.append((sid, did, ts, q1, t, q, ngo, ssd))
                if len(batch) >= 500:
                    con.executemany(upsert_sql, batch)
                    rows += len(batch)
                    batch.clear()
            if batch:
                con.executemany(upsert_sql, batch)
                rows += len(batch)
            files_done += 1
            if files_done % 50 == 0:
                print(f"{files_done}/{len(files)} files, rows={rows}")

        # Оставляем только пары "радиация + НГО" для расчетов.
        con.execute("DELETE FROM meteo_observation WHERE q_mjm2 IS NULL OR ngo_m IS NULL")
        con.commit()
        ngo_rows = con.execute(
            "SELECT COUNT(*) FROM meteo_observation WHERE ngo_m IS NOT NULL"
        ).fetchone()[0]
        print(f"Done. files={files_done}, rows={rows}, ngo_rows={ngo_rows}, db={DB_PATH}")
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


if __name__ == "__main__":
    main()

