"""
Download B-road and minor-road way segments from the Overpass API for Great
Britain and save to data/osm_roads.parquet.

Each OSM way returns its centre-point coordinates + tags, giving geographic
coverage along each road's route (many segments per road number). This fills
the gap left by OS Open Names, which stores only a single national centroid
per B-road number.

Usage:
    python scripts/download_osm_roads.py
"""

import json
import sys
import time
import urllib.parse
import urllib.request
import warnings
from pathlib import Path

import polars as pl

try:
    from pyproj import Transformer
    _TRANSFORMER = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)
    _HAS_PYPROJ = True
except ImportError:
    _HAS_PYPROJ = False
    warnings.warn("pyproj not installed — GEOMETRY_X/Y will be stored as NaN")

DATA_DIR    = Path(__file__).parent.parent / "data"
OUT_PATH    = DATA_DIR / "osm_roads.parquet"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# B-roads are tagged highway=secondary or highway=tertiary in OSM
# with a ref tag starting with B.
# We query the full GB bounding box and retry with regional splits on timeout.
GB_BBOX = (49.0, -10.0, 60.9, 2.0)

REGION_BBOXES = [
    ("England-S", (49.0, -6.0, 52.5, 2.0)),
    ("England-N", (52.5, -4.0, 55.5, 2.0)),
    ("Wales",     (51.2, -5.4, 53.5, -2.7)),
    ("Scotland",  (54.5, -7.6, 60.9, -0.5)),
]

TYPE_WEIGHT_MAP = {
    "B Road": 3,
}

_HEADERS = {
    "User-Agent": "ukgeo/0.1 (B-road segment lookup, geocoder research)",
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "application/json",
}


def _build_overpass_query(bbox: tuple) -> str:
    s, w, n, e = bbox
    return (
        '[out:json][timeout:180];\n'
        '(\n'
        f'  way["highway"="secondary"]["ref"~"^B[0-9]+"]({s},{w},{n},{e});\n'
        f'  way["highway"="tertiary"]["ref"~"^B[0-9]+"]({s},{w},{n},{e});\n'
        ');\n'
        'out center tags;\n'
    )


def fetch_overpass(query: str, label: str = "", retry: bool = True) -> dict | None:
    data = urllib.parse.urlencode({"data": query}).encode()
    req = urllib.request.Request(OVERPASS_URL, data=data, headers=_HEADERS)
    print(f"  Querying Overpass API ({label}) ...", flush=True)
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            raw = resp.read()
        print(f"  Received {len(raw) / 1e6:.1f} MB", flush=True)
        return json.loads(raw)
    except Exception as exc:
        msg = str(exc)
        if retry and ("timed out" in msg.lower() or "timeout" in msg.lower() or "429" in msg):
            print(f"  Timeout/rate-limit for {label!r}. Waiting 60s before retry ...", flush=True)
            time.sleep(60)
            try:
                with urllib.request.urlopen(req, timeout=300) as resp:
                    raw = resp.read()
                print(f"  Retry succeeded: {len(raw) / 1e6:.1f} MB", flush=True)
                return json.loads(raw)
            except Exception as exc2:
                print(f"  Retry failed: {exc2}", flush=True)
                return None
        else:
            print(f"  Request failed: {exc}", flush=True)
            return None


def _wgs84_to_bng(lon: float, lat: float) -> tuple[float, float]:
    if _HAS_PYPROJ:
        x, y = _TRANSFORMER.transform(lon, lat)
        return round(x, 1), round(y, 1)
    return float("nan"), float("nan")


def parse_elements(data: dict) -> list[dict]:
    rows = []
    for el in data.get("elements", []):
        if el.get("type") != "way":
            continue
        center = el.get("center")
        if not center:
            continue
        try:
            lat = float(center["lat"])
            lon = float(center["lon"])
        except (KeyError, TypeError, ValueError):
            continue

        tags = el.get("tags", {})
        ref = tags.get("ref", "").strip()
        if not ref or not ref[1:].isdigit() or ref[0].upper() != "B":
            continue

        name2 = tags.get("name", "").strip()
        geom_x, geom_y = _wgs84_to_bng(lon, lat)

        rows.append({
            "NAME1":      ref.upper(),
            "NAME2":      name2,
            "LAT":        lat,
            "LON":        lon,
            "GEOMETRY_X": geom_x,
            "GEOMETRY_Y": geom_y,
            "LOCAL_TYPE": "B Road",
            "OSM_ID":     int(el.get("id", 0)),
        })
    return rows


def fetch_all_regions() -> list[dict]:
    """Try GB-wide query first; fall back to per-region queries on timeout."""
    print("Attempting GB-wide Overpass query ...")
    query = _build_overpass_query(GB_BBOX)
    data = fetch_overpass(query, label="GB", retry=True)

    if data and data.get("elements"):
        rows = parse_elements(data)
        print(f"  GB-wide query returned {len(rows)} way segments")
        return rows

    print("GB-wide query failed or empty. Falling back to per-region queries ...")
    all_rows: list[dict] = []
    seen_ids: set[int] = set()

    for label, bbox in REGION_BBOXES:
        print(f"\nQuerying {label} ...")
        q = _build_overpass_query(bbox)
        rdata = fetch_overpass(q, label=label, retry=True)
        if not rdata:
            warnings.warn(f"Skipping {label} — query failed")
            continue
        rows = parse_elements(rdata)
        new = [r for r in rows if r["OSM_ID"] not in seen_ids]
        seen_ids.update(r["OSM_ID"] for r in new)
        all_rows.extend(new)
        print(f"  {label}: {len(new)} new segments (total so far: {len(all_rows)})")
        # Brief pause between region queries to be polite to Overpass
        time.sleep(5)

    return all_rows


def build_parquet(rows: list[dict], out_path: Path) -> pl.DataFrame:
    if not rows:
        print("No rows — nothing to save.", file=sys.stderr)
        sys.exit(1)

    df = pl.DataFrame(rows, schema={
        "NAME1":      pl.Utf8,
        "NAME2":      pl.Utf8,
        "LAT":        pl.Float64,
        "LON":        pl.Float64,
        "GEOMETRY_X": pl.Float64,
        "GEOMETRY_Y": pl.Float64,
        "LOCAL_TYPE": pl.Utf8,
        "OSM_ID":     pl.Int64,
    })

    df = df.with_columns([
        pl.col("NAME1").str.to_uppercase().alias("NAME1_UPPER"),
        pl.col("NAME2").fill_null("").str.to_uppercase().alias("NAME2_UPPER"),
        pl.lit(TYPE_WEIGHT_MAP["B Road"]).cast(pl.Int8).alias("TYPE_WEIGHT"),
    ])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(out_path)
    return df


def main():
    if OUT_PATH.exists():
        ans = input(f"{OUT_PATH} already exists. Re-download? [y/N]: ").strip().lower()
        if ans != "y":
            print("Skipping download.")
            return

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    rows = fetch_all_regions()
    print(f"\nTotal way segments fetched: {len(rows)}")

    if not rows:
        print("No data fetched — exiting.", file=sys.stderr)
        sys.exit(1)

    df = build_parquet(rows, OUT_PATH)

    unique_roads = df["NAME1_UPPER"].n_unique()
    print(f"\nSaved to {OUT_PATH}")
    print(f"  Rows (way segments):  {len(df):,}")
    print(f"  Unique B-road refs:   {unique_roads:,}")
    print(f"  Sample:")
    print(df.sample(min(5, len(df)), seed=42).select(["NAME1", "NAME2", "LAT", "LON", "TYPE_WEIGHT"]))


if __name__ == "__main__":
    main()
