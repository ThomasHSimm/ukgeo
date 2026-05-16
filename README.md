
# ukgeo

A tiered UK location free-text geocoder. Converts messy location strings — addresses, road references, place names, colloquial names — to latitude/longitude coordinates using a pipeline that escalates from fast regex matching to OS Open Names lookup, with optional API and local LLM fallbacks.

Designed for bulk processing (hundreds to thousands of entries) with a single parquet-backed setup step.

## Features

- **Tiered pipeline** — fast paths handle the easy cases; slower paths only fire when needed
- **UK-specific** — built on OS Open Names and postcodes.io, tuned for British address conventions
- **Bulk-first design** — loads OS data once, processes thousands of entries in-process
- **Confidence scoring** — every result includes a normalised match score and confidence level
- **Tuneable weights** — scoring parameters are configurable and can be calibrated against labelled test data
- **Extensible** — Level 3 (API) and Level 4 (local Ollama LLM) stubs ready to implement

## Pipeline levels

| Level | Method | Speed | Handles |
|---|---|---|---|
| 1 | Regex + postcodes.io | ~1ms | Full UK postcodes, road pattern extraction |
| 2 | OS Open Names token scoring | ~5ms | Place names, towns, villages, A-roads |
| 3 | API fallback *(stub)* | ~500ms | Ambiguous cases needing external lookup |
| 4 | Local Ollama LLM *(stub)* | ~2s | Last resort — typos, novel references |

## Quick start (pre-built data)

Download `ukgeo_data.parquet` from [Kaggle](https://www.kaggle.com/datasets/thomashsimm/ukgeo-data)
and place it in the `data/` folder, then:

```python
from ukgeo import Geocoder
geo = Geocoder()
print(geo.geocode("M62 Junction 26"))
```

No other setup needed.

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

### 2. Download OS Open Names

OS Open Names is published under the [Open Government Licence](https://www.nationalarchives.gov.uk/doc/open-government-licence/). Download and build the parquet lookup (~39MB on disk):

```bash
python scripts/download_os_open_names.py
```

This downloads the OS Open Names CSV (~98MB zip), filters to relevant local types, and writes `data/os_open_names.parquet`. Takes 2–3 minutes. Only needs to be run once, or when you want to update to a newer quarterly release.

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

The following are documented gaps in the current implementation, tracked as issues:

- **Motorway junctions** (e.g. `M62 Junction 26`) — OS Open Names CSV does not include junction point geometry. Requires OS Open Roads (`MotorwayJunction` layer) as an additional data source. See issue #1.
- **Named interchanges and roundabouts** (e.g. `Lofthouse Interchange`, `Magic Roundabout Swindon`) — present in OS NGD Geographical Names but not OS Open Names CSV. See issue #2.
- **Spatial candidate filtering** implemented via MBR bounding box intersection. Remaining mis-snaps on ambiguous suburban area names (e.g. Sighthill) may require OS NGD Geographical Names data.
- **Road + place disambiguation** (e.g. `A64 York bypass near Tadcaster`) — without junction data, road references resolve to road centroids which may be far from the described location. See issue #1.

## Data sources

| Source | Licence | Used for |
|---|---|---|
| [OS Open Names](https://osdatahub.os.uk/downloads/open/OpenNames) | Open Government Licence | Place names, roads, postcodes |
| [postcodes.io](https://postcodes.io) | MIT | Postcode centroid lookup |
| [OS Open Roads](https://osdatahub.os.uk/downloads/open/OpenRoads) *(planned)* | Open Government Licence | Motorway junction points |
| [OS NGD Geographical Names](https://osdatahub.os.uk/downloads/open/NGDGeographicalNames) *(planned)* | Open Government Licence | Named junctions and roundabouts |

## Running tests

```bash
pytest -v
```

Tests require the OS Open Names parquet to be present (skip otherwise). The suite covers postcodes, motorway junctions, A-roads, named interchanges, road-suffix abbreviations, `St`/`Saint` ambiguity, colloquial county context, bad county context, place-name typos, and batch geocoding.

Known gaps are documented with strict `xfail` regression cases rather than being counted as ordinary failures.

## Project structure

```
ukgeo/
├── scripts/
│   ├── download_os_open_names.py   # one-time data setup
│   └── calibrate.py                # weight calibration against labelled data
├── ukgeo/
│   ├── pipeline.py                 # Geocoder class, orchestrates levels
│   ├── level1_regex.py             # postcode + road pattern extraction
│   ├── level2_ner.py               # token tagging + OS Names candidate scoring
│   ├── lookup.py                   # parquet loader and query helpers
│   ├── models.py                   # GeoResult dataclass
│   └── uk_admin.py                 # static UK administrative geography reference
├── tests/
│   └── test_pipeline.py
└── data/                           # OS Open Names parquet lives here (gitignored)
```

## Licence

MIT License
