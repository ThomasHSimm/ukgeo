
# ukgeo

A tiered UK location free-text geocoder. Converts messy location strings — addresses, road references, place names, colloquial names — to latitude/longitude coordinates using a pipeline that escalates from fast regex matching to OS Open Names lookup, with optional API and local LLM fallbacks.

Designed for bulk processing (hundreds to thousands of entries) with a parquet-backed setup step.

## Features

- **Tiered pipeline** — fast paths handle the easy cases; slower paths only fire when needed
- **UK-specific** — built on OS Open Names, OS Open Roads, OSM road references, and postcodes.io, tuned for British address conventions
- **Bulk-first design** — loads OS data once, processes thousands of entries in-process
- **Road-aware matching** — handles M/A/B road references, motorway junctions, named junctions, and common road suffix abbreviations
- **Packaged data fallback** — can use richer local source parquets, or a combined Kaggle parquet for simpler setup
- **Confidence scoring** — every result includes a normalised match score and confidence level
- **Tuneable weights** — scoring parameters are configurable and can be calibrated against labelled test data
- **Extensible** — Level 3 (API) and Level 4 (local Ollama LLM) stubs ready to implement

## Pipeline levels

| Level | Method | Speed | Handles |
|---|---|---|---|
| 1 | Regex + postcodes.io/local postcode fallback | ~1ms | Full UK postcodes, M/A/B road pattern extraction |
| 2 | OS/OpenStreetMap token scoring | ~5ms | Places, roads, junctions, named roundabouts/interchanges |
| 3 | API fallback *(stub)* | ~500ms | Ambiguous cases needing external lookup |
| 4 | Local Ollama LLM *(stub)* | ~2s | Last resort — typos, novel references |

## Quick start (pre-built data)

Download `ukgeo_data.parquet` from [Kaggle](https://www.kaggle.com/datasets/thomashsimm/ukgeo-data)
and place it at `data/kaggle/ukgeo_data.parquet`, then:

```python
from ukgeo import Geocoder
geo = Geocoder()
print(geo.geocode("M62 Junction 26"))
```

No other setup needed.

If individual source parquets are also present, `ukgeo` prefers those because they contain richer source-specific metadata. The combined Kaggle parquet is used as a fallback.

## Setup (build data locally)

### 1. Install

```bash
git clone https://github.com/ThomasHSimm/ukgeo.git
cd ukgeo
pip install -e ".[dev]"
```

For BNG→WGS84 coordinate conversion (recommended):

```bash
pip install pyproj
```

### 2. Download source data

OS Open Names is published under the [Open Government Licence](https://www.nationalarchives.gov.uk/doc/open-government-licence/). Download and build the parquet lookup (~39MB on disk):

```bash
python scripts/download_os_open_names.py
```

This downloads the OS Open Names CSV (~98MB zip), filters to relevant local types, and writes `data/os_open_names.parquet`. Takes 2–3 minutes. Only needs to be run once, or when you want to update to a newer quarterly release.

For full road-reference coverage, also build the road and junction parquets:

```bash
python scripts/download_os_open_roads.py
python scripts/download_osm_named_junctions.py
python scripts/download_osm_roads.py
```

To build the single fallback release file used for the Kaggle dataset:

```bash
python scripts/build_kaggle_dataset.py
```

## Usage

### Single geocode

```python
from ukgeo import Geocoder

geo = Geocoder()
result = geo.geocode("Skipton, North Yorkshire")

print(result.lat, result.lon)        # 53.9602, -2.0177
print(result.confidence)             # High
print(result.interpreted_as)         # Skipton (Town)
print(result.level_resolved)         # 2
print(result.notes)                  # match_score=0.308
```

### Bulk geocode

```python
import polars as pl
from ukgeo import Geocoder

geo = Geocoder()
locations = ["LS1 1BA", "M62 Junction 26", "Spaghetti Junction Birmingham", ...]
df = geo.geocode_batch(locations)
df.write_csv("results.csv")
```

Output columns: `input`, `lat`, `lon`, `interpreted_as`, `match_type`, `level_resolved`, `confidence`, `candidates_considered`, `notes`.

### Benchmarking

```python
test_data = [
    {"input": "Skipton, North Yorkshire", "lat": 53.9619, "lon": -2.0175},
    {"input": "LS1 1BA",                 "lat": 53.7997, "lon": -1.5492},
]
geo.benchmark(test_data)
```

### Custom weights

```python
from ukgeo import Geocoder, ScoringWeights

weights = ScoringWeights(
    county_context_match=7.0,
    junction_match=10.0,
    high_threshold=0.30,
)
geo = Geocoder(weights=weights)
```

### Calibrate weights against your own data

Provide a CSV with columns `input, lat, lon`:

```bash
python scripts/calibrate.py --test data/my_test_locations.csv --trials 300
```

Best-fit weights are saved to `config/weights.yaml` and loaded automatically on next `Geocoder()` init.

## Known limitations

The following are documented gaps in the current implementation:

- **A1(M) bracket variants** — inputs such as `A1M` and `A1 M` are tracked with strict `xfail` regression tests until Level 1 normalisation handles them.
- **Road references are not linear referencing** — a road-only match usually returns a representative road segment or centroid, not a collision-specific point along the carriageway.
- **Spatial contradictions need stronger vetoes** — bad county context such as `Bradford Cornwall` should not produce overconfident matches.
- **Some OSM road aliases are missing** — coverage depends on available OSM `ref`/name tagging and local segment data.
- **Level 3 and Level 4 are still stubs** — external API and local LLM fallbacks are reserved for future ambiguous or novel inputs.

## Data sources

| Source | Licence | Used for |
|---|---|---|
| [OS Open Names](https://osdatahub.os.uk/downloads/open/OpenNames) | Open Government Licence | Place names, roads, postcodes |
| [postcodes.io](https://postcodes.io) | MIT | Postcode centroid lookup |
| [OS Open Roads](https://osdatahub.os.uk/downloads/open/OpenRoads) | Open Government Licence | Motorway junction points |
| [OpenStreetMap](https://www.openstreetmap.org/) | ODbL | Named junctions, roundabouts, and B-road segments |
| [Kaggle ukgeo data](https://www.kaggle.com/datasets/thomashsimm/ukgeo-data) | Mixed source licences | Combined fallback parquet for simpler setup |

## Running tests

```bash
pytest -v
```

Tests require the OS Open Names parquet to be present (skip otherwise). The suite covers postcodes, motorway junctions, A-roads, named interchanges, road-suffix abbreviations, `St`/`Saint` ambiguity, colloquial county context, bad county context, place-name typos, and batch geocoding.
Additional coverage is included for B-road extraction and OSM-backed road segment lookup when the relevant local parquet is available.

Known gaps are documented with strict `xfail` regression cases rather than being counted as ordinary failures.

## Project structure

```
ukgeo/
├── scripts/
│   ├── download_os_open_names.py        # OS Open Names parquet
│   ├── download_os_open_roads.py        # motorway junction parquet
│   ├── download_osm_named_junctions.py  # named junctions/roundabouts parquet
│   ├── download_osm_roads.py            # OSM B-road segment parquet
│   ├── build_kaggle_dataset.py          # combined fallback release parquet
│   ├── build_stats19_eval.py            # STATS19 benchmark input builder
│   └── calibrate.py                     # weight calibration against labelled data
├── ukgeo/
│   ├── pipeline.py                 # Geocoder class, orchestrates levels
│   ├── level1_regex.py             # postcode + road pattern extraction
│   ├── level2_ner.py               # token tagging + OS Names candidate scoring
│   ├── lookup.py                   # parquet loader and query helpers
│   ├── models.py                   # GeoResult dataclass
│   └── uk_admin.py                 # static UK administrative geography reference
├── tests/
│   └── test_pipeline.py
└── data/                           # source and fallback parquets live here (gitignored)
```

## Licence

MIT License
