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
OSM_ROADS_PARQUET     = Path(__file__).parent.parent / "data" / "osm_roads.parquet"
COMBINED_PARQUET      = Path(__file__).parent.parent / "data" / "kaggle" / "ukgeo_data.parquet"
DEFAULT_PARQUET       = Path(__file__).parent.parent / "data" / "os_open_names.parquet"
ALIASES_CSV           = Path(__file__).parent.parent / "data" / "infrastructure_aliases.csv"

_NULL_CONTEXT_COLS = [
    pl.lit(None).cast(pl.Utf8).alias("COUNTY_UNITARY"),
    pl.lit(None).cast(pl.Utf8).alias("DISTRICT_BOROUGH"),
    pl.lit(None).cast(pl.Utf8).alias("POPULATED_PLACE"),
]

_MBR_COLS = ["MBR_XMIN", "MBR_YMIN", "MBR_XMAX", "MBR_YMAX"]


def _drop_null_mbr(df: pl.DataFrame) -> pl.DataFrame:
    """Drop MBR columns when all values are null.

    The combined Kaggle parquet stores MBR columns but fills them with null
    for sources without bounding-box data.  _filter_by_bng_extent() checks
    for column *presence* before using them, so null-filled columns cause it
    to return empty results instead of falling through to the GEOMETRY_X/Y
    point-in-box path.  Dropping them restores correct fallback behaviour.
    """
    mbr_present = [c for c in _MBR_COLS if c in df.columns]
    if not mbr_present:
        return df
    if all(df[c].is_null().all() for c in mbr_present):
        return df.drop(mbr_present)
    return df


class OSNamesLookup:
    """
    Loads OS Open Names parquet and exposes query methods.

    Prefers individual parquet files when present because they retain richer
    metadata. Falls back to data/kaggle/ukgeo_data.parquet when users have only
    downloaded the combined Kaggle release.
    """

    def __init__(self, parquet_path: Path = DEFAULT_PARQUET):
        # Prefer individual parquets when the default OS Names file exists —
        # they retain richer metadata (COUNTY_UNITARY, DISTRICT_BOROUGH,
        # POPULATED_PLACE) that improves scoring.  The combined Kaggle parquet
        # is the fallback for users who have only downloaded ukgeo_data.parquet.
        if parquet_path == DEFAULT_PARQUET and not DEFAULT_PARQUET.exists() and COMBINED_PARQUET.exists():
            self._load_from_combined()
        else:
            self._load_individual(parquet_path)

        # OSM B-road way segments — prefer the richer separate parquet if present.
        # _load_from_combined() sets this from the Kaggle slice when available.
        if OSM_ROADS_PARQUET.exists():
            self._osm_roads = pl.read_parquet(OSM_ROADS_PARQUET)
        elif not hasattr(self, "_osm_roads"):
            self._osm_roads = None
        self._aliases = self._load_aliases()

    def _load_from_combined(self) -> None:
        """Load all data slices from the combined Kaggle parquet."""
        raw = pl.read_parquet(COMBINED_PARQUET)

        # OS Open Names slice — reconstruct columns dropped for Kaggle release.
        # Drop null MBR columns so _filter_by_bng_extent falls through to the
        # GEOMETRY_X/Y point-in-box path rather than returning empty results.
        os_slice = raw.filter(pl.col("SOURCE") == "os_open_names")
        os_slice = _drop_null_mbr(os_slice)
        self._df = os_slice.with_columns(
            [pl.col("NAME2").fill_null("").str.to_uppercase().alias("NAME2_UPPER")]
            + _NULL_CONTEXT_COLS
        )

        # OS Open Roads junctions slice — restore expected JUNCTION_NUMBER column
        roads_slice = raw.filter(pl.col("SOURCE") == "os_open_roads")
        if len(roads_slice) > 0:
            self._junctions = _drop_null_mbr(
                roads_slice.rename({"NAME1": "JUNCTION_NUMBER"})
            )
        else:
            self._junctions = None

        # OSM named junctions slice — reconstruct NAME2_UPPER and context nulls
        osm_slice = raw.filter(pl.col("SOURCE") == "osm")
        if len(osm_slice) > 0:
            self._osm_junctions = _drop_null_mbr(osm_slice).with_columns(
                [pl.col("NAME2").fill_null("").str.to_uppercase().alias("NAME2_UPPER")]
                + _NULL_CONTEXT_COLS
            )
        else:
            self._osm_junctions = None

        # OSM B-road segments slice.
        osm_roads_slice = raw.filter(pl.col("SOURCE") == "osm_roads")
        if len(osm_roads_slice) > 0:
            self._osm_roads = _drop_null_mbr(osm_roads_slice).with_columns(
                [pl.col("NAME2").fill_null("").str.to_uppercase().alias("NAME2_UPPER")]
                + _NULL_CONTEXT_COLS
            )
        else:
            self._osm_roads = None

    def _load_individual(self, parquet_path: Path) -> None:
        """Load data from the original individual parquet files."""
        if not parquet_path.exists():
            raise FileNotFoundError(
                f"OS Open Names parquet not found at {parquet_path}. "
                "Run scripts/download_os_open_names.py first, or place "
                "data/kaggle/ukgeo_data.parquet for auto-detection."
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

    def _load_aliases(self) -> dict[str, dict]:
        """Load infrastructure aliases CSV as a dict keyed by uppercased name."""
        if not ALIASES_CSV.exists():
            return {}

        try:
            df = (
                pl.read_csv(ALIASES_CSV, comment_prefix="#")
                .with_columns(pl.col("lat").cast(pl.Utf8).alias("lat_text"))
                .filter(pl.col("lat_text").str.len_chars() > 0)
            )
        except Exception:
            return {}

        aliases = {}
        for row in df.to_dicts():
            try:
                aliases[row["name"].upper().strip()] = {
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                    "category": row.get("category", ""),
                    "verified_name": row.get("verified_name", ""),
                    "notes": row.get("notes", ""),
                }
            except (TypeError, ValueError, KeyError):
                continue
        return aliases

    def lookup_alias(self, text: str) -> dict | None:
        """Check if input matches a known infrastructure alias."""
        return self._aliases.get(text.upper().strip())

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
        if near_name and "POPULATED_PLACE" in q.columns:
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
        osm_roads = self.search_osm_roads(road_upper)
        if not osm_roads.is_empty() and len(q) < 3:
            q = pl.concat([q, osm_roads], how="diagonal") if not q.is_empty() else osm_roads
        return q.sort("TYPE_WEIGHT", descending=True).head(50)

    def search_osm_roads(self, road_ref: str) -> pl.DataFrame:
        """
        Return OSM B-road way-segment rows whose NAME1_UPPER exactly matches
        road_ref. Returns an empty DataFrame if osm_roads.parquet is not loaded.
        Column schema is compatible with search_road() and try_level2().
        """
        if self._osm_roads is None:
            return pl.DataFrame()
        ref_upper = road_ref.upper().strip()
        return (
            self._osm_roads
            .filter(pl.col("NAME1_UPPER") == ref_upper)
            .sort("TYPE_WEIGHT", descending=True)
            .head(50)
        )

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
        import math

        if not math.isfinite(easting) or not math.isfinite(northing):
            return math.nan, math.nan

        # Use pyproj if available for better accuracy, else approximate
        try:
            from pyproj import Transformer
            t = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
            lon_wgs, lat_wgs = t.transform(easting, northing)
            if math.isfinite(lat_wgs) and math.isfinite(lon_wgs):
                return round(lat_wgs, 6), round(lon_wgs, 6)
        except ImportError:
            pass

        return _bng_to_wgs84_fallback(easting, northing)


def _bng_to_wgs84_fallback(easting: float, northing: float) -> tuple[float, float]:
    """Convert OSGB36 / British National Grid eastings/northings to WGS84."""
    import math

    # Airy 1830 ellipsoid and National Grid projection constants.
    a, b = 6377563.396, 6356256.909
    f0 = 0.9996012717
    lat0, lon0 = math.radians(49.0), math.radians(-2.0)
    n0, e0 = -100000.0, 400000.0
    e2 = 1 - (b * b) / (a * a)
    n = (a - b) / (a + b)

    lat = lat0
    meridional_arc = 0.0
    while abs(northing - n0 - meridional_arc) >= 0.00001:
        lat = (northing - n0 - meridional_arc) / (a * f0) + lat
        ma = (1 + n + 5 / 4 * n**2 + 5 / 4 * n**3) * (lat - lat0)
        mb = (3 * n + 3 * n**2 + 21 / 8 * n**3) * math.sin(lat - lat0) * math.cos(lat + lat0)
        mc = (15 / 8 * n**2 + 15 / 8 * n**3) * math.sin(2 * (lat - lat0)) * math.cos(2 * (lat + lat0))
        md = 35 / 24 * n**3 * math.sin(3 * (lat - lat0)) * math.cos(3 * (lat + lat0))
        meridional_arc = b * f0 * (ma - mb + mc - md)

    sin_lat = math.sin(lat)
    cos_lat = math.cos(lat)
    tan_lat = math.tan(lat)
    nu = a * f0 / math.sqrt(1 - e2 * sin_lat**2)
    rho = a * f0 * (1 - e2) / (1 - e2 * sin_lat**2) ** 1.5
    eta2 = nu / rho - 1
    d_e = easting - e0

    vii = tan_lat / (2 * rho * nu)
    viii = tan_lat / (24 * rho * nu**3) * (5 + 3 * tan_lat**2 + eta2 - 9 * tan_lat**2 * eta2)
    ix = tan_lat / (720 * rho * nu**5) * (61 + 90 * tan_lat**2 + 45 * tan_lat**4)
    x = 1 / (cos_lat * nu)
    xi = 1 / (cos_lat * 6 * nu**3) * (nu / rho + 2 * tan_lat**2)
    xii = 1 / (cos_lat * 120 * nu**5) * (5 + 28 * tan_lat**2 + 24 * tan_lat**4)
    xiia = 1 / (cos_lat * 5040 * nu**7) * (
        61 + 662 * tan_lat**2 + 1320 * tan_lat**4 + 720 * tan_lat**6
    )

    lat_osgb = lat - vii * d_e**2 + viii * d_e**4 - ix * d_e**6
    lon_osgb = lon0 + x * d_e - xi * d_e**3 + xii * d_e**5 - xiia * d_e**7

    return _osgb36_latlon_to_wgs84(lat_osgb, lon_osgb, a, b)


def _osgb36_latlon_to_wgs84(
    lat: float,
    lon: float,
    osgb_a: float,
    osgb_b: float,
) -> tuple[float, float]:
    """Apply the standard Helmert transform from OSGB36 to WGS84."""
    import math

    osgb_e2 = 1 - (osgb_b * osgb_b) / (osgb_a * osgb_a)
    nu = osgb_a / math.sqrt(1 - osgb_e2 * math.sin(lat) ** 2)

    x1 = nu * math.cos(lat) * math.cos(lon)
    y1 = nu * math.cos(lat) * math.sin(lon)
    z1 = (1 - osgb_e2) * nu * math.sin(lat)

    tx, ty, tz = 446.448, -125.157, 542.060
    s = 20.4894 * 1e-6
    rx, ry, rz = (math.radians(v / 3600) for v in (0.1502, 0.2470, 0.8421))

    x2 = tx + (1 + s) * x1 - rz * y1 + ry * z1
    y2 = ty + rz * x1 + (1 + s) * y1 - rx * z1
    z2 = tz - ry * x1 + rx * y1 + (1 + s) * z1

    wgs_a, wgs_b = 6378137.000, 6356752.3141
    wgs_e2 = 1 - (wgs_b * wgs_b) / (wgs_a * wgs_a)
    p = math.sqrt(x2**2 + y2**2)
    lat_wgs = math.atan2(z2, p * (1 - wgs_e2))
    previous = 0.0
    while abs(lat_wgs - previous) > 1e-12:
        previous = lat_wgs
        nu = wgs_a / math.sqrt(1 - wgs_e2 * math.sin(lat_wgs) ** 2)
        lat_wgs = math.atan2(z2 + wgs_e2 * nu * math.sin(lat_wgs), p)
    lon_wgs = math.atan2(y2, x2)

    return round(math.degrees(lat_wgs), 6), round(math.degrees(lon_wgs), 6)
