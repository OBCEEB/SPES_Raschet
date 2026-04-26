import io
import math
import os
import sqlite3
import time
import urllib.request


USER_AGENT = "SPES-OfflinemapBuilder/1.0 (+local-dev)"
TILE_SERVER = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"

# Expanded bbox for entire CFO with margin.
MIN_LON = 27.0
MIN_LAT = 49.0
MAX_LON = 49.0
MAX_LAT = 61.2

# Keep moderate by default; can be increased later.
MIN_ZOOM = 6
MAX_ZOOM = 10


def deg2num(lat_deg, lon_deg, zoom):
    lat_rad = math.radians(lat_deg)
    n = 2.0 ** zoom
    xtile = int((lon_deg + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return xtile, ytile


def ensure_mbtiles(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    cur = con.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute(
        "CREATE TABLE IF NOT EXISTS metadata (name TEXT, value TEXT, UNIQUE(name))"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB, UNIQUE(zoom_level, tile_column, tile_row))"
    )
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS tile_index ON tiles (zoom_level, tile_column, tile_row)"
    )
    con.commit()
    return con


def set_metadata(con):
    cur = con.cursor()
    metadata = {
        "name": "SPES CFO Offline Map",
        "type": "baselayer",
        "version": "1",
        "description": "OSM raster tiles for Central Federal District (offline cache).",
        "format": "png",
        "minzoom": str(MIN_ZOOM),
        "maxzoom": str(MAX_ZOOM),
        "bounds": f"{MIN_LON},{MIN_LAT},{MAX_LON},{MAX_LAT}",
        "attribution": "© OpenStreetMap contributors (ODbL)",
    }
    for k, v in metadata.items():
        cur.execute(
            "INSERT INTO metadata(name, value) VALUES(?, ?) ON CONFLICT(name) DO UPDATE SET value=excluded.value",
            (k, v),
        )
    con.commit()


def fetch_tile(z, x, y):
    url = TILE_SERVER.format(z=z, x=x, y=y)
    last_error = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=25) as resp:
                return resp.read()
        except Exception as ex:
            last_error = ex
            time.sleep(0.25 * (attempt + 1))
    raise last_error


def main():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    mbtiles_path = os.path.join(root, "MapData", "CFO", "cfo_map.mbtiles")
    con = ensure_mbtiles(mbtiles_path)
    set_metadata(con)
    cur = con.cursor()

    total = 0
    downloaded = 0
    skipped = 0
    failed = 0

    for z in range(MIN_ZOOM, MAX_ZOOM + 1):
        x_min, y_max = deg2num(MIN_LAT, MIN_LON, z)
        x_max, y_min = deg2num(MAX_LAT, MAX_LON, z)

        if x_min > x_max:
            x_min, x_max = x_max, x_min
        if y_min > y_max:
            y_min, y_max = y_max, y_min

        for x in range(x_min, x_max + 1):
            for y_osm in range(y_min, y_max + 1):
                total += 1
                tms_y = (2 ** z - 1) - y_osm
                row = cur.execute(
                    "SELECT 1 FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                    (z, x, tms_y),
                ).fetchone()
                if row:
                    skipped += 1
                    continue

                try:
                    tile_data = fetch_tile(z, x, y_osm)
                    cur.execute(
                        "INSERT OR REPLACE INTO tiles(zoom_level, tile_column, tile_row, tile_data) VALUES(?, ?, ?, ?)",
                        (z, x, tms_y, sqlite3.Binary(tile_data)),
                    )
                    downloaded += 1
                    if downloaded % 100 == 0:
                        con.commit()
                    time.sleep(0.1)  # gentle rate limiting
                except Exception:
                    failed += 1
                    time.sleep(0.2)

    con.commit()
    con.close()

    print("Done")
    print(f"Path: {mbtiles_path}")
    print(f"Total considered: {total}")
    print(f"Downloaded: {downloaded}")
    print(f"Skipped(existing): {skipped}")
    print(f"Failed: {failed}")


if __name__ == "__main__":
    main()
