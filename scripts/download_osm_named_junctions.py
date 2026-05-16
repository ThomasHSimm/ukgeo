"""
Fetch named UK road junctions and roundabouts from OpenStreetMap via the
Overpass API, then save to data/osm_named_junctions.parquet.

Features queried:
  - Named motorway junction nodes (highway=motorway_junction + name)
  - Named roundabout ways/relations (junction=roundabout + name)

Usage:
    python scripts/download_osm_named_junctions.py

Data is licensed under ODbL — see https://www.openstreetmap.org/copyright
"""

import json
import sys
import urllib.request
import urllib.parse
from pathlib import Path

import polars as pl

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
DATA_DIR = Path(__file__).parent.parent / "data"
OUT_PATH = DATA_DIR / "osm_named_junctions.parquet"

# Great Britain bounding box (south,west,north,east)
BBOX_GB = "49.0,-10.0,60.9,2.0"

OVERPASS_QUERY = f"""
[out:json][timeout:180];
(
  node["highway"="motorway_junction"]["name"]({BBOX_GB});
  way["junction"="roundabout"]["name"]({BBOX_GB});
  relation["junction"="roundabout"]["name"]({BBOX_GB});
);
out center tags;
"""

TYPE_WEIGHT_MAP = {
    "Named Junction":    9,
    "Named Roundabout":  8,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _progress(msg: str):
    print(msg, flush=True)


def fetch_overpass(query: str) -> dict:
    _progress("Querying Overpass API ...")
    data = urllib.parse.urlencode({"data": query}).encode()
    req = urllib.request.Request(
        OVERPASS_URL,
        data=data,
        headers={
            "User-Agent": "ukgeo/0.1 (geocoder research project)",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req, timeout=200) as resp:
        return json.loads(resp.read())


def parse_elements(data: dict) -> list[dict]:
    """
    Extract (name, alt_name, lat, lon, osm_type, osm_id, local_type) from Overpass elements.
    Ways/relations use the centre coordinate from `out center` output.
    """
    rows = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name")
        if not name:
            continue

        osm_type = el["type"]
        osm_id   = el["id"]

        if osm_type == "node":
            lat = el.get("lat")
            lon = el.get("lon")
        else:
            # way / relation — use centroid from `out center`
            center = el.get("center", {})
            lat = center.get("lat")
            lon = center.get("lon")

        if lat is None or lon is None:
            continue

        # Determine junction type from tags
        if tags.get("highway") == "motorway_junction":
            local_type = "Named Junction"
        else:
            local_type = "Named Roundabout"

        # alt_name covers colloquial names (e.g. "Spaghetti Junction")
        alt_name = tags.get("alt_name") or tags.get("name:en") or ""

        rows.append({
            "NAME1":      name,
            "NAME2":      alt_name,
            "LAT":        float(lat),
            "LON":        float(lon),
            "OSM_TYPE":   osm_type,
            "OSM_ID":     int(osm_id),
            "LOCAL_TYPE": local_type,
        })
    return rows


def add_bng_columns(df: pl.DataFrame) -> pl.DataFrame:
    """Convert LAT/LON to BNG eastings/northings using pyproj."""
    try:
        from pyproj import Transformer
        t = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)
        lons = df["LON"].to_list()
        lats = df["LAT"].to_list()
        eastings, northings = t.transform(lons, lats)
        return df.with_columns([
            pl.Series("GEOMETRY_X", eastings, dtype=pl.Float64),
            pl.Series("GEOMETRY_Y", northings, dtype=pl.Float64),
        ])
    except ImportError:
        _progress("Warning: pyproj not available — GEOMETRY_X/Y will be null")
        return df.with_columns([
            pl.lit(None).cast(pl.Float64).alias("GEOMETRY_X"),
            pl.lit(None).cast(pl.Float64).alias("GEOMETRY_Y"),
        ])


def build_parquet(rows: list[dict], out_path: Path):
    _progress(f"Building parquet from {len(rows):,} features ...")
    df = pl.DataFrame(rows)
    df = df.with_columns([
        pl.col("NAME1").str.to_uppercase().alias("NAME1_UPPER"),
        pl.col("NAME2").fill_null("").str.to_uppercase().alias("NAME2_UPPER"),
        pl.col("LOCAL_TYPE").replace(TYPE_WEIGHT_MAP).cast(pl.Int8).alias("TYPE_WEIGHT"),
    ])
    df = add_bng_columns(df)

    # Drop duplicates (same OSM element could appear via multiple query branches)
    df = df.unique(subset=["OSM_TYPE", "OSM_ID"])

    # Log breakdown
    for lt, count in df.group_by("LOCAL_TYPE").agg(pl.len()).iter_rows():
        _progress(f"  {lt}: {count:,}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(out_path, compression="zstd")
    size_kb = out_path.stat().st_size / 1024
    _progress(f"Saved {len(df):,} rows → {out_path} ({size_kb:.0f} KB)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if OUT_PATH.exists():
        ans = input(f"{OUT_PATH} already exists. Re-download? [y/N] ").strip().lower()
        if ans != "y":
            sys.exit(0)

    data = fetch_overpass(OVERPASS_QUERY)
    rows = parse_elements(data)
    if not rows:
        print("No features returned — check query or internet connection.")
        sys.exit(1)

    build_parquet(rows, OUT_PATH)
