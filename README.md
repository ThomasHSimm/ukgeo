# ukgeo

[![Kaggle Dataset](https://img.shields.io/badge/Kaggle-ukgeo--combined--dataset-20BEFF?logo=kaggle)](https://www.kaggle.com/datasets/thomassimm/ukgeo-combined-dataset)
[![License: MIT](https://img.shields.io/badge/Code-MIT-yellow)](#licence)
[![Data: ODbL](https://img.shields.io/badge/Data-ODbL-brightgreen)](https://opendatacommons.org/licenses/odbl/)

## Quick start

**Option A — Pre-built data (fastest):**
Download `ukgeo_data.parquet` from [Kaggle](https://www.kaggle.com/datasets/thomassimm/ukgeo-combined-dataset), place it at `data/kaggle/ukgeo_data.parquet`, then:

```bash
pip install -e .
```

```python
from ukgeo import Geocoder

geo = Geocoder()
print(geo.geocode("M62 Junction 26"))
print(geo.geocode("Skipton, North Yorkshire"))
print(geo.geocode("LS1 1BA"))
```

**Option B — Build data locally (latest source data):**

```bash
pip install -e ".[dev]"
python scripts/download_os_open_names.py
python scripts/download_os_open_roads.py
python scripts/download_osm_named_junctions.py
python scripts/download_osm_roads.py
```

## CLI usage

After installation, `ukgeo` is available as a command:

```bash
# Single query
ukgeo geocode "M62 Junction 26"
ukgeo geocode "Skipton, North Yorkshire"

# Geocode a CSV file (auto-detects first string column)
ukgeo geocode locations.csv --output results.csv

# Specify column and domain
ukgeo geocode crashes.csv --column road_reference --domain road_safety

# Enable Level 3 OS Names API fallback (requires OS_API_KEY in .env)
ukgeo geocode locations.csv --max-level 3

# Generate an interactive HTML map from geocoded results
ukgeo geocode locations.csv --output results.csv
ukgeo plot results.csv --output results_map.html

# Check installation status
ukgeo info
```

Output columns added to CSV: `lat`, `lon`, `confidence`, `level_resolved`,
`interpreted_as`, `match_type`, `candidates_considered`, `notes`.

A tiered UK location free-text geocoder. Converts messy location strings — addresses, road references, place names, colloquial names — to latitude/longitude coordinates using a pipeline that escalates from fast regex matching to OS Open Names lookup, with optional API and local LLM fallbacks.

Designed for bulk processing with a parquet-backed setup step: load reference data once, then geocode hundreds, thousands, or millions of UK location strings in-process.

## Features

- **Tiered pipeline** — fast paths handle the easy cases; slower paths only fire when needed
- **UK-specific** — built on OS Open Names, OS Open Roads, OSM road references, and postcodes.io, tuned for British address conventions
- **Road-aware matching** — handles M/A/B road references, motorway junctions, named junctions, and common road suffix abbreviations
- **Bulk-first design** — loads OS data once, processes thousands of entries in-process
- **Packaged data fallback** — uses richer local source parquets when present, or the combined Kaggle parquet for simpler setup
- **Confidence scoring** — every result includes a normalised match score and confidence level
- **Tuneable weights** — scoring parameters are configurable and can be calibrated against labelled test data
- **Extensible** — Level 3 API and Level 4 local Ollama LLM stubs are ready for future fallback work

## Pipeline levels

| Level | Method | Handles |
|---|---|---|
| 1 | Regex + postcodes.io/local postcode fallback | Full UK postcodes, M/A/B road pattern extraction |
| 2 | OS/OpenStreetMap token scoring | Places, roads, junctions, named roundabouts/interchanges |
| 3 | API fallback *(stub)* | Ambiguous cases needing external lookup |
| 4 | Local Ollama LLM *(stub)* | Last resort: typos, novel references |

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
print(result.notes)                  # match_score=...
```

### Bulk geocode

```python
from ukgeo import Geocoder

geo = Geocoder()
locations = ["LS1 1BA", "M62 Junction 26", "Spaghetti Junction Birmingham"]
df = geo.geocode_batch(locations)
df.write_csv("results.csv")
```

Output columns: `input`, `lat`, `lon`, `interpreted_as`, `match_type`, `level_resolved`, `confidence`, `candidates_considered`, `notes`.

### Benchmarking

```python
test_data = [
    {"input": "Skipton, North Yorkshire", "lat": 53.9619, "lon": -2.0175},
    {"input": "LS1 1BA", "lat": 53.7997, "lon": -1.5492},
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

### Calibrate weights

Provide a CSV with columns `input, lat, lon`:

```bash
python scripts/calibrate.py --test data/my_test_locations.csv --trials 300
```

Best-fit weights are saved to `config/weights.yaml` and loaded automatically on next `Geocoder()` init.

## Data setup

`ukgeo` prefers individual source parquets because they preserve richer metadata. If those are absent, it falls back to the combined Kaggle parquet at `data/kaggle/ukgeo_data.parquet`.

To regenerate the combined Kaggle release file from local source parquets:

```bash
python scripts/build_kaggle_dataset.py
```

For BNG to WGS84 coordinate conversion, `pyproj` is recommended and included in the project dependencies.

## Data sources

| Source | Licence | Used for |
|---|---|---|
| [OS Open Names](https://osdatahub.os.uk/downloads/open/OpenNames) | Open Government Licence | Place names, roads, postcodes |
| [OS Open Roads](https://osdatahub.os.uk/downloads/open/OpenRoads) | Open Government Licence | Motorway junction points |
| [OpenStreetMap](https://www.openstreetmap.org/) | ODbL | Named junctions, roundabouts, and B-road segments |
| [postcodes.io](https://postcodes.io) | MIT | Postcode centroid lookup |
| [Kaggle ukgeo combined dataset](https://www.kaggle.com/datasets/thomassimm/ukgeo-combined-dataset) | Mixed source licences | Combined fallback parquet for simpler setup |

## Running tests

```bash
pytest -v
```

Tests require the OS Open Names parquet to be present; they skip otherwise. The suite covers postcodes, motorway junctions, A-roads, B-roads, named interchanges, road-suffix abbreviations, `St`/`Saint` ambiguity, colloquial county context, bad county context, place-name typos, and batch geocoding.

Known gaps are documented with strict `xfail` regression cases rather than being counted as ordinary failures.

## Known limitations

See [docs/STATUS.md](docs/STATUS.md) for current test results and documented gaps.

## Project structure

```text
ukgeo/
├── scripts/
│   ├── download_os_open_names.py
│   ├── download_os_open_roads.py
│   ├── download_osm_named_junctions.py
│   ├── download_osm_roads.py
│   ├── build_kaggle_dataset.py
│   ├── build_stats19_eval.py
│   └── calibrate.py
├── ukgeo/
│   ├── pipeline.py
│   ├── level1_regex.py
│   ├── level2_ner.py
│   ├── lookup.py
│   ├── models.py
│   └── uk_admin.py
├── tests/
│   └── test_pipeline.py
└── data/
```

## See also

- [Kaggle dataset](https://www.kaggle.com/datasets/thomassimm/ukgeo-combined-dataset) — pre-built data download
- [Open Road Risk](https://github.com/ThomasHSimm/open-road-risk) — road safety risk modelling pipeline that ukgeo supports
- [docs/alternative.md](docs/alternative.md) — honest comparison with other UK geocoding tools
- [docs/gaps_and_ecosystem.md](docs/gaps_and_ecosystem.md) — what ukgeo is missing and the broader ecosystem
- [docs/STATUS.md](docs/STATUS.md) — current test results and benchmark numbers
- [TODO.md](TODO.md) — development roadmap

## Licence

MIT License
