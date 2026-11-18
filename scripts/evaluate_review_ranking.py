"""Learn which extra SAR proposals to review, and evaluate on fresh acquisitions."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path

import numpy as np
from PIL import Image
from shapely import intersects_xy, orient_polygons
from shapely.geometry import GeometryCollection, box
from shapely.ops import unary_union
from sklearn.base import clone
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
import torch
from ultralytics import YOLO

from land_mask import get_mask
from score_vn_reference_rtc import (
    BUDGET, GEOD, ROOT, geographic_distances, digest, infer_map, infer_slc, matched, refill, valid_water,
)
from prepare_opensar_geo import unique_water_support
from refresh_detailed_scan import allowed_pixels
from sonarnet.data.planetary import gray_rgba

MATCH_DISTANCE = 100
FEATURES = (
    'map_score', 'slc_score', 'radar_peak_db', 'radar_contrast_db',
    'ring_noise_db', 'coastal', 'rtc_valid_fraction',
)
MODELS = {
    'linear': make_pipeline(StandardScaler(), LogisticRegression(max_iter=400, class_weight='balanced', C=.2)),
    'boosting': HistGradientBoostingClassifier(max_iter=65, max_leaf_nodes=8, max_depth=3, min_samples_leaf=20,
                                              learning_rate=.12, random_state=20261118),
}


def local_db(db, x, y):
    y0, y1, x0, x1 = max(0,y-12), y+13, max(0,x-12), x+13
    neighborhood = db[y0:y1, x0:x1].copy()
    target = db[max(0,y-2):y+3, max(0,x-2):x+3]
    neighborhood[max(0,y-y0-3):y-y0+4, max(0,x-x0-3):x-x0+4] = np.nan
    target = target[np.isfinite(target)]
    background = neighborhood[np.isfinite(neighborhood)]
    if not target.size or not background.size:
        return -38., 0., 0.
    peak = float(np.percentile(target,85))
    q1, median, q3 = np.percentile(background,(25,50,75))
    return peak, peak-float(median), float(q3-q1)


def method_scores(candidates, other, max_distance=60.):
    dist = geographic_distances(candidates, [p[:2] for p in other])
    scores = np.array([p[2] for p in other])
    if not len(scores):
        return np.zeros(len(candidates))
    return np.where(dist <= max_distance, scores[None,:], 0.).max(axis=1)


def crop_features(raw, support, bounds, shapes, original, slc):
    all_candidates = [list(row) for row in (*original,*slc)]
    if not all_candidates:
        return []
    xy = np.asarray(all_candidates)
    in_support = intersects_xy(support,xy[:,0],xy[:,1])
    candidates = [row for row,inside in zip(all_candidates,in_support) if inside]
    map_scores = method_scores(candidates,original)
    slc_scores = method_scores(candidates,slc)
    w,s,e,n = bounds
    wet = raw > 0
    db = np.full(raw.shape,np.nan,dtype=float)
    db[wet] = 10*np.log10(raw[wet])
    coverage = float(wet.mean())
    features = []
    for (lon,lat,_), m, v in zip(candidates,map_scores,slc_scores):
        x = int(np.clip((lon-w)/(e-w)*raw.shape[1],0,raw.shape[1]-1))
        y = int(np.clip((n-lat)/(n-s)*raw.shape[0],0,raw.shape[0]-1))
        stats = local_db(db,x,y)
        features.append([float(lon),float(lat),float(m),float(v),*stats,
                         float(intersects_xy(shapes['coast'],lon,lat)),coverage])
    return features


def collect(cohort, dirname, bounds, baseline, slc, mask):
    region = box(*bounds[cohort['region']])
    meta, shapes = mask
    only_land = (meta,{**shapes,'coast':GeometryCollection()})
    windows = sorted(cohort['windows'],key=lambda item:item['window_id'])
    crops = []
    for window in windows:
        path = dirname/window['file']
        if digest(path) != window['sha256']:
            raise ValueError('RTC input checksum changed')
        with np.load(path,allow_pickle=False) as archive:
            gamma = archive['gamma0']
        geo = valid_water(gamma,window['bbox'],region,shapes['land'])
        crops.append((window,gamma,geo))
    if not crops:
        return None
    supports = list(unique_water_support([geo for _,_,geo in crops]))
    points = np.array(cohort['points']).reshape(-1,2)
    all_support = unary_union(supports)
    truth = points[intersects_xy(all_support,points[:,0],points[:,1])].tolist()
    if not truth:
        return None
    area = sum(abs(GEOD.geometry_area_perimeter(orient_polygons(geo))[0]) for geo in supports)/1e6
    incumbent, baseline_low, candidates = [], [], []
    for (window,gamma,_), support in zip(crops,supports):
        if support.is_empty:
            continue
        bbox=window['bbox']
        rgba=gray_rgba(np.ma.masked_less_equal(gamma,0))
        image=Image.fromarray(rgba)
        def scored(pool):
            return [[float(a),float(b),float(c)] for a,b,c in pool if intersects_xy(support,a,b)]
        incumbent += scored(infer_map(baseline,image,bbox,.35,mask))
        baseline_low += scored(infer_map(baseline,image,bbox,.05,mask))
        map_pool = infer_map(baseline,image,bbox,.05,only_land)
        allowed, _ = allowed_pixels(image,bbox,only_land)
        gray = rgba[:,:,0].copy()
        gray[~allowed] = 0
        portable = infer_slc(slc,gray,bbox,False,.005)
        candidates += crop_features(gamma,support,bbox,shapes,map_pool,portable)
    return dict(scene=cohort['scene'],region=cohort['region'],truth=truth,
                candidates=candidates,incumbent=incumbent,baseline_low=baseline_low,
                windows=len(windows),missing_windows=len(cohort['failed_windows']),
                budget=int(BUDGET*area),area_km2=area)


def fit(models, scenes):
    all_x, all_y = [], []
    for scene in scenes:
        features = np.asarray(scene['candidates']).reshape(-1,len(FEATURES)+2)
        if not len(features):
            continue
        proposals = np.c_[features[:,:2],np.zeros(len(features))]
        labels = geographic_distances(proposals,scene['truth']).min(axis=1) <= MATCH_DISTANCE
        all_x.append(features[:,2:])
        all_y.append(labels)
    x, y = np.concatenate(all_x), np.concatenate(all_y)
    if len(np.unique(y)) != 2:
        raise ValueError('Need hits and unmatched candidates in fitting acquisitions')
    return {name:clone(model).fit(x,y) for name,model in models.items()}


def measure(case, models, *, match_count=False):
    sorted_rows = lambda rows:sorted(rows,key=lambda row:-row[2])
    base=sorted_rows(case['incumbent'])
    relaxed=sorted_rows(case['baseline_low'])
    limit = min(case['budget'],len(base)) if match_count else case['budget']
    summary={
        'map_default': matched(base[:limit],case['truth'],(MATCH_DISTANCE,))[MATCH_DISTANCE],
        'map_lower_threshold': matched(relaxed[:limit],case['truth'],(MATCH_DISTANCE,))[MATCH_DISTANCE],
    }
    rows=np.asarray(case['candidates']).reshape(-1,len(FEATURES)+2)
    for name,model in models.items():
        if len(rows):
            p = model.predict_proba(rows[:,2:])[:,1]
            prioritized=sorted_rows(np.c_[rows[:,:2],p].tolist())
        else:
            prioritized=[]
        rank = refill([],prioritized,limit)
        protected=refill(base,prioritized,limit)
        summary[f'{name}_rank_only']=matched(rank,case['truth'],(MATCH_DISTANCE,))[MATCH_DISTANCE]
        summary[f'{name}_preserve_map']=matched(protected,case['truth'],(MATCH_DISTANCE,))[MATCH_DISTANCE]
    return summary


def save(path, obj):
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(obj,ensure_ascii=False,indent=2))
    temporary.replace(path)


def cache_group(source, out, baseline, slc, mask, exclude_dates=()):
    dirname=source/'rtc-512'
    data=json.loads((dirname/'manifest.json').read_text())
    bounds=json.loads((source/'screened.json').read_text())['bounds']
    results=[]
    for c in data['cohorts']:
        if c['scene'].split('_')[4][:8] in exclude_dates:
            continue
        case=collect(c,dirname,bounds,baseline,slc,mask)
        if case:
            results.append(case)
            with gzip.open(out,'wt') as progress:
                json.dump(results,progress)
            print(case['region'],case['scene'].split('_')[4],len(case['truth']),'labels',
                  len(case['candidates']),'proposals',flush=True)
    with gzip.open(out,'wt') as f:
        json.dump(results,f)
    return results


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--development',required=True,type=Path)
    p.add_argument('--fresh',required=True,type=Path)
    p.add_argument('--out',required=True,type=Path)
    args=p.parse_args()
    torch.set_num_threads(4)
    directory=args.out
    directory.mkdir(exist_ok=False)
    weights=ROOT/'assets/models'
    map_weights=weights/'sonarnet_baseline.pt'
    slc_weights=weights/'sonarnet_slc_vv_20261118.pt'
    mask=get_mask(ROOT)
    baseline,slc=YOLO(str(map_weights)),YOLO(str(slc_weights))
    training_source=args.development/'rtc-512/manifest.json'
    test_source=args.fresh/'rtc-512/manifest.json'
    save(directory/'protocol.json',dict(
        created_utc=datetime.now(timezone.utc).isoformat(),
        code_sha256=digest(Path(__file__)),features=FEATURES,models=list(MODELS),
        map_weights_sha256=digest(map_weights),slc_weights_sha256=digest(slc_weights),
        development_manifest_sha256=digest(training_source),fresh_manifest_sha256=digest(test_source),
        rule='Hold out one full acquisition at a time during development. Pick maximum summed hits at same cap; ties prefer fewer unmatched.',
        review_budget_per_km2=BUDGET,matching_distance_m=MATCH_DISTANCE,
        label_scope='Matches to Ai2 labels, not a truth claim about identities or unknown contacts.',
        independence='No test candidates scored until the policy is locked; acquisitions on the same UTC day as development are excluded.',
    ))
    train=cache_group(args.development,directory/'development_features.json.gz',baseline,slc,mask)
    if len(train)<3:
        raise ValueError('Need at least three labelled development acquisitions')
    folds=[]
    for idx,case in enumerate(train):
        models=fit(MODELS,[r for k,r in enumerate(train) if k!=idx])
        folds.append(dict(scene=case['scene'],methods=measure(case,models)))
    names=[name for name in folds[0]['methods'] if name not in ('map_default','map_lower_threshold')]
    def key(name):
        return (sum(row['methods'][name]['matched'] for row in folds),
                -sum(row['methods'][name]['unmatched'] for row in folds))
    selected=max(names,key=key)
    save(directory/'selected.json',dict(locked_utc=datetime.now(timezone.utc).isoformat(),
                                      method=selected,development_folds=folds))
    print('Locked',selected,key(selected),flush=True)
    final=fit(MODELS,train)
    days={r['scene'].split('_')[4][:8] for r in train}
    fresh=cache_group(args.fresh,directory/'fresh_features.json.gz',baseline,slc,mask,exclude_dates=days)
    if not fresh:
        raise ValueError('No fresh labelled acquisition could be scored')
    data=[]
    for case in fresh:
        data.append(dict(
            scene=case['scene'],region=case['region'],area_km2=case['area_km2'],windows=case['windows'],
            missing_windows=case['missing_windows'],budget=case['budget'],
            methods=measure(case,final), matched_review_count=measure(case,final,match_count=True),
        ))
    save(directory/'results.json',dict(selected=selected,test=data))
    for name in data[0]['methods']:
        print(name, sum(r['methods'][name]['matched'] for r in data),'matched /',
              sum(r['methods'][name]['predictions'] for r in data),'reviewed',flush=True)


if __name__=='__main__':
    main()
