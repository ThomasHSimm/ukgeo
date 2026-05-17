"""
Level 3 — OS Names API fallback.

Fires only when Levels 1 and 2 return unresolved or Low confidence,
and the input contains no road reference that OS Open Roads can handle.

Requires an OS Data Hub API key: set OS_API_KEY in .env or as an
environment variable. Free account at https://osdatahub.os.uk/

Rate limit: 600 requests/minute (live mode).
Average latency: ~217ms per query.
"""

import os
from typing import Optional

import httpx

from .models import GeoResult
from .lookup import OSNamesLookup
from .utils import load_env

OS_NAMES_URL = "https://api.os.uk/search/names/v1/find"
DEFAULT_MAX_RESULTS = 5


def _get_api_key() -> Optional[str]:
    load_env()
    return os.getenv("OS_API_KEY")


def query_os_names(
    text: str,
    api_key: str,
    max_results: int = DEFAULT_MAX_RESULTS,
    timeout: float = 10.0,
) -> list[dict]:
    """
    Query the OS Names API /find endpoint.
    Returns a list of GAZETTEER_ENTRY dicts, ordered by API relevance.
    Returns empty list if the API call fails or returns no results.
    """
    try:
        r = httpx.get(
            OS_NAMES_URL,
            params={
                "query": text,
                "key": api_key,
                "maxresults": max_results,
            },
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
        return [item["GAZETTEER_ENTRY"] for item in data.get("results", [])]
    except Exception:
        return []


def implied_confidence(
    candidates: list[dict],
    lookup: OSNamesLookup,
) -> tuple[str, float]:
    """
    Derive an implied confidence from the spread of API candidates.

    Logic:
    - 0 candidates → Low, spread=None
    - 1 candidate → Medium (no comparison possible)
    - 2+ candidates: compute std dev of distances between top result and others
        - std dev < 2km  → High   (tight cluster, top result is unambiguous)
        - std dev < 10km → Medium (moderate spread)
        - std dev >= 10km → Low   (top result is an outlier or very ambiguous)

    Returns: (confidence_str, spread_km)
    """
    if not candidates:
        return "Low", 0.0

    if len(candidates) == 1:
        return "Medium", 0.0

    top = candidates[0]
    try:
        top_lat, top_lon = lookup.bng_to_wgs84(top["GEOMETRY_X"], top["GEOMETRY_Y"])
    except Exception:
        return "Low", 0.0

    distances = []
    for c in candidates[1:]:
        try:
            lat, lon = lookup.bng_to_wgs84(c["GEOMETRY_X"], c["GEOMETRY_Y"])
            d = _haversine_km(top_lat, top_lon, lat, lon)
            distances.append(d)
        except Exception:
            continue

    if not distances:
        return "Medium", 0.0

    spread = (sum(d**2 for d in distances) / len(distances)) ** 0.5  # RMS distance

    if spread < 2.0:
        return "High", spread
    if spread < 10.0:
        return "Medium", spread
    return "Low", spread


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math

    R = 6371.0
    p = math.pi / 180
    a = (
        math.sin((lat2 - lat1) * p / 2) ** 2
        + math.cos(lat1 * p) * math.cos(lat2 * p)
        * math.sin((lon2 - lon1) * p / 2) ** 2
    )
    return 2 * R * math.asin(math.sqrt(a))


def try_level3(
    text: str,
    lookup: OSNamesLookup,
    api_key: Optional[str] = None,
    max_results: int = DEFAULT_MAX_RESULTS,
) -> Optional[GeoResult]:
    """
    Attempt to resolve text using the OS Names API.
    Returns GeoResult if resolved, None otherwise.
    """
    key = api_key or _get_api_key()
    if not key:
        return None

    candidates = query_os_names(text, key, max_results=max_results)
    if not candidates:
        return None

    top = candidates[0]
    try:
        lat, lon = lookup.bng_to_wgs84(top["GEOMETRY_X"], top["GEOMETRY_Y"])
    except Exception:
        return None

    confidence, spread_km = implied_confidence(candidates, lookup)

    return GeoResult(
        input=text,
        lat=lat,
        lon=lon,
        interpreted_as=f"{top.get('NAME1', '')} ({top.get('LOCAL_TYPE', '')})",
        match_type=top.get("LOCAL_TYPE", "").lower().replace(" ", "_"),
        level_resolved=3,
        confidence=confidence,
        candidates_considered=len(candidates),
        notes=(
            f"source=os_names_api,"
            f"county={top.get('COUNTY_UNITARY', '')},"
            f"spread_km={spread_km:.2f},"
            f"n_candidates={len(candidates)}"
        ),
    )
