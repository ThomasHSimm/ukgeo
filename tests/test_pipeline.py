"""
Tests against the 15 UK edge cases from the design phase.
Requires OS Open Names parquet to be present (skipped otherwise).
"""

import pytest
from pathlib import Path
from ukgeo.pipeline import Geocoder, _haversine

PARQUET = Path(__file__).parent.parent / "data" / "os_open_names.parquet"
pytestmark = pytest.mark.skipif(
    not PARQUET.exists(),
    reason="OS Open Names parquet not built — run scripts/download_os_open_names.py"
)

@pytest.fixture(scope="module")
def geo():
    return Geocoder()

# (input, expected_lat, expected_lon, tolerance_m, min_confidence)
CASES = [
    ("LS1 1BA",                        53.7997, -1.5492,   500,  "High"),
    ("WF10 4QH",                       53.7230, -1.3550,  2000,  "Medium"),
    ("M62 Junction 26",                53.7054, -1.8016,  2000,  "High"),
    ("A647 near Bradford",             53.7950, -1.7800,  5000,  "Medium"),
    ("Lofthouse Interchange",          53.7617, -1.5420,  2000,  "High"),
    ("Spaghetti Junction Birmingham",  52.5137, -1.8346,  2000,  "High"),
    ("Magic Roundabout Swindon",       51.5585, -1.7837,  2000,  "High"),
    ("A64 York bypass near Tadcaster", 53.8720, -1.2650, 10000,  "Medium"),
    ("Skipton, North Yorkshire",       53.9619, -2.0175,  2000,  "High"),
    ("Aberford West Yorkshire",        53.8333, -1.3333,  2000,  "High"),
    ("Dartford Crossing Kent",         51.4454,  0.2744,  2000,  "High"),
    ("Station Road Leeds",             53.7955, -1.5490,  5000,  "Medium"),
    ("A1(M) Junction 47 Garforth",     53.7897, -1.3542,  5000,  "Medium"),
    ("Brafford West Yorkshire",        53.7950, -1.7594,  5000,  "Medium"),
    ("Sighthill Edinburgh",            55.9285, -3.2441,  3000,  "High"),
]

CONF_ORDER = {"High": 2, "Medium": 1, "Low": 0}

@pytest.mark.parametrize("inp,true_lat,true_lon,tol_m,min_conf", CASES)
def test_case(geo, inp, true_lat, true_lon, tol_m, min_conf):
    result = geo.geocode(inp)
    assert result.resolved, f"Unresolved: {inp!r} — {result.notes}"
    dist = _haversine(true_lat, true_lon, result.lat, result.lon)
    assert dist <= tol_m, (
        f"{inp!r}: {dist:.0f}m error (tolerance {tol_m}m) — "
        f"got {result.lat},{result.lon}, expected {true_lat},{true_lon}"
    )
    assert CONF_ORDER.get(result.confidence, -1) >= CONF_ORDER[min_conf], (
        f"{inp!r}: confidence {result.confidence!r} below minimum {min_conf!r}"
    )

def test_batch(geo):
    inputs = [c[0] for c in CASES]
    df = geo.geocode_batch(inputs, show_progress=False)
    assert len(df) == len(inputs)
    assert "lat" in df.columns
    resolved = df.filter(df["lat"].is_not_null())
    assert len(resolved) >= len(inputs) * 0.8, "Less than 80% resolved in batch"

def test_empty_input(geo):
    r = geo.geocode("")
    assert not r.resolved
    assert r.confidence == "Low"

def test_match_score_present(geo):
    r = geo.geocode("Skipton, North Yorkshire")
    assert r.notes and "match_score=" in r.notes
