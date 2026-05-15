"""
Level 1 — regex pattern matching.
Handles: UK postcodes, motorway/A-road references, junction numbers.
Fast, no external dependencies beyond requests.
"""

import re
import requests
from typing import Optional
from .models import GeoResult

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# Full UK postcode: e.g. LS1 1BA, WF10 4QH, SW1A 2AA
_POSTCODE_FULL = re.compile(
    r"\b([A-Z]{1,2}\d{1,2}[A-Z]?)\s*(\d[A-Z]{2})\b", re.IGNORECASE
)

# Outward code only: e.g. LS1, WF10 — lower confidence
_POSTCODE_OUTWARD = re.compile(r"\b([A-Z]{1,2}\d{1,2}[A-Z]?)\b", re.IGNORECASE)

# Motorway: M1, M62, M25 etc.
_MOTORWAY = re.compile(r"\bM(\d{1,3})\b", re.IGNORECASE)

# A-road (including motorway-standard): A1, A647, A1(M)
_AROAD = re.compile(r"\bA(\d{1,4})(\(M\))?(?=\W|$)", re.IGNORECASE)

# Junction number following a road reference: J26, Junction 26, junction 47
_JUNCTION = re.compile(r"\b(?:J|junction)\s*(\d{1,3})\b", re.IGNORECASE)

# ---------------------------------------------------------------------------
# postcodes.io lookup (CORS-friendly, no key, precise centroid)
# ---------------------------------------------------------------------------

_POSTCODES_IO = "https://api.postcodes.io/postcodes/{}"


def _lookup_postcode(postcode: str) -> Optional[dict]:
    """Return postcodes.io result dict or None."""
    clean = postcode.replace(" ", "").upper()
    try:
        r = requests.get(_POSTCODES_IO.format(clean), timeout=5)
        if r.status_code == 200:
            return r.json().get("result")
    except requests.RequestException:
        pass
    return None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def try_level1(text: str) -> Optional[GeoResult]:
    """
    Attempt to resolve text using regex patterns only.
    Returns a GeoResult if resolved, None if level 1 cannot handle it.
    """
    upper = text.upper()

    # --- Full postcode ---
    m = _POSTCODE_FULL.search(upper)
    if m:
        postcode = f"{m.group(1)} {m.group(2)}"
        data = _lookup_postcode(postcode)
        if data:
            return GeoResult(
                input=text,
                lat=data["latitude"],
                lon=data["longitude"],
                interpreted_as=f"Postcode {postcode}",
                match_type="postcode",
                level_resolved=1,
                confidence="High",
                notes=f"postcodes.io match: {data.get('admin_district', '')}",
            )
        # postcode found but lookup failed — return low-confidence shell
        return GeoResult(
            input=text,
            interpreted_as=f"Postcode {postcode} (lookup failed)",
            match_type="postcode",
            level_resolved=1,
            confidence="Low",
            notes="postcodes.io unavailable",
        )

    # --- Road + junction: extract for Level 2 to use, don't resolve here ---
    # We return None so Level 2 gets the structured road entities,
    # but we annotate what we found for pipeline visibility.
    motorway = _MOTORWAY.search(upper)
    aroad = _AROAD.search(upper)
    junction = _JUNCTION.search(upper)

    if motorway or aroad:
        # Pass road metadata downstream via notes — Level 2 will use these
        junc_num = junction.group(1) if junction else None
        road_ref = (
            f"M{motorway.group(1)}" if motorway
            else f"A{aroad.group(1)}{aroad.group(2) or ''}"
        )
        return GeoResult(
            input=text,
            interpreted_as=f"{road_ref}" + (f" J{junc_num}" if junc_num else ""),
            match_type="road" if not junc_num else "junction",
            level_resolved=None,
            confidence=None,
            notes=f"road_ref={road_ref}" + (f",junction={junc_num}" if junc_num else ""),
        )

    return None
