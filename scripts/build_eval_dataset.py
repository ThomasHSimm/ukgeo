"""
Build a real-world evaluation dataset for ukgeo from two public data sources:

  1. Police.uk street-level crime API  — extracts street names with coordinates
  2. National Highways RSS feeds       — extracts incident/planned-works titles
                                         with georss:point coordinates

Output: data/eval_dataset.csv  (columns: input, lat, lon, source)

Usage:
    python scripts/build_eval_dataset.py
"""

import re
import sys
import time
import warnings
from pathlib import Path

import httpx
import polars as pl

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent.parent / "data"
OUT_PATH = DATA_DIR / "eval_dataset.csv"

SEEDS = [
    ("Leeds",       53.7954, -1.5491),
    ("Bradford",    53.7950, -1.7594),
    ("Birmingham",  52.4862, -1.8904),
    ("Edinburgh",   55.9533, -3.1883),
    ("Swindon",     51.5585, -1.7837),
    ("Dartford",    51.4454,  0.2744),
    ("York",        53.9590, -1.0815),
    ("Wakefield",   53.6833, -1.4977),
]

MONTH = "2024-06"

FEEDS = [
    "https://m.highwaysengland.co.uk/feeds/rss/incidents.xml",
    "https://m.highwaysengland.co.uk/feeds/rss/plannedworks.xml",
]

POLICE_API = "https://data.police.uk/api/crimes-street/all-crime"
CALL_DELAY = 0.5  # seconds between Police.uk requests

_HTML_TAG = re.compile(r"<[^>]+>")


# ---------------------------------------------------------------------------
# Source 1: Police.uk
# ---------------------------------------------------------------------------

def _strip_on_or_near(name: str) -> str:
    return re.sub(r"^On or near\s+", "", name, flags=re.IGNORECASE).strip()


def fetch_police_crimes(city: str, lat: float, lon: float) -> list[dict]:
    """Return deduplicated (input, lat, lon) rows from one city seed."""
    try:
        resp = httpx.get(
            POLICE_API,
            params={"lat": lat, "lng": lon, "date": MONTH},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as exc:
        warnings.warn(f"Police.uk request failed for {city}: {exc}")
        return []

    seen = set()
    rows = []
    for crime in resp.json():
        loc = crime.get("location", {})
        street = loc.get("street", {}).get("name", "")
        street = _strip_on_or_near(street)
        if len(street) < 4:
            continue
        try:
            clat = float(loc["latitude"])
            clon = float(loc["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        key = (street, clat, clon)
        if key not in seen:
            seen.add(key)
            rows.append({"input": street, "lat": clat, "lon": clon, "source": "police_uk"})
    return rows


def build_police_dataset() -> pl.DataFrame:
    all_rows: list[dict] = []
    for i, (city, lat, lon) in enumerate(SEEDS):
        print(f"  Police.uk [{i+1}/{len(SEEDS)}] {city} ...", end=" ", flush=True)
        rows = fetch_police_crimes(city, lat, lon)
        print(f"{len(rows)} rows")
        all_rows.extend(rows)
        if i < len(SEEDS) - 1:
            time.sleep(CALL_DELAY)

    if not all_rows:
        return pl.DataFrame(schema={"input": pl.Utf8, "lat": pl.Float64, "lon": pl.Float64, "source": pl.Utf8})

    df = pl.DataFrame(all_rows)
    return df.unique(subset=["input", "lat", "lon"])


# ---------------------------------------------------------------------------
# Source 2: National Highways RSS
# ---------------------------------------------------------------------------

def _clean_title(title: str) -> str:
    title = _HTML_TAG.sub("", title)
    return title.strip()[:120]


def _parse_georss_point(entry) -> tuple[float, float] | None:
    """Extract lat/lon from a feedparser entry's georss:point tag."""
    raw = getattr(entry, "georss_point", None)
    if not raw:
        # feedparser may also expose it under tags dict
        for tag in entry.get("tags", []):
            if "georss" in tag.get("term", "").lower():
                raw = tag.get("scheme", "")
                break
    if not raw:
        return None
    parts = raw.strip().split()
    if len(parts) == 2:
        try:
            return float(parts[0]), float(parts[1])
        except ValueError:
            pass
    return None


def fetch_highway_feed(url: str) -> list[dict]:
    try:
        import feedparser
    except ImportError:
        warnings.warn("feedparser not installed — skipping Highways feeds")
        return []

    try:
        feed = feedparser.parse(url)
    except Exception as exc:
        warnings.warn(f"Failed to parse feed {url}: {exc}")
        return []

    if feed.get("bozo") and not feed.get("entries"):
        warnings.warn(f"Feed parse error for {url}: {feed.get('bozo_exception')}")
        return []

    rows = []
    for entry in feed.get("entries", []):
        title = _clean_title(entry.get("title", ""))
        if len(title) < 4:
            continue
        coords = _parse_georss_point(entry)
        if coords is None:
            continue
        lat, lon = coords
        rows.append({"input": title, "lat": lat, "lon": lon, "source": "highways_england"})
    return rows


def build_highways_dataset() -> pl.DataFrame:
    all_rows: list[dict] = []
    for url in FEEDS:
        print(f"  Highways feed: {url.split('/')[-1]} ...", end=" ", flush=True)
        rows = fetch_highway_feed(url)
        print(f"{len(rows)} rows")
        all_rows.extend(rows)

    if not all_rows:
        return pl.DataFrame(schema={"input": pl.Utf8, "lat": pl.Float64, "lon": pl.Float64, "source": pl.Utf8})

    df = pl.DataFrame(all_rows)
    return df.unique(subset=["input", "lat", "lon"])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("Fetching Police.uk street-level crime data ...")
    police_df = build_police_dataset()

    print("Fetching National Highways RSS feeds ...")
    highways_df = build_highways_dataset()

    combined = pl.concat([police_df, highways_df], how="diagonal").unique(
        subset=["input", "lat", "lon"]
    )

    combined.write_csv(OUT_PATH)

    print()
    print(f"Police.uk:          {len(police_df):>5} rows")
    print(f"Highways England:   {len(highways_df):>5} rows")
    print(f"Total unique:       {len(combined):>5} rows")
    print(f"Saved to {OUT_PATH}")
    print()
    print("First 10 rows:")
    print(combined.head(10))


if __name__ == "__main__":
    main()
