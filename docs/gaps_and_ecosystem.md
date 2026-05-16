# Gaps, ecosystem context, and complementary tools

This document covers what ukgeo is missing, how it sits within the broader open road safety ecosystem, and what tools complement it and Open Road Risk. It is intended as a thinking document — honest about gaps, not a roadmap commitment.

Last updated: May 2026.

---

## 1. Geocoding pipeline gaps

### B-roads (known, in progress)
OS Open Names does not include B-roads as geocodable named road entries. The STATS19 benchmark showed 31.1% of inputs unresolved, driven primarily by B-road references. OSM road data via the Overpass API is being added as a supplementary source to fill this.

### Linear referencing — the deeper problem
"M62 between J26 and J27" or "A64 2 miles east of Tadcaster" are not geocoding problems — they are linear referencing problems. The input describes a point on a line, not a named place. ukgeo currently approximates this by finding the nearest road section to an anchor place, but a proper solution requires road geometry and interpolation along it.

The correct tool for this is geopandas with OS Open Roads geometry (which has full road centreline data) or OSMnx (which has the same from OSM). A proper linear referencing module would:
1. Find the road geometry for the road reference
2. Take the anchor place as a fractional offset or distance along that geometry
3. Return the interpolated point

This is a meaningful piece of work but would significantly improve accuracy for road safety data where "between junction X and Y" is a common location format.

### STATS19 already has coordinates
The STATS19 benchmark confirmed an important finding: STATS19 records already have Easting/Northing from GPS at the scene. ukgeo's road centroid output (median 4.6km error) is worse than the existing coordinates for these records.

ukgeo's actual value for STATS19 is:
- **Data quality flagging** — identify records where the existing Easting/Northing looks implausible (e.g. point is on water, in a field, or far from the stated road)
- **Derived/summary datasets** — handle reports, extracts, or aggregated tables that have road references but no coordinates
- **Missing coordinates** — fill in where STATS19 coordinates are absent or redacted

This should be reflected clearly in documentation to set honest expectations.

### No reverse geocoding
Given coordinates, what road/junction/place is this? Useful for validating STATS19 records and for interpreting Open Road Risk output ("this high-risk link is on the A647 near Bradford"). Currently completely absent. Would use the same OS Names parquet data already downloaded — moderate effort to add.

---

## 2. What ukgeo is missing as a tool

### CLI interface
`ukgeo geocode input.csv output.csv` does not exist. For road safety analysts who are not Python users, a command-line interface is the difference between usable and not. This is a low-effort high-value addition — Python's `argparse` or `click`, wrapping `geocode_batch()`.

```bash
ukgeo geocode locations.csv --output results.csv --domain road_safety
ukgeo geocode "M62 Junction 26"  # single query
```

### Map output
`geocode_batch()` returns a DataFrame. A simple `plot_results()` function using folium showing resolved (green) vs unresolved (red) points on a UK map would make results immediately communicable to non-technical stakeholders. Also useful for spotting systematic mis-snaps.

### Confidence calibration
"High confidence" needs to be validated, not assumed. A calibration curve — for inputs labelled High/Medium/Low, what % are actually within 500m/1km/5km of true location — would show whether the confidence scores are meaningful or misleading. The STATS19 benchmark is a start but measures road centroids, not true location accuracy.

What is needed: a human-labelled set of ~200 inputs with verified true coordinates, stratified by input type (postcode, junction, place name, road+place, colloquial). Without this, accuracy claims are not defensible.

### Chunked/streaming batch processing
`geocode_batch()` loads all inputs into memory. For full STATS19 1979–2024 (~2M records, 1.4GB CSV) this is impractical on a standard machine. A generator-based or chunked alternative — processing N rows at a time and appending to a parquet output — would handle this without memory issues.

### Data quality pre-screening
Before geocoding, flag inputs likely to resolve poorly: too short, all qualifier tokens, no recognisable place or road reference. A `screen_inputs()` function that returns a quality tier (likely resolvable / uncertain / likely to fail) would save time on bulk jobs and set honest expectations before running the full pipeline.

---

## 3. The broader open road safety ecosystem

### R stats19 package — the closest equivalent
The R `stats19` package (Lovelace et al., published in JOSS 2019, updated to v4.0.0 as of 2026) covers downloading, reading, formatting, and spatial analysis of STATS19 data end-to-end. It is peer-reviewed, widely used in UK road safety research, and accompanied by a published book ("Reproducible Road Safety Research with R", 2025 Quarto edition) used in university teaching.

**There is no Python equivalent.** Python users working with STATS19 have no clean package for data access and formatting — they write their own parsing code, which is exactly the duplicated effort the R package was built to eliminate. ukgeo could anchor a Python STATS19 ecosystem but currently only covers geocoding.

Key capabilities of the R stats19 package that have no Python equivalent:
- `get_stats19()` — single function download, decode, and format
- `format_collisions()` / `format_casualties()` / `format_vehicles()` — decode integer codes to readable labels
- `format_sf()` — convert to spatial object with correct CRS
- Integration with `sf`, `dplyr`, `tmap` for spatial analysis

### OSMnx
Python package for downloading, modelling, and analysing street networks from OSM. Used widely in transport research. Key features relevant to Open Road Risk and ukgeo:
- Road network as a NetworkX graph — routing, centrality, network metrics
- Speed and travel time attributes on edges
- Works with geopandas — easy spatial joins
- Useful for cross-validating OS Open Roads geometry

OSMnx uses the Overpass API and is best for city/region-scale work. For GB-wide analysis, Pyrosm (which reads local OSM PBF files from Geofabrik) is faster.

### Pyrosm
Reads OSM PBF data files locally — faster than Overpass API for large areas. Can parse driving networks for all of Great Britain from a single ~1.5GB PBF download. Outputs as GeoDataFrame. Relevant if ukgeo or Open Road Risk needs GB-scale OSM road geometry without repeated API calls.

### stplanr (R)
R package for sustainable transport planning — origin-destination data, route networks, spatial aggregation. Less directly relevant but the broader ecosystem context for the kind of analysis Open Road Risk does.

---

## 4. Complementary tools for Open Road Risk

These are not gaps in ukgeo but tools worth knowing about for the Open Road Risk pipeline.

### PySAL / esda — spatial autocorrelation
Open Road Risk has a Moran's I diagnostic as a TODO. `esda.Moran` from the PySAL ecosystem is the standard implementation. Integrates cleanly with a polars/geopandas workflow via a simple spatial weights matrix from the road network.

```python
from esda.moran import Moran
from libpysal.weights import Queen
w = Queen.from_dataframe(gdf)
moran = Moran(gdf["residuals"], w)
print(moran.I, moran.p_sim)
```

### SHAP — model interpretability
Open Road Risk's XGBoost model produces `risk_percentile`. SHAP values would show which features drive high risk on specific road links — speed limit, road type, junction density, AADT. Standard in the XGBoost ecosystem, would add interpretability to the operational output for users asking "why is this road high risk?"

```python
import shap
explainer = shap.TreeExplainer(xgb_model)
shap_values = explainer.shap_values(X)
shap.summary_plot(shap_values, X)
```

### IMD / deprivation indices
Open Road Risk produces risk percentiles by road link. Adding Index of Multiple Deprivation (LSOA-level) as a covariate or post-hoc join would allow analysis of whether high-risk roads disproportionately affect deprived areas — a significant policy question. The data is open (MHCLG), the join is a standard spatial operation via `geopandas`.

### momepy — urban morphology metrics
Could add road network geometry metrics (intersection density, street length distribution, connectivity) as Stage 2 XGBoost features. More relevant for urban links where network structure correlates with risk.

### folium / keplergl — interactive map output
For the Open Road Risk Quarto site, folium is the lower-friction Python path to interactive maps. keplergl handles larger datasets better. Both produce self-contained HTML that embeds in Quarto. The React/Leaflet prototype explored earlier was more powerful but higher maintenance.

---

## 5. The missing benchmark

The most important thing absent from both ukgeo and Open Road Risk is a properly constructed evaluation dataset.

The STATS19 benchmark measures road centroid accuracy — not geocoding quality for the intended use cases. What is needed:

- ~300–500 inputs covering all input types: postcode, motorway junction, A-road+place, named interchange, colloquial name, old county name, road suffix abbreviation, typo
- Human-verified true coordinates (not derived from another dataset)
- Stratified so each input type is represented
- Ideally with two labellers for disputed cases

Without this, accuracy claims are not reproducible or comparable to other tools. This is low effort to construct (manual, not algorithmic) but high value for credibility — especially if Open Road Risk or ukgeo is eventually written up or published.

---

## 6. Python STATS19 ecosystem — the opportunity

This section is speculative but worth capturing.

The R stats19 package succeeded because it eliminated duplicated effort: every researcher was writing their own STATS19 parsing code with their own bugs. A Python equivalent — `pip install stats19` — would do the same for the growing number of Python-first road safety analysts.

The minimal viable Python stats19 package would need:
- `download_stats19(year, type)` — download raw CSVs from data.gov.uk
- `read_collisions(path)` — parse and decode integer codes to labels
- `read_casualties(path)` / `read_vehicles(path)` — same
- `to_geodataframe(df)` — convert Easting/Northing to a GeoDataFrame with OSGB36 CRS

ukgeo's `scripts/build_stats19_eval.py` is already partway there. Whether this grows into a separate package or stays as utility scripts is a decision for later — but the gap is real and documented here.