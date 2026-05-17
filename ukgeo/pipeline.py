"""
Main Geocoder class — orchestrates levels 1-2 (and stubs for 3-4).
Designed for single calls and bulk batch processing.
"""

import os
from pathlib import Path
from typing import Optional, Union
import polars as pl

from .models import GeoResult
from .lookup import OSNamesLookup
from .level1_regex import try_level1
from .level2_ner import ScoringWeights, TokenGazetteer, try_level2

DEFAULT_PARQUET = Path(__file__).parent.parent / "data" / "os_open_names.parquet"


class Geocoder:
    """
    UK geocoder with tiered resolution pipeline.

    Levels:
        1 — regex (postcode → postcodes.io, road pattern extraction)
        2 — OS Names token scoring
        3 — OS Names API / Nominatim proxy  [stub]
        4 — local Ollama LLM               [stub]

    Usage:
        geo = Geocoder()
        result = geo.geocode("LS1 1BA")
        df = geo.geocode_batch(["LS1 1BA", "M62 Junction 26", ...])
    """

    def __init__(
        self,
        parquet_path: Path = DEFAULT_PARQUET,
        weights: Optional[ScoringWeights] = None,
        weights_path: Optional[Path] = None,
        max_level: int = 2,
        extra_qualifiers: list[str] | None = None,
        os_api_key: Optional[str] = None,
    ):
        """
        Args:
            parquet_path:  Path to OS Open Names parquet (built by download script).
            weights:       ScoringWeights instance. If None, loads from weights_path
                           or uses defaults.
            weights_path:  Path to a YAML weights file (config/weights.yaml).
            max_level:     Maximum pipeline level to attempt (1-4). Default 2.
            extra_qualifiers: Additional domain words to treat as qualifiers.
            os_api_key:    Optional OS Names API key for Level 3 fallback.
        """
        self._lookup = OSNamesLookup(parquet_path)
        self._gazetteer = TokenGazetteer(self._lookup)
        self._weights = weights or self._load_weights(weights_path)
        if extra_qualifiers is not None:
            self._weights.extra_qualifiers = extra_qualifiers
        self._max_level = max_level
        self._os_api_key = os_api_key or os.getenv("OS_API_KEY")

    # ------------------------------------------------------------------
    # Weight loading
    # ------------------------------------------------------------------

    @staticmethod
    def _load_weights(path: Optional[Path]) -> ScoringWeights:
        if path and path.exists():
            import yaml
            with open(path) as f:
                d = yaml.safe_load(f)
            return ScoringWeights(**d)
        return ScoringWeights()

    def save_weights(self, path: Path):
        import yaml
        import dataclasses
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(dataclasses.asdict(self._weights), f)

    # ------------------------------------------------------------------
    # Single geocode
    # ------------------------------------------------------------------

    def geocode(self, text: str) -> GeoResult:
        """Resolve a single location string. Always returns a GeoResult."""
        text = text.strip()
        if not text:
            return GeoResult(input=text, confidence="Low", notes="empty input")

        # Level 0 — infrastructure alias lookup
        alias = self._lookup.lookup_alias(text)
        if alias:
            return GeoResult(
                input=text,
                lat=alias["lat"],
                lon=alias["lon"],
                interpreted_as=alias.get("verified_name", text),
                match_type=alias.get("category", "infrastructure"),
                level_resolved=0,
                confidence="High",
                candidates_considered=1,
                notes=f"source=alias_csv,{alias.get('notes', '')}",
            )

        # Level 1 — regex / postcode
        result = try_level1(text)
        if result and result.resolved:
            return result
        if result and result.match_type == "postcode":
            local_postcode = self._try_local_postcode(result)
            if local_postcode and local_postcode.resolved:
                return local_postcode

        # Level 2 — OS Names token scoring
        if self._max_level >= 2:
            partial = result  # may carry road_ref etc.
            result2 = try_level2(text, partial, self._lookup, self._gazetteer, self._weights)
            if result2 and result2.resolved and result2.confidence != "Low":
                return result2

        # Level 3 stub — API fallback
        if self._max_level >= 3:
            result3 = self._try_level3(text)
            if result3 and result3.resolved:
                return result3

        if self._max_level >= 2 and "result2" in locals() and result2 and result2.resolved:
            return result2

        # Level 4 stub — local LLM
        if self._max_level >= 4:
            result4 = self._try_level4(text)
            if result4 and result4.resolved:
                return result4

        # Unresolved
        return GeoResult(
            input=text,
            confidence="Low",
            level_resolved=None,
            notes="unresolved after all levels",
        )

    def _try_local_postcode(self, result: GeoResult) -> Optional[GeoResult]:
        """Fallback to OS Open Names postcode rows when postcodes.io is unavailable."""
        if not result.interpreted_as:
            return None
        postcode = (
            result.interpreted_as
            .removeprefix("Postcode ")
            .split(" (", 1)[0]
            .strip()
        )
        if not postcode:
            return None

        candidates = self._lookup.search_name(postcode, local_types=["Postcode"], limit=1)
        if candidates.is_empty():
            return None

        row = candidates.row(0, named=True)
        lat, lon = self._lookup.bng_to_wgs84(row["GEOMETRY_X"], row["GEOMETRY_Y"])
        return GeoResult(
            input=result.input,
            lat=lat,
            lon=lon,
            interpreted_as=f"Postcode {row['NAME1']}",
            match_type="postcode",
            level_resolved=2,
            confidence="High",
            candidates_considered=len(candidates),
            notes="OS Open Names postcode fallback; postcodes.io unavailable",
        )

    # ------------------------------------------------------------------
    # Bulk geocode
    # ------------------------------------------------------------------

    def geocode_batch(
        self,
        inputs: Union[list[str], pl.Series],
        show_progress: bool = True,
    ) -> pl.DataFrame:
        """
        Geocode a list/Series of location strings.
        Returns a polars DataFrame with one row per input.
        Preserves input order.
        """
        if isinstance(inputs, pl.Series):
            inputs = inputs.to_list()

        results = []
        n = len(inputs)
        for i, text in enumerate(inputs):
            results.append(self.geocode(text).as_dict())
            if show_progress and (i + 1) % 500 == 0:
                print(f"  {i+1}/{n} geocoded")

        return pl.DataFrame(results)

    # ------------------------------------------------------------------
    # Benchmarking
    # ------------------------------------------------------------------

    def benchmark(
        self,
        test_data: list[dict],  # [{"input": str, "lat": float, "lon": float}, ...]
        label: str = "ukgeo",
    ) -> pl.DataFrame:
        """
        Run geocoder against labelled test data and report distance errors.
        test_data: list of dicts with keys: input, lat (true), lon (true)
        Returns a DataFrame with per-row distance error in metres.
        """
        import math

        rows = []
        for item in test_data:
            text = item["input"]
            true_lat = item["lat"]
            true_lon = item["lon"]
            result = self.geocode(text)
            if result.resolved:
                dist = _haversine(true_lat, true_lon, result.lat, result.lon)
            else:
                dist = None
            rows.append({
                "input": text,
                "true_lat": true_lat,
                "true_lon": true_lon,
                "pred_lat": result.lat,
                "pred_lon": result.lon,
                "confidence": result.confidence,
                "level_resolved": result.level_resolved,
                "match_score": _parse_match_score(result.notes),
                "distance_m": dist,
                "resolved": result.resolved,
                "geocoder": label,
            })

        df = pl.DataFrame(rows)
        resolved = df.filter(pl.col("resolved"))
        print(f"\n--- {label} benchmark ---")
        print(f"  Resolved:     {len(resolved)}/{len(df)} ({100*len(resolved)/max(len(df),1):.1f}%)")
        if len(resolved) > 0:
            errs = resolved["distance_m"].drop_nulls()
            print(f"  Median error: {errs.median():.0f} m")
            print(f"  Mean error:   {errs.mean():.0f} m")
            print(f"  <100m:        {(errs < 100).sum()}/{len(errs)}")
            print(f"  <1000m:       {(errs < 1000).sum()}/{len(errs)}")
        return df

    # ------------------------------------------------------------------
    # Level stubs
    # ------------------------------------------------------------------

    def _try_level3(self, text: str) -> Optional[GeoResult]:
        partial = try_level1(text)
        if partial and partial.match_type == "junction":
            return None

        from .level3_os_names import try_level3

        return try_level3(text, self._lookup, api_key=self._os_api_key)

    def _try_level4(self, text: str) -> Optional[GeoResult]:
        # TODO: local Ollama LLM call
        return None


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _haversine(lat1, lon1, lat2, lon2) -> float:
    """Distance in metres between two WGS84 points."""
    import math
    R = 6_371_000
    p = math.pi / 180
    a = (
        math.sin((lat2 - lat1) * p / 2) ** 2
        + math.cos(lat1 * p) * math.cos(lat2 * p)
        * math.sin((lon2 - lon1) * p / 2) ** 2
    )
    return 2 * R * math.asin(math.sqrt(a))


def _parse_match_score(notes: Optional[str]) -> Optional[float]:
    if not notes:
        return None
    for part in notes.split(","):
        if part.startswith("match_score="):
            try:
                return float(part.split("=", 1)[1])
            except ValueError:
                pass
    return None
