"""
Build data/infrastructure_aliases.csv for known UK infrastructure gaps.

The output is intentionally small and curated: it is a seed alias table for
major named road infrastructure that is poorly represented in OS Open Names,
OSM named junctions, or the OS Names API top result.
"""

from __future__ import annotations

import csv
import time
from pathlib import Path


# (input_name, category, query_override, fq_override)
# query_override: alternative search term for API (None = use input_name)
# fq_override: OS API fq filter (None = auto-detect)
TARGETS = [
    # --- Major bridges and river crossings ---
    ("Dartford Crossing", "bridge", "Dartford Crossing", None),
    ("QE2 Bridge", "bridge", "Queen Elizabeth II Bridge", None),
    ("Severn Bridge", "bridge", "Severn Bridge", None),
    ("Second Severn Crossing", "bridge", "Prince of Wales Bridge", None),
    ("Humber Bridge", "bridge", "Humber Bridge", None),
    ("Forth Road Bridge", "bridge", "Forth Road Bridge", None),
    ("Forth Bridge", "bridge", "Forth Bridge", None),
    ("Tay Road Bridge", "bridge", "Tay Road Bridge", None),
    ("Tyne Tunnel", "tunnel", "Tyne Tunnel", None),
    ("Mersey Gateway", "bridge", "Mersey Gateway", None),
    ("Runcorn Bridge", "bridge", "Silver Jubilee Bridge", None),
    ("Tinsley Viaduct", "viaduct", "Tinsley Viaduct", None),
    ("Thelwall Viaduct", "viaduct", "Thelwall Viaduct", None),
    ("Almondsbury Interchange", "junction", "Almondsbury Interchange", None),
    ("Lofthouse Interchange", "junction", "Lofthouse Interchange", None),
    ("Gravelly Hill Interchange", "junction", "Gravelly Hill Interchange", None),
    ("Spaghetti Junction", "junction", "Gravelly Hill Interchange", None),
    ("Magic Roundabout Swindon", "roundabout", "Magic Roundabout", "Roundabout"),
    ("Chiswick Flyover", "junction", "Chiswick Flyover", None),

    # --- Bus stations OS API gets wrong ---
    ("Harrogate Bus Station", "bus_station", "Harrogate Bus Station", "Bus_Station"),
    ("Liverpool One Bus Station", "bus_station", "Liverpool One Bus Station", "Bus_Station"),
    ("Manchester Coach Station", "bus_station", "Chorlton Street Coach Station", "Coach_Station"),

    # --- Motorway services OS API misnames ---
    ("Cobham Services", "services", "Cobham Services", "Road_User_Services"),
    ("Clacket Lane Services", "services", "Clacket Lane Services", "Road_User_Services"),
    ("Heston Services", "services", "Heston Services", "Road_User_Services"),

    # --- Named road tunnels ---
    ("Mersey Tunnel", "tunnel", "Queensway Tunnel", None),
    ("Kingsway Tunnel", "tunnel", "Kingsway Tunnel", None),
    ("Blackwall Tunnel", "tunnel", "Blackwall Tunnel", None),
    ("Rotherhithe Tunnel", "tunnel", "Rotherhithe Tunnel", None),
    ("Dartford Tunnel", "tunnel", "Dartford Crossing", None),
    ("Brynglas Tunnels", "tunnel", "Brynglas Tunnels", None),
    ("Queensway Tunnel Birmingham", "tunnel", "Queensway Tunnel Birmingham", None),
]

OVERPASS_URLS = ["https://overpass-api.de/api/interpreter"]
GB_BBOX = "(49.0,-10.0,61.0,2.0)"
HTTP_HEADERS = {"User-Agent": "ukgeo infrastructure alias builder"}


def query_osm_overpass(name: str, category: str) -> dict | None:
    """
    Query Overpass API for named infrastructure.
    Returns {"lat": float, "lon": float, "osm_name": str, "source": "osm"} or None.
    """
    import httpx

    tag_queries = {
        "bridge": 'way["bridge"="yes"]["name"~"{name}",i]',
        "tunnel": 'way["tunnel"="yes"]["name"~"{name}",i]',
        "viaduct": 'way["bridge"="viaduct"]["name"~"{name}",i]',
        "junction": 'node["highway"="motorway_junction"]["name"~"{name}",i]',
        "roundabout": 'way["junction"="roundabout"]["name"~"{name}",i]',
        "services": 'node["highway"="services"]["name"~"{name}",i]',
        "bus_station": 'node["amenity"="bus_station"]["name"~"{name}",i]',
    }

    tag_q = tag_queries.get(category, 'node["name"~"{name}",i]')
    query = f"""
    [out:json][timeout:30];
    (
      {tag_q.format(name=name)}{GB_BBOX};
    );
    out center;
    """

    try:
        elements = []
        for url in OVERPASS_URLS:
            try:
                r = httpx.post(
                    url,
                    data={"data": query},
                    headers=HTTP_HEADERS,
                    timeout=httpx.Timeout(12.0, connect=5.0),
                )
                r.raise_for_status()
                elements = r.json().get("elements", [])
                break
            except Exception as e:
                print(f"  OSM error for {name} via {url}: {e}")
        if not elements:
            return None

        el = elements[0]
        if el.get("type") == "way":
            center = el.get("center", {})
            lat, lon = center.get("lat"), center.get("lon")
        else:
            lat, lon = el.get("lat"), el.get("lon")

        if lat and lon:
            return {
                "lat": lat,
                "lon": lon,
                "osm_name": el.get("tags", {}).get("name", name),
                "osm_type": el.get("tags", {}).get("highway")
                or el.get("tags", {}).get("bridge")
                or el.get("tags", {}).get("tunnel")
                or el.get("type", ""),
                "source": "osm",
            }
    except Exception as e:
        print(f"  OSM error for {name}: {e}")
    return None


_OS_LOOKUP = None


def _significant_tokens(text: str) -> set[str]:
    stop = {"the", "of", "and"}
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in text)
    tokens = set()
    for token in cleaned.split():
        if len(token) <= 2 or token in stop:
            continue
        if token.endswith("s") and len(token) > 4:
            token = token[:-1]
        tokens.add(token)
    return tokens


def _os_api_result_matches(query: str, result_name: str) -> bool:
    query_tokens = _significant_tokens(query)
    if not query_tokens:
        return True
    result_tokens = _significant_tokens(result_name)
    return query_tokens.issubset(result_tokens)


def query_os_api(name: str, fq: str | None, api_key: str) -> dict | None:
    """Query OS Names API and convert the top result to WGS84."""
    global _OS_LOOKUP

    from ukgeo.level3_os_names import query_os_names
    from ukgeo.lookup import DEFAULT_PARQUET, OSNamesLookup

    results = query_os_names(name, api_key, max_results=3, fq=fq)
    if not results:
        return None

    if _OS_LOOKUP is None:
        _OS_LOOKUP = OSNamesLookup(DEFAULT_PARQUET)

    top = results[0]
    os_name = top.get("NAME1", "")
    if not _os_api_result_matches(name, os_name):
        print(f"  OS API rejected weak match: {os_name}")
        return None

    try:
        lat, lon = _OS_LOOKUP.bng_to_wgs84(top["GEOMETRY_X"], top["GEOMETRY_Y"])
        return {
            "lat": lat,
            "lon": lon,
            "os_name": os_name,
            "os_type": top.get("LOCAL_TYPE", ""),
            "os_county": top.get("COUNTY_UNITARY", ""),
            "source": "os_names_api",
        }
    except Exception:
        return None


def main() -> int:
    from ukgeo.utils import get_env_key, load_env

    load_env()
    api_key = get_env_key("OS_API_KEY", required=False)

    rows = []

    for input_name, category, query, fq in TARGETS:
        print(f"\n{input_name} ({category})")
        result = None
        query_text = query or input_name

        if category in ("bridge", "tunnel", "viaduct", "junction", "roundabout"):
            result = query_osm_overpass(query_text, category)
            if result:
                print(
                    f"  OSM: {result['osm_name']} -> "
                    f"{result['lat']:.5f}, {result['lon']:.5f}"
                )

        if not result and api_key:
            result = query_os_api(query_text, fq, api_key)
            if result:
                print(
                    f"  OS API: {result['os_name']} ({result['os_type']}) -> "
                    f"{result['lat']:.5f}, {result['lon']:.5f}"
                )

        if not result:
            print("  not found - needs manual entry")
            rows.append({
                "name": input_name,
                "category": category,
                "lat": "",
                "lon": "",
                "source": "manual_required",
                "verified_name": "",
                "notes": "not found by script - needs manual coordinate entry",
            })
        else:
            rows.append({
                "name": input_name,
                "category": category,
                "lat": result.get("lat", ""),
                "lon": result.get("lon", ""),
                "source": result.get("source", ""),
                "verified_name": result.get("osm_name") or result.get("os_name", ""),
                "notes": result.get("os_type", "") or result.get("os_county", ""),
            })

        time.sleep(1.1)

    out_path = Path(__file__).parent.parent / "data" / "infrastructure_aliases.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", newline="") as f:
        f.write("# ukgeo infrastructure aliases\n")
        f.write("# Sources: OpenStreetMap (ODbL) © OpenStreetMap contributors\n")
        f.write("#          OS Names API — Contains OS data © Crown Copyright 2024\n")
        f.write("# Manually verified and maintained. Add new rows as gaps are found.\n")
        f.write("# Columns: name (input text), category, lat, lon, source, verified_name, notes\n")
        writer = csv.DictWriter(
            f,
            fieldnames=["name", "category", "lat", "lon", "source", "verified_name", "notes"],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWritten {len(rows)} rows to {out_path}")

    found = sum(1 for r in rows if r["lat"])
    print(f"Found: {found}/{len(rows)}")
    print(f"Needs manual entry: {len(rows) - found}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
