"""
One-time setup: download OS Open Roads GeoPackage, extract the
motorway_junction layer, convert to parquet for fast in-process querying.

Usage:
    python scripts/download_os_open_roads.py

OS Open Roads is published under the Open Government Licence.
Download page: https://osdatahub.os.uk/downloads/open/OpenRoads
Updated every 6 months (April and October).

The motorway_junction layer contains ~669 features with:
  - junction_number: e.g. "M62 J26"
  - geometry: point in BNG (EPSG:27700)
"""

import io
import sys
import zipfile
from pathlib import Path

import httpx
import polars as pl
import pyogrio

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OS_OPEN_ROADS_URL = (
    "https://api.os.uk/downloads/v1/products/OpenRoads/downloads?"
    "area=GB&format=GeoPackage&redirect"
)
DATA_DIR = Path(__file__).parent.parent / "data"
OUT_PATH = DATA_DIR / "os_open_roads_junctions.parquet"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _progress(msg: str):
    print(msg, flush=True)


def download_gpkg(url: str) -> bytes:
    _progress(f"Downloading OS Open Roads from {url} ...")
    buf = bytearray()
    with httpx.stream("GET", url, follow_redirects=True, timeout=300) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        received = 0
        for chunk in r.iter_bytes(chunk_size=1 << 20):
            buf.extend(chunk)
            received += len(chunk)
            if total:
                pct = received / total * 100
                print(f"\r  {pct:.1f}%  ({received // (1<<20)} MB)", end="", flush=True)
    print()
    return bytes(buf)


def extract_junctions(raw: bytes) -> pl.DataFrame:
    """
    Extract the motorway_junction layer from the GeoPackage zip using pyogrio.
    """
    _progress("Extracting motorway_junction layer ...")

    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        gpkg_files = [f for f in zf.namelist() if f.endswith(".gpkg")]
        if not gpkg_files:
            raise ValueError("No .gpkg file found in downloaded zip")
        gpkg_name = gpkg_files[0]
        _progress(f"  Found GeoPackage: {gpkg_name}")
        gpkg_bytes = zf.read(gpkg_name)

    tmp = DATA_DIR / "_tmp_openroads.gpkg"
    tmp.write_bytes(gpkg_bytes)

    try:
        layers = pyogrio.list_layers(str(tmp))
        _progress(f"  Layers: {[l[0] for l in layers]}")

        junction_layer = next(
            (l[0] for l in layers if "junction" in l[0].lower()),
            None
        )
        if not junction_layer:
            raise ValueError(f"No junction layer found. Layers: {layers}")

        _progress(f"  Reading layer: {junction_layer}")
        gdf = pyogrio.read_dataframe(str(tmp), layer=junction_layer)
        _progress(f"  {len(gdf)} junction features found")
        _progress(f"  Columns: {list(gdf.columns)}")
    finally:
        tmp.unlink(missing_ok=True)

    # Extract point coordinates from geometry
    gdf["GEOMETRY_X"] = gdf.geometry.x
    gdf["GEOMETRY_Y"] = gdf.geometry.y

    # Normalise junction_number column name
    rename = {}
    for col in gdf.columns:
        if "junction" in col.lower() and "number" in col.lower():
            rename[col] = "JUNCTION_NUMBER"
    gdf = gdf.rename(columns=rename)

    keep = [c for c in ["JUNCTION_NUMBER", "GEOMETRY_X", "GEOMETRY_Y"] if c in gdf.columns]
    df = pl.from_pandas(gdf[keep])

    if "JUNCTION_NUMBER" in df.columns:
        df = df.with_columns(
            pl.col("JUNCTION_NUMBER").cast(pl.Utf8).str.to_uppercase().alias("JUNCTION_NUMBER")
        )

    return df


def build_parquet(df: pl.DataFrame, out_path: Path):
    _progress(f"Writing parquet to {out_path} ...")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(out_path, compression="zstd")
    size_mb = out_path.stat().st_size / (1 << 20)
    _progress(f"Done. {out_path} ({size_mb:.2f} MB, {len(df)} junctions)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if OUT_PATH.exists():
        ans = input(f"{OUT_PATH} already exists. Re-download? [y/N] ").strip().lower()
        if ans != "y":
            sys.exit(0)

    raw = download_gpkg(OS_OPEN_ROADS_URL)
    df = extract_junctions(raw)

    if df.is_empty():
        _progress("No junction data extracted — check the download.")
        sys.exit(1)

    build_parquet(df, OUT_PATH)
    _progress("\nSample output:")
    print(df.head(10))