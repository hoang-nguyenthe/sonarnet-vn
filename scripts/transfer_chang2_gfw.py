"""Transfer AIS behavior models between Denmark and Global Fishing Watch cohorts."""
import argparse
from dataclasses import replace
from hashlib import file_digest
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

from evaluate_chang2 import REVIEW_POSITIVE, SEEDS
from evaluate_chang2_real_ais import CSV_MD5, frozen_model, grouped_windows, metrics, windows
from sonarnet.behavior.features import features_matrix
from sonarnet.data.geo import meters_per_degree
from sonarnet.data.tracks import KNOT_TO_MS
from stress_chang2_real_ais import fit_model, thin

GFW_COMMIT = '58815d23bb0924d03fc4cad99953613e3c36d28f'
GFW_SOURCE = 'https://github.com/GlobalFishingWatch/training-data/tree/'+GFW_COMMIT
FILES = {
    'purse_seines': ('gfw-purse-seines.npz', 'pybossa_project_3_Purse_seines.measures.labels.npz',
                     '65f08ef20383adb3fc78d72793c192ecff3e63ca6b930e140ca60cf70d2f5f49'),
    'longlines': ('gfw-longlines.npz', 'kristina_longliner_Drifting_longlines.measures.labels.npz',
                  'e322bd8703186accabeec5fa10ccb18f66cd7041e7519012e359a6b01216b262'),
    'trawlers': ('gfw-trawlers.npz', 'kristina_trawl_Trawlers.measures.labels.npz',
                 'b1aba8244c3af7abaa49ab0fda39d060e3d907f7f9591f9cf79af67c9d55db20'),
}


def load_gfw(directory, filename, checksum):
    path = directory/filename
    with path.open('rb') as source:
        if file_digest(source,'sha256').hexdigest()!=checksum:
            raise ValueError(f'Git LFS SHA-256 mismatch for {filename}')
    with np.load(path,allow_pickle=False) as data:
        records = data['x']
    df = pd.DataFrame({
        'id':np.char.add(records['mmsi'].astype(np.int64).astype(str),'-0'),
        't':pd.to_datetime(records['timestamp'],unit='s',utc=True),
        'latitude':records['lat'], 'longitude':records['lon'],
        'bearing':records['course'], 'euc_speed':records['speed'], 'positive':records['is_fishing'],
    })
    valid = df[df.positive.between(0,1)].drop_duplicates()
    return valid, len(df), df.id.nunique()


def shared_kinematics(tracks):
    adjusted = []
    for t in tracks:
        lat_m, lon_m = meters_per_degree(float(np.mean(t.lats)))
        east, north = np.diff(t.lons)*lon_m, np.diff(t.lats)*lat_m
        speed = np.clip(np.hypot(east,north)/np.diff(t.times_s)/KNOT_TO_MS,0,40)
        course = np.degrees(np.arctan2(east,north))%360
        adjusted.append(replace(t,speeds_kn=np.r_[speed[0],speed],
                                courses_deg=np.r_[course[0],course]))
    return features_matrix(adjusted)[0]


def equal_class_indices(y, seed):
    rng = np.random.default_rng(seed)
    indices = [np.flatnonzero(y==label) for label in (False,True)]
    n = max(map(len,indices))
    return np.concatenate([rng.choice(i,n,replace=len(i)<n) for i in indices])


def scores(y, model_predictions):
    return {model:metrics(y,prediction) for model,prediction in model_predictions.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('zenodo_csv',type=Path)
    parser.add_argument('gfw_directory',type=Path)
    parser.add_argument('--out',type=Path,default=Path('reports/final/chang2/gfw-transfer.json'))
    args = parser.parse_args()
    with args.zenodo_csv.open('rb') as source:
        if file_digest(source,'md5').hexdigest()!=CSV_MD5:
            parser.error('Use the MD5-verified Zenodo CSV.')
    tracks, y_dk, _g_dk, _stable, _audit = windows(args.zenodo_csv)
    X_dk, _ = features_matrix(tracks)
    denmark = fit_model('xgboost',101,X_dk,y_dk)
    K_dk = shared_kinematics(tracks)
    aligned = fit_model('xgboost',101,K_dk,y_dk)
    balanced = equal_class_indices(y_dk,101)
    aligned_balanced = fit_model('xgboost',101,K_dk[balanced],y_dk[balanced])
    native_balanced = fit_model('xgboost',101,X_dk[balanced],y_dk[balanced])
    augmented = fit_model('xgboost',101,np.vstack([X_dk,thin(tracks,101,'gap'),thin(tracks,101,'half')]),
                          np.tile(y_dk,3))
    dataset = {gear:load_gfw(args.gfw_directory,spec[0],spec[2]) for gear,spec in FILES.items()}
    frozen = {seed:frozen_model(seed) for seed in SEEDS}
    suites = {}
    for min_bins in (9,5):
        cohorts, X, K, y, groups, worn = {}, [], [], [], [], []
        for gear,(df, messages, vessels) in dataset.items():
            ts, yes, group, _, audit = grouped_windows(df,minimum_bins=min_bins)
            matrix,_ = features_matrix(ts)
            X.append(matrix)
            K.append(shared_kinematics(ts))
            y.append(yes)
            groups.append(group)
            worn.extend([gear]*len(yes))
            cohorts[gear] = dict(windows=len(yes),positive=int(yes.sum()),scored_vessels=len(set(group)),
                                 input_vessels=vessels,input_rows=messages,
                                 deduplicated_rows=len(df),**audit)
        X, y, groups, gears = np.vstack(X), np.concatenate(y), np.concatenate(groups), np.array(worn)
        K = np.vstack(K)
        pred = np.zeros(len(y),bool)
        folds = []
        for n,(train,test) in enumerate(GroupKFold(n_splits=5).split(X,y,groups),1):
            assert not set(groups[train]) & set(groups[test])
            assert len(np.unique(y[test]))==2
            m = fit_model('xgboost',101,X[train],y[train])
            pred[test] = m.predict_proba(X[test])[:,1]>=.5
            folds.append(dict(fold=n,windows=len(test),test_vessels=len(set(groups[test])),
                              **metrics(y[test],pred[test])))
        methods = {'denmark_to_gfw':denmark.predict_proba(X)[:,1]>=.5,
                   'denmark_augmented_to_gfw':augmented.predict_proba(X)[:,1]>=.5,
                   'gfw_held_vessel':pred,
                   'denmark_aligned':aligned.predict_proba(K)[:,1]>=.5,
                   'denmark_aligned_balanced':aligned_balanced.predict_proba(K)[:,1]>=.5,
                   'denmark_native_balanced':native_balanced.predict_proba(X)[:,1]>=.5}
        methods.update({f'synthetic_only_{seed}':np.isin(model.predict(X),sorted(REVIEW_POSITIVE))
                        for seed,model in frozen.items()})
        methods['gfw_held_gear_multisource'] = np.zeros(len(y),bool)
        for gear in cohorts:
            test = gears==gear
            train = ~test & ~np.isin(groups,groups[test])
            assert not set(groups[train]) & set(groups[test])
            # Keep the test gear entirely out of training. Recompute speed and
            # course identically across sources before pooling training windows.
            combined = fit_model('xgboost',101,np.vstack([K_dk,K[train]]),
                                 np.concatenate([y_dk,y[train]]))
            methods['gfw_held_gear_multisource'][test] = combined.predict_proba(K[test])[:,1]>=.5
        for gear,audit in cohorts.items():
            keep = gears==gear
            audit['models'] = scores(y[keep],{name:p[keep] for name,p in methods.items()})
        pooled = fit_model('xgboost',101,X,y)
        back = pooled.predict_proba(X_dk)[:,1]>=.5
        suite = dict(min_bins=min_bins,windows=len(y),positive=int(y.sum()),vessels=len(set(groups)),
                     cohorts=cohorts,models=scores(y,methods),gfw_folds=folds,
                     gfw_to_denmark=metrics(y_dk,back))
        suites[str(min_bins)] = suite
        print(min_bins,len(y),'windows',len(set(groups)),'vessels',flush=True)
    release = {name:dict(file=fields[1],sha256=fields[2]) for name,fields in FILES.items()}
    args.out.write_text(json.dumps(dict(source=GFW_SOURCE,license='CC BY 4.0',release=release,
                                        suites=suites),indent=2)+'\n')
    print(args.out,flush=True)


if __name__=='__main__':
    main()
