"""Exercise production AIS smoothing and matching on mixed synthetic histories."""
import argparse
from collections import Counter
import csv
import gzip
import json
from pathlib import Path

import numpy as np

from evaluate_ais_matching import legacy
from sonarnet.config import RunConfig
from sonarnet.data.geo import meters_per_degree
from sonarnet.fusion.matching import Detection, SARAISFusion

SEED = 20261121
REPEATS = 120
BASE_UTC = 1773705600
LAT_REF, LON_REF = 12., 109.
METRES_LAT, METRES_LON = meters_per_degree(LAT_REF)
SEPARATED = ((-620., 0.), (-190., 12.), (215., 18.), (640., -14.))
SCENARIOS = {
    'mixed_quality': (SEPARATED, ('fresh', 'stale', 'missing', 'noisy')),
    'near_crossing': (((-12., -6.), (12., 7.), (-380., 220.), (440., -165.)),
                      ('fresh', 'fresh', 'fresh', 'missing')),
    'keep_two_crossing_tracks_when_separated': (
        ((-160., -10.), (160., 10.), (-430., 335.), (590., -185.)),
        ('fresh', 'fresh', 'missing', 'noisy')),
    'unlabeled_clutter_near_track': (SEPARATED, ('fresh', 'fresh', 'missing', 'fresh')),
    'sparse_one_sided': (SEPARATED, ('fresh', 'one_sided', 'one_sided', 'missing')),
    'position_bias': (((-70., -8.), (70., 8.), (-460., 40.), (520., -145.)),
                      ('biased_east', 'biased_west', 'fresh', 'missing')),
    'position_bias_beyond_guard': (((-105., -8.), (105., 8.), (-460., 40.), (520., -145.)),
                                   ('biased_east', 'biased_west', 'fresh', 'missing')),
}


def coordinates(point):
    east, north = point
    return float(LAT_REF+north/METRES_LAT), float(LON_REF+east/METRES_LON)


def build_trial(rng, scenario):
    centers, states = SCENARIOS[scenario]
    positions = np.array(centers) + rng.normal(0, 8, (4, 2))
    velocities = np.array([[5., .05], [-4.5, -.05], [2., -1.], [-2., .75]])
    raw, detections, truths = [], [], []
    for i, (pos, vel, state) in enumerate(zip(positions, velocities, states)):
        ident = 100+i
        detections.append(coordinates(pos + rng.normal(0, 7, 2)))
        truths.append(ident)
        if state == 'missing':
            continue
        times = {
            'stale': (-470, -402, -365, -321, -271),
            'one_sided': (-333, -281, -229, -163, -121),
        }.get(state, (-136, -79, -38, 37, 84, 144))
        shift = (0., 0.)
        if state.startswith('biased_'):
            bound = (208., 242.) if scenario == 'position_bias_beyond_guard' else (128., 185.)
            offset = rng.uniform(*bound)
            shift = (offset if state == 'biased_east' else -offset, 0.)
        uncertainty = 220 if state == 'noisy' else 12
        for dt in times:
            jittered = dt + int(rng.integers(-12, 13))
            lat, lon = coordinates(pos + vel*jittered + shift + rng.normal(0, uncertainty, 2))
            raw.append(dict(mmsi=ident, timestamp=BASE_UTC+jittered, lat=lat, lon=lon))
    if scenario == 'unlabeled_clutter_near_track':
        detections.append(coordinates(positions[0] + [rng.uniform(12, 48), rng.uniform(-15, 15)]))
        truths.append(None)
    return raw, detections, truths


def count_trial(counts, matches, truth):
    for i, actual in enumerate(truth):
        proposed = matches.get(i)
        counts['points'] += 1
        counts['links_correct'] += proposed == actual and actual is not None
        counts['links_wrong'] += proposed is not None and actual is not None and proposed != actual
        counts['links_to_clutter'] += proposed is not None and actual is None
        counts['abstained_on_target'] += proposed is None and actual is not None
        counts['clutter_unmatched'] += proposed is None and actual is None


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    rng = np.random.default_rng(SEED)
    cfg = RunConfig()
    cfg.fusion.preserve_proposed_pair = False
    fusion = SARAISFusion(cfg)
    previous_cfg = RunConfig()
    previous_cfg.fusion.systematic_bias_guard_m = 0.
    previous_cfg.fusion.preserve_proposed_pair = False
    previous_fusion = SARAISFusion(previous_cfg)
    summary, examples = [], []
    for scenario in SCENARIOS:
        counts = {name:Counter() for name in ('distance_only', 'quality_gated_previous', 'quality_gated')}
        for i in range(REPEATS):
            raw, positions, truth = build_trial(rng, scenario)
            estimates = fusion.interpolate_ais(raw, BASE_UTC)
            detections = [Detection(k, lat, lon, 80., 20., (0, 0, 8, 2))
                          for k, (lat, lon) in enumerate(positions)]
            reference = legacy(detections, estimates)
            previous = previous_fusion.match(detections, estimates)[0]
            result, distances, reasons = fusion.match_with_reasons(detections, estimates)
            count_trial(counts['distance_only'], reference, truth)
            count_trial(counts['quality_gated_previous'], previous, truth)
            count_trial(counts['quality_gated'], result, truth)
            examples.append(dict(scenario=scenario, trial=i, raw_records=raw, sar_lat_lon=positions,
                truth=truth, estimates={ident:dict(pos=[e.lat, e.lon], sigma_m=e.position_sigma_m,
                 age_s=e.gap_to_nearest_s) for ident,e in estimates.items()}, distance_only=reference,
                quality_gated_previous=previous,
                quality_gated=result, reasons=reasons, distances_m=distances))
        for method, values in counts.items():
            summary.append(dict(scenario=scenario, method=method, **values))
    with (output/'summary.csv').open('w', newline='') as file:
        writer=csv.DictWriter(file, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    with gzip.open(output/'cases.json.gz', 'wt') as file:
        json.dump(dict(dataset_type='synthetic_trajectories', seed=SEED, capture_time=BASE_UTC,
                       thresholds=vars(cfg.fusion), cases=examples), file, allow_nan=False)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    run(parser.parse_args().output)
