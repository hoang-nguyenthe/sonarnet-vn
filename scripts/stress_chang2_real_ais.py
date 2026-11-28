"""Repeated tests by vessel, nested model selection, and missing-report stress."""
import argparse
from dataclasses import replace
from hashlib import file_digest
from importlib.metadata import version
import json
from pathlib import Path

import numpy as np
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold, StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from evaluate_chang2_real_ais import CSV_MD5, metrics, windows
from sonarnet.behavior.classifier import BehaviorClassifier
from sonarnet.behavior.features import features_matrix

SEEDS = (101, 203, 307, 409, 503)
MODEL_NAMES = ('logistic', 'extra_trees', 'hist_gradient')
THRESHOLDS = np.arange(10, 91, 5)/100
PRECISION_FLOOR = .95


def fit_model(name, seed, X, y):
    if name == 'xgboost':
        return BehaviorClassifier(backend='xgboost', seed=seed).fit(X, y.astype(int))
    if name == 'logistic':
        estimator = make_pipeline(StandardScaler(), LogisticRegression(C=1, max_iter=1200))
    elif name == 'extra_trees':
        estimator = ExtraTreesClassifier(n_estimators=180, min_samples_leaf=3, max_features=.8,
                                         random_state=seed, n_jobs=1)
    else:
        estimator = HistGradientBoostingClassifier(max_iter=150, max_leaf_nodes=15,
                                                    l2_regularization=2, random_state=seed)
    return estimator.fit(X, y.astype(int))


def choices(X, y, groups, seed):
    splits = list(StratifiedGroupKFold(n_splits=3, shuffle=True, random_state=seed)
                  .split(X, y, groups))
    candidates = []
    for name in MODEL_NAMES:
        p = np.zeros(len(y))
        for train, valid in splits:
            assert not set(groups[train]) & set(groups[valid])
            p[valid] = fit_model(name, seed, X[train], y[train]).predict_proba(X[valid])[:, 1]
        for threshold in THRESHOLDS:
            candidates.append((name, float(threshold), metrics(y, p>=threshold)))
    macro = max(candidates, key=lambda c: (c[2]['macro_f1'], c[2]['precision']))
    eligible = [c for c in candidates if c[2]['precision'] >= PRECISION_FLOOR]
    recall = max(eligible, key=lambda c: (c[2]['recall'], c[2]['macro_f1'])) if eligible else macro
    return {'nested_macro':macro, 'nested_recall':recall}


def thin_tracks(tracks, seed, kind):
    rng = np.random.default_rng(seed)
    result = []
    for t in tracks:
        n = len(t)
        if kind == 'gap':
            start = int(rng.integers(1, n-3))
            idx = np.delete(np.arange(n), np.arange(start,start+3))
        else:
            idx = np.sort(rng.choice(n, size=(n+1)//2, replace=False))
        result.append(replace(t,times_s=t.times_s[idx],lats=t.lats[idx],lons=t.lons[idx],
                              speeds_kn=t.speeds_kn[idx],courses_deg=t.courses_deg[idx]))
    return result


def thin(tracks, seed, kind):
    return features_matrix(thin_tracks(tracks,seed,kind))[0]


def needs_augmentation(track):
    # A two-hour window is sparse if fewer than nine bins are present or if
    # at least three consecutive 10-minute bins are missing internally.
    return len(track)<9 or np.max(np.diff(track.times_s))>1800


def repeated(tracks, y, group):
    X, _ = features_matrix(tracks)
    rows, folds = [], []
    for seed in SEEDS:
        stress_tracks = {'clean':tracks,'gap':thin_tracks(tracks,seed,'gap'),
                         'half':thin_tracks(tracks,seed,'half')}
        stress = {kind:X if kind=='clean' else features_matrix(items)[0]
                  for kind,items in stress_tracks.items()}
        use_augmented = {kind:np.asarray([needs_augmentation(t) for t in items])
                         for kind,items in stress_tracks.items()}
        policies = ('xgboost','augmented','quality_routed','nested_macro','nested_recall')
        output = {name:{kind:np.zeros(len(y),bool) for kind in stress} for name in policies}
        splitter = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=seed)
        for fold, (train,test) in enumerate(splitter.split(X,y,group),1):
            assert not set(group[train]) & set(group[test])
            assert len(np.unique(y[test])) == 2
            base = fit_model('xgboost',seed,X[train],y[train])
            Xa = np.vstack([data[train] for data in stress.values()])
            ya = np.tile(y[train],len(stress))
            augmented = fit_model('xgboost',seed,Xa,ya)
            selected = choices(X[train],y[train],group[train],seed)
            models = {'xgboost':(base,.5),'augmented':(augmented,.5)}
            trained = {}
            details = dict(seed=seed,fold=fold,vessels=len(set(group[test])),windows=len(test),
                           positives=int(y[test].sum()),choices={})
            for policy,(name,threshold,inner) in selected.items():
                if name not in trained:
                    trained[name] = fit_model(name,seed,X[train],y[train])
                models[policy] = trained[name],threshold
                details['choices'][policy] = dict(model=name,threshold=threshold,
                                                   inner_oof_precision=inner['precision'],
                                                   inner_oof_recall=inner['recall'])
            for name,(model,threshold) in models.items():
                for kind,data in stress.items():
                    p = model.predict_proba(data[test])[:,1]
                    output[name][kind][test] = p>=threshold
            for kind, route in use_augmented.items():
                output['quality_routed'][kind][test] = np.where(
                    route[test], output['augmented'][kind][test], output['xgboost'][kind][test]
                )
            folds.append(details)
        for name, states in output.items():
            for kind, prediction in states.items():
                rows.append(dict(seed=seed,model=name,scenario=kind,
                                 sparse_windows=int(use_augmented[kind].sum()),**metrics(y,prediction)))
        print('Completed grouped repetition',seed,flush=True)
    return rows, folds


def duration_experiment(csv, cached):
    results = []
    for duration, minimum in ((60,5),(120,9),(240,18)):
        tracks,y,group,_,_ = cached if duration==120 else windows(csv,duration,minimum)
        X,_ = features_matrix(tracks)
        predicted = np.zeros(len(y),bool)
        for train,test in GroupKFold(n_splits=5).split(X,y,group):
            assert not set(group[train]) & set(group[test])
            model = fit_model('xgboost',101,X[train],y[train])
            predicted[test] = model.predict_proba(X[test])[:,1]>=.5
        results.append(dict(duration_minutes=duration,min_bins=minimum,windows=len(y),
                            vessels=len(set(group)),positives=int(y.sum()),**metrics(y,predicted)))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--out',type=Path,default=Path('reports/final/chang2/ais-robustness.json'))
    args = parser.parse_args()
    with args.source.open('rb') as source:
        if file_digest(source,'md5').hexdigest()!=CSV_MD5:
            parser.error('Use the MD5-verified Zenodo CSV.')
    data = windows(args.source)
    tracks,y,group,*_ = data
    summaries,folds = repeated(tracks,y,group)
    out = dict(dataset_file_md5=CSV_MD5,seeds=SEEDS,
               versions={p:version(p) for p in ('numpy','pandas','scikit-learn','xgboost')},
               inner_precision_floor=PRECISION_FLOOR,
               unique_vessels=len(set(group)),windows=len(y),
               repeated_results=summaries,fold_selection=folds,
               duration=duration_experiment(args.source,data))
    args.out.write_text(json.dumps(out,indent=2)+'\n')
    print(args.out,flush=True)


if __name__ == '__main__':
    main()
