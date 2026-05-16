# Alternatives to ukgeo

This document is for anyone evaluating whether to use ukgeo or something else. It is written to be honest: if another tool does your job better, we say so.

The alternatives are described by what they do, not by how they compare to ukgeo. That way this document stays accurate even as ukgeo changes.

**In this file:** we compare ukgeo with other geocoding, address parsing, and location lookup tools so a user can choose the right tool for a job. For ukgeo's own gaps and roadmap context, see `docs/gaps_and_ecosystem.md`.

Limits, pricing, and service terms for hosted APIs change over time. Treat the numbers below as orientation, not procurement advice.

---

## What kind of geocoding problem do you have?

Before comparing tools, it helps to be precise about what you need:

- **Input type**: clean structured addresses, postcodes, road references, free text, crash report descriptions?
- **Volume**: a handful of lookups, thousands, millions?
- **Accuracy requirement**: within 100m, 1km, 5km?
- **Online/offline**: can you make API calls per query, or do you need bulk offline processing?
- **UK-specific or global**: do you need UK road network awareness, or general geocoding?
- **Cost**: free at scale, or acceptable to pay per query?

---

## Tools and what they actually do

### Nominatim / OpenStreetMap

**What it is:** The geocoder that powers openstreetmap.org. Open source, self-hostable, or usable via the public API.

**Strengths:**
- Free, globally comprehensive
- Handles place names, addresses, landmarks well
- Self-hostable for unlimited queries

**Weaknesses:**
- Public API rate-limited (1 request/second, no bulk)
- CORS restrictions prevent use from browser-based tools
- UK road network coverage is patchy — motorway junctions, named interchanges, and road section references are unreliable
- Free text input quality depends heavily on how well the input matches OSM naming conventions
- Not tuned for ukgeo-style administrative context scoring (e.g. Sighthill in Edinburgh vs Glasgow)

**When to use it:** Clean place names and addresses at low volume, or self-hosted for high volume. Not recommended for road reference inputs or crash report style text.

---

### geopy

**What it is:** A Python library that wraps multiple geocoding APIs (Nominatim, Google, Bing, ArcGIS etc.) with a consistent interface.

**Strengths:**
- Simple API, widely used, well documented
- Easy to switch between providers
- Handles single queries cleanly

**Weaknesses:**
- Every query is an API call — no offline bulk processing
- Rate limits and costs depend on the underlying provider
- No UK-specific logic; accuracy limited by whichever provider you use
- Not designed for road reference inputs

**When to use it:** When you want a clean Python wrapper around a provider you already have access to, at moderate volume. If you have a Google Maps API key and need general geocoding, geopy is a good choice.

---

### Geoapify

**What it is:** A commercial geocoding API with a free tier (3,000 requests/day, 500 rows per batch).

**Strengths:**
- Good global coverage
- Batch geocoding with confidence scores
- Simple REST API

**Weaknesses:**
- CORS restrictions — cannot be called directly from a browser without a server in the middle
- Free tier limited to 3,000 requests/day, which is insufficient for bulk STATS19-scale work
- No UK road network awareness
- Paid tiers required for serious volume

**When to use it:** Small-scale batch geocoding of clean addresses where you have a backend server. Not suitable for offline bulk processing or road reference inputs.

---

### Google Maps Geocoding API

**What it is:** Google's geocoding API. Highly accurate, globally comprehensive.

**Strengths:**
- Best-in-class accuracy for clean addresses
- Handles ambiguity and misspellings well
- Very good UK coverage

**Weaknesses:**
- Paid beyond the free tier ($5 per 1,000 requests after $200/month credit)
- Every query is an API call — no offline processing
- Terms of service restrict storing results and using them outside Google Maps context
- Not suitable for bulk historical data processing (STATS19 at scale would be expensive)

**When to use it:** If accuracy is paramount, volume is low to moderate, and cost is acceptable. The ToS restrictions are a real constraint for road safety research use cases.

---

### ArcGIS / Esri World Geocoder

**What it is:** Esri's geocoding service, integrated into ArcGIS products.

**Strengths:**
- Very accurate for UK addresses
- Integrated with GIS workflows

**Weaknesses:**
- Requires ArcGIS licence or credits — not free at scale
- Bulk geocoding costs extra (credits consumed per match)
- Vendor lock-in
- Not open source

**When to use it:** If your organisation already has ArcGIS licences and you need occasional geocoding as part of a GIS workflow. Not suitable for open research pipelines.

---

### Photon (Komoot)

**What it is:** An open source geocoder built on OpenSearch, backed by OSM data. Self-hostable.

**Strengths:**
- Fast, scalable when self-hosted
- Open source
- Better free-text handling than raw Nominatim

**Weaknesses:**
- Still OSM-backed — same UK road network gaps as Nominatim
- Self-hosting requires OpenSearch infrastructure (non-trivial setup)
- Public demo server is rate-limited and unreliable for production
- No UK-specific data sources

**When to use it:** If you want a self-hosted geocoder for general place name queries at scale, and you're comfortable running OpenSearch. Not suitable for road reference inputs.

---

### postcodes.io

**What it is:** A free, open source API for UK postcode lookup. Returns precise centroid coordinates, admin geography, and statistical geographies for any UK postcode.

**Strengths:**
- Extremely accurate for postcodes (ONS data)
- Free, no key required, generous rate limits
- Returns useful context: LSOA, ward, local authority, region
- CORS-friendly

**Weaknesses:**
- Postcodes only — not a general geocoder
- No road references, place names, or free text
- Centroid coordinates represent the postcode sector, not a specific address

**When to use it:** Any time you have a full or partial postcode. ukgeo uses postcodes.io internally at Level 1.

---

### OS Names API

**What it is:** Ordnance Survey's geocoding API, backed by OS Open Names data (the same data ukgeo uses locally).

**Strengths:**
- Authoritative UK data — OS is the ground truth for UK geography
- Handles place names, postcodes, and some road references
- Free tier available (1,000 requests/day)

**Weaknesses:**
- Requires an OS Data Hub account and API key
- Free tier (1,000 requests/day) is insufficient for bulk processing
- No handling of messy free text or road-safety-style inputs
- Rate-limited — not suitable as a primary geocoder for thousands of records

**When to use it:** As a fallback for difficult cases that your primary geocoder can't resolve. ukgeo plans to use this as a Level 3 fallback.

---

### OS Places API / AddressBase / Royal Mail PAF

**What it is:** Authoritative UK address-level data and services. These are the right class of tools when the problem is precise address geocoding rather than messy road-reference text.

**Strengths:**
- Best fit for address-level and premises-level accuracy
- Authoritative UK address sources
- Better suited to sub-100m address matching than ukgeo

**Weaknesses:**
- Premium/licensed data or service access
- Licensing can restrict redistribution, derived data, and storage
- Not designed around road-safety-style text such as `B6265 near Pateley Bridge` or `M62 between J26 and J27`

**When to use it:** When you need address-level precision, have budget/licensing coverage, and your inputs are genuine addresses rather than road references or crash-report descriptions.

---

### libpostal

**What it is:** An open source C library (with Python bindings) for parsing and normalising international street addresses.

**Strengths:**
- Excellent at parsing structured address components (house number, street, city, postcode)
- Handles many languages and international formats
- Fast, offline

**Weaknesses:**
- A parser, not a geocoder — it extracts address components but does not return coordinates
- UK road reference inputs (M62 J26, A647 near Bradford) are not address-structured and parse poorly
- Requires a C build environment and significant disk space for the language models

**When to use it:** As a pre-processing step to normalise structured addresses before geocoding. Useful upstream of Nominatim or a commercial API for clean address data. Less useful for road reference or crash report inputs.

---

## Summary table

| Tool | Free at scale | Offline bulk | UK road refs | Free text | Accuracy (UK) |
|---|---|---|---|---|---|
| ukgeo | ✓ | ✓ | ✓ | ✓ | Medium–High |
| Nominatim | ✓ (self-host) | ✓ (self-host) | ✗ | Partial | Medium |
| geopy | Depends on provider | ✗ | ✗ | Depends | Depends |
| Geoapify | Limited free tier | ✗ | ✗ | Partial | Medium–High |
| Google Maps API | ✗ | ✗ | ✗ | ✓ | High |
| ArcGIS | ✗ | ✗ | ✗ | Partial | High |
| Photon | ✓ (self-host) | ✓ (self-host) | ✗ | Partial | Medium |
| postcodes.io | ✓ | ✓ | ✗ | ✗ | High (postcodes) |
| OS Names API | Limited free tier | ✗ | Partial | ✗ | High |
| OS Places / AddressBase / PAF | ✗ | Depends on licence | ✗ | Partial | Very high (addresses) |
| libpostal | ✓ | ✓ | ✗ | ✗ | N/A (parser only) |

---

## When ukgeo is probably not the right choice

- **You have clean, structured UK addresses or postcodes at low volume** — postcodes.io + geopy/Nominatim is simpler and well-tested.
- **You need sub-100m accuracy for house-level addresses** — OS AddressBase or Royal Mail PAF (both premium) are the authoritative sources. ukgeo does not attempt precise address-level geocoding.
- **You need global coverage** — ukgeo is UK-only by design.
- **You need real-time single-query geocoding in a production web app** — a hosted API (Google, Geoapify, OpenCage) with a proper SLA is more appropriate than ukgeo's local parquet approach.
- **Your inputs are already well-structured** — the tiered pipeline adds complexity that isn't needed if your data is clean.

## When ukgeo is the right choice

- You have messy UK location text: road references, junction descriptions, crash report style, colloquial names, old county names.
- You need offline bulk processing — thousands to millions of records without API costs or rate limits.
- Your domain is road safety, transport, or any application where road network references appear in free text.
- You need M/A/B-road reference handling rather than address-level premises matching.
- You want full control over the data and methodology — no black-box API, auditable pipeline, tuneable weights.
- You're working with STATS19, AADF, or similar UK road datasets where location fields are semi-structured rather than clean addresses.
