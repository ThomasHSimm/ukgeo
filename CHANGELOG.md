# Changelog

## v0.4 — May 2026

### Major additions
- **Level 0 infrastructure aliases** — instant exact lookup for named UK
  infrastructure via `data/infrastructure_aliases.csv`. The current generated
  file has 35 coordinate-backed aliases.
- **Level 3 OS Names API** — fallback for unresolved inputs, with operator prefix
  normalisation (`Moto Keele` → `Keele Services`) and `fq` type filtering.
- **CLI** — `ukgeo geocode`, `ukgeo plot`, `ukgeo info` commands.
- **Map output** — `plot_results()` and `plot_batch_summary()` via folium.
- **utils module** — `load_env()` and `get_env_key()` helpers.

### Test suite
- 47 passed, 6 xfailed

### Data
- Added `data/infrastructure_aliases.csv` — curated infrastructure coordinate
  lookup for known named-infrastructure gaps.
- Added `data/osm_roads.parquet` — 105,720 OSM B-road segments.

---

## v0.3 — May 2026

### Major improvements
- **B-road resolution**: 68.9% → 99.9% resolve rate on STATS19 benchmark
  - Added B-road regex extraction in `level1_regex.py`
  - Added `road_b` token type and scoring in `level2_ner.py`
  - Downloaded 105,720 OSM B-road segments via `scripts/download_osm_roads.py`
  - Added `search_osm_roads()` and OSM augmentation in `lookup.py`
- **Kaggle dataset**: combined `ukgeo_data.parquet` built from all three sources
  via `scripts/build_kaggle_dataset.py`, released on Kaggle
- **Loading priority fixed**: individual parquets (richer metadata) take precedence
  over combined Kaggle parquet; Kaggle parquet is fallback for users without local data

### Test suite
- 40 passed, 6 xfailed (all expected)
- Added 3 B-road test cases (2 pass, 1 xfail: B1224 York routing issue)

### Benchmark (STATS19 2024, 5000 inputs)
| Metric | v0.2 | v0.3 |
|---|---|---|
| Resolve rate | 68.9% | 99.9% |
| Median error | 4,593m | 3,299m |
| Within 5km | 51.6% | 59.9% |
| B-roads resolved | 5.1% | 99.9% |

### Data sources added
- `data/osm_roads.parquet` — 105,720 OSM B-road segments (ODbL)
- `data/kaggle/ukgeo_data.parquet` — combined release file

---

## v0.2 — May 2026

### Major improvements
- OSM named junctions and roundabouts (`scripts/download_osm_named_junctions.py`)
  — resolves Spaghetti Junction, Magic Roundabout, Lofthouse Interchange
- MBR-based spatial candidate filtering via `uk_admin.py` ADMIN_BNG_EXTENTS
  — fixes Edinburgh/Glasgow disambiguation
- Two-pass fuzzy matching — fuzzy only fires when no exact place token found
- Place-anchored road section selection — A-road + near place now spatially anchored
- Configurable qualifier tokens via `ScoringWeights.extra_qualifiers`
- Domain config file `config/domain_road_safety.yaml`

### Test suite
- 15/18 core cases passing, 38 total passed, 5 xfailed

### Benchmark (STATS19 2024, 5000 inputs)
| Metric | v0.1 | v0.2 |
|---|---|---|
| Resolve rate | — | 68.9% |
| Median error | — | 4,593m |

---

## v0.1 — May 2026

### Initial release
- Tiered pipeline: regex + postcodes.io (Level 1), OS Names token scoring (Level 2)
- OS Open Roads motorway junction lookup (669 junctions)
- UK admin geography reference with BNG extent filtering (`uk_admin.py`)
- 12/18 core edge cases passing
- Data sources: OS Open Names, OS Open Roads
- Calibration script, benchmark script, Police.uk eval dataset builder
