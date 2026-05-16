"""
Download the most recent STATS19 collision CSV, synthesise free-text location
strings from road and junction fields, geocode with ukgeo, and write a benchmark
report comparing predictions against ground-truth coordinates.

Usage:
    python scripts/build_stats19_eval.py

Outputs:
    data/stats19_collisions.csv   — raw STATS19 download (skipped if present)
    data/stats19_benchmark.csv    — full geocoded results with distances
"""

import math
import re
import sys
import warnings
from pathlib import Path

import httpx
import polars as pl

# ---------------------------------------------------------------------------
# Paths and config
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent.parent / "data"
COLLISIONS_PATH = DATA_DIR / "stats19_collisions.csv"
BENCHMARK_PATH  = DATA_DIR / "stats19_benchmark.csv"

STATS_PAGE = "https://www.gov.uk/government/statistics/road-safety-data"
SAMPLE_N   = 5000
RANDOM_SEED = 42

# ---------------------------------------------------------------------------
# STATS19 field decoders
# ---------------------------------------------------------------------------

# first_road_class / second_road_class codes
# 1=Motorway  2=A(M)  3=A  4=B  5=C  6=Unclassified
_ROAD_PREFIX = {"1": "M", "2": "A", "3": "A", "4": "B", "5": "C"}
_ROAD_SUFFIX = {"2": "(M)"}  # class 2 = A(M) motorway

# junction_detail codes → human-readable qualifier
# 0 / -1 → skip (not at junction / missing)
_JUNCTION_LABEL = {
    "1":  "roundabout",
    "2":  "mini-roundabout",
    "3":  "junction",
    "5":  "slip road junction",
    "6":  "junction",
    "7":  "junction",
    "8":  "junction",
    "9":  "junction",
    "13": "junction",
    "16": "junction",
}
_JUNCTION_SKIP = {"-1", "0"}


def _road_ref(road_class: str, road_number: str) -> str:
    """Return a road reference string like 'M62', 'A64', 'B6265' or ''."""
    prefix = _ROAD_PREFIX.get(road_class, "")
    if not prefix:
        return ""
    num = road_number.strip()
    if not num or num in ("-1", "0"):
        return ""
    suffix = _ROAD_SUFFIX.get(road_class, "")
    return f"{prefix}{num}{suffix}"


def make_location_string(
    first_road_class: str,
    first_road_number: str,
    second_road_class: str,
    second_road_number: str,
    junction_detail: str,
) -> str:
    parts = []

    road1 = _road_ref(first_road_class, first_road_number)
    if road1:
        parts.append(road1)

    # When a second road is present it pins a specific junction
    road2 = _road_ref(second_road_class, second_road_number)
    if road2 and road2 != road1:
        parts.append(road2)

    if parts:  # only add junction qualifier when we have at least one road reference
        junc = _JUNCTION_LABEL.get(junction_detail, "") if junction_detail not in _JUNCTION_SKIP else ""
        if junc and not road2:
            # Only append junction type when we don't already have two roads
            parts.append(junc)

    return " ".join(parts).strip()


# ---------------------------------------------------------------------------
# Step 1 — Download
# ---------------------------------------------------------------------------

def find_most_recent_collision_url() -> str:
    """
    Fetch the gov.uk road-safety-data statistics page and return the URL
    of the most recent finalised (non-provisional) collision CSV.
    Falls back to the 2024 known URL if scraping fails.
    """
    try:
        resp = httpx.get(STATS_PAGE, timeout=20, follow_redirects=True)
        resp.raise_for_status()
    except Exception as exc:
        warnings.warn(f"Could not fetch stats page ({exc}), falling back to 2024 URL")
        return "https://data.dft.gov.uk/road-accidents-safety-data/dft-road-casualty-statistics-collision-2024.csv"

    pattern = re.compile(
        r"https://data\.dft\.gov\.uk/road-accidents-safety-data/"
        r"dft-road-casualty-statistics-collision-(\d{4})\.csv"
    )
    matches = pattern.findall(resp.text)
    if not matches:
        warnings.warn("No collision CSV links found on stats page, using 2024 URL")
        return "https://data.dft.gov.uk/road-accidents-safety-data/dft-road-casualty-statistics-collision-2024.csv"

    most_recent_year = max(int(y) for y in matches)
    return (
        "https://data.dft.gov.uk/road-accidents-safety-data/"
        f"dft-road-casualty-statistics-collision-{most_recent_year}.csv"
    )


def download_stats19() -> Path:
    if COLLISIONS_PATH.exists():
        print(f"Skipping download — {COLLISIONS_PATH} already present.")
        return COLLISIONS_PATH

    url = find_most_recent_collision_url()
    print(f"Downloading STATS19 collisions from:\n  {url}")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with httpx.stream("GET", url, timeout=120, follow_redirects=True) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            with open(COLLISIONS_PATH, "wb") as fh:
                for chunk in resp.iter_bytes(chunk_size=65536):
                    fh.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = downloaded / total * 100
                        print(f"  {downloaded / 1e6:.1f} MB / {total / 1e6:.1f} MB ({pct:.0f}%)\r", end="", flush=True)
        print(f"\n  Saved to {COLLISIONS_PATH}")
    except Exception as exc:
        COLLISIONS_PATH.unlink(missing_ok=True)
        print(f"Download failed: {exc}", file=sys.stderr)
        sys.exit(1)

    return COLLISIONS_PATH


# ---------------------------------------------------------------------------
# Step 2 — Synthesise location strings
# ---------------------------------------------------------------------------

def build_location_df() -> pl.DataFrame:
    print("Loading STATS19 collisions ...")
    df = pl.read_csv(
        COLLISIONS_PATH,
        infer_schema_length=0,   # read all as strings first
        null_values=["-1", ""],
    )
    print(f"  Loaded {len(df):,} rows, {len(df.columns)} columns")

    # Ensure required columns exist (graceful handling across years)
    required = {
        "first_road_class", "first_road_number",
        "second_road_class", "second_road_number",
        "junction_detail", "latitude", "longitude",
    }
    missing = required - set(df.columns)
    if missing:
        print(f"Missing expected columns: {missing}", file=sys.stderr)
        sys.exit(1)

    # Fill nulls with sentinels for string ops
    df = df.with_columns([
        pl.col("first_road_class").fill_null("-1"),
        pl.col("first_road_number").fill_null("-1"),
        pl.col("second_road_class").fill_null("-1"),
        pl.col("second_road_number").fill_null("-1"),
        pl.col("junction_detail").fill_null("-1"),
    ])

    # Convert lat/lon to float, drop bad rows
    df = df.with_columns([
        pl.col("latitude").cast(pl.Float64, strict=False),
        pl.col("longitude").cast(pl.Float64, strict=False),
    ]).filter(
        pl.col("latitude").is_not_null()
        & pl.col("longitude").is_not_null()
        & (pl.col("latitude") != 0.0)
        & (pl.col("longitude") != 0.0)
    )

    print(f"  After coord filter: {len(df):,} rows")

    # Synthesise location strings row-by-row via map_elements
    print("  Synthesising location strings ...")
    location_series = pl.Series(
        "input",
        [
            make_location_string(
                row["first_road_class"],
                row["first_road_number"],
                row["second_road_class"],
                row["second_road_number"],
                row["junction_detail"],
            )
            for row in df.iter_rows(named=True)
        ],
    )
    df = df.with_columns(location_series)

    # Filter short / empty strings
    df = df.filter(pl.col("input").str.len_chars() >= 5)
    print(f"  After location-string filter: {len(df):,} rows")

    # Keep only what we need
    df = df.select(["input", "latitude", "longitude"])

    # Sample
    if len(df) > SAMPLE_N:
        df = df.sample(n=SAMPLE_N, seed=RANDOM_SEED, shuffle=True)
        print(f"  Sampled {SAMPLE_N} rows (seed {RANDOM_SEED})")

    return df


# ---------------------------------------------------------------------------
# Haversine
# ---------------------------------------------------------------------------

def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Step 3 — Geocode
# ---------------------------------------------------------------------------

def geocode(location_df: pl.DataFrame) -> pl.DataFrame:
    from ukgeo import Geocoder

    print(f"\nGeocoding {len(location_df):,} inputs ...")
    geo = Geocoder()
    results = geo.geocode_batch(location_df["input"].to_list(), show_progress=True)

    # Join true coords back
    joined = location_df.with_columns([
        pl.col("latitude").alias("true_lat"),
        pl.col("longitude").alias("true_lon"),
    ]).drop(["latitude", "longitude"])

    joined = joined.with_columns([
        results["lat"].alias("pred_lat"),
        results["lon"].alias("pred_lon"),
        results["confidence"],
        results["level_resolved"],
    ])

    # Resolved flag
    joined = joined.with_columns(
        (pl.col("pred_lat").is_not_null() & (pl.col("pred_lat") != 0.0)).alias("resolved")
    )

    # Haversine distance (only for resolved rows)
    distances = []
    for row in joined.iter_rows(named=True):
        if row["resolved"]:
            d = haversine_m(row["true_lat"], row["true_lon"], row["pred_lat"], row["pred_lon"])
        else:
            d = float("nan")
        distances.append(d)

    joined = joined.with_columns(pl.Series("distance_m", distances, dtype=pl.Float64))
    return joined


# ---------------------------------------------------------------------------
# Step 4 — Benchmark report
# ---------------------------------------------------------------------------

def _pct(n: int, total: int) -> str:
    return f"{n / total * 100:.1f}%" if total else "n/a"


def _median(vals: list[float]) -> float:
    if not vals:
        return float("nan")
    s = sorted(vals)
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2


def print_report(df: pl.DataFrame) -> None:
    total     = len(df)
    resolved  = df.filter(pl.col("resolved"))
    unresolved = df.filter(~pl.col("resolved"))

    n_res   = len(resolved)
    n_unres = len(unresolved)

    dists = [r for r in resolved["distance_m"].to_list() if not math.isnan(r)]
    mean_d  = sum(dists) / len(dists) if dists else float("nan")

    def within(m: float) -> int:
        return sum(1 for d in dists if d <= m)

    print()
    print("STATS19 Benchmark — ukgeo")
    print("=" * 41)
    print(f"Total inputs:        {total:>5}")
    print(f"Resolved:            {n_res:>5} ({_pct(n_res, total)})")
    print(f"Unresolved:          {n_unres:>5} ({_pct(n_unres, total)})")
    print()
    print("Distance errors (resolved only):")
    print(f"  Median:           {_median(dists):>6.0f} m")
    print(f"  Mean:             {mean_d:>6.0f} m")
    for thresh in [500, 1000, 5000, 10000]:
        n = within(thresh)
        print(f"  Within {thresh:>6}m:   {n:>5} ({_pct(n, n_res)})")
    print()
    print("By confidence:")
    for conf in ["High", "Medium", "Low"]:
        sub = resolved.filter(pl.col("confidence") == conf)
        sub_dists = [d for d in sub["distance_m"].to_list() if not math.isnan(d)]
        med = f"{_median(sub_dists):.0f} m" if sub_dists else "n/a"
        print(f"  {conf:<7}: {len(sub):>5} resolved, median {med}")
    print()
    print("By level resolved:")
    for lvl, label in [(1, "Level 1 (postcode/regex)"), (2, "Level 2 (OS Names)")]:
        n = len(df.filter(pl.col("level_resolved") == lvl))
        print(f"  {label}:  {n:>5}")
    n_unres_lvl = len(df.filter(pl.col("level_resolved").is_null() | (pl.col("level_resolved") == 0)))
    print(f"  Unresolved:                  {n_unres_lvl:>5}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    download_stats19()
    location_df = build_location_df()
    result_df   = geocode(location_df)

    # Save benchmark CSV
    result_df.write_csv(BENCHMARK_PATH)
    print(f"\nSaved full results to {BENCHMARK_PATH}")

    print_report(result_df)
    print("First 10 rows:")
    print(result_df.select(["input", "true_lat", "true_lon", "pred_lat", "pred_lon", "distance_m", "confidence", "level_resolved", "resolved"]).head(10))


if __name__ == "__main__":
    main()
