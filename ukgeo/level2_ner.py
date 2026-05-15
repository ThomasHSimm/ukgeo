"""
Level 2 — token-based entity tagging + OS Names candidate scoring.
No spaCy dependency. Fast enough for bulk (10k+ entries/sec target).
"""

import re
from dataclasses import dataclass
from difflib import get_close_matches
from typing import Optional
import polars as pl

from .models import GeoResult
from .lookup import OSNamesLookup
from .uk_admin import ALL_ADMIN

# ---------------------------------------------------------------------------
# Scoring weights (tuneable via calibration)
# ---------------------------------------------------------------------------

@dataclass
class ScoringWeights:
    # Candidate boosts (additive)
    county_context_match: float = 5.0
    district_context_match: float = 3.0
    city_context_match: float = 2.0
    road_context_match: float = 4.0
    junction_match: float = 8.0
    type_weight_scale: float = 1.0

    # Penalties (subtractive)
    admin_contradiction: float = -4.0
    ambiguous_token: float = -1.0
    near_qualifier: float = -1.0

    # Confidence thresholds (on normalised 0-1 score)
    # These are intentionally low — normalisation denominator is a theoretical
    # maximum; real scores cluster in 0.1-0.4 range for correct matches.
    high_threshold: float = 0.25
    medium_threshold: float = 0.10

    # Fuzzy matching
    fuzzy_cutoff: float = 0.75      # difflib cutoff for close matches
    fuzzy_confidence_cap: str = "Medium"  # fuzzy matches never exceed this


# ---------------------------------------------------------------------------
# Token entity types
# ---------------------------------------------------------------------------

_QUALIFIER_TOKENS = {
    "near", "by", "at", "on", "off", "between", "junction", "interchange",
    "roundabout", "bypass", "crossing", "bridge", "tunnel", "services",
    "northbound", "southbound", "eastbound", "westbound", "road", "street",
    "avenue", "lane", "drive", "way", "close", "place",
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
    ambiguous: bool = False
    preceded_by_qualifier: bool = False
    fuzzy_match: bool = False


# ---------------------------------------------------------------------------
# Gazetteer sets — built from OS Names parquet at Geocoder startup
# ---------------------------------------------------------------------------

class TokenGazetteer:
    """
    Lightweight lookup sets derived from OS Open Names.
    Built once at Geocoder init, O(1) set membership per token.
    """

    def __init__(self, lookup: OSNamesLookup):
        df = lookup._df
        # OS Names CSV has no county rows — supplement with static reference
        self.counties   = ALL_ADMIN
        self.districts  = self._name_set(df, ["District Borough"])
        self.cities     = self._name_set(df, ["City", "Suburban Area"])
        self.towns      = self._name_set(df, ["Town"])
        self.villages   = self._name_set(df, ["Village", "Hamlet", "Other Settlement"])
        self.motorways  = self._name_set(df, ["Motorway"])
        self.a_roads    = self._name_set(df, ["Numbered Road", "Named Road"])

        # Combined place set for fuzzy matching
        self.all_places = (
            self.counties | self.districts | self.cities | self.towns | self.villages
        )
        # Pre-compiled phrase joiner for multi-word admin names
        self.phrase_pattern = _build_phrase_pattern(self.counties)

    @staticmethod
    def _name_set(df: pl.DataFrame, local_types: list[str]) -> set[str]:
        return set(
            df.filter(pl.col("LOCAL_TYPE").is_in(local_types))
            ["NAME1_UPPER"].to_list()
        )

    def tag(self, token: str) -> list[str]:
        """Return all matching entity types for a token (>1 = ambiguous).
        Token may be a restored multi-word phrase e.g. 'WEST YORKSHIRE'."""
        t = token.upper()
        matches = []
        if t in self.counties:             matches.append("county")
        if t in self.districts:            matches.append("district")
        if t in self.cities:               matches.append("city")
        if t in self.towns:                matches.append("town")
        if t in self.villages:             matches.append("village")
        if _ROAD_MOTORWAY_RE.match(t):     matches.append("road_motorway")
        if _ROAD_A_RE.match(t):            matches.append("road_a")
        if _JUNCTION_RE.match(t):          matches.append("junction")
        return matches or ["unknown"]

    def fuzzy_tag(self, token: str, cutoff: float = 0.65) -> Optional[str]:
        """
        Try difflib fuzzy match against all place names.
        Returns the best match string if found, else None.
        Only used when exact tag returns 'unknown'.
        Minimum token length of 5 prevents short common words mis-matching.
        """
        t = token.upper()
        if len(t) < 5:
            return None
        matches = get_close_matches(t, self.all_places, n=1, cutoff=cutoff)
        return matches[0] if matches else None


# ---------------------------------------------------------------------------
# Tokenise + tag
# ---------------------------------------------------------------------------

def _build_phrase_pattern(admin_set: set[str]) -> re.Pattern:
    """
    Build a regex that matches any multi-word admin phrase (longest first).
    Used to pre-join phrases like 'West Yorkshire' → 'West_Yorkshire' before tokenising.
    """
    multi_word = sorted(
        (p for p in admin_set if " " in p),
        key=len, reverse=True  # longest first so 'East Riding of Yorkshire' beats 'Yorkshire'
    )
    escaped = [re.escape(p) for p in multi_word]
    return re.compile(r"\b(" + "|".join(escaped) + r")\b", re.IGNORECASE)


def _join_phrases(text: str, pattern: re.Pattern) -> str:
    """Replace spaces within matched admin phrases with underscores."""
    return pattern.sub(lambda m: m.group(0).replace(" ", "_"), text)


def tokenise(text: str, phrase_pattern: Optional[re.Pattern] = None) -> list[str]:
    """
    Split text into tokens. If phrase_pattern is supplied, multi-word admin
    phrases are pre-joined with underscores so they survive as single tokens.
    """
    if phrase_pattern:
        text = _join_phrases(text, phrase_pattern)
    return [t for t in re.split(r"[\s,;/\(\)\-]+", text.strip()) if t]


def tag_tokens(
    tokens: list[str],
    gazetteer: TokenGazetteer,
    fuzzy_cutoff: float = 0.65,
) -> list[TaggedToken]:
    tagged = []
    prev_qualifier = False
    for raw in tokens:
        # Restore underscores → spaces for display/matching
        norm = raw.upper().replace("_", " ")
        is_qual = norm.lower() in _QUALIFIER_TOKENS
        types = gazetteer.tag(norm)  # tag on restored form
        fuzzy = False

        if _JUNCTION_NUM_RE.match(norm) and prev_qualifier:
            types = ["junction"]

        if types == ["unknown"] and not is_qual:
            fuzzy_match = gazetteer.fuzzy_tag(norm, cutoff=fuzzy_cutoff)
            if fuzzy_match:
                types = gazetteer.tag(fuzzy_match)
                fuzzy = True

        tagged.append(TaggedToken(
            raw=raw.replace("_", " "),
            normalised=norm,
            entity_type=types[0],
            is_qualifier=is_qual,
            ambiguous=len(types) > 1,
            preceded_by_qualifier=prev_qualifier,
            fuzzy_match=fuzzy,
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
    score = row.get("TYPE_WEIGHT", 1) * weights.type_weight_scale

    county_upper   = (row.get("COUNTY_UNITARY") or "").upper()
    district_upper = (row.get("DISTRICT_BOROUGH") or "").upper()
    place_upper    = (row.get("POPULATED_PLACE") or "").upper()
    name_upper     = (row.get("NAME1_UPPER") or "")

    for tk in tagged:
        norm = tk.normalised

        if tk.ambiguous:
            score += weights.ambiguous_token

        if tk.fuzzy_match:
            # Fuzzy matches contribute but at half weight
            score += weights.city_context_match * 0.5
            continue

        if tk.entity_type == "county":
            if norm in county_upper:
                score += weights.county_context_match
            elif county_upper and norm not in county_upper:
                score += weights.admin_contradiction

        elif tk.entity_type == "district":
            if norm in district_upper:
                score += weights.district_context_match

        elif tk.entity_type in ("city", "town", "village"):
            if norm in place_upper or norm in county_upper:
                score += weights.city_context_match

        elif tk.entity_type in ("road_motorway", "road_a"):
            if norm in name_upper:
                score += weights.road_context_match

        elif tk.entity_type == "junction":
            if norm in name_upper:
                score += weights.junction_match

        if tk.preceded_by_qualifier:
            score += weights.near_qualifier

    return score


def normalise_score(raw: float, max_possible: float) -> float:
    if max_possible <= 0:
        return 0.0
    return max(0.0, min(1.0, raw / max_possible))


def confidence_from_score(
    score: float,
    weights: ScoringWeights,
    fuzzy_used: bool = False,
) -> str:
    if fuzzy_used:
        # Fuzzy matches are capped at Medium
        if score >= weights.high_threshold:
            return weights.fuzzy_confidence_cap
        if score >= weights.medium_threshold:
            return "Medium"
        return "Low"
    if score >= weights.high_threshold:
        return "High"
    if score >= weights.medium_threshold:
        return "Medium"
    return "Low"


def max_possible_score(tagged: list[TaggedToken], weights: ScoringWeights) -> float:
    base = 10 * weights.type_weight_scale
    per_token = max(
        weights.county_context_match,
        weights.district_context_match,
        weights.city_context_match,
        weights.road_context_match,
        weights.junction_match,
    )
    return base + len(tagged) * per_token


# ---------------------------------------------------------------------------
# Candidate filtering — use admin context to hard-filter before scoring
# ---------------------------------------------------------------------------

def filter_by_admin_context(
    candidates: pl.DataFrame,
    tagged: list[TaggedToken],
) -> pl.DataFrame:
    """
    OS Names CSV stores COUNTY_UNITARY and POPULATED_PLACE as URIs — unusable
    for text filtering. Instead we filter by NAME1_UPPER containment only,
    preferring rows whose name contains a tagged city/town token.
    Falls back to full candidate set if filtering yields nothing.
    """
    city_tokens = [
        tk.normalised for tk in tagged
        if tk.entity_type in ("city", "town", "village") and not tk.is_qualifier
    ]

    filtered = candidates
    for token in city_tokens:
        attempt = filtered.filter(
            pl.col("NAME1_UPPER").str.contains(token, literal=True)
        )
        if len(attempt) > 0:
            filtered = attempt

    return filtered if len(filtered) > 0 else candidates


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
    tokens = tokenise(text, phrase_pattern=gazetteer.phrase_pattern)
    if not tokens:
        return None

    tagged = tag_tokens(tokens, gazetteer, fuzzy_cutoff=weights.fuzzy_cutoff)
    fuzzy_used = any(tk.fuzzy_match for tk in tagged)

    # Extract road ref + junction from Level 1 partial
    road_ref = None
    junction_num = None
    if partial and partial.notes:
        for part in partial.notes.split(","):
            if part.startswith("road_ref="):
                road_ref = part.split("=", 1)[1]
            if part.startswith("junction="):
                junction_num = part.split("=", 1)[1]

    # Collect context tokens by type
    county_tokens = [tk for tk in tagged if tk.entity_type == "county" and not tk.is_qualifier]
    place_tokens  = [tk for tk in tagged if tk.entity_type in ("city", "town", "village") and not tk.is_qualifier]
    all_non_qual  = [tk for tk in tagged if not tk.is_qualifier and tk.entity_type != "unknown"]

    if road_ref:
        near_name = place_tokens[0].raw if place_tokens else None
        candidates_df = lookup.search_road(road_ref, junction_num=junction_num, near_name=near_name)
        # Road/junction not in OS Names — fall back to nearby place
        if candidates_df.is_empty() and near_name:
            candidates_df = lookup.search_name(near_name)
        elif candidates_df.is_empty() and county_tokens:
            candidates_df = lookup.search_name(county_tokens[0].raw)
    else:
        # Primary search token: prefer specific place over county
        primary_tk = (
            place_tokens[0] if place_tokens
            else all_non_qual[0] if all_non_qual
            else None
        )
        if primary_tk is None:
            return None
        candidates_df = lookup.search_name(primary_tk.raw)

    if candidates_df.is_empty():
        return None

    # Filter: if county tokens present, prefer candidates whose NAME1_UPPER
    # or MBR overlaps — use NAME1_UPPER containment as a soft pre-filter
    # (hard filter done in filter_by_admin_context)
    candidates_df = filter_by_admin_context(candidates_df, tagged)

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
    confidence = confidence_from_score(norm_score, weights, fuzzy_used=fuzzy_used)

    lat, lon = lookup.bng_to_wgs84(best_row["GEOMETRY_X"], best_row["GEOMETRY_Y"])

    notes_parts = [f"match_score={norm_score:.3f}"]
    if fuzzy_used:
        notes_parts.append("fuzzy=true")
    if road_ref and junction_num:
        notes_parts.append("junction_data=unavailable")

    return GeoResult(
        input=text,
        lat=lat,
        lon=lon,
        interpreted_as=f"{best_row['NAME1']} ({best_row['LOCAL_TYPE']})",
        match_type=(
            partial.match_type if partial
            else best_row["LOCAL_TYPE"].lower().replace(" ", "_")
        ),
        level_resolved=2,
        confidence=confidence,
        candidates_considered=len(candidates_df),
        notes=",".join(notes_parts),
    )