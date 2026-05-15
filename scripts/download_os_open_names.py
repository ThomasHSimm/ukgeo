"""
One-time setup: download OS Open Names, filter to relevant local types,
convert BNG to parquet for fast in-process querying.

Usage:
    python scripts/download_os_open_names.py

OS Open Names is published under the Open Government Licence.
Download page: https://osdatahub.os.uk/downloads/open/OpenNames
"""

import zipfile
import io
import sys
from pathlib import Path

import httpx
import polars as pl

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OS_OPEN_NAMES_URL = (
    "https://api.os.uk/downloads/v1/products/OpenNames/downloads?"
    "area=GB&format=CSV&redirect"
)
DATA_DIR = Path(__file__).parent.parent / "data"
OUT_PATH = DATA_DIR / "os_open_names.parquet"

# Local types to keep (mirrors lookup.py ALL_TYPES)
KEEP_TYPES = {
    "City", "Suburban Area",
    "Town", "Village", "Hamlet", "Other Settlement",
    "Named Road", "Numbered Road", "Motorway",
    "Junction", "Roundabout",
    "County", "Unitary Authority", "District Borough",
    "London Borough", "Metropolitan District",
    "Postcode",
}

TYPE_WEIGHT = {
    "City": 10, "Suburban Area": 7,
    "Town": 8, "Village": 6, "Hamlet": 4, "Other Settlement": 3,
    "Junction": 9, "Roundabout": 8,
    "Named Road": 5, "Numbered Road": 5, "Motorway": 6,
    "County": 2, "Unitary Authority": 2, "District Borough": 2,
    "London Borough": 2, "Metropolitan District": 2,
    "Postcode": 1,
}

# OS Open Names CSV has no header — these are the column positions
# Reference: OS Open Names product specification
COLNAMES = [
    "ID", "NAMES_URI", "NAME1", "NAME1_LANG", "NAME2", "NAME2_LANG",
    "TYPE", "LOCAL_TYPE", "GEOMETRY_X", "GEOMETRY_Y",
    "MOST_DETAIL_VIEW_RES", "LEAST_DETAIL_VIEW_RES",
    "MBR_XMIN", "MBR_YMIN", "MBR_XMAX", "MBR_YMAX",
    "POSTCODE_DISTRICT", "POPULATED_PLACE", "POPULATED_PLACE_URI",
    "POPULATED_PLACE_TYPE", "DISTRICT_BOROUGH", "DISTRICT_BOROUGH_URI",
    "DISTRICT_BOROUGH_TYPE", "COUNTY_UNITARY", "COUNTY_UNITARY_URI",
    "COUNTY_UNITARY_TYPE", "REGION", "COUNTRY", "RELATED_SPATIAL_OBJECT",
    "SAME_AS_DBPEDIA", "SAME_AS_GEONAMES",
]

KEEP_COLS = [
    "NAME1", "NAME1_LANG", "NAME2", "TYPE", "LOCAL_TYPE",
    "GEOMETRY_X", "GEOMETRY_Y",
    "COUNTY_UNITARY", "DISTRICT_BOROUGH", "POPULATED_PLACE",
    "POSTCODE_DISTRICT", "REGION",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _progress(msg: str):
    print(msg, flush=True)


def download_and_extract(url: str) -> list[pl.DataFrame]:
    """Stream-download the OS Open Names zip and parse all CSVs inside."""
    _progress(f"Downloading OS Open Names from {url} ...")
    chunks = []
    with httpx.stream("GET", url, follow_redirects=True, timeout=120) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        received = 0
        buf = bytearray()
        for chunk in r.iter_bytes(chunk_size=1 << 20):
            buf.extend(chunk)
            received += len(chunk)
            if total:
                pct = received / total * 100
                print(f"\r  {pct:.1f}%  ({received // (1<<20)} MB)", end="", flush=True)
    print()
    _progress("Parsing CSVs inside zip ...")

    dfs = []
    with zipfile.ZipFile(io.BytesIO(bytes(buf))) as zf:
        csv_files = [f for f in zf.namelist() if f.endswith(".csv")]
        _progress(f"  Found {len(csv_files)} CSV files.")
        for i, name in enumerate(csv_files, 1):
            print(f"\r  Processing {i}/{len(csv_files)}: {name}", end="", flush=True)
            with zf.open(name) as f:
                try:
                    df = pl.read_csv(
                        f,
                        has_header=False,
                        new_columns=COLNAMES,
                        infer_schema_length=1000,
                        ignore_errors=True,
                    )
                    df = df.filter(pl.col("LOCAL_TYPE").is_in(KEEP_TYPES))
                    df = df.select(KEEP_COLS)
                    if len(df) > 0:
                        dfs.append(df)
                except Exception as e:
                    print(f"\n  Warning: skipped {name} ({e})")
    print()
    return dfs


def build_parquet(dfs: list[pl.DataFrame], out_path: Path):
    _progress("Concatenating and enriching ...")
    df = pl.concat(dfs, rechunk=True)

    df = df.with_columns([
        pl.col("NAME1").str.to_uppercase().alias("NAME1_UPPER"),
        pl.col("NAME2").fill_null("").str.to_uppercase().alias("NAME2_UPPER"),
        pl.col("LOCAL_TYPE").replace(TYPE_WEIGHT).cast(pl.Int8).alias("TYPE_WEIGHT"),
        pl.col("GEOMETRY_X").cast(pl.Float64),
        pl.col("GEOMETRY_Y").cast(pl.Float64),
    ])

    _progress(f"  {len(df):,} rows retained across {df['LOCAL_TYPE'].n_unique()} local types.")
    _progress(f"Writing parquet to {out_path} ...")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(out_path, compression="zstd")
    size_mb = out_path.stat().st_size / (1 << 20)
    _progress(f"Done. {out_path} ({size_mb:.1f} MB)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if OUT_PATH.exists():
        ans = input(f"{OUT_PATH} already exists. Re-download? [y/N] ").strip().lower()
        if ans != "y":
            sys.exit(0)

    dfs = download_and_extract(OS_OPEN_NAMES_URL)
    if not dfs:
        print("No data extracted — check the download URL or your internet connection.")
        sys.exit(1)

    build_parquet(dfs, OUT_PATH)
