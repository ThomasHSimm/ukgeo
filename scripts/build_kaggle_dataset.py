"""
Build the combined ukgeo Kaggle dataset.

Combines OS Open Names, OS Open Roads junctions, OSM named junctions,
OSM B-road segments, and curated infrastructure aliases into a single
unified parquet file, and writes the associated Kaggle metadata files.

Usage:
    python scripts/build_kaggle_dataset.py

Outputs:
    data/kaggle/ukgeo_data.parquet    — combined geocoding reference data
    data/kaggle/dataset-metadata.json — Kaggle dataset metadata
    data/kaggle/README.md             — dataset documentation
"""

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import polars as pl
from pyproj import Transformer

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT         = Path(__file__).parent.parent
DATA_DIR     = ROOT / "data"
KAGGLE_DIR   = DATA_DIR / "kaggle"
OUT_PARQUET  = KAGGLE_DIR / "ukgeo_data.parquet"
OUT_METADATA = KAGGLE_DIR / "dataset-metadata.json"
OUT_README   = KAGGLE_DIR / "README.md"

OS_NAMES_PATH    = DATA_DIR / "os_open_names.parquet"
OS_ROADS_PATH    = DATA_DIR / "os_open_roads_junctions.parquet"
OSM_PATH         = DATA_DIR / "osm_named_junctions.parquet"
OSM_ROADS_PATH   = DATA_DIR / "osm_roads.parquet"
ALIASES_PATH     = DATA_DIR / "infrastructure_aliases.csv"

# Unified schema column order
COLUMNS = [
    "NAME1",
    "NAME1_UPPER",
    "NAME2",
    "LOCAL_TYPE",
    "TYPE_WEIGHT",
    "GEOMETRY_X",
    "GEOMETRY_Y",
    "MBR_XMIN",
    "MBR_YMIN",
    "MBR_XMAX",
    "MBR_YMAX",
    "OSM_ID",
    "SOURCE",
    "BUILT_AT",
]

KEEP_TYPES = {
    "City", "Suburban Area", "Town", "Village", "Hamlet", "Other Settlement",
    "Named Road", "Numbered Road", "Motorway",
    "Junction", "Roundabout",
    "County", "Unitary Authority", "District Borough",
    "London Borough", "Metropolitan District", "Postcode",
}

# ---------------------------------------------------------------------------
# Source loading helpers
# ---------------------------------------------------------------------------

def _null_mbr_cols(df: pl.DataFrame) -> pl.DataFrame:
    """Add null MBR columns if not already present."""
    for col in ("MBR_XMIN", "MBR_YMIN", "MBR_XMAX", "MBR_YMAX"):
        if col not in df.columns:
            df = df.with_columns(pl.lit(None).cast(pl.Float64).alias(col))
    return df


def load_os_names(built_at: str) -> pl.DataFrame:
    df = pl.read_parquet(OS_NAMES_PATH)

    # Filter to relevant local types only
    df = df.filter(pl.col("LOCAL_TYPE").is_in(KEEP_TYPES))

    # Add null MBR columns (parquet was built before MBR support)
    df = _null_mbr_cols(df)

    df = df.select([
        pl.col("NAME1").cast(pl.Utf8),
        pl.col("NAME1_UPPER").cast(pl.Utf8),
        pl.col("NAME2").fill_null("").cast(pl.Utf8),
        pl.col("LOCAL_TYPE").cast(pl.Utf8),
        pl.col("TYPE_WEIGHT").cast(pl.Int8),
        pl.col("GEOMETRY_X").cast(pl.Float64),
        pl.col("GEOMETRY_Y").cast(pl.Float64),
        pl.col("MBR_XMIN").cast(pl.Float64),
        pl.col("MBR_YMIN").cast(pl.Float64),
        pl.col("MBR_XMAX").cast(pl.Float64),
        pl.col("MBR_YMAX").cast(pl.Float64),
        pl.lit(None).cast(pl.Int64).alias("OSM_ID"),
        pl.lit("os_open_names").cast(pl.Utf8).alias("SOURCE"),
        pl.lit(built_at).cast(pl.Utf8).alias("BUILT_AT"),
    ])
    return df


def load_os_roads(built_at: str) -> pl.DataFrame:
    df = pl.read_parquet(OS_ROADS_PATH)

    df = df.select([
        pl.col("JUNCTION_NUMBER").cast(pl.Utf8).alias("NAME1"),
        pl.col("JUNCTION_NUMBER").str.to_uppercase().alias("NAME1_UPPER"),
        pl.lit("").cast(pl.Utf8).alias("NAME2"),
        pl.lit("Motorway Junction").cast(pl.Utf8).alias("LOCAL_TYPE"),
        pl.lit(9).cast(pl.Int8).alias("TYPE_WEIGHT"),
        pl.col("GEOMETRY_X").cast(pl.Float64),
        pl.col("GEOMETRY_Y").cast(pl.Float64),
        pl.lit(None).cast(pl.Float64).alias("MBR_XMIN"),
        pl.lit(None).cast(pl.Float64).alias("MBR_YMIN"),
        pl.lit(None).cast(pl.Float64).alias("MBR_XMAX"),
        pl.lit(None).cast(pl.Float64).alias("MBR_YMAX"),
        pl.lit(None).cast(pl.Int64).alias("OSM_ID"),
        pl.lit("os_open_roads").cast(pl.Utf8).alias("SOURCE"),
        pl.lit(built_at).cast(pl.Utf8).alias("BUILT_AT"),
    ])
    return df


def load_osm_junctions(built_at: str) -> pl.DataFrame:
    df = pl.read_parquet(OSM_PATH)

    # Ensure NAME2 exists; fill nulls
    if "NAME2" not in df.columns:
        df = df.with_columns(pl.lit("").cast(pl.Utf8).alias("NAME2"))

    df = df.select([
        pl.col("NAME1").cast(pl.Utf8),
        pl.col("NAME1_UPPER").cast(pl.Utf8),
        pl.col("NAME2").fill_null("").cast(pl.Utf8),
        pl.col("LOCAL_TYPE").cast(pl.Utf8),
        pl.col("TYPE_WEIGHT").cast(pl.Int8),
        pl.col("GEOMETRY_X").cast(pl.Float64),
        pl.col("GEOMETRY_Y").cast(pl.Float64),
        pl.lit(None).cast(pl.Float64).alias("MBR_XMIN"),
        pl.lit(None).cast(pl.Float64).alias("MBR_YMIN"),
        pl.lit(None).cast(pl.Float64).alias("MBR_XMAX"),
        pl.lit(None).cast(pl.Float64).alias("MBR_YMAX"),
        (
            pl.col("OSM_ID").cast(pl.Int64)
            if "OSM_ID" in df.columns
            else pl.lit(None).cast(pl.Int64).alias("OSM_ID")
        ),
        pl.lit("osm").cast(pl.Utf8).alias("SOURCE"),
        pl.lit(built_at).cast(pl.Utf8).alias("BUILT_AT"),
    ])
    return df


def load_osm_roads(built_at: str) -> pl.DataFrame:
    df = pl.read_parquet(OSM_ROADS_PATH)

    df = df.select([
        pl.col("NAME1").cast(pl.Utf8),
        pl.col("NAME1_UPPER").cast(pl.Utf8),
        pl.col("NAME2").fill_null("").cast(pl.Utf8),
        pl.col("LOCAL_TYPE").cast(pl.Utf8),
        pl.col("TYPE_WEIGHT").cast(pl.Int8),
        pl.col("GEOMETRY_X").cast(pl.Float64),
        pl.col("GEOMETRY_Y").cast(pl.Float64),
        pl.lit(None).cast(pl.Float64).alias("MBR_XMIN"),
        pl.lit(None).cast(pl.Float64).alias("MBR_YMIN"),
        pl.lit(None).cast(pl.Float64).alias("MBR_XMAX"),
        pl.lit(None).cast(pl.Float64).alias("MBR_YMAX"),
        pl.col("OSM_ID").cast(pl.Int64),
        pl.lit("osm_roads").cast(pl.Utf8).alias("SOURCE"),
        pl.lit(built_at).cast(pl.Utf8).alias("BUILT_AT"),
    ])
    return df


def load_aliases(built_at: str) -> pl.DataFrame:
    df = pl.read_csv(ALIASES_PATH, comment_prefix="#")
    df = df.filter(pl.col("lat").is_not_null() & pl.col("lon").is_not_null())

    transformer = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)
    rows = []
    for row in df.iter_rows(named=True):
        lon = float(row["lon"])
        lat = float(row["lat"])
        easting, northing = transformer.transform(lon, lat)
        rows.append({
            "NAME1": row["name"],
            "NAME1_UPPER": row["name"].upper(),
            "NAME2": "",
            "LOCAL_TYPE": row["category"],
            "TYPE_WEIGHT": 10,
            "GEOMETRY_X": easting,
            "GEOMETRY_Y": northing,
            "MBR_XMIN": None,
            "MBR_YMIN": None,
            "MBR_XMAX": None,
            "MBR_YMAX": None,
            "OSM_ID": None,
            "SOURCE": "alias",
            "BUILT_AT": built_at,
        })

    if not rows:
        return pl.DataFrame(schema={
            "NAME1": pl.Utf8,
            "NAME1_UPPER": pl.Utf8,
            "NAME2": pl.Utf8,
            "LOCAL_TYPE": pl.Utf8,
            "TYPE_WEIGHT": pl.Int8,
            "GEOMETRY_X": pl.Float64,
            "GEOMETRY_Y": pl.Float64,
            "MBR_XMIN": pl.Float64,
            "MBR_YMIN": pl.Float64,
            "MBR_XMAX": pl.Float64,
            "MBR_YMAX": pl.Float64,
            "OSM_ID": pl.Int64,
            "SOURCE": pl.Utf8,
            "BUILT_AT": pl.Utf8,
        })

    return pl.DataFrame(rows).select([
        pl.col("NAME1").cast(pl.Utf8),
        pl.col("NAME1_UPPER").cast(pl.Utf8),
        pl.col("NAME2").cast(pl.Utf8),
        pl.col("LOCAL_TYPE").cast(pl.Utf8),
        pl.col("TYPE_WEIGHT").cast(pl.Int8),
        pl.col("GEOMETRY_X").cast(pl.Float64),
        pl.col("GEOMETRY_Y").cast(pl.Float64),
        pl.col("MBR_XMIN").cast(pl.Float64),
        pl.col("MBR_YMIN").cast(pl.Float64),
        pl.col("MBR_XMAX").cast(pl.Float64),
        pl.col("MBR_YMAX").cast(pl.Float64),
        pl.col("OSM_ID").cast(pl.Int64),
        pl.col("SOURCE").cast(pl.Utf8),
        pl.col("BUILT_AT").cast(pl.Utf8),
    ])


# ---------------------------------------------------------------------------
# Part 1: Combined parquet
# ---------------------------------------------------------------------------

def build_combined() -> pl.DataFrame:
    required_paths = (OS_NAMES_PATH, OS_ROADS_PATH, OSM_PATH, OSM_ROADS_PATH, ALIASES_PATH)
    missing = [p for p in required_paths if not p.exists()]
    if missing:
        for p in missing:
            print(f"ERROR: Missing required parquet: {p}", file=sys.stderr)
        print(
            "\nRun the download scripts first:\n"
            "  python scripts/download_os_open_names.py\n"
            "  python scripts/download_os_open_roads.py\n"
            "  python scripts/download_osm_named_junctions.py\n"
            "  python scripts/download_osm_roads.py\n"
            "  python scripts/build_infrastructure_aliases.py",
            file=sys.stderr,
        )
        sys.exit(1)

    built_at = date.today().isoformat()
    print(f"Building combined dataset (built_at={built_at}) ...")

    print("  Loading OS Open Names ...", end=" ", flush=True)
    os_names_df = load_os_names(built_at)
    print(f"{len(os_names_df):,} rows")

    print("  Loading OS Open Roads junctions ...", end=" ", flush=True)
    os_roads_df = load_os_roads(built_at)
    print(f"{len(os_roads_df):,} rows")

    print("  Loading OSM named junctions ...", end=" ", flush=True)
    osm_df = load_osm_junctions(built_at)
    print(f"{len(osm_df):,} rows")

    print("  Loading OSM road segments ...", end=" ", flush=True)
    osm_roads_df = load_osm_roads(built_at)
    print(f"{len(osm_roads_df):,} rows")

    print("  Loading infrastructure aliases ...", end=" ", flush=True)
    aliases_df = load_aliases(built_at)
    print(f"{len(aliases_df):,} rows")

    df = pl.concat(
        [os_names_df, os_roads_df, osm_df, osm_roads_df, aliases_df],
        rechunk=True,
    )
    df = df.select(COLUMNS)

    return (
        df,
        len(os_names_df),
        len(os_roads_df),
        len(osm_df),
        len(osm_roads_df),
        len(aliases_df),
        built_at,
    )


def print_summary(
    df: pl.DataFrame,
    n_names: int,
    n_roads: int,
    n_osm: int,
    n_osm_roads: int,
    n_aliases: int,
    out_path: Path,
) -> None:
    size_mb = out_path.stat().st_size / 1e6 if out_path.exists() else 0.0
    built_at = df["BUILT_AT"][0] if len(df) > 0 else "unknown"

    print()
    print("ukgeo combined dataset")
    print("=" * 40)
    print(f"Total rows:         {len(df):>11,}")
    print(f"  OS Open Names:    {n_names:>11,}")
    print(f"  OS Open Roads:    {n_roads:>11,}")
    print(f"  OSM junctions:    {n_osm:>11,}")
    print(f"  OSM road segs:    {n_osm_roads:>11,}")
    print(f"  Aliases:          {n_aliases:>11,}")
    print()
    print("LOCAL_TYPE breakdown:")
    counts = (
        df.group_by("LOCAL_TYPE")
        .len()
        .sort("len", descending=True)
    )
    for row in counts.iter_rows(named=True):
        print(f"  {row['LOCAL_TYPE']:<28}  {row['len']:>9,}")
    print()
    print(f"File size:          {size_mb:>9.1f} MB")
    print(f"Built:              {built_at}")
    print()


# ---------------------------------------------------------------------------
# Part 2: Kaggle metadata files
# ---------------------------------------------------------------------------

METADATA = {
    "title": "ukgeo UK Geocoding Reference Data",
    "id": "thomassimm/ukgeo-combined-dataset",
    "licenses": [{"name": "ODbL-1.0"}],
    "keywords": [
        "geocoding",
        "united-kingdom",
        "road-safety",
        "openstreetmap",
        "ordnance-survey",
        "geospatial",
        "transportation",
        "python",
    ],
}

README_CONTENT = """\
# ukgeo — UK Geocoding Reference Data

Combined geocoding reference dataset for Great Britain, built from three open data sources
and formatted for use with the [ukgeo Python geocoder](https://github.com/ThomasHSimm/ukgeo).

## What this dataset contains

A single parquet file (`ukgeo_data.parquet`) combining:

| Source | Rows (approx) | Content |
|---|---|---|
| OS Open Names | 2,670,000 | Places, towns, villages, roads, postcodes (OGL) |
| OS Open Roads | 669 | Motorway junction point locations (OGL) |
| OpenStreetMap | ~3,000 | Named interchanges and roundabouts (ODbL) |
| OpenStreetMap | ~105,000 | B-road way segments (ODbL) |
| Curated aliases | ~35 | Named infrastructure aliases (mixed source/manual) |

## Schema

| Column | Type | Description |
|---|---|---|
| `NAME1` | str | Primary name |
| `NAME1_UPPER` | str | Uppercased NAME1 for lookup |
| `NAME2` | str | Secondary/alias name (empty string if none) |
| `LOCAL_TYPE` | str | Feature type (Town, Junction, Named Roundabout, etc.) |
| `TYPE_WEIGHT` | int8 | Scoring weight — higher = preferred candidate |
| `GEOMETRY_X` | float64 | BNG Easting (EPSG:27700) |
| `GEOMETRY_Y` | float64 | BNG Northing (EPSG:27700) |
| `MBR_XMIN` | float64 | Bounding box min easting (null for point features) |
| `MBR_YMIN` | float64 | Bounding box min northing (null for point features) |
| `MBR_XMAX` | float64 | Bounding box max easting (null for point features) |
| `MBR_YMAX` | float64 | Bounding box max northing (null for point features) |
| `OSM_ID` | int64 | OpenStreetMap way/node id when available |
| `SOURCE` | str | `os_open_names`, `os_open_roads`, `osm`, `osm_roads`, or `alias` |
| `BUILT_AT` | str | ISO date this file was built |

## Coordinate reference system

All coordinates are in **British National Grid (BNG, EPSG:27700)** — eastings and northings
in metres. Use `pyproj` to convert to WGS84 (EPSG:4326) lat/lon:

```python
from pyproj import Transformer
t = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
lon, lat = t.transform(easting, northing)
```

## Licence

This dataset is released under the **Open Database Licence (ODbL) v1.0**.

Attribution required:
- Contains OS data © Crown Copyright and database right 2024
- © OpenStreetMap contributors

## Usage with ukgeo

```python
# Download ukgeo_data.parquet from Kaggle, place in data/
from ukgeo import Geocoder
geo = Geocoder()  # auto-detects ukgeo_data.parquet if present
result = geo.geocode("M62 Junction 26")
```

## Source data

| Dataset | Publisher | Licence | Update frequency |
|---|---|---|---|
| OS Open Names | Ordnance Survey | OGL v3 | Quarterly |
| OS Open Roads | Ordnance Survey | OGL v3 | 6-monthly |
| OpenStreetMap | OSM contributors | ODbL v1.0 | Continuous (snapshot) |

## Related

- [ukgeo GitHub repo](https://github.com/ThomasHSimm/ukgeo)
- [Open Road Risk](https://github.com/ThomasHSimm/open-road-risk)
"""


def write_metadata(out_parquet: Path) -> None:
    KAGGLE_DIR.mkdir(parents=True, exist_ok=True)

    OUT_METADATA.write_text(json.dumps(METADATA, indent=2))
    print(f"Wrote {OUT_METADATA}")

    OUT_README.write_text(README_CONTENT)
    print(f"Wrote {OUT_README}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Upload to Kaggle after building (requires kaggle CLI configured)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    KAGGLE_DIR.mkdir(parents=True, exist_ok=True)

    df, n_names, n_roads, n_osm, n_osm_roads, n_aliases, built_at = build_combined()

    # Print summary before writing
    # Temporarily write to a buffer to get size, then finalize
    print("\nWriting parquet ...")
    df.write_parquet(OUT_PARQUET, compression="zstd")

    print_summary(df, n_names, n_roads, n_osm, n_osm_roads, n_aliases, OUT_PARQUET)
    print(f"Saved to {OUT_PARQUET}")

    write_metadata(OUT_PARQUET)

    if args.upload:
        print("\nUploading to Kaggle...")
        kaggle_dir = OUT_PARQUET.parent
        result = subprocess.run(
            [
                "kaggle",
                "datasets",
                "version",
                "-p",
                str(kaggle_dir),
                "-m",
                f"v0.4.0 built {built_at} — aliases included",
            ],
            capture_output=True,
            text=True,
        )
        print(result.stdout)
        if result.returncode != 0:
            print(f"Upload failed:\n{result.stderr}", file=sys.stderr)
            sys.exit(1)
        print("Upload complete.")


if __name__ == "__main__":
    main()
