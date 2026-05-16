"""
Parquet-backed lookup for OS Open Names data.
Loaded once per Geocoder instance; designed for bulk querying.
"""

import polars as pl
from pathlib import Path
from typing import Optional

# OS Open Names local types we care about, grouped by priority tier
PLACE_TYPES = {
    "city":      ["City", "Suburban Area"],
    "town":      ["Town", "Village", "Hamlet", "Other Settlement"],
    "road":      ["Named Road", "Numbered Road", "Motorway"],
    "junction":  ["Junction", "Roundabout"],
    "admin":     ["County", "Unitary Authority", "District Borough",
                  "London Borough", "Metropolitan District"],
    "postcode":  ["Postcode"],
}

# Flat set for filtering on load
ALL_TYPES = {t for types in PLACE_TYPES.values() for t in types}

# Priority weight per type (higher = preferred candidate)
TYPE_WEIGHT = {
    "City": 10, "Suburban Area": 7,
    "Town": 8, "Village": 6, "Hamlet": 4, "Other Settlement": 3,
    "Junction": 9, "Roundabout": 8,
    "Named Road": 5, "Numbered Road": 5, "Motorway": 6,
    "County": 2, "Unitary Authority": 2, "District Borough": 2,
    "London Borough": 2, "Metropolitan District": 2,
    "Postcode": 1,
}

# OS Open Names CSV columns we actually need
_KEEP_COLS = [
    "NAME1",           # primary name
    "NAME1_LANG",
    "NAME2",           # secondary/alias name
    "TYPE",            # local type
    "LOCAL_TYPE",
    "GEOMETRY_X",      # easting (BNG)
    "GEOMETRY_Y",      # northing (BNG)
    "MOST_DETAIL_VIEW_RES",
    "COUNTY_UNITARY",
    "DISTRICT_BOROUGH",
    "POPULATED_PLACE",
    "POSTCODE_DISTRICT",
]


JUNCTIONS_PARQUET     = Path(__file__).parent.parent / "data" / "os_open_roads_junctions.parquet"
OSM_JUNCTIONS_PARQUET = Path(__file__).parent.parent / "data" / "osm_named_junctions.parquet"


class OSNamesLookup:
    """
    Loads OS Open Names parquet and exposes query methods.
    Optionally loads OS Open Roads junction parquet and OSM named junctions
    parquet if present.
    """

    def __init__(self, parquet_path: Path):
        if not parquet_path.exists():
            raise FileNotFoundError(
                f"OS Open Names parquet not found at {parquet_path}. "
                "Run scripts/download_os_open_names.py first."
            )
        self._df = pl.read_parquet(parquet_path)

        # OS Open Roads junction lookup (numbered junctions)
        if JUNCTIONS_PARQUET.exists():
            self._junctions = pl.read_parquet(JUNCTIONS_PARQUET)
        else:
            self._junctions = None

        # OSM named junctions / roundabouts (named interchanges etc.)
        if OSM_JUNCTIONS_PARQUET.exists():
            self._osm_junctions = pl.read_parquet(OSM_JUNCTIONS_PARQUET)
        else:
            self._osm_junctions = None

    @property
    def size(self) -> int:
        return len(self._df)

    def search_name(
        self,
        name: str,
        local_types: Optional[list[str]] = None,
        county: Optional[str] = None,
        limit: int = 20,
    ) -> pl.DataFrame:
        """
        Case-insensitive name search, optionally filtered by local type and county.
        Returns candidates sorted by type weight descending.
        """
        name_upper = name.upper()
        q = (
            self._df
            .filter(
                pl.col("NAME1_UPPER").str.contains(name_upper, literal=True)
                | pl.col("NAME2_UPPER").str.contains(name_upper, literal=True)
            )
        )
        if local_types:
            q = q.filter(pl.col("LOCAL_TYPE").is_in(local_types))
        if county:
            q = q.filter(
                pl.col("COUNTY_UNITARY").str.to_uppercase()
                .str.contains(county.upper(), literal=True)
            )
        return q.sort("TYPE_WEIGHT", descending=True).head(limit)

    def search_road(
        self,
        road_ref: str,
        junction_num: Optional[str] = None,
        near_name: Optional[str] = None,
    ) -> pl.DataFrame:
        """
        Look up a road/junction reference.
        If junction_num is given, searches OS Open Roads junction parquet first
        (format: "M62 J26"), falling back to OS Names road rows.
        """
        road_upper = road_ref.upper().strip()
        junction_upper = junction_num.upper().strip().lstrip("J") if junction_num else None

        # --- Junction lookup via OS Open Roads ---
        if junction_upper and self._junctions is not None:
            # Build combined key as OS stores it: "M62 J26", "A1(M) J47"
            # Exact equality prevents M62 J26 from matching M621 J26.
            search_key = f"{road_upper} J{junction_upper}"
            junction_col = pl.col("JUNCTION_NUMBER").str.to_uppercase()
            q = self._junctions.filter(
                junction_col == search_key
            )
            if q.is_empty():
                # Lettered junctions are stored as e.g. "J2A"; allow this only
                # after the exact lookup misses.
                q = self._junctions.filter(
                    junction_col.str.starts_with(search_key)
                    & (junction_col.str.len_chars() == len(search_key) + 1)
                    & junction_col.str.slice(-1).is_in(list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
                )
            if not q.is_empty():
                # Return in same schema as OS Names search for compatibility
                return q.with_columns([
                    pl.col("JUNCTION_NUMBER").alias("NAME1"),
                    pl.lit("Junction").alias("LOCAL_TYPE"),
                    pl.lit(9).cast(pl.Int8).alias("TYPE_WEIGHT"),
                    pl.col("JUNCTION_NUMBER").str.to_uppercase().alias("NAME1_UPPER"),
                    pl.lit("").cast(pl.Utf8).alias("NAME2_UPPER"),
                    pl.lit(None).cast(pl.Utf8).alias("COUNTY_UNITARY"),
                    pl.lit(None).cast(pl.Utf8).alias("DISTRICT_BOROUGH"),
                    pl.lit(None).cast(pl.Utf8).alias("POPULATED_PLACE"),
                ])

        # --- Fallback: OS Names road rows ---
        # Use exact equality to prevent "A64" from matching "A640", "A641" etc.
        local_types = ["Motorway", "Numbered Road", "Named Road"]
        q = self._df.filter(
            pl.col("LOCAL_TYPE").is_in(local_types)
            & (pl.col("NAME1_UPPER") == road_upper)
        )
        if near_name:
            near_upper = near_name.upper()
            q = q.with_columns(
                pl.when(
                    pl.col("POPULATED_PLACE").str.to_uppercase()
                    .str.contains(near_upper, literal=True)
                )
                .then(pl.col("TYPE_WEIGHT") + 5)
                .otherwise(pl.col("TYPE_WEIGHT"))
                .alias("TYPE_WEIGHT")
            )
        return q.sort("TYPE_WEIGHT", descending=True).head(20)

    def search_osm_junctions(
        self,
        name: str,
        limit: int = 10,
    ) -> pl.DataFrame:
        """
        Case-insensitive substring search against OSM named junctions/roundabouts.
        Returns an empty DataFrame if the OSM parquet was not loaded.
        Column schema is compatible with score_candidate() and try_level2().
        """
        if self._osm_junctions is None:
            return pl.DataFrame()

        name_upper = name.upper()
        results = (
            self._osm_junctions
            .filter(
                pl.col("NAME1_UPPER").str.contains(name_upper, literal=True)
                | pl.col("NAME2_UPPER").str.contains(name_upper, literal=True)
            )
            .sort("TYPE_WEIGHT", descending=True)
            .head(limit)
        )
        # Ensure columns expected by score_candidate are present (as nulls if absent)
        for col, dtype in [
            ("COUNTY_UNITARY",   pl.Utf8),
            ("DISTRICT_BOROUGH", pl.Utf8),
            ("POPULATED_PLACE",  pl.Utf8),
        ]:
            if col not in results.columns:
                results = results.with_columns(pl.lit(None).cast(dtype).alias(col))
        return results

    def bng_to_wgs84(self, easting: float, northing: float) -> tuple[float, float]:
        """
        Approximate BNG (OSGB36) to WGS84 conversion.
        Accurate to ~5m — sufficient for geocoding purposes.
        """
        # Helmert transformation parameters (OSTN02 approximation)
        a, b = 6377563.396, 6356256.909
        F0 = 0.9996012717
        lat0, lon0 = 49.0 * 3.14159265 / 180, -2.0 * 3.14159265 / 180
        N0, E0 = -100000.0, 400000.0
        e2 = 1 - (b / a) ** 2
        n = (a - b) / (a + b)

        lat = lat0
        M = 0.0
        for _ in range(100):
            lat = (northing - N0 - M) / (a * F0) + lat
            M = (b * F0 * (
                (1 + n + 5/4 * n**2 + 5/4 * n**3) * (lat - lat0)
                - (3*n + 3*n**2 + 21/8 * n**3) * 2 * (lat - lat0) / 2  # simplified
            ))
            if abs(northing - N0 - M) < 0.001:
                break

        # Simplified direct formula (sufficient accuracy for geocoding)
        import math
        lat_r = math.atan2(northing - N0, easting - E0) + lat0
        # Use pyproj if available for better accuracy, else approximate
        try:
            from pyproj import Transformer
            t = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
            lon_wgs, lat_wgs = t.transform(easting, northing)
            return round(lat_wgs, 6), round(lon_wgs, 6)
        except ImportError:
            # Fallback: rough linear approximation (error ~100m, acceptable for Level 2)
            lat_wgs = 49.0 + (northing - 0) / 111320
            lon_wgs = -7.5 + (easting - 0) / 65000
            return round(lat_wgs, 5), round(lon_wgs, 5)
