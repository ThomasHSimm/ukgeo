# ukgeo

[![PyPI](https://img.shields.io/pypi/v/ukgeo)](https://pypi.org/project/ukgeo/)
[![Open Road Risk](https://img.shields.io/badge/Open%20Road%20Risk-ukgeo-2E7D32)](https://openroadrisk.org/tools/ukgeo.html)
[![Kaggle Dataset](https://img.shields.io/badge/Kaggle-ukgeo--combined--dataset-20BEFF?logo=kaggle)](https://www.kaggle.com/datasets/thomassimm/ukgeo-combined-dataset)
[![License: MIT](https://img.shields.io/badge/Code-MIT-yellow)](#licence)
[![Data: ODbL](https://img.shields.io/badge/Data-ODbL-brightgreen)](https://opendatacommons.org/licenses/odbl/)

`ukgeo` is a UK-focused free-text geocoder for turning messy location strings into latitude/longitude coordinates. It is designed for strings like road references, postcodes, place names, motorway junctions, named junctions, and colloquial infrastructure names, especially when processing CSVs or other bulk datasets.

It uses a tiered pipeline: fast postcode and road-reference handling first, then OS/OpenStreetMap token scoring, with optional OS Names API fallback. Reference data is loaded locally from parquet files, so repeated batch geocoding can run in-process after setup.

Project page with examples and fuller context: [openroadrisk.org/tools/ukgeo.html](https://openroadrisk.org/tools/ukgeo.html)

## What it is

- A Python package and CLI for UK location text geocoding
- A batch-friendly tool for datasets with noisy, partial, or non-address location descriptions
- A road-aware matcher for M/A/B roads, motorway junctions, named roundabouts, bridges, tunnels, stations, and places
- A transparent geocoder that returns confidence, match type, pipeline level, candidates considered, and notes

## What it is not

- A global geocoder
- A routing engine, distance matrix, or travel-time API
- A rooftop-accurate address geocoder
- A substitute for authoritative emergency-service, legal, cadastral, or safety-critical location systems
- A magic fixer for every vague location string; ambiguous inputs still need review

## Quick start

### Option A — pip install (recommended)

```bash
pip install ukgeo
ukgeo setup        # downloads ~51MB data file from Kaggle
ukgeo geocode "M62 Junction 26"
```

### Option B — from source

```bash
git clone https://github.com/ThomasHSimm/ukgeo.git
cd ukgeo
pip install -e ".[dev]"
python scripts/download_os_open_names.py   # ~5 min, builds local parquets
python scripts/download_os_open_roads.py
python scripts/download_osm_named_junctions.py
python scripts/download_osm_roads.py
```

### Python API

```python
from ukgeo import Geocoder

geo = Geocoder()
print(geo.geocode("M62 Junction 26"))
print(geo.geocode("Spaghetti Junction Birmingham"))
print(geo.geocode("Skipton, North Yorkshire"))
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
| 0 | Infrastructure alias lookup | Named bridges, tunnels, junctions, bus stations |
| 1 | Regex + postcodes.io | Full UK postcodes, M/A/B road pattern extraction |
| 2 | OS/OSM token scoring | Places, roads, junctions, named roundabouts |
| 3 | OS Names API fallback | Bus stations, airports, service stations |
| 4 | Local Ollama LLM (stub) | Last resort — not yet implemented |

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
- [docs/alternatives.md](docs/alternatives.md) — honest comparison with other UK geocoding tools
- [docs/gaps_and_ecosystem.md](docs/gaps_and_ecosystem.md) — what ukgeo is missing and the broader ecosystem
- [docs/STATUS.md](docs/STATUS.md) — current test results and benchmark numbers
- [TODO.md](TODO.md) — development roadmap

## Licence

MIT License
