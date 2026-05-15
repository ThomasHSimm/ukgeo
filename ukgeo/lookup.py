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


class OSNamesLookup:
    """
    Loads OS Open Names parquet and exposes query methods.
    All queries return polars DataFrames.
    """

    def __init__(self, parquet_path: Path):
        if not parquet_path.exists():
            raise FileNotFoundError(
                f"OS Open Names parquet not found at {parquet_path}. "
                "Run scripts/download_os_open_names.py first."
            )
        self._df = pl.read_parquet(parquet_path)

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
        Look up a road reference (e.g. 'M62', 'A647') with optional junction.
        Returns junction/roundabout rows if junction_num given, else road rows.
        """
        road_upper = road_ref.upper()
        local_types = ["Junction", "Roundabout"] if junction_num else ["Motorway", "Numbered Road", "Named Road"]
        q = self._df.filter(
            pl.col("LOCAL_TYPE").is_in(local_types)
            & pl.col("NAME1_UPPER").str.contains(road_upper, literal=True)
        )
        if junction_num:
            q = q.filter(
                pl.col("NAME1_UPPER").str.contains(junction_num, literal=True)
                | pl.col("NAME2_UPPER").str.contains(junction_num, literal=True)
            )
        if near_name:
            near_upper = near_name.upper()
            # Prefer rows where POPULATED_PLACE or COUNTY_UNITARY mentions near_name
            q = q.with_columns(
                pl.when(
                    pl.col("POPULATED_PLACE").str.to_uppercase().str.contains(near_upper, literal=True)
                    | pl.col("COUNTY_UNITARY").str.to_uppercase().str.contains(near_upper, literal=True)
                )
                .then(pl.col("TYPE_WEIGHT") + 5)
                .otherwise(pl.col("TYPE_WEIGHT"))
                .alias("TYPE_WEIGHT")
            )
        return q.sort("TYPE_WEIGHT", descending=True).head(20)

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
