"""
ukgeo command-line interface.

Usage examples:
    ukgeo geocode "M62 Junction 26"
    ukgeo geocode locations.csv --output results.csv
    ukgeo geocode locations.csv --output results.csv --domain road_safety
    ukgeo geocode locations.csv --column address --output results.csv
    ukgeo geocode locations.csv --max-level 3
    ukgeo info
"""

import argparse
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=UserWarning, module="requests")
warnings.filterwarnings(
    "ignore",
    message="Unable to find acceptable character detection dependency.*",
    category=Warning,
    module="requests",
)


def cmd_geocode(args) -> int:
    """Geocode a single string or a CSV file."""
    from ukgeo import Geocoder

    # Load domain qualifier config if specified
    extra_qualifiers = []
    if args.domain:
        import yaml

        domain_path = Path(__file__).parent.parent / "config" / f"domain_{args.domain}.yaml"
        if not domain_path.exists():
            print(f"Error: domain config not found: {domain_path}", file=sys.stderr)
            return 1
        with open(domain_path) as f:
            cfg = yaml.safe_load(f)
        extra_qualifiers = cfg.get("extra_qualifiers", [])

    geo = Geocoder(
        max_level=args.max_level,
        extra_qualifiers=extra_qualifiers or None,
    )

    # --- Single string mode ---
    if not args.input.endswith(".csv") and not Path(args.input).exists():
        result = geo.geocode(args.input)
        if result.resolved:
            print(f"lat:        {result.lat}")
            print(f"lon:        {result.lon}")
            print(f"confidence: {result.confidence}")
            print(f"interpreted:{result.interpreted_as}")
            print(f"level:      {result.level_resolved}")
            print(f"notes:      {result.notes}")
        else:
            print(f"Unresolved: {result.notes}", file=sys.stderr)
            return 1
        return 0

    # --- CSV file mode ---
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: input file not found: {input_path}", file=sys.stderr)
        return 1

    import polars as pl

    df = pl.read_csv(input_path)

    # Detect column
    col = args.column
    if col is None:
        # Auto-detect: first string column
        str_cols = [c for c, t in zip(df.columns, df.dtypes) if str(t) == "String"]
        if not str_cols:
            print("Error: no string column found. Use --column to specify.", file=sys.stderr)
            return 1
        col = str_cols[0]
        print(f"Auto-detected input column: '{col}'", file=sys.stderr)

    if col not in df.columns:
        print(f"Error: column '{col}' not found. Available: {df.columns}", file=sys.stderr)
        return 1

    inputs = df[col].to_list()
    print(f"Geocoding {len(inputs)} rows from '{col}'...", file=sys.stderr)

    t0 = time.time()
    results_df = geo.geocode_batch(inputs, show_progress=True)
    elapsed = time.time() - t0

    # Join results back to original df
    # Drop any geocoder output columns already present in the source CSV
    # (e.g. if the CSV was previously geocoded or has lat/lon columns)
    GEOCODER_COLS = ["lat", "lon", "confidence", "level_resolved",
                     "interpreted_as", "match_type", "candidates_considered", "notes"]
    df_clean = df.drop([c for c in GEOCODER_COLS if c in df.columns])
    output_df = pl.concat([df_clean, results_df.drop("input")], how="horizontal")

    # Output
    output_path = Path(args.output) if args.output else input_path.with_suffix(".geocoded.csv")
    output_df.write_csv(output_path)

    resolved = results_df["lat"].drop_nulls().len()
    print(f"\nDone in {elapsed:.1f}s", file=sys.stderr)
    print(f"Resolved:   {resolved}/{len(inputs)} ({100*resolved/max(len(inputs),1):.1f}%)", file=sys.stderr)
    print(f"Output:     {output_path}", file=sys.stderr)

    return 0


def cmd_info(args) -> int:
    """Print info about the current ukgeo installation and data."""
    from ukgeo import __version__
    from ukgeo.lookup import DEFAULT_PARQUET, JUNCTIONS_PARQUET, OSM_ROADS_PARQUET
    from ukgeo.level3_os_names import _get_api_key

    print(f"ukgeo {__version__}")
    print()
    print("Data files:")

    files = [
        ("OS Open Names", DEFAULT_PARQUET),
        ("OS Open Roads junctions", JUNCTIONS_PARQUET),
        ("OSM roads (B-roads)", OSM_ROADS_PARQUET),
    ]

    for label, path in files:
        if path.exists():
            size_mb = path.stat().st_size / (1 << 20)
            print(f"  ✓ {label:<30} {path.name} ({size_mb:.1f} MB)")
        else:
            print(f"  ✗ {label:<30} not found — run download script")

    print()
    api_key = _get_api_key()
    print(f"OS Names API key: {'set' if api_key else 'not set (Level 3 disabled)'}")
    print()
    print("Pipeline levels available:")
    print("  Level 1 — regex + postcodes.io     always")
    print(f"  Level 2 — OS Names parquet         {'yes' if DEFAULT_PARQUET.exists() else 'no — download OS Open Names'}")
    print(f"  Level 3 — OS Names API             {'yes' if api_key else 'no — set OS_API_KEY in .env'}")
    print("  Level 4 — Ollama LLM               not implemented")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="ukgeo",
        description="UK location free-text geocoder",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 0.3.0")
    sub = parser.add_subparsers(dest="command", required=True)

    # --- geocode subcommand ---
    geo_p = sub.add_parser("geocode", help="Geocode a string or CSV file")
    geo_p.add_argument(
        "input",
        help="Location string (e.g. 'M62 Junction 26') or path to a CSV file",
    )
    geo_p.add_argument(
        "--output", "-o",
        help="Output CSV path (default: input.geocoded.csv)",
    )
    geo_p.add_argument(
        "--column", "-c",
        help="Column name in CSV containing location strings (default: auto-detect first string column)",
    )
    geo_p.add_argument(
        "--domain", "-d",
        help="Domain config to load (e.g. 'road_safety' loads config/domain_road_safety.yaml)",
    )
    geo_p.add_argument(
        "--max-level", "-l",
        type=int,
        default=2,
        choices=[1, 2, 3],
        help="Maximum pipeline level to use (default: 2; use 3 to enable OS Names API fallback)",
    )
    geo_p.set_defaults(func=cmd_geocode)

    # --- info subcommand ---
    info_p = sub.add_parser("info", help="Show ukgeo installation status")
    info_p.set_defaults(func=cmd_info)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
