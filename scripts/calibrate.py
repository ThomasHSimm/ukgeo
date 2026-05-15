"""
Calibrate ScoringWeights against user-supplied labelled test data.

Usage:
    python scripts/calibrate.py --test data/my_test_locations.csv

CSV format (no header required beyond these columns):
    input, lat, lon
    "M62 Junction 26", 53.7054, -1.8016
    "LS1 1BA", 53.7997, -1.5492
    ...

Writes best-fit weights to config/weights.yaml.
"""

import argparse
import csv
import dataclasses
import itertools
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from ukgeo.pipeline import Geocoder, _haversine
from ukgeo.level2_ner import ScoringWeights

CONFIG_DIR = Path(__file__).parent.parent / "config"
WEIGHTS_OUT = CONFIG_DIR / "weights.yaml"

# Parameter search space — coarse grid, refine manually after
SEARCH_GRID = {
    "county_context_match":   [3.0, 5.0, 7.0],
    "district_context_match": [2.0, 3.0, 5.0],
    "city_context_match":     [1.0, 2.0, 4.0],
    "road_context_match":     [3.0, 5.0, 7.0],
    "junction_match":         [6.0, 8.0, 10.0],
    "admin_contradiction":    [-6.0, -4.0, -2.0],
    "ambiguous_token":        [-2.0, -1.0, -0.5],
}


def load_test_data(path: Path) -> list[dict]:
    rows = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                "input": row["input"].strip(),
                "lat": float(row["lat"]),
                "lon": float(row["lon"]),
            })
    print(f"Loaded {len(rows)} test cases from {path}")
    return rows


def evaluate(geo: Geocoder, test_data: list[dict]) -> float:
    """Return mean distance error in metres (lower = better). Unresolved = 50km penalty."""
    PENALTY = 50_000
    errors = []
    for item in test_data:
        r = geo.geocode(item["input"])
        if r.resolved:
            errors.append(_haversine(item["lat"], item["lon"], r.lat, r.lon))
        else:
            errors.append(PENALTY)
    return sum(errors) / len(errors) if errors else PENALTY


def calibrate(test_data: list[dict], n_trials: int = 200):
    import random
    import yaml

    best_score = float("inf")
    best_weights = ScoringWeights()

    # Start with defaults
    geo = Geocoder(weights=best_weights)
    best_score = evaluate(geo, test_data)
    print(f"Default weights score: {best_score:.0f} m mean error")

    # Random search over grid combinations (full grid search is expensive)
    keys = list(SEARCH_GRID.keys())
    combos = list(itertools.product(*[SEARCH_GRID[k] for k in keys]))
    random.shuffle(combos)
    combos = combos[:n_trials]

    print(f"Searching {len(combos)} weight combinations ...")
    for i, combo in enumerate(combos):
        params = dict(zip(keys, combo))
        w = ScoringWeights(**{**dataclasses.asdict(best_weights), **params})
        geo = Geocoder(weights=w)
        score = evaluate(geo, test_data)
        if score < best_score:
            best_score = score
            best_weights = w
            print(f"  [{i+1}/{len(combos)}] New best: {score:.0f} m — {params}")

    print(f"\nBest mean error: {best_score:.0f} m")
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(WEIGHTS_OUT, "w") as f:
        import yaml
        yaml.dump(dataclasses.asdict(best_weights), f)
    print(f"Weights saved to {WEIGHTS_OUT}")
    return best_weights


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", required=True, help="Path to labelled CSV test data")
    parser.add_argument("--trials", type=int, default=200, help="Number of random search trials")
    args = parser.parse_args()

    test_data = load_test_data(Path(args.test))
    calibrate(test_data, n_trials=args.trials)
