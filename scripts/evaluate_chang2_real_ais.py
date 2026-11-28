"""External AIS benchmark and vessel-held-out binary behavior experiment."""
import argparse
from hashlib import file_digest
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

from evaluate_chang2 import REVIEW_POSITIVE, SEEDS, classify
from sonarnet.behavior.classifier import BehaviorClassifier
from sonarnet.behavior.features import FEATURE_NAMES, features_matrix
from sonarnet.data.tracks import Track

DATASET = 'https://doi.org/10.5281/zenodo.7283281'
CSV_MD5 = 'c5953081f511e228b19e46ca85fe304f'
WINDOW_MINUTES = 120
BIN_MINUTES = 10
MIN_BINS = 9


def windows(path, window_minutes=WINDOW_MINUTES, minimum_bins=MIN_BINS):
    raw = pd.read_csv(path, usecols=[
        'id', 't', 'longitude', 'latitude', 'bearing', 'euc_speed', 'label'
    ])
    raw['t'] = pd.to_datetime(raw['t'], utc=True)
    raw['positive'] = raw['label'].str.endswith('-fishing').astype(float)
    masks = raw['label'].str.endswith(('-fishing', '-sailing'), na=False)
    tracks, truth, vessel, stable, audit = grouped_windows(
        raw[masks], window_minutes, minimum_bins
    )
    audit['messages'] = len(raw)
    audit['manual_label_counts'] = {str(k): int(v) for k, v in raw['label'].value_counts().items()}
    return tracks, truth, vessel, stable, audit


def grouped_windows(raw, window_minutes=WINDOW_MINUTES, minimum_bins=MIN_BINS):
    kinematic = raw['euc_speed'].between(0, 40) & raw['bearing'].between(0, 360)
    valid = raw[kinematic & raw['latitude'].between(-90, 90)
                & raw['longitude'].between(-180, 180)].copy()
    valid['window'] = valid['t'].dt.floor(f'{window_minutes}min')
    valid['bin'] = valid['t'].dt.floor(f'{BIN_MINUTES}min')
    direction = np.radians(valid['bearing'])
    valid['sin'], valid['cos'] = np.sin(direction), np.cos(direction)
    bins = valid.groupby(['id', 'window', 'bin'], sort=True).agg(
        lat=('latitude', 'median'), lon=('longitude', 'median'),
        speed=('euc_speed', 'median'), sin=('sin', 'mean'), cos=('cos', 'mean'),
        positive_share=('positive', 'mean'),
    )
    tracks, truth, vessel, stable = [], [], [], []
    sparse = tied = 0
    for (trip, _), block in bins.groupby(level=['id', 'window'], sort=True):
        if len(block) < minimum_bins:
            sparse += 1
            continue
        vote = (block.positive_share > .5).sum() - (block.positive_share < .5).sum()
        if vote == 0:
            tied += 1
            continue
        truth.append(vote > 0)
        stable.append(max((block.positive_share > .5).mean(),
                          (block.positive_share < .5).mean()) >= .8)
        vessel.append(trip.rsplit('-', 1)[0])
        time = block.index.get_level_values('bin')
        lons = block.lon.to_numpy()
        if np.any(np.abs(np.diff(lons)) > 180):
            lons = np.degrees(np.unwrap(np.radians(lons)))
        tracks.append(Track(
            mmsi=0, behaviour='unlabeled', times_s=(time - time[0]).total_seconds().to_numpy(),
            lats=block.lat.to_numpy(), lons=lons,
            speeds_kn=block.speed.to_numpy(),
            courses_deg=np.degrees(np.arctan2(block.sin, block.cos)).to_numpy() % 360,
        ))
    audit = {
        'messages': len(raw), 'valid_messages': len(valid),
        'trips': raw['id'].nunique(), 'start_utc': raw['t'].min().isoformat(),
        'end_utc': raw['t'].max().isoformat(), 'excluded_sparse_windows': sparse,
        'excluded_tied_windows': tied, 'window_minutes': window_minutes,
        'bin_minutes': BIN_MINUTES, 'minimum_bins': minimum_bins,
    }
    return tracks, np.asarray(truth), np.asarray(vessel), np.asarray(stable), audit


def metrics(y, pred):
    tp = int((y & pred).sum())
    fn = int((y & ~pred).sum())
    fp = int((~y & pred).sum())
    tn = int((~y & ~pred).sum())

    def divide(a, b):
        return a / b if b else 0.

    return dict(tn=tn, fp=fp, fn=fn, tp=tp,
                recall=divide(tp, tp+fn), precision=divide(tp, tp+fp),
                macro_f1=(divide(2*tp, 2*tp+fp+fn) + divide(2*tn, 2*tn+fp+fn))/2)


def frozen_model(seed):
    trial = classify(seed)
    while True:
        try:
            next(trial)
        except StopIteration as result:
            return result.value


def vessel_bootstrap(y, baseline, candidate, groups):
    indices = [np.flatnonzero(groups == g) for g in np.unique(groups)]
    rng = np.random.default_rng(8201)
    recall, macro_f1 = [], []
    for _ in range(2000):
        idx = np.concatenate([indices[i] for i in rng.integers(len(indices), size=len(indices))])
        if not (y[idx].any() and (~y[idx]).any()):
            continue
        a, b = metrics(y[idx], baseline[idx]), metrics(y[idx], candidate[idx])
        recall.append(b['recall']-a['recall'])
        macro_f1.append(b['macro_f1']-a['macro_f1'])
    return {'macro_f1_delta_ci': np.percentile(macro_f1, [2.5, 97.5]).tolist(),
            'recall_delta_ci': np.percentile(recall, [2.5, 97.5]).tolist(),
            'valid_bootstrap_draws': len(recall)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--out', type=Path, default=Path('reports/final/chang2/real-ais.json'))
    args = parser.parse_args()
    with args.source.open('rb') as source:
        checksum = file_digest(source, 'md5').hexdigest()
    if checksum != CSV_MD5:
        parser.error('CSV MD5 differs from the official Zenodo release.')
    tracks, y, groups, stable, audit = windows(args.source)
    print(f'{len(tracks)} windows · {len(set(groups))} vessels · {y.sum()} positives', flush=True)
    X, _ = features_matrix(tracks)
    majority, observed_speed, observed_speed_history, observed_history = (
        np.zeros(len(y), bool) for _ in range(4)
    )
    speed = np.array([[t.speeds_kn[-1]] for t in tracks], dtype=np.float32)
    speed_features = [i for i, name in enumerate(FEATURE_NAMES)
                      if name.startswith(('speed_', 'accel_'))
                      or name in ('stop_fraction', 'moving_fraction', 'n_points')]
    labels = np.where(y, 'fishing', 'sailing')
    folds = []
    for fold, (train, test) in enumerate(GroupKFold(n_splits=5).split(X, y, groups), 1):
        assert not set(groups[train]) & set(groups[test])
        assert len(np.unique(y[train])) == 2 and len(np.unique(y[test])) == 2
        majority[test] = y[train].mean() > .5
        row = dict(fold=fold, test_vessels=len(set(groups[test])), test_windows=len(test),
                   test_positives=int(y[test].sum()))
        for name, data, pred in (('speed_snapshot', speed, observed_speed),
                                 ('speed_history', X[:, speed_features], observed_speed_history),
                                 ('history', X, observed_history)):
            model = BehaviorClassifier(backend='xgboost', seed=101).fit(data[train], labels[train])
            pred[test] = model.predict(data[test]) == 'fishing'
            row[name] = metrics(y[test], pred[test])
        folds.append(row)

    frozen = []
    for seed in SEEDS:
        model = frozen_model(seed)
        pred = np.isin(model.predict(X), sorted(REVIEW_POSITIVE))
        frozen.append({'seed': seed, **metrics(y, pred)})
    results = {
        'dataset': DATASET, 'license': 'CC BY 4.0', 'source_csv_md5': checksum,
        'scope': 'Manually annotated Danish AIS; fishing vs sailing; no local field survey.',
        'coverage': {**audit, 'scored_windows': len(y), 'scored_vessels': len(set(groups)),
                     'fishing_windows': int(y.sum()), 'sailing_windows': int((~y).sum()),
                     'stable_windows': int(stable.sum()), 'mixed_windows': int((~stable).sum())},
        'synthetic_only': frozen,
        'vessel_held_out': {
            'training_majority': metrics(y, majority), 'speed_snapshot': metrics(y, observed_speed),
            'speed_history': metrics(y, observed_speed_history),
            'history': metrics(y, observed_history),
            'history_on_stable': metrics(y[stable], observed_history[stable]),
            'history_on_mixed': metrics(y[~stable], observed_history[~stable]),
            'folds': folds, 'features': FEATURE_NAMES,
            'paired_vessel_bootstrap': vessel_bootstrap(y, observed_speed_history, observed_history, groups),
        },
    }
    args.out.write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results['coverage'], ensure_ascii=False), flush=True)
    print(json.dumps({name: results['vessel_held_out'][name] for name in ('speed_snapshot', 'history')}))


if __name__ == '__main__':
    main()
