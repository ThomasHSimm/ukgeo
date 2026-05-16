# ukgeo — Project Status

## Test Suite

**40 passed, 6 xfailed** (as of 2026-05-16)

All substantive test cases pass. The 5 `xfail` entries are documented known gaps, not regressions.

### Core geocoding cases (15/15 passing)

| Input | Expected location | Tolerance | Confidence | Result |
|---|---|---|---|---|
| `LS1 1BA` | Leeds city centre | 1 000 m | High | ✓ |
| `WF10 4QH` | Castleford | 2 000 m | Medium | ✓ |
| `M62 Junction 26` | M62 J26, W Yorks | 2 000 m | High | ✓ |
| `A647 near Bradford` | Bradford / A647 | 5 000 m | Medium | ✓ |
| `Lofthouse Interchange` | M62/M1 junction | 3 000 m | Medium | ✓ |
| `Spaghetti Junction Birmingham` | Gravelly Hill | 2 000 m | High | ✓ |
| `Magic Roundabout Swindon` | Swindon centre | 2 000 m | High | ✓ |
| `A64 York bypass near Tadcaster` | Tadcaster area | 10 000 m | Medium | ✓ |
| `Skipton, North Yorkshire` | Skipton | 2 000 m | High | ✓ |
| `Aberford West Yorkshire` | Aberford village | 2 000 m | High | ✓ |
| `Dartford Crossing Kent` | Dartford | 3 000 m | High | ✓ |
| `Station Road Leeds` | Leeds centre | 5 000 m | Medium | ✓ |
| `A1(M) Junction 47 Garforth` | Garforth / A1(M) | 5 000 m | Medium | ✓ |
| `Brafford West Yorkshire` *(typo)* | Bradford | 5 000 m | Medium | ✓ |
| `Sighthill Edinburgh` | Sighthill | 5 000 m | High | ✓ |

### Extended test groups (all passing unless noted)

| Group | Cases | Status |
|---|---|---|
| Road suffix abbreviations (`Rd`, `St`, `Sq`, `Gdns`) | 7 | ✓ All pass |
| `St` prefix disambiguation (Saint vs Street) | 2 | ✓ All pass |
| Typo tolerance (difflib fuzzy matching) | 4 pass / 2 xfail | ✓ / xfail |
| Historic / colloquial county names (`Berkshire`, `Cleveland`, `Glamorgan`) | 6 | ✓ All pass |
| Wrong county context suppression (`Skipton Kent`, etc.) | 1 pass / 2 xfail | ✓ / xfail |
| Lofthouse old ground truth (disputed coordinates) | 1 xfail | xfail |
| Batch geocoding (≥ 80 % resolved) | 1 | ✓ |
| Empty input → Low confidence + unresolved | 1 | ✓ |
| `match_score` present in notes | 1 | ✓ |

### xfail cases

These are documented known gaps tracked as regression guards, not failures:

| Case | Reason |
|---|---|
| `A1M Junction 47 Garforth` (no brackets) | Level 1 regex requires `A1(M)` form |
| `A1 M Junction 47 Garforth` (space) | Same |
| `Bradford Cornwall` | Spatial contradiction suppression not strong enough for short city names |
| `Dartford Yorkshire` | Same |
| Lofthouse old ground-truth `(53.7617, -1.542)` | Original test coordinates were ~4.5 km from the actual M62/M1 interchange; updated in test suite to `(53.732, -1.521)` |
| `B1224 York` | B1224 runs Harrogate→York direction; closest OSM segment resolves ~11km west of York city centre because the road itself does not pass through York |

---

## Data Sources

The first three parquet files are required; the OSM roads file is optional but strongly recommended.

| File | Size | Source | Script |
|---|---|---|---|
| `os_open_names.parquet` | ~39 MB | OS Open Names (OGL) | `scripts/download_os_open_names.py` |
| `os_open_roads_junctions.parquet` | ~3 MB | OS Open Roads (OGL) | `scripts/download_os_open_roads.py` |
| `osm_named_junctions.parquet` | ~1.3 MB | OpenStreetMap (ODbL) | `scripts/download_osm_named_junctions.py` |
| `osm_roads.parquet` | ~6 MB | OpenStreetMap (ODbL) | `scripts/download_osm_roads.py` |

### Regenerating data

```bash
python scripts/download_os_open_names.py
python scripts/download_os_open_roads.py
python scripts/download_osm_named_junctions.py
```

Each script prompts before overwriting an existing file.

---

## Pipeline Architecture

```
Input string
    │
    ▼
Level 1 — Regex (level1_regex.py)
    │  Handles: full UK postcodes  →  postcodes.io API  →  lat/lon
    │           road refs + junction numbers (extracted, passed to Level 2)
    │
    ▼ (if unresolved or partial)
Level 2 — OS Names NER + scoring (level2_ner.py)
    │
    ├─ Token tagging (TokenGazetteer)
    │     Pass 1: exact gazetteer lookup
    │     Pass 2: county-scoped difflib fuzzy (only when no place token resolved)
    │
    ├─ Road-ref path
    │     OS Open Roads junction parquet → exact junction coords
    │     Falls back to OS Names road rows + BNG distance anchor to place name
    │
    └─ Place-name path
          OS Names candidate search (primary token)
          Admin-context spatial filter (BNG extent lookup, uk_admin.py)
          OSM junction augmentation (when "interchange"/"junction"/"roundabout" present
              AND unknown tokens exist — e.g. "Spaghetti", "Magic")
              ├─ Searches osm_named_junctions.parquet by NAME1 and NAME2 (alt_name)
              ├─ Spatial filter: discard OSM candidates > 20 km from anchor place
              └─ OS Names bridge: strips structural suffix from OSM NAME1,
                    looks up base place in OS Names for better centroid coords
          Candidate scoring (TYPE_WEIGHT + context match bonuses/penalties)
          Confidence: score/max_possible_score ≥ 0.15 → High, ≥ 0.10 → Medium
    │
    ▼ (stub — not implemented)
Level 3 — External API fallback
Level 4 — Local Ollama LLM fallback
```

---

## Scoring Weights (defaults)

| Parameter | Value | Role |
|---|---|---|
| `county_context_match` | 5.0 | Bonus when county token matches candidate |
| `district_context_match` | 3.0 | Bonus for district match |
| `city_context_match` | 2.0 | Bonus for city/town/village context match |
| `road_context_match` | 4.0 | Bonus for road name match |
| `junction_match` | 8.0 | Bonus for junction token match |
| `type_weight_scale` | 1.0 | Scales OS Names TYPE_WEIGHT contribution |
| `admin_contradiction` | −4.0 | Penalty for county context mismatch |
| `ambiguous_token` | −1.0 | Penalty for tokens with multiple gazetteer types |
| `near_qualifier` | −1.0 | Penalty for tokens preceded by a qualifier word |
| `high_threshold` | 0.15 | score/max ≥ this → "High" confidence |
| `medium_threshold` | 0.10 | score/max ≥ this → "Medium" confidence |
| `fuzzy_cutoff` | 0.75 | difflib similarity threshold for fuzzy matching |
| `road_place_anchor_km` | 20.0 | Max km between road candidates and anchor place |

Weights can be overridden at `Geocoder()` init or calibrated with `scripts/calibrate.py`.

---

## Known Limitations

- **`A1(M)` bracket normalisation** — inputs without brackets (`A1M`, `A1 M`) are not parsed as motorway designators. Would require additional Level 1 regex variants.
- **Spatial contradiction for short city names** — `Bradford Cornwall` still resolves to Bradford rather than being suppressed, because "Bradford" is an unambiguous high-weight match. Requires a harder admin-context veto, not yet implemented.
- **OS Names URI fields** — `COUNTY_UNITARY` and `POPULATED_PLACE` are stored as linked-data URIs in the CSV export; context scoring falls back to BNG spatial extents rather than string matching.
- **Colloquial junction names without alt_name in OSM** — if an interchange has no `alt_name` tag in OpenStreetMap (e.g. a newly named roundabout), it will not be found via the OSM augmentation path.
- **Level 3 / Level 4 not implemented** — API and LLM fallback stubs exist in `pipeline.py` but are not wired up.
