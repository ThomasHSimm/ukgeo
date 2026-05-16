# ukgeo — TODO

Priority: 🔴 High / 🟡 Medium / 🟢 Low / 💡 Idea

---

## 🔴 Next up

### STATS19 integration / Open Road Risk bridge
Build a script that:
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
- STATS19 collision data already flows through Open Road Risk Stage 2
- ukgeo could replace or supplement any existing location parsing in that pipeline
- Key fields to synthesise from: `Road_1`, `Road_2`, `Junction_Detail`, `Local_Authority_District`, `LSOA_of_Accident_Location`
- Suggested import pattern: `from ukgeo import Geocoder` in Open Road Risk utility module