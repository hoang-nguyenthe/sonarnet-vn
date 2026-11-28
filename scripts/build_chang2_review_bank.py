"""Make a balanced, independent 200-case AIS review bank."""
from collections import defaultdict
from pathlib import Path

import numpy as np

from deep_ablation_chang2 import block_gap
from evaluate_chang2 import CLASSES, REVIEW_POSITIVE, SCENARIOS, VN, classify, dataset, degraded, write_json
from sonarnet.behavior.features import features_matrix
from sonarnet.data.geo import meters_per_degree

OUTPUT = Path(__file__).resolve().parents[1]/'reports/final/chang2/review-bank-200.json'
BANK_SEED = 2026112802
NOISE_SEED = 2026112803
MODEL_SEED = 101
PER_CELL = 10


def trained_model(seed):
    benchmark = classify(seed)
    while True:
        try:
            next(benchmark)
        except StopIteration as stop:
            return stop.value


def main():
    conditions = (*SCENARIOS, 'block_gap')
    rng = np.random.default_rng(NOISE_SEED)
    tracks = dataset(len(conditions)*PER_CELL, np.random.default_rng(BANK_SEED))
    by_class = defaultdict(list)
    for track in tracks:
        by_class[track.behaviour].append(track)

    groups = []
    for label in CLASSES:
        for i, scenario in enumerate(conditions):
            for j, track in enumerate(by_class[label][i*PER_CELL:(i+1)*PER_CELL]):
                # Select every cell before any score is available. Split each
                # cell evenly so A/B have the same reference case mix.
                observed = block_gap(track,rng) if scenario=='block_gap' else degraded(track,scenario,rng)
                groups.append((observed, scenario, 'AB'[j%2]))
    model = trained_model(MODEL_SEED)
    predictions = model.predict(features_matrix([g[0] for g in groups])[0])
    cases = []
    for i,((track,scenario,pack),hint) in enumerate(zip(groups,predictions),1):
        mlat,mlon = meters_per_degree(float(track.lats[0]))
        cases.append(dict(
            id=f'C{i:03}', pack=pack, scenario=scenario,
            elapsed_min=np.round((track.times_s-track.times_s[0])/60,1).tolist(),
            east_m=np.round((track.lons-track.lons[0])*mlon,1).tolist(),
            north_m=np.round((track.lats-track.lats[0])*mlat,1).tolist(),
            speed_kn=np.round(track.speeds_kn,1).tolist(),
            course_deg=np.round(track.courses_deg).astype(int).tolist(),
            reference_class=track.behaviour, priority=track.behaviour in REVIEW_POSITIVE,
            hint_class=VN[hint], hint_priority=hint in REVIEW_POSITIVE,
        ))
    assert len(cases)==200
    assert sum(x['priority'] for x in cases)==100
    write_json(OUTPUT,cases)
    print(f'{len(cases)} cases ({sum(x["priority"] for x in cases)} positive)')
    print(f'{sum(x["priority"]!=x["hint_priority"] for x in cases)} incorrect priority hints')


if __name__=='__main__':
    main()
