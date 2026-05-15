
"""
Level 2 — token-based entity tagging + OS Names candidate scoring.
No spaCy dependency. Fast enough for bulk (10k+ entries/sec target).
"""

import re
from dataclasses import dataclass, field
from typing import Optional
import polars as pl

from .models import GeoResult
from .lookup import OSNamesLookup

# ---------------------------------------------------------------------------
# Scoring weights (tuneable via calibration)
# ---------------------------------------------------------------------------

@dataclass
class ScoringWeights:
    # Candidate boosts (additive)
    county_context_match: float = 5.0    # candidate is in mentioned county
    district_context_match: float = 3.0  # candidate is in mentioned district
    city_context_match: float = 2.0      # candidate near mentioned city
    road_context_match: float = 4.0      # candidate is on mentioned road
    junction_match: float = 8.0          # explicit junction number match
    type_weight_scale: float = 1.0       # multiplier on OS Names TYPE_WEIGHT

    # Penalties (subtractive)
    admin_contradiction: float = -4.0    # county mentioned but candidate outside it
    ambiguous_token: float = -1.0        # token matched multiple entity types
    near_qualifier: float = -1.0         # "near X" — X is context not primary

    # Confidence thresholds (on normalised 0-1 score)
    high_threshold: float = 0.65
    medium_threshold: float = 0.35


# ---------------------------------------------------------------------------
# Token entity types
# ---------------------------------------------------------------------------

ENTITY_TYPES = (
    "county", "district", "city", "town", "village",
    "road_motorway", "road_a", "junction", "qualifier", "unknown"
)

_QUALIFIER_TOKENS = {
    "near", "by", "at", "on", "off", "between", "junction", "interchange",
    "roundabout", "bypass", "crossing", "bridge", "tunnel", "services",
    "northbound", "southbound", "eastbound", "westbound",
}

_ROAD_MOTORWAY_RE = re.compile(r"^M\d{1,3}$", re.IGNORECASE)
_ROAD_A_RE = re.compile(r"^A\d{1,4}(\(M\))?$", re.IGNORECASE)
_JUNCTION_RE = re.compile(r"^J\d{1,3}$", re.IGNORECASE)
_JUNCTION_NUM_RE = re.compile(r"^\d{1,3}$")


@dataclass
class TaggedToken:
    raw: str
    normalised: str
    entity_type: str
    is_qualifier: bool = False
    ambiguous: bool = False          # matched >1 entity type
    preceded_by_qualifier: bool = False


# ---------------------------------------------------------------------------
# Gazetteer sets — built from OS Names parquet at Geocoder startup
# ---------------------------------------------------------------------------

class TokenGazetteer:
    """
    Lightweight lookup sets derived from OS Open Names.
    Built once, queried per token (O(1) set membership).
    """

    def __init__(self, lookup: OSNamesLookup):
        df = lookup._df
        self.counties   = self._name_set(df, ["County", "Unitary Authority",
                                               "Metropolitan District", "London Borough"])
        self.districts  = self._name_set(df, ["District Borough"])
        self.cities     = self._name_set(df, ["City", "Suburban Area"])
        self.towns      = self._name_set(df, ["Town"])
        self.villages   = self._name_set(df, ["Village", "Hamlet", "Other Settlement"])
        self.motorways  = self._name_set(df, ["Motorway"])
        self.a_roads    = self._name_set(df, ["Numbered Road", "Named Road"])

    @staticmethod
    def _name_set(df: pl.DataFrame, local_types: list[str]) -> set[str]:
        return set(
            df.filter(pl.col("LOCAL_TYPE").is_in(local_types))
            ["NAME1_UPPER"].to_list()
        )

    def tag(self, token: str) -> list[str]:
        """Return all matching entity types for a token (may be >1 = ambiguous)."""
        t = token.upper()
        matches = []
        if t in self.counties:                    matches.append("county")
        if t in self.districts:                   matches.append("district")
        if t in self.cities:                      matches.append("city")
        if t in self.towns:                       matches.append("town")
        if t in self.villages:                    matches.append("village")
        if _ROAD_MOTORWAY_RE.match(t):            matches.append("road_motorway")
        if _ROAD_A_RE.match(t):                   matches.append("road_a")
        if _JUNCTION_RE.match(t) or t in self.motorways: matches.append("junction")
        return matches or ["unknown"]


# ---------------------------------------------------------------------------
# Tokenise + tag
# ---------------------------------------------------------------------------

def tokenise(text: str) -> list[str]:
    """Split on whitespace and punctuation, drop empties."""
    return [t for t in re.split(r"[\s,;/\(\)\-]+", text.strip()) if t]


def tag_tokens(tokens: list[str], gazetteer: TokenGazetteer) -> list[TaggedToken]:
    tagged = []
    prev_qualifier = False
    for raw in tokens:
        norm = raw.upper()
        is_qual = norm.lower() in _QUALIFIER_TOKENS
        types = gazetteer.tag(raw)

        # Junction number: bare digit(s) after a qualifier like "Junction"
        if _JUNCTION_NUM_RE.match(norm) and prev_qualifier:
            types = ["junction"]

        tagged.append(TaggedToken(
            raw=raw,
            normalised=norm,
            entity_type=types[0],
            is_qualifier=is_qual,
            ambiguous=len(types) > 1,
            preceded_by_qualifier=prev_qualifier,
        ))
        prev_qualifier = is_qual
    return tagged


# ---------------------------------------------------------------------------
# Candidate scoring
# ---------------------------------------------------------------------------

def score_candidate(
    row: dict,
    tagged: list[TaggedToken],
    weights: ScoringWeights,
) -> float:
    """
    Score a single OS Names candidate row against the tagged tokens.
    Returns a raw float score (higher = better match).
    """
    score = row.get("TYPE_WEIGHT", 1) * weights.type_weight_scale

    county_upper  = (row.get("COUNTY_UNITARY") or "").upper()
    district_upper = (row.get("DISTRICT_BOROUGH") or "").upper()
    place_upper   = (row.get("POPULATED_PLACE") or "").upper()
    name_upper    = (row.get("NAME1_UPPER") or "")

    for tk in tagged:
        norm = tk.normalised
        if tk.ambiguous:
            score += weights.ambiguous_token

        if tk.entity_type == "county" and norm in county_upper:
            score += weights.county_context_match
        elif tk.entity_type == "county" and county_upper and norm not in county_upper:
            score += weights.admin_contradiction

        if tk.entity_type == "district" and norm in district_upper:
            score += weights.district_context_match

        if tk.entity_type in ("city", "town") and norm in place_upper:
            score += weights.city_context_match

        if tk.entity_type in ("road_motorway", "road_a") and norm in name_upper:
            score += weights.road_context_match

        if tk.entity_type == "junction" and norm in name_upper:
            score += weights.junction_match

        if tk.preceded_by_qualifier:
            score += weights.near_qualifier

    return score


def normalise_score(raw: float, max_possible: float) -> float:
    """Normalise score to 0-1."""
    if max_possible <= 0:
        return 0.0
    return max(0.0, min(1.0, raw / max_possible))


def confidence_from_score(score: float, weights: ScoringWeights) -> str:
    if score >= weights.high_threshold:
        return "High"
    if score >= weights.medium_threshold:
        return "Medium"
    return "Low"


# ---------------------------------------------------------------------------
# Max possible score (for normalisation)
# ---------------------------------------------------------------------------

def max_possible_score(tagged: list[TaggedToken], weights: ScoringWeights) -> float:
    """Upper bound: every token matches perfectly, no penalties."""
    base = 10 * weights.type_weight_scale  # max TYPE_WEIGHT
    per_token = max(
        weights.county_context_match,
        weights.district_context_match,
        weights.city_context_match,
        weights.road_context_match,
        weights.junction_match,
    )
    return base + len(tagged) * per_token


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def try_level2(
    text: str,
    partial: Optional[GeoResult],
    lookup: OSNamesLookup,
    gazetteer: TokenGazetteer,
    weights: ScoringWeights,
) -> Optional[GeoResult]:
    """
    Attempt to resolve text using token tagging + OS Names candidate scoring.
    `partial` is the GeoResult from Level 1 (may carry road_ref / junction in notes).
    Returns GeoResult if a candidate is found, None otherwise.
    """
    tokens = tokenise(text)
    if not tokens:
        return None

    tagged = tag_tokens(tokens, gazetteer)

    # Extract road ref + junction from Level 1 partial if available
    road_ref = None
    junction_num = None
    if partial and partial.notes:
        for part in partial.notes.split(","):
            if part.startswith("road_ref="):
                road_ref = part.split("=", 1)[1]
            if part.startswith("junction="):
                junction_num = part.split("=", 1)[1]

    # Extract county/near context from tagged tokens for search narrowing
    county_tokens = [tk.normalised for tk in tagged if tk.entity_type == "county"]
    county_hint = county_tokens[0] if county_tokens else None

    # Choose search strategy
    if road_ref and junction_num:
        candidates_df = lookup.search_road(road_ref, junction_num=junction_num)
    elif road_ref:
        near_tokens = [tk.raw for tk in tagged if tk.entity_type in ("city", "town", "village")]
        candidates_df = lookup.search_road(road_ref, near_name=near_tokens[0] if near_tokens else None)
    else:
        # General place search — use the most specific non-qualifier token
        place_tokens = [
            tk for tk in tagged
            if tk.entity_type in ("city", "town", "village", "district")
            and not tk.is_qualifier
        ]
        if not place_tokens:
            place_tokens = [tk for tk in tagged if not tk.is_qualifier and tk.entity_type != "unknown"]
        if not place_tokens:
            return None
        primary = place_tokens[0].raw
        candidates_df = lookup.search_name(primary, county=county_hint)

    if candidates_df.is_empty():
        return None

    # Score each candidate
    max_score = max_possible_score(tagged, weights)
    best_score = -999.0
    best_row = None

    for row in candidates_df.to_dicts():
        s = score_candidate(row, tagged, weights)
        if s > best_score:
            best_score = s
            best_row = row

    if best_row is None:
        return None

    norm_score = normalise_score(best_score, max_score)
    confidence = confidence_from_score(norm_score, weights)

    lat, lon = lookup.bng_to_wgs84(
        best_row["GEOMETRY_X"], best_row["GEOMETRY_Y"]
    )

    return GeoResult(
        input=text,
        lat=lat,
        lon=lon,
        interpreted_as=f"{best_row['NAME1']} ({best_row['LOCAL_TYPE']})",
        match_type=partial.match_type if partial else best_row["LOCAL_TYPE"].lower().replace(" ", "_"),
        level_resolved=2,
        confidence=confidence,
        candidates_considered=len(candidates_df),
        notes=f"match_score={norm_score:.3f}",
    )