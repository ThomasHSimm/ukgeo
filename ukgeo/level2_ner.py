"""
Level 2 — token-based entity tagging + OS Names candidate scoring.
No spaCy dependency. Fast enough for bulk (10k+ entries/sec target).
"""

import re
from dataclasses import dataclass, field
from difflib import get_close_matches
from typing import Optional

import polars as pl

from .lookup import OSNamesLookup
from .models import GeoResult
from .uk_admin import ADMIN_BNG_EXTENTS, ALL_ADMIN, resolve_alias

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
    high_threshold: float = 0.15
    medium_threshold: float = 0.10

    # Fuzzy matching
    fuzzy_cutoff: float = 0.75      # difflib cutoff for close matches
    fuzzy_confidence_cap: str = "Medium"  # fuzzy matches never exceed this

    # Road-place anchor: filter road sections to those within this distance (km)
    # of the place token when a road ref is present alongside a place name.
    road_place_anchor_km: float = 20.0

    # Domain-specific words to treat as context/qualifiers rather than places
    extra_qualifiers: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Token entity types
# ---------------------------------------------------------------------------

_QUALIFIER_TOKENS = {
    "near", "by", "at", "on", "off", "between", "junction", "interchange",
    "roundabout", "bypass", "crossing", "bridge", "tunnel", "services",
    "northbound", "southbound", "eastbound", "westbound", "road", "street",
    "avenue", "lane", "drive", "way", "close", "place",
    "motorway", "expressway", "flyover", "viaduct", "overpass", "underpass",
    "carriageway", "sliproad", "spur", "msa", "welcome", "extra", "moto",
    "break",
}

_ROAD_MOTORWAY_RE = re.compile(r"^M\d{1,3}$", re.IGNORECASE)
_ROAD_A_RE = re.compile(r"^A\d{1,4}(\(M\))?$", re.IGNORECASE)
_ROAD_B_RE = re.compile(r"^B\d{1,4}$", re.IGNORECASE)
_JUNCTION_RE = re.compile(r"^J\d{1,3}$", re.IGNORECASE)
_JUNCTION_NUM_RE = re.compile(r"^\d{1,3}$")

# Qualifier words that signal the input may name a junction/interchange/roundabout
_JUNCTION_HINT_QUALIFIERS = {"interchange", "junction", "roundabout"}


@dataclass
class TaggedToken:
    raw: str
    normalised: str
    entity_type: str
    is_qualifier: bool = False
    ambiguous: bool = False
    preceded_by_qualifier: bool = False
    fuzzy_match: bool = False
    fuzzy_resolved: Optional[str] = None  # uppercased gazetteer name used for search


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
        if t in self.counties:
            matches.append("county")
        if t in self.districts:
            matches.append("district")
        if t in self.cities:
            matches.append("city")
        if t in self.towns:
            matches.append("town")
        if t in self.villages:
            matches.append("village")
        if _ROAD_MOTORWAY_RE.match(t):
            matches.append("road_motorway")
        if _ROAD_A_RE.match(t):
            matches.append("road_a")
        if _ROAD_B_RE.match(t):
            matches.append("road_b")
        if _JUNCTION_RE.match(t):
            matches.append("junction")
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
    weights: ScoringWeights,
) -> list[TaggedToken]:
    """Pass 1: exact tagging only — no fuzzy. Call _apply_fuzzy_tokens() for pass 2."""
    tagged = []
    prev_qualifier = False
    qualifier_tokens = _QUALIFIER_TOKENS | {
        token.lower() for token in weights.extra_qualifiers
    }
    for raw in tokens:
        norm = raw.upper().replace("_", " ")
        is_qual = norm.lower() in qualifier_tokens
        types = gazetteer.tag(norm)

        if _JUNCTION_NUM_RE.match(norm) and prev_qualifier:
            types = ["junction"]

        tagged.append(TaggedToken(
            raw=raw.replace("_", " "),
            normalised=norm,
            entity_type=types[0],
            is_qualifier=is_qual,
            ambiguous=len(types) > 1,
            preceded_by_qualifier=prev_qualifier,
        ))
        prev_qualifier = is_qual
    return tagged


def _county_name_set(
    lookup: "OSNamesLookup",
    county_token: str,
) -> Optional[set[str]]:
    """Return NAME1_UPPER values from lookup._df within the county's BNG extent."""
    extent = ADMIN_BNG_EXTENTS.get(resolve_alias(county_token))
    if extent is None:
        return None
    county_df = _filter_by_bng_extent(lookup._df, extent)
    return set(county_df["NAME1_UPPER"].to_list())


def _apply_fuzzy_tokens(
    tagged: list[TaggedToken],
    gazetteer: TokenGazetteer,
    weights: ScoringWeights,
    county_names: Optional[set[str]] = None,
) -> None:
    """
    Pass 2: apply fuzzy matching in-place only when ALL of:
      - the token is unknown and not a qualifier
      - no city/town/village token already exists in the tagged list
    Uses county_names (county-scoped set) when available, else the global
    all_places set, so "Brafford" + "West Yorkshire" resolves to "Bradford"
    rather than the phonetically-closer but geographically-wrong "Rafford".
    """
    _PLACE_TYPES = {"city", "town", "village"}
    has_place_token = any(
        tk.entity_type in _PLACE_TYPES and not tk.is_qualifier
        for tk in tagged
    )
    if has_place_token:
        return

    name_set = county_names if county_names is not None else gazetteer.all_places

    for tk in tagged:
        if tk.entity_type == "unknown" and not tk.is_qualifier:
            matches = get_close_matches(tk.normalised, name_set, n=1, cutoff=weights.fuzzy_cutoff)
            if matches:
                fuzzy_name = matches[0]
                types = gazetteer.tag(fuzzy_name)
                tk.entity_type = types[0]
                tk.ambiguous = len(types) > 1
                tk.fuzzy_match = True
                tk.fuzzy_resolved = fuzzy_name


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
    name2_upper    = (row.get("NAME2_UPPER") or "")

    for tk in tagged:
        norm = tk.normalised

        if tk.ambiguous:
            score += weights.ambiguous_token

        if tk.fuzzy_match:
            # Fuzzy matches contribute but at half weight
            score += weights.city_context_match * 0.5
            continue

        if tk.entity_type == "county":
            if row.get("_ADMIN_CONTEXT_MATCH"):
                score += weights.county_context_match
            elif norm in county_upper:
                score += weights.county_context_match
            elif county_upper and norm not in county_upper:
                score += weights.admin_contradiction

        elif tk.entity_type == "district":
            if norm in district_upper:
                score += weights.district_context_match

        elif tk.entity_type in ("city", "town", "village"):
            if norm in place_upper or norm in county_upper:
                score += weights.city_context_match

        elif tk.entity_type in ("road_motorway", "road_a", "road_b"):
            if norm in name_upper:
                score += weights.road_context_match

        elif tk.entity_type == "junction":
            if norm in name_upper:
                score += weights.junction_match

        elif tk.entity_type == "unknown" and not tk.is_qualifier:
            # Named junction/roundabout candidates: reward when the unrecognised
            # token (e.g. "Spaghetti", "Magic") appears in the candidate's name or alt_name.
            if norm in name_upper or norm in name2_upper:
                score += weights.city_context_match

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
    OS Names stores COUNTY_UNITARY and POPULATED_PLACE as linked-data URIs in
    some exports, so text matching against them is unreliable. County/unitary
    context is applied spatially by intersecting candidate MBRs with a static
    admin BNG extent. Falls back to the full candidate set if an extent is
    unavailable or the spatial filter yields nothing.
    """
    original = candidates

    county_tokens = [
        tk.normalised for tk in tagged
        if tk.entity_type == "county" and not tk.is_qualifier
    ]
    city_tokens = [
        tk.normalised for tk in tagged
        if tk.entity_type in ("city", "town", "village") and not tk.is_qualifier
    ]

    filtered = candidates

    for token in county_tokens:
        extent = ADMIN_BNG_EXTENTS.get(resolve_alias(token))
        if extent is None:
            return original

        attempt = _filter_by_bng_extent(filtered, extent)
        if len(attempt) == 0:
            return original
        filtered = attempt.with_columns(pl.lit(True).alias("_ADMIN_CONTEXT_MATCH"))

    for token in city_tokens:
        attempt = filtered.filter(
            pl.col("NAME1_UPPER").str.contains(token, literal=True)
        )
        if len(attempt) > 0:
            filtered = attempt

    return filtered if len(filtered) > 0 else original


def _filter_by_bng_extent(
    candidates: pl.DataFrame,
    extent: tuple[float, float, float, float],
) -> pl.DataFrame:
    xmin, ymin, xmax, ymax = extent
    mbr_cols = {"MBR_XMIN", "MBR_YMIN", "MBR_XMAX", "MBR_YMAX"}

    if mbr_cols.issubset(candidates.columns):
        return candidates.filter(
            pl.col("MBR_XMIN").is_not_null()
            & pl.col("MBR_YMIN").is_not_null()
            & pl.col("MBR_XMAX").is_not_null()
            & pl.col("MBR_YMAX").is_not_null()
            & (pl.col("MBR_XMIN") <= xmax)
            & (pl.col("MBR_XMAX") >= xmin)
            & (pl.col("MBR_YMIN") <= ymax)
            & (pl.col("MBR_YMAX") >= ymin)
        )

    # Compatibility for older local parquets built before MBR columns were
    # retained: treat the point geometry as a degenerate candidate rectangle.
    if {"GEOMETRY_X", "GEOMETRY_Y"}.issubset(candidates.columns):
        return candidates.filter(
            pl.col("GEOMETRY_X").is_not_null()
            & pl.col("GEOMETRY_Y").is_not_null()
            & (pl.col("GEOMETRY_X") >= xmin)
            & (pl.col("GEOMETRY_X") <= xmax)
            & (pl.col("GEOMETRY_Y") >= ymin)
            & (pl.col("GEOMETRY_Y") <= ymax)
        )

    return candidates.head(0)


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

    # Pass 1: exact tagging
    tagged = tag_tokens(tokens, gazetteer, weights)

    # Derive county context before pass 2 so fuzzy can be county-scoped
    county_tokens_pre = [
        tk for tk in tagged if tk.entity_type == "county" and not tk.is_qualifier
    ]
    county_names = (
        _county_name_set(lookup, county_tokens_pre[0].normalised)
        if county_tokens_pre
        else None
    )

    # Pass 2: county-aware fuzzy for sole unknown place tokens
    _apply_fuzzy_tokens(tagged, gazetteer, weights, county_names)
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

    # Collect context tokens by type (after fuzzy resolution)
    county_tokens = [tk for tk in tagged if tk.entity_type == "county" and not tk.is_qualifier]
    place_tokens = [
        tk
        for tk in tagged
        if tk.entity_type in ("city", "town", "village") and not tk.is_qualifier
    ]
    all_non_qual = [
        tk for tk in tagged if not tk.is_qualifier and tk.entity_type not in ("unknown",)
    ]

    road_unanchored = False
    b_road_osm_used = False
    if road_ref:
        # Prefer qualifier-preceded place (e.g. "near Tadcaster") as spatial anchor
        anchor_place = next(
            (tk for tk in place_tokens if tk.preceded_by_qualifier),
            place_tokens[0] if place_tokens else None,
        )
        near_name = anchor_place.raw if anchor_place else None
        candidates_df = lookup.search_road(road_ref, junction_num=junction_num, near_name=near_name)

        # Place-anchor filtering: when road + place present but no junction,
        # restrict road candidates to those within road_place_anchor_km of the place.
        if not candidates_df.is_empty() and near_name and not junction_num:
            place_df = lookup.search_name(near_name)
            if not place_df.is_empty():
                place_row = place_df.row(0, named=True)
                px, py = place_row["GEOMETRY_X"], place_row["GEOMETRY_Y"]
                anchor_m = weights.road_place_anchor_km * 1000
                dist_expr = (
                    (pl.col("GEOMETRY_X") - px) ** 2
                    + (pl.col("GEOMETRY_Y") - py) ** 2
                ).sqrt()
                is_b_road = road_ref.upper().startswith("B")
                mbr_cols = {"MBR_XMIN", "MBR_YMIN", "MBR_XMAX", "MBR_YMAX"}
                if mbr_cols.issubset(candidates_df.columns) and not is_b_road:
                    anchored = (
                        candidates_df
                        .with_columns([
                            ((pl.col("MBR_XMIN") + pl.col("MBR_XMAX")) / 2).alias("_cx"),
                            ((pl.col("MBR_YMIN") + pl.col("MBR_YMAX")) / 2).alias("_cy"),
                        ])
                        .filter(
                            ((pl.col("_cx") - px) ** 2 + (pl.col("_cy") - py) ** 2).sqrt()
                            <= anchor_m
                        )
                        .drop(["_cx", "_cy"])
                    )
                else:
                    anchored = (
                        candidates_df
                        .with_columns(dist_expr.alias("_dist"))
                        .filter(pl.col("_dist") <= anchor_m)
                        .sort("_dist")
                        .drop("_dist")
                    )
                if not anchored.is_empty():
                    candidates_df = anchored
                    # For B-road OSM segments: pick the closest segment to the anchor
                    # rather than relying on score tie-breaking among equal-weight rows.
                    has_osm_road = (
                        is_b_road
                        and (
                            "OSM_ID" in candidates_df.columns
                            or "B Road" in candidates_df["LOCAL_TYPE"].to_list()
                        )
                    )
                    if has_osm_road:
                        b_road_osm_used = True
                        candidates_df = (
                            anchored
                            .with_columns(dist_expr.alias("_dist"))
                            .filter(pl.col("LOCAL_TYPE") == "B Road")
                            .sort("_dist")
                            .head(1)
                            .drop("_dist")
                        )
                else:
                    candidates_df = place_df
                    road_unanchored = True

        elif not junction_num and near_name:
            # candidates_df was empty (no OS Names / OSM result for road_ref).
            # For B-roads with a place anchor, try OSM roads directly.
            osm_segs = lookup.search_osm_roads(road_ref)
            if not osm_segs.is_empty():
                place_df = lookup.search_name(near_name)
                if not place_df.is_empty():
                    place_row = place_df.row(0, named=True)
                    px, py = place_row["GEOMETRY_X"], place_row["GEOMETRY_Y"]
                    anchor_m = weights.road_place_anchor_km * 1000
                    dist_expr = (
                        (pl.col("GEOMETRY_X") - px) ** 2
                        + (pl.col("GEOMETRY_Y") - py) ** 2
                    ).sqrt()
                    closest = (
                        osm_segs
                        .with_columns(dist_expr.alias("_dist"))
                        .filter(pl.col("_dist") <= anchor_m)
                        .sort("_dist")
                        .head(1)
                        .drop("_dist")
                    )
                    if not closest.is_empty():
                        candidates_df = closest
                        b_road_osm_used = True

        # Road/junction not in OS Names or OSM — fall back to nearby place
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
        # Use fuzzy-resolved name when available (e.g. "BRADFORD" for "Brafford")
        primary_name = primary_tk.fuzzy_resolved or primary_tk.raw
        candidates_df = lookup.search_name(primary_name)

    if candidates_df.is_empty():
        return None

    # Filter: if county tokens present, prefer candidates whose NAME1_UPPER
    # or MBR overlaps — use NAME1_UPPER containment as a soft pre-filter
    # (hard filter done in filter_by_admin_context)
    candidates_df = filter_by_admin_context(candidates_df, tagged)

    # OSM named-junction augmentation (non-road path only).
    # Triggered when junction-hint qualifiers are present (e.g. "interchange",
    # "junction", "roundabout") to catch named junctions absent from OS Names.
    # OSM candidates bypass the city-name filter above but get spatial
    # filtering against any place context tokens.
    if not road_ref:
        has_junction_hint = any(
            tk.is_qualifier and tk.normalised.lower() in _JUNCTION_HINT_QUALIFIERS
            for tk in tagged
        )
        if has_junction_hint:
            unknown_non_qual = [
                tk for tk in tagged
                if tk.entity_type == "unknown" and not tk.is_qualifier
            ]
            # Only search OSM when there are unknown tokens (e.g. "Spaghetti").
            # If all non-qualifier tokens are already resolved place names
            # (e.g. "Lofthouse Interchange"), OS Names gives the right answer.
            if unknown_non_qual:
                osm_pool = pl.DataFrame()
                for otk in unknown_non_qual:
                    res = lookup.search_osm_junctions(otk.raw)
                    if not res.is_empty():
                        osm_pool = pl.concat([osm_pool, res]) if not osm_pool.is_empty() else res

                if not osm_pool.is_empty():
                    # Spatially filter to candidates near the place context.
                    # If no candidates pass the spatial filter, discard OSM results
                    # entirely rather than falling back to a geographically wrong match.
                    osm_filtered = pl.DataFrame()
                    if place_tokens:
                        anchor_tk = next(
                            (tk for tk in place_tokens if tk.preceded_by_qualifier),
                            place_tokens[0],
                        )
                        place_df = lookup.search_name(anchor_tk.fuzzy_resolved or anchor_tk.raw)
                        if not place_df.is_empty():
                            pr = place_df.row(0, named=True)
                            px, py = pr["GEOMETRY_X"], pr["GEOMETRY_Y"]
                            anchor_m = weights.road_place_anchor_km * 1000
                            dist_expr = (
                                (pl.col("GEOMETRY_X") - px) ** 2
                                + (pl.col("GEOMETRY_Y") - py) ** 2
                            ).sqrt()
                            spatial = osm_pool.with_columns(
                                dist_expr.alias("_dist_to_anchor")
                            ).filter(pl.col("_dist_to_anchor") <= anchor_m)
                            if not spatial.is_empty():
                                # Pick the candidate closest to the anchor place
                                osm_filtered = (
                                    spatial.sort("_dist_to_anchor")
                                    .head(1)
                                    .drop("_dist_to_anchor")
                                )
                                # Bridge: if the OSM entry's formal name ends with a
                                # structural suffix (e.g. "Gravelly Hill Interchange"),
                                # look up the base geographic name in OS Names instead —
                                # OS Names has precise centroid coords for the suburb/place.
                                _STRUCTURAL_SUFFIXES = (
                                    " Interchange", " Junction", " Motorway Junction",
                                )
                                osm_name1 = osm_filtered["NAME1"][0] or ""
                                for _suf in _STRUCTURAL_SUFFIXES:
                                    if osm_name1.upper().endswith(_suf.upper()):
                                        _base = osm_name1[: -len(_suf)].strip()
                                        _bridged = lookup.search_name(_base)
                                        if not _bridged.is_empty():
                                            _near_bridged = _bridged.filter(
                                                (
                                                    (pl.col("GEOMETRY_X") - px) ** 2
                                                    + (pl.col("GEOMETRY_Y") - py) ** 2
                                                ).sqrt()
                                                <= anchor_m
                                            )
                                            if not _near_bridged.is_empty():
                                                # Boost TYPE_WEIGHT above OSM node score
                                                # so the OS Names centroid wins in scoring
                                                osm_filtered = (
                                                    _near_bridged.with_columns(
                                                        pl.lit(11).cast(pl.Int8).alias("TYPE_WEIGHT")
                                                    )
                                                    .head(1)
                                                )
                                        break
                    else:
                        osm_filtered = osm_pool

                    if not osm_filtered.is_empty():
                        candidates_df = (
                            pl.concat([candidates_df, osm_filtered], how="diagonal")
                            if not candidates_df.is_empty()
                            else osm_filtered
                        )

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
    if road_unanchored:
        notes_parts.append("road_section=unanchored")
    if b_road_osm_used:
        notes_parts.append("source=osm")

    inferred_match_type = best_row["LOCAL_TYPE"].lower().replace(" ", "_")
    if b_road_osm_used:
        inferred_match_type = "b_road_osm"

    return GeoResult(
        input=text,
        lat=lat,
        lon=lon,
        interpreted_as=f"{best_row['NAME1']} ({best_row['LOCAL_TYPE']})",
        match_type=(
            partial.match_type if partial and not b_road_osm_used
            else inferred_match_type
        ),
        level_resolved=2,
        confidence=confidence,
        candidates_considered=len(candidates_df),
        notes=",".join(notes_parts),
    )
