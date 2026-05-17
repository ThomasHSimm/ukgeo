# OS Names API — comparison findings

**Date:** May 2026  
**Notebook:** `notebooks/os_names_api_comparison.ipynb`  
**Purpose:** Scope whether the OS Names API `/find` endpoint is worth implementing as a Level 3 fallback in the ukgeo pipeline.

---

## Setup

- **Endpoint:** `GET https://api.os.uk/search/names/v1/find`
- **Auth:** API key via OS Data Hub (free account required)
- **Rate limit:** 600 transactions/minute (live mode)
- **Test set:** 15 core regression cases + 6 documented xfail cases (21 total)
- **Method:** Top-1 result from API vs ukgeo Level 2 output, compared against ground truth coordinates

---

## Results summary

| Metric | ukgeo Level 2 | OS Names API |
|---|---|---|
| Cases resolved | 21/21 | 21/21 |
| Median distance (core 15) | ~600m | ~7,400m |
| Latency | ~5ms | ~217ms |
| ukgeo wins (lower distance) | 10 cases | — |
| API wins (lower distance) | 5 cases | — |
| Tied (identical result) | 6 cases | — |

---

## Where ukgeo decisively beats the API

### Motorway junctions
The API returns the road as a `Section Of Numbered Road` centroid, not the junction point.
ukgeo uses OS Open Roads junction geometry — dramatically more accurate.

| Input | ukgeo | API |
|---|---|---|
| M62 Junction 26 | 2m | 7,423m |
| A1(M) Junction 47 Garforth | 2m | 58,629m |

### Colloquial names
The API has no concept of colloquial/alias names. It returns whatever OS Names string
best matches the tokens — often wrong.

| Input | ukgeo | API | API returned |
|---|---|---|---|
| Magic Roundabout Swindon | 358m | 20,465m | "Roundabout" (a woodland in Wiltshire) |
| Spaghetti Junction Birmingham | 957m | 8,095m | "Junction Road" |

### Typos
The API has no fuzzy matching — it fails completely on misspellings.

| Input | ukgeo | API | API returned |
|---|---|---|---|
| Brafford West Yorkshire | 565m | 267,525m | "Crawford Place" (West Berkshire) |

### Road + place descriptions
ukgeo's place-anchored road selection finds the road section nearest the named place.
The API returns the road centroid regardless of the place context.

| Input | ukgeo | API |
|---|---|---|
| A64 York bypass near Tadcaster | 1,421m | 20,180m |
| Station Road Leeds | 586m | 13,605m |

---

## Where the API beats ukgeo

### Named infrastructure sites
The API sometimes finds named infrastructure that OS Open Names has but our
local scoring doesn't surface as the top result.

| Input | ukgeo | API | API returned |
|---|---|---|---|
| Dartford Crossing Kent | 2,254m | 1,111m | "Stone Crossing" (railway, near Dartford) |
| Lofthouse Interchange | 2,235m | 1,575m | "Lofthouse" (village, slightly closer) |

Note: neither result is the actual Dartford Crossing or Lofthouse Interchange —
the gap is that named motorway infrastructure is absent from both.

### B-road centroids
The API's `Section Of Numbered Road` for B-roads sometimes picks a section
closer to the true location than our OSM segment selection.

| Input | ukgeo | API |
|---|---|---|
| B1224 York | 11,243m | 2,873m |

---

## The COUNTY_UNITARY finding

The API returns `COUNTY_UNITARY` as **readable text** ("North Yorkshire", "City of Edinburgh",
"Cornwall"). Our OS Open Names parquet returns URIs for this field.

This is significant: if we enriched our local parquet with county text from the API
(or rebuilt with GeoPackage format which includes text), our Level 2 scoring would improve
without any API calls at runtime.

Examples from the comparison:
- "Skipton, North Yorkshire" → API county: "North Yorkshire" ✓
- "Sighthill Edinburgh" → API county: "City of Edinburgh" ✓
- "Bradford Cornwall" → API county: "Cornwall" ✓ (but still returned wrong Bradford)

---

## Recommendation

### Implement as Level 3: yes, but narrowly

**Trigger condition for Level 3 API call:**
- Level 2 returns `confidence = "Low"` or unresolved, AND
- Input contains no road reference that OS Open Roads can handle (no motorway junction pattern)

**Do not call the API when:**
- Input matches a motorway junction pattern — ukgeo is 3,000–29,000x more accurate
- Input contains a typo — ukgeo fuzzy matching is far better than the API
- Input is a road + place description — ukgeo place-anchored selection beats the API

**Expected benefit of Level 3:**
- Named infrastructure sites with no clear road reference (bridges, crossings, stations)
- Cases where local parquet returns no candidates at all
- Estimated 2–5% improvement in resolve rate on real-world inputs

**Cost:**
- 217ms latency per call (43x slower than Level 2)
- Requires OS Data Hub API key (free account)
- 600 requests/minute rate limit — fine for a fallback, not for bulk

---

## Implementation notes for Level 3

When implementing, pass the Level 2 interpreted tokens (not the raw input) to the API
where possible — e.g. if Level 2 tagged "Dartford" as a city and "Kent" as a county,
query `"Dartford Kent"` rather than `"Dartford Crossing Kent"`. This should improve
API result quality by removing qualifier noise.

Also consider using the `fq` (filter by local type) parameter to avoid the API
returning woodland, railways, and other irrelevant types when geocoding road-related inputs.

---

## Implied confidence from candidate spread

The OS Names API returns results ordered by relevance but provides no
confidence score. A proxy confidence can be derived from the spread of
the top-N candidates:

| Spread (RMS distance) | Implied confidence |
|---|---|
| < 2km | High — candidates cluster tightly, top result is unambiguous |
| 2–10km | Medium — some ambiguity |
| > 10km | Low — top result may be an outlier |

This is implemented in `ukgeo/level3_os_names.py` as `implied_confidence()`.
It uses `maxresults=5` by default — enough to detect spread without
excessive API calls.

---

## Data sources

- OS Names API documentation: https://docs.os.uk/os-apis/accessing-os-apis/os-names-api
- Comparison data: `data/os_names_api_comparison.csv`
- Notebook: `notebooks/os_names_api_comparison.ipynb`
