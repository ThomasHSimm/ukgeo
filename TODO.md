# ukgeo — TODO

Priority: 🔴 High / 🟡 Medium / 🟢 Low / 💡 Idea

---

## 🔴 Next up

### CLI interface
Add `ukgeo geocode input.csv --output results.csv` and `ukgeo geocode "M62 Junction 26"`.
Low effort, high value — makes the tool accessible to non-Python road safety analysts.
Use `argparse` or `click`, wrapping `geocode_batch()` and single `geocode()`.
Add to `pyproject.toml` as a console script entry point.

### Human-labelled evaluation set
~300 inputs with human-verified true coordinates, stratified by input type.
Without this, accuracy claims are not defensible or comparable to other tools.
See `docs/gaps_and_ecosystem.md` section 5 for specification.
This is the highest-credibility gap — low effort to construct (manual), high value.

### ✅ STATS19 benchmark + B-road gap — COMPLETE (2026-05-16)
v2 benchmark: 99.9% resolve rate (+31.0%), 3,299m median error (−1,293m), B-roads 5.1%→99.9%.

Fix: Level 1 B-road regex + Level 2 road_b token type + OSM road segments (105,720 ways).
See `data/stats19_diagnosis.txt` for full analysis. See `data/stats19_benchmark_v2.csv` for results.

Remaining open question: ukgeo assigns road centroids, not collision-specific points.
ukgeo is most valuable for STATS19 where existing coordinates are missing or suspect, or
for derived/summary datasets with road refs but no coordinates.
1. Downloads a year of STATS19 collision data from data.gov.uk
2. Synthesises free-text location strings from `Road_1`, `Junction_Detail`, `Local_Authority_District` fields
3. Runs them through `ukgeo.geocode_batch()` 
4. Compares results against STATS19 `Easting`/`Northing` ground truth
5. Outputs a benchmark report (median error, % resolved, % within 500m/1km/5km)

This doubles as:
- A real-world bulk evaluation of ukgeo accuracy
- Proof-of-concept integration with Open Road Risk pipeline
- A calibration dataset for `scripts/calibrate.py`

Related: ukgeo should be importable from Open Road Risk as a utility module. Consider publishing to PyPI or at minimum documenting as a git submodule/dependency.

---

## 🟡 Pipeline improvements

### Linear referencing for road+offset inputs
"M62 between J26 and J27" is a linear referencing problem, not a geocoding problem.
Proper solution: find road geometry (OS Open Roads or OSMnx), interpolate point at
fractional offset or distance from anchor place.
See `docs/gaps_and_ecosystem.md` section 1 for detail.
High value for road safety domain. Medium-high effort.

### Reverse geocoding
Given coordinates, return road/junction/place name.
Useful for STATS19 data quality validation and Open Road Risk output interpretation.
Uses existing OS Names parquet — moderate effort to add as new pipeline direction.

### A1(M) bracket normalisation
Level 1 regex doesn't handle `A1M` or `A1 M` (no brackets).
Fix: add alternative patterns to `_MOTORWAY`/`_AROAD` regex in `level1_regex.py`.
Currently tracked as 2 xfail test cases.

### Spatial contradiction veto for short city names
`Bradford Cornwall` still resolves to Bradford with High confidence.
The MBR filter doesn't veto when the primary token is a strong unambiguous match.
Fix: if county token MBR contradicts candidate location by > N km, cap confidence at Medium regardless of score.
Currently tracked as 2 xfail test cases.

### Level 3 — OS Names API fallback
Implement the Level 3 stub in `pipeline.py`.
OS Names API: free tier, 1000 calls/day, no key needed for basic queries.
Fires only when Levels 1+2 return unresolved or Low confidence.
Good for novel/ambiguous inputs that the parquet can't handle.

### Level 4 — Local Ollama LLM fallback
Implement the Level 4 stub.
Last resort for genuinely unresolvable inputs.
Use `ollama` Python client; model configurable (default: `qwen2.5:7b`).
Only fires if Level 3 also fails.

---

## 🟡 Data

### Rebuild OS Open Names parquet with MBR columns
The current parquet was built before MBR columns were added to `download_os_open_names.py`.
Re-running the download will include `MBR_XMIN/YMIN/XMAX/YMAX` for better spatial filtering.
Command: `python scripts/download_os_open_names.py` (answer `y`).

### National Highways RSS eval data
`scripts/build_eval_dataset.py` couldn't parse the Highways England RSS feeds (malformed XML at time of run).
Retry periodically — when working, these give excellent motorway/A-road phrasing examples:
`M62 eastbound between J26 and J27`, `A1(M) northbound at J47` etc.
Add to eval dataset when available.

---

## 🟢 Testing

### Confidence calibration plot
For High/Medium/Low resolved results, what % are actually within 500m/1km/5km?
Add to `pipeline.py` as `geocoder.calibration_report(labelled_data)`.
Needs the human-labelled eval set first.

### Map output for batch results
`geocoder.plot_results(df)` using folium — green resolved, red unresolved, on UK basemap.
Low effort, high communicability for non-technical stakeholders and systematic mis-snap detection.

### Human text variation test set
Curated set of inputs that test how humans write UK locations:
- Old/historic county names: `St Helens Lancashire` (now Merseyside), `Stockton Cleveland`, `Humberside`
- Colloquial names: `The Smoke`, `The Potteries`, `Black Country`
- Welsh/Gaelic place names with English approximations
- Social media style: `nr Leeds`, `just off the M62`, `past the Tesco on A64`
No existing dataset covers this well — needs hand-curation or crowd-sourcing.

### Expand road suffix abbreviation tests
Current suite covers: `Rd`, `St`, `Ave`, `Ln`, `Dr`, `Cl`, `Cres`, `Pl`
Add: `Ct` (Court), `Sq` (Square), `Ter` (Terrace), `Gdns` (Gardens), `Gr` (Grove)
Also: `St` ambiguity — `St Johns` (Saint) vs `Station St` (Street) regression test.

---

## 🟢 Infrastructure

### PyPI packaging
Add `__version__` to `ukgeo/__init__.py`, set up `hatch build`, publish to PyPI.
Allows Open Road Risk (and others) to `pip install ukgeo` rather than git submodule.

### CI/CD
Add GitHub Actions workflow to run `pytest` on PRs.
Requires data parquets — either mock them in tests or add a `--no-data` skip flag.
Note: data files are gitignored so CI needs a way to skip data-dependent tests.

### Calibrate weights against STATS19
Once STATS19 eval corpus is built, run `scripts/calibrate.py` against it.
Current default weights were set manually against 15 edge cases — STATS19 will give
a much more representative signal across thousands of real inputs.

---

## 💡 Ideas / longer term

### Python STATS19 package
There is no Python equivalent of the R stats19 package (Lovelace et al., JOSS 2019).
`scripts/build_stats19_eval.py` is partway there. Minimal viable package:
- `download_stats19(year, type)` — fetch raw CSVs from data.gov.uk
- `read_collisions(path)` / `read_casualties()` / `read_vehicles()` — decode integer codes
- `to_geodataframe(df)` — convert Easting/Northing to GeoDataFrame (OSGB36)
Could be a separate repo or grow from ukgeo utility scripts.
See `docs/gaps_and_ecosystem.md` section 6.

### Chunked/streaming batch processing
`geocode_batch()` loads all inputs into memory. Full STATS19 1979-2024 is ~2M records.
Add a chunked generator variant: process N rows at a time, append to parquet output.

### Data quality pre-screening
`screen_inputs(texts)` — flag inputs likely to fail before running full pipeline.
Returns quality tier: likely resolvable / uncertain / likely to fail.
Saves time on bulk jobs and sets honest expectations.

### Open Road Risk complementary tools (for reference)
These are not ukgeo tasks but worth knowing for Open Road Risk development:
- **PySAL/esda** — `esda.Moran` for the spatial autocorrelation TODO in Open Road Risk
- **SHAP** — interpretability for XGBoost risk_percentile model
- **IMD/deprivation join** — LSOA-level deprivation as covariate or post-hoc analysis
- **momepy** — road network geometry metrics as Stage 2 XGBoost features
- **folium/keplergl** — interactive map output for Quarto site
- **Pyrosm** — faster alternative to Overpass API for GB-scale OSM road geometry
See `docs/gaps_and_ecosystem.md` section 4 for detail.

### Domain config profiles
`Geocoder(domain="road_safety")` loads preset qualifier tokens and scoring weights
tuned for that domain. `domain="logistics"` would add `depot`, `warehouse` etc.
Config files in `config/domain_*.yaml`. Currently only `domain_road_safety.yaml` exists.

### Postcode sector / district fallback
If full postcode lookup fails (postcodes.io down), fall back to outward code centroid
from a local lookup table. Avoids network dependency for partial postcodes.

### Welsh language support
OS Open Names includes Welsh place name aliases (`NAME2` / `NAME2_LANG = "cym"`).
Token gazetteer currently ignores `NAME2`. Adding it would improve Welsh input handling
e.g. `Caerdydd` → Cardiff.

### Batch confidence histogram
`geocoder.benchmark()` already reports median error.
Add a confidence calibration plot: for inputs labelled High/Medium/Low,
what % are actually within tolerance? Helps identify overconfident results.

### Open Road Risk integration notes
Integration approach: **loosely coupled via CSV exchange**, not shared code or imports.

ukgeo outputs: `input, lat, lon, confidence, level_resolved, match_type, notes`
Open Road Risk reads that CSV as a location lookup table.

This keeps both repos independently usable. Revisit tighter coupling only if the CSV
exchange becomes a bottleneck (e.g. latency, schema drift, large file sizes).

Key STATS19 fields to synthesise location strings from:
`Road_1`, `Road_2`, `Junction_Detail`, `Local_Authority_District`, `LSOA_of_Accident_Location`

Data path design: `Geocoder(data_dir=...)` should accept an override path so users
who have data elsewhere (e.g. Open Road Risk data dir) don't re-download.
Implement when the integration workflow is clearer — don't over-engineer yet.

Do not assume Open Road Risk is present. Do not import from it. Do not share parquet files.