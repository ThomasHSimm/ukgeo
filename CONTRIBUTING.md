# Contributing to ukgeo

Thank you for your interest in contributing. This document covers the most common ways to help.

---

## Reporting a geocoding failure

If ukgeo returns a wrong result or can't resolve a location, open an issue with:

- The input string that failed
- What you expected
- What ukgeo returned

```python
from ukgeo import Geocoder
geo = Geocoder()
print(geo.geocode("your input here").as_dict())
```

---

## Adding infrastructure aliases

The quickest contribution. If a well-known UK location resolves incorrectly — a bridge, tunnel, bus station, motorway interchange, or service station — add it to `data/infrastructure_aliases.csv`.

**Format:**

```
name,category,lat,lon,source,verified_name,notes
Dartford Crossing,bridge,51.4454,0.2744,manual,Dartford Crossing,A282 Thames crossing
```

**Categories:** `bridge`, `tunnel`, `viaduct`, `junction`, `roundabout`, `services`, `bus_station`, `airport`, `other`

**Rules:**
- Verify coordinates against OpenStreetMap or Google Maps before submitting
- Add all common name variants as separate rows pointing to the same coordinates
- Note the source (manual, osm, os_names_api) in the `source` column

---

## Development setup

```bash
git clone https://github.com/ThomasHSimm/ukgeo.git
cd ukgeo
pip install -e ".[dev]"

# Download data (choose one)
ukgeo setup                              # downloads from Kaggle (~41MB)
# or build from source:
python scripts/download_os_open_names.py
python scripts/download_os_open_roads.py
python scripts/download_osm_named_junctions.py
python scripts/download_osm_roads.py

pytest -v --cache-clear
```

---

## Making a pull request

1. Create a branch from `main`

```bash
git checkout -b feat/your-feature-name
```

2. Make your changes and add tests where relevant

3. Run the test suite

```bash
pytest -v --cache-clear
```

4. Update `CHANGELOG.md` with a brief description of your change

5. Open a pull request against `main`

---

## Data licences

ukgeo combines data from three open sources. Any contributions that include derived data must respect these licences:

| Source | Licence | Attribution required |
|---|---|---|
| OS Open Names | Open Government Licence v3 | Contains OS data © Crown Copyright [year] |
| OS Open Roads | Open Government Licence v3 | Contains OS data © Crown Copyright [year] |
| OpenStreetMap | Open Database Licence (ODbL) | © OpenStreetMap contributors |

Do not include data from sources that are not compatible with ODbL or OGL.

---

## Questions

Open an issue or start a discussion on the GitHub repository.