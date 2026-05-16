"""
Pipeline regression tests for UK geocoding edge cases.
Requires OS Open Names parquet to be present (skipped otherwise).
"""

import pytest
from pathlib import Path
import math
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
    ("LS1 1BA",                        53.7997, -1.5492,  1000,  "High"),
    ("WF10 4QH",                       53.7230, -1.3550,  2000,  "Medium"),
    ("M62 Junction 26",                53.736186, -1.726631,  2000,  "High"),
    ("A647 near Bradford",             53.7950, -1.7800,  5000,  "Medium"),
    ("Lofthouse Interchange",          53.7320, -1.5210,  3000,  "Medium"),
    ("Spaghetti Junction Birmingham",  52.5137, -1.8346,  2000,  "High"),
    ("Magic Roundabout Swindon",       51.5585, -1.7837,  2000,  "High"),
    ("A64 York bypass near Tadcaster", 53.8720, -1.2650, 10000,  "Medium"),
    ("Skipton, North Yorkshire",       53.9619, -2.0175,  2000,  "High"),
    ("Aberford West Yorkshire",        53.8333, -1.3333,  2000,  "High"),
    ("Dartford Crossing Kent",         51.4454,  0.2744,  3000,  "High"),
    ("Station Road Leeds",             53.7955, -1.5490,  5000,  "Medium"),
    ("A1(M) Junction 47 Garforth",     54.009541, -1.377813,  5000,  "Medium"),
    ("Brafford West Yorkshire",        53.7950, -1.7594,  5000,  "Medium"),
    ("Sighthill Edinburgh",            55.9285, -3.2441,  5000,  "High"),
]

ROAD_SUFFIX_EQUIVALENCE_CASES = [
    ("Station Road Leeds", "Station Rd Leeds"),
    ("Station Road Leeds", "Station Rd. Leeds"),
    ("Abbey Road London", "Abbey Rd London"),
    ("Abbey Road London", "Abbey Rd. London"),
    ("Station Street Leeds", "Station St Leeds"),
    ("Hanover Square Leeds", "Hanover Sq Leeds"),
    ("Spring Gardens Leeds", "Spring Gdns Leeds"),
]

ST_AMBIGUITY_CASES = [
    ("St Johns Road Leeds", "Saint Johns Road Leeds", "Street Johns Road Leeds"),
]

STREET_SUFFIX_CASES = [
    ("Station Street Leeds", "Station St Leeds"),
]

TYPO_EQUIVALENCE_CASES = [
    ("Bradford West Yorkshire", "Brdford West Yorkshire", 2000),
    ("Bradford West Yorkshire", "Bradferd West Yorkshire", 2000),
    ("Skipton North Yorkshire", "Skiptom North Yorkshire", 2000),
    ("Tadcaster North Yorkshire", "Tadcastr North Yorkshire", 2000),
    pytest.param(
        "A1(M) Junction 47 Garforth",
        "A1M Junction 47 Garforth",
        7000,
        marks=pytest.mark.xfail(
            strict=True,
            reason="Collapsed A1(M) spelling currently resolves to Garforth, not the junction.",
        ),
    ),
    pytest.param(
        "A1(M) Junction 47 Garforth",
        "A1 M Junction 47 Garforth",
        7000,
        marks=pytest.mark.xfail(
            strict=True,
            reason="Spaced A1(M) spelling currently resolves to an A1 road segment, not the junction.",
        ),
    ),
]

COUNTY_CONTEXT_CASES = [
    ("Bournemouth Dorset", 50.7210, -1.8767, 5000, "High"),
    ("Stockton on Tees Cleveland", 54.5640, -1.3127, 7000, "High"),
    ("Reading Berkshire", 51.4538, -0.9738, 5000, "High"),
    ("Croydon Surrey", 51.3544, -0.0889, 7000, "High"),
    ("Swansea Glamorgan", 51.6201, -3.9414, 7000, "Medium"),
    ("Sighthill Midlothian", 55.9246, -3.2973, 7000, "Medium"),
]

BAD_CONTEXT_CASES = [
    ("Skipton Kent", 53.9602, -2.0177, 5000),
    pytest.param(
        "Bradford Cornwall",
        53.7908,
        -1.7546,
        7000,
        marks=pytest.mark.xfail(
            strict=True,
            reason="Wrong county currently allows a confident Bradford-on-Avon match.",
        ),
    ),
    pytest.param(
        "Dartford Yorkshire",
        51.4454,
        0.2744,
        7000,
        marks=pytest.mark.xfail(
            strict=True,
            reason="Wrong county currently allows a confident unrelated road-name match.",
        ),
    ),
]

CONF_ORDER = {"High": 2, "Medium": 1, "Low": 0}


def _assert_resolved_finite(result, inp):
    assert result.resolved, f"Unresolved: {inp!r} — {result.notes}"
    assert math.isfinite(result.lat) and math.isfinite(result.lon), (
        f"{inp!r}: resolved with non-finite coordinates "
        f"{result.lat},{result.lon} — {result.notes}"
    )


def _assert_min_confidence(result, inp, min_conf):
    assert CONF_ORDER.get(result.confidence, -1) >= CONF_ORDER[min_conf], (
        f"{inp!r}: confidence {result.confidence!r} below minimum {min_conf!r}"
    )


@pytest.mark.parametrize("inp,true_lat,true_lon,tol_m,min_conf", CASES)
def test_case(geo, inp, true_lat, true_lon, tol_m, min_conf):
    result = geo.geocode(inp)
    _assert_resolved_finite(result, inp)
    dist = _haversine(true_lat, true_lon, result.lat, result.lon)
    assert dist <= tol_m, (
        f"{inp!r}: {dist:.0f}m error (tolerance {tol_m}m) — "
        f"got {result.lat},{result.lon}, expected {true_lat},{true_lon}"
    )
    _assert_min_confidence(result, inp, min_conf)


@pytest.mark.parametrize("full_form,abbrev_form", ROAD_SUFFIX_EQUIVALENCE_CASES)
def test_road_suffix_abbreviations_resolve_equivalently(geo, full_form, abbrev_form):
    full = geo.geocode(full_form)
    abbrev = geo.geocode(abbrev_form)

    _assert_resolved_finite(full, full_form)
    _assert_resolved_finite(abbrev, abbrev_form)

    dist = _haversine(full.lat, full.lon, abbrev.lat, abbrev.lon)
    assert dist <= 500, (
        f"{abbrev_form!r} resolved {dist:.0f}m from {full_form!r} — "
        f"full={full.lat},{full.lon}; abbrev={abbrev.lat},{abbrev.lon}"
    )
    _assert_min_confidence(abbrev, abbrev_form, "Medium")


@pytest.mark.parametrize("st_form,saint_form,street_form", ST_AMBIGUITY_CASES)
def test_st_prefix_prefers_saint_context_over_street_suffix(geo, st_form, saint_form, street_form):
    st = geo.geocode(st_form)
    saint = geo.geocode(saint_form)
    street = geo.geocode(street_form)

    _assert_resolved_finite(st, st_form)
    _assert_resolved_finite(saint, saint_form)

    dist = _haversine(st.lat, st.lon, saint.lat, saint.lon)
    assert dist <= 500, (
        f"{st_form!r} should track the Saint spelling, but was {dist:.0f}m away — "
        f"st={st.lat},{st.lon}; saint={saint.lat},{saint.lon}"
    )
    _assert_min_confidence(st, st_form, "Medium")
    if street.resolved:
        assert CONF_ORDER[st.confidence] > CONF_ORDER[street.confidence], (
            f"{st_form!r} should not be scored like {street_form!r} — "
            f"st confidence={st.confidence}, street confidence={street.confidence}"
        )


@pytest.mark.parametrize("street_form,st_suffix_form", STREET_SUFFIX_CASES)
def test_st_suffix_can_mean_street_when_context_is_clear(geo, street_form, st_suffix_form):
    street = geo.geocode(street_form)
    st_suffix = geo.geocode(st_suffix_form)

    _assert_resolved_finite(street, street_form)
    _assert_resolved_finite(st_suffix, st_suffix_form)

    dist = _haversine(street.lat, street.lon, st_suffix.lat, st_suffix.lon)
    assert dist <= 500, (
        f"{st_suffix_form!r} should track {street_form!r}, but was {dist:.0f}m away — "
        f"street={street.lat},{street.lon}; suffix={st_suffix.lat},{st_suffix.lon}"
    )
    _assert_min_confidence(st_suffix, st_suffix_form, "Medium")


@pytest.mark.parametrize("correct_form,typo_form,tol_m", TYPO_EQUIVALENCE_CASES)
def test_typo_queries_resolve_near_correct_spelling(geo, correct_form, typo_form, tol_m):
    correct = geo.geocode(correct_form)
    typo = geo.geocode(typo_form)

    _assert_resolved_finite(correct, correct_form)
    _assert_resolved_finite(typo, typo_form)

    dist = _haversine(correct.lat, correct.lon, typo.lat, typo.lon)
    assert dist <= tol_m, (
        f"{typo_form!r} resolved {dist:.0f}m from {correct_form!r} "
        f"(tolerance {tol_m}m) — correct={correct.lat},{correct.lon}; "
        f"typo={typo.lat},{typo.lon}"
    )
    _assert_min_confidence(typo, typo_form, "Medium")


@pytest.mark.parametrize("inp,true_lat,true_lon,tol_m,min_conf", COUNTY_CONTEXT_CASES)
def test_historic_or_colloquial_county_contexts(geo, inp, true_lat, true_lon, tol_m, min_conf):
    result = geo.geocode(inp)
    _assert_resolved_finite(result, inp)
    dist = _haversine(true_lat, true_lon, result.lat, result.lon)
    assert dist <= tol_m, (
        f"{inp!r}: {dist:.0f}m error (tolerance {tol_m}m) — "
        f"got {result.lat},{result.lon}, expected {true_lat},{true_lon}"
    )
    _assert_min_confidence(result, inp, min_conf)


@pytest.mark.parametrize("inp,true_lat,true_lon,tol_m", BAD_CONTEXT_CASES)
def test_wrong_county_context_does_not_create_confident_bad_match(geo, inp, true_lat, true_lon, tol_m):
    result = geo.geocode(inp)
    if not result.resolved:
        return

    _assert_resolved_finite(result, inp)
    dist = _haversine(true_lat, true_lon, result.lat, result.lon)
    assert dist <= tol_m or result.confidence != "High", (
        f"{inp!r}: wrong county/context produced a confident bad match — "
        f"got {result.lat},{result.lon}, confidence={result.confidence}, "
        f"notes={result.notes}"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "The old Lofthouse Interchange CASES coordinate is likely bad test "
        "ground truth near Belle Isle/Beeston, not a geocoder failure."
    ),
)
def test_lofthouse_interchange_old_ground_truth_is_disputed(geo):
    result = geo.geocode("Lofthouse Interchange")
    _assert_resolved_finite(result, "Lofthouse Interchange")
    old_lat, old_lon = 53.7617, -1.5420
    dist = _haversine(old_lat, old_lon, result.lat, result.lon)
    assert dist <= 2000, (
        f"Old Lofthouse ground truth is {dist:.0f}m from current result — "
        f"got {result.lat},{result.lon}; old expected {old_lat},{old_lon}"
    )

def test_batch(geo):
    inputs = [c[0] for c in CASES]
    df = geo.geocode_batch(inputs, show_progress=False)
    assert len(df) == len(inputs)
    assert "lat" in df.columns
    resolved = df.filter(df["lat"].is_not_null())
    assert len(resolved) >= len(inputs) * 0.8, "Less than 80% resolved in batch"

B_ROAD_CASES = [
    # B-road + local authority context — should resolve within 10km
    ("B6265 Bradford",    53.7950, -1.7594, 10000, "Medium"),
    pytest.param(
        "B1224 York", 53.9590, -1.0815, 10000, "Medium",
        marks=pytest.mark.xfail(
            strict=True,
            reason=(
                "B1224 runs between Harrogate and York; closest OSM segment resolves "
                "~11km west of York city centre because the road itself is not in York."
            ),
        ),
    ),
    ("B6113 Huddersfield", 53.6458, -1.7850, 10000, "Medium"),
]

@pytest.mark.parametrize("inp,true_lat,true_lon,tol_m,min_conf", B_ROAD_CASES)
def test_b_road_cases(geo, inp, true_lat, true_lon, tol_m, min_conf):
    result = geo.geocode(inp)
    _assert_resolved_finite(result, inp)
    dist = _haversine(true_lat, true_lon, result.lat, result.lon)
    assert dist <= tol_m, (
        f"{inp!r}: {dist:.0f}m error (tolerance {tol_m}m) — "
        f"got {result.lat},{result.lon}"
    )
    _assert_min_confidence(result, inp, min_conf)


def test_empty_input(geo):
    r = geo.geocode("")
    assert not r.resolved
    assert r.confidence == "Low"

def test_match_score_present(geo):
    r = geo.geocode("Skipton, North Yorkshire")
    assert r.notes and "match_score=" in r.notes
