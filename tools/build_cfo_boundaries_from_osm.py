import json
import os
import time
import urllib.parse
import urllib.request


USER_AGENT = "SPES-CFO-BoundaryBuilder/1.0 (+local-dev)"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

REGIONS = [
    "Белгородская область",
    "Брянская область",
    "Владимирская область",
    "Воронежская область",
    "Ивановская область",
    "Калужская область",
    "Костромская область",
    "Курская область",
    "Липецкая область",
    "Московская область",
    "Орловская область",
    "Рязанская область",
    "Смоленская область",
    "Тамбовская область",
    "Тверская область",
    "Тульская область",
    "Ярославская область",
    "Москва",
]


def request_region_geojson(region_name):
    params = {
        "q": f"{region_name}, Россия",
        "format": "jsonv2",
        "polygon_geojson": "1",
        "limit": "1",
        "countrycodes": "ru",
    }
    url = f"{NOMINATIM_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=40) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        if not data:
            raise RuntimeError(f"Nominatim returned empty result for '{region_name}'")
        return data[0]["geojson"]


def convert_geojson_to_internal(geojson):
    result = {}

    gtype = geojson.get("type")
    if gtype == "Polygon":
        polygons = [geojson.get("coordinates", [])]
    elif gtype == "MultiPolygon":
        polygons = geojson.get("coordinates", [])
    else:
        return result

    idx = 0
    for poly in polygons:
        if not poly:
            continue
        outer_ring = poly[0]
        converted = []
        for coord in outer_ring:
            if len(coord) < 2:
                continue
            lon = float(coord[0])
            lat = float(coord[1])
            converted.append([lat, lon])  # app internal format
        if len(converted) >= 3:
            result[f"poly_{idx}"] = converted
            idx += 1
    return result


def main():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    output_path = os.path.join(root, "regions_bounds_cfo.json")

    combined = {}
    for i, region in enumerate(REGIONS, start=1):
        print(f"[{i}/{len(REGIONS)}] {region}")
        geojson = request_region_geojson(region)
        polygons = convert_geojson_to_internal(geojson)
        if not polygons:
            raise RuntimeError(f"Unsupported/empty polygon for region '{region}'")
        combined[region] = polygons
        time.sleep(1.1)  # respectful rate limit

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(combined, f, ensure_ascii=False, separators=(",", ":"))

    print("Done")
    print(f"Saved: {output_path}")
    print(f"Regions: {len(combined)}")


if __name__ == "__main__":
    main()
