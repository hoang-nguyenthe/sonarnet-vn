"""Compare single/dual-polarization SAR ranking at exactly the baseline review count."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path

import numpy as np
from scipy.special import logit
from shapely import intersects_xy
from shapely.geometry import box
from shapely.ops import unary_union
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from evaluate_review_ranking import local_db, MATCH_DISTANCE
from land_mask import get_mask
from prepare_opensar_geo import unique_water_support
from score_vn_reference_rtc import ROOT, geographic_distances, digest, matched, valid_water

ALPHAS = (.125, .25, .5, 1.)
COLUMNS = {'vv': slice(3, 7), 'vv_vh': slice(3, 11)}


def db_image(values):
    valid = values > 0
    image = np.full(values.shape,np.nan)
    image[valid] = 10*np.log10(values[valid])
    return image


def checked_channel(folder, entry):
    file = folder / entry['file']
    if digest(file) != entry['sha256']:
        raise ValueError('RTC chip differs from manifest')
    with np.load(file, allow_pickle=False) as source:
        return source['gamma0']


def summarize(candidates, bbox, support, vv, vh):
    if support.is_empty or not len(candidates):
        return np.empty((0,11))
    coverage = np.isfinite(vv) & np.isfinite(vh)
    coords = np.array(candidates, dtype=float)
    coords = coords[intersects_xy(support,coords[:,0],coords[:,1])]
    west,south,east,north = bbox
    size_y,size_x = vv.shape
    rows = []
    for lon,lat,conf in coords:
        col = int(np.clip((lon-west)/(east-west)*size_x,0,size_x-1))
        row = int(np.clip((north-lat)/(north-south)*size_y,0,size_y-1))
        v = local_db(vv,col,row)
        h = local_db(vh,col,row)
        rows.append((lon,lat,conf,*v,float(np.isfinite(vv[row,col])),
                     *h,float(coverage[row,col])))
    return np.array(rows).reshape(-1,11)


def channel_index(root, band):
    folder = root / ('rtc-512' if band == 'vv' else 'rtc-vh-512')
    manifest = folder / 'manifest.json'
    cohorts = {c['scene']:c for c in json.loads(manifest.read_text())['cohorts']}
    return folder,manifest,cohorts


def add_channels(root, cases, mask):
    paths = {band: channel_index(root,band) for band in ('vv','vh')}
    bounds = json.loads((root/'screened.json').read_text())['bounds']
    out = []
    for case in cases:
        scene = case['scene']
        vv_dir,_,vv_cases = paths['vv']
        vh_dir,_,vh_cases = paths['vh']
        vv_window = vv_cases[scene]
        vh_window = vh_cases[scene]
        if (vv_window['source']['source_item_url'] != vh_window['source']['source_item_url']
                or vh_window['source']['band'] != 'VH'
                or vv_window['source']['band'] != 'VV'):
            raise ValueError('VV and VH do not identify the same Sentinel-1 item')
        region = box(*bounds[case['region']])
        overlap, chips = [], []
        lookup = {w['window_id']:w for w in vh_window['windows']}
        for row in sorted(vv_window['windows'],key=lambda w:w['window_id']):
            if row['window_id'] not in lookup:
                continue
            other = lookup[row['window_id']]
            if row['bbox'] != other['bbox']:
                raise ValueError('VV and VH grids differ')
            vv,vh = checked_channel(vv_dir,row),checked_channel(vh_dir,other)
            if vv.shape != vh.shape:
                raise ValueError('VV and VH raster shapes differ')
            support = valid_water(vv,row['bbox'],region,mask['land'])
            overlap.append(support)
            chips.append((row['bbox'],db_image(vv),db_image(vh)))
        if not chips:
            raise ValueError('No paired windows in acquisition')
        supports = list(unique_water_support(overlap))
        reliable = unary_union(supports)
        keep = lambda data: [row for row in data if intersects_xy(reliable,*row[:2])]
        c = dict(case, paired_windows=len(chips),missing_vh_windows=len(vv_window['windows'])-len(chips),
                 truth=keep(case['truth']),incumbent=keep(case['incumbent']),baseline_low=keep(case['baseline_low']))
        if not c['truth']:
            raise ValueError('No source labels within paired window support')
        adjusted = [summarize(c['baseline_low'],bbox,support,vv,vh)
                    for (bbox,vv,vh),support in zip(chips,supports)]
        c['features'] = np.concatenate(adjusted)
        if len(c['features']) != len(c['baseline_low']):
            raise ValueError('Archived low-threshold candidates and paired support differ')
        out.append(c)
    return out


def fit(cases, columns):
    inputs, labels = [], []
    for case in cases:
        features = case['features']
        if not len(features):
            continue
        distance = geographic_distances(features[:,:3], case['truth'])
        inputs.append(features[:,columns])
        labels.append(distance.min(axis=1) <= MATCH_DISTANCE)
    estimator = make_pipeline(StandardScaler(), LogisticRegression(
        C=.15, class_weight='balanced', max_iter=400,
    ))
    return estimator.fit(np.concatenate(inputs), np.concatenate(labels))


def count(points, truth, limit):
    sample = [tuple(x) for x in points[:limit]]
    return matched(sample,truth,(MATCH_DISTANCE,))[MATCH_DISTANCE]


def rank(case, model, columns, alpha):
    points = case['features']
    if len(points):
        prior = logit(np.clip(points[:,2], 1e-5, 1-1e-5))
        value = prior + alpha * model.decision_function(points[:,columns])
        return points[np.argsort(-value,kind='stable'),:3]
    return points[:,:3]


def assess(case, model_by_band):
    old = sorted(case['incumbent'],key=lambda p:-p[2])
    low = sorted(case['baseline_low'],key=lambda p:-p[2])
    limit = min(case['budget'], len(old))
    results = dict(map_default=count(old,case['truth'],limit),
                   confidence=count(low,case['truth'],limit))
    for band, columns in COLUMNS.items():
        for alpha in ALPHAS:
            key=f'{band}_{alpha:g}'
            results[key]=count(rank(case,model_by_band[band],columns,alpha),case['truth'],limit)
    return dict(review_limit=limit, results=results)


def total(folds,key):
    return sum(r['results'][key]['matched'] for r in folds)


def get_cases(cache, name):
    with gzip.open(cache/f'{name}_features.json.gz','rt') as stream:
        return json.load(stream)


def save(path, data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dev',required=True,type=Path)
    p.add_argument('--test',required=True,type=Path)
    p.add_argument('--cache',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    args=p.parse_args()
    args.output.mkdir(exist_ok=False)
    mask = get_mask(ROOT)[1]
    manifests = {name:{band:digest(channel_index(root,band)[1]) for band in ('vv','vh')}
                 for name,root in (('development',args.dev),('test',args.test))}
    save(args.output/'protocol.json',dict(
        started_utc=datetime.now(timezone.utc).isoformat(), code_sha256=digest(Path(__file__)),
        manifests=manifests, source_vv_features={
            name:digest(args.cache/f'{name}_features.json.gz') for name in ('development','fresh')},
        alphas=ALPHAS, cv='Leave one acquisition out on five development sets. Select within each band family by matched count and prefer weaker adjustment on a tie. Keep the map as recommendation when it ties.',
        scope='Rerank only the earlier 0.05 threshold proposals. Exactly the incumbent candidate count in common paired image support per scene. The 12 test scenes were scored before but not used for this ranking fit or alpha selection.',
    ))
    dev = add_channels(args.dev,get_cases(args.cache,'development'),mask)
    folds = []
    for i,case in enumerate(dev):
        training = dev[:i]+dev[i+1:]
        models = {b:fit(training,c) for b,c in COLUMNS.items()}
        folds.append(assess(case,models))
    choose = {}
    for b in COLUMNS:
        keys = [f'{b}_{alpha:g}' for alpha in ALPHAS]
        choose[b] = max(keys,key=lambda key:total(folds,key))
    recommendation = max(('map_default', *choose.values()),key=lambda key:total(folds,key))
    save(args.output/'selection.json',dict(locked_utc=datetime.now(timezone.utc).isoformat(),choice=choose,
                                           recommendation=recommendation,folds=folds))
    print('Development-selected:',choose,flush=True)
    fresh = add_channels(args.test,get_cases(args.cache,'fresh'),mask)
    fitted = {b:fit(dev,c) for b,c in COLUMNS.items()}
    results = [dict(scene=c['scene'],region=c['region'],paired_windows=c['paired_windows'],
                    missing_vh_windows=c['missing_vh_windows'],**assess(c,fitted)) for c in fresh]
    for key in results[0]['results']:
        print(key, total(results,key), 'matched',flush=True)
    save(args.output/'results.json',dict(selected=choose,recommendation=recommendation,outside_development=results))


if __name__=='__main__':
    main()
