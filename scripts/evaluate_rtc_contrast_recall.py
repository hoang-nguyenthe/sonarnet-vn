"""Test independent radar peaks and duplicate suppression at fixed review cost."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter, maximum_filter
from scipy.special import logit
from shapely import intersects_xy
from shapely.geometry import box
from shapely.ops import unary_union
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from evaluate_review_ranking import method_scores, save
from evaluate_sar_recall_candidates import ring_statistics
from land_mask import get_mask
from prepare_opensar_geo import unique_water_support
from score_vn_reference_rtc import ROOT, digest, geographic_distances, matched, raster_points, valid_water

RADII = (50, 100, 150)
PROFILES = ((.8, 7, 25), (1.6, 11, 39), (2.4, 17, 55))
FEATURES = ('map_score', 'slc_score', 'contrast_z', 'contrast_db', 'target_db', 'nearshore')


def contrast_proposals(gamma, sea, limit=16):
    db = np.zeros(gamma.shape, dtype=float)
    db[sea] = 10 * np.log10(gamma[sea])
    proposals = []
    for scale, guard, outer in PROFILES:
        coverage = gaussian_filter(sea.astype(float), scale, mode='constant')
        smooth = gaussian_filter(db, scale, mode='constant') / np.maximum(coverage, 1e-12)
        valid = sea & (coverage >= .9)
        mean, noise, support = ring_statistics(smooth, valid, guard, outer)
        contrast = smooth - mean
        z = contrast / np.maximum(noise, .5)
        eligible = valid & (support >= .35 * (outer**2 - guard**2)) & (contrast >= 2.) & (z >= 2.5)
        peaks = eligible & (z == maximum_filter(np.where(eligible, z, -np.inf), size=7))
        y, x = np.where(peaks)
        order = np.argsort(-z[y,x], kind='stable')[:limit]
        y, x = y[order], x[order]
        proposals.extend(zip(x+.5, y+.5, z[y,x], contrast[y,x], smooth[y,x]))
    return np.asarray(proposals, dtype=float).reshape(-1,5)


def radar_candidates(folder, cohort, bounds, mask):
    region = box(*bounds[cohort['region']])
    chips = []
    for row in sorted(cohort['windows'], key=lambda w:w['window_id']):
        path = folder / row['file']
        if digest(path) != row['sha256']:
            raise ValueError('RTC window checksum differs from manifest')
        with np.load(path,allow_pickle=False) as source:
            gamma = source['gamma0']
        chips.append((row['bbox'], gamma, valid_water(gamma,row['bbox'],region,mask['land'])))
    supports = list(unique_water_support([item[2] for item in chips]))
    points = np.asarray(cohort['points'], dtype=float).reshape(-1,2)
    eligible = intersects_xy(unary_union(supports),points[:,0],points[:,1])
    rows = []
    for (bbox, gamma, _), support in zip(chips,supports):
        if support.is_empty:
            continue
        h,w = gamma.shape
        west,south,east,north = bbox
        lon = west+(np.arange(w)+.5)/w*(east-west)
        lat = north-(np.arange(h)+.5)/h*(north-south)
        sea = (gamma > 0) & ~intersects_xy(mask['land'],lon[None,:],lat[:,None])
        peaks = contrast_proposals(gamma,sea)
        x,y = raster_points(peaks[:,:2],bbox,gamma.shape)
        valid = intersects_xy(support,x,y)
        rows.extend(np.c_[x,y,peaks[:,2:]][valid].tolist())
    return points[eligible], np.asarray(rows,dtype=float).reshape(-1,5)


def join_proposals(case, radar, coast):
    pool = np.asarray(case['candidates'],dtype=float).reshape(-1,9)
    points = np.unique(np.r_[pool[:,:2],radar[:,:2]],axis=0)
    queries = np.c_[points,np.zeros(len(points))]
    radar_features = np.full((len(points),3), [0.,0.,-35.])
    if len(radar) and len(points):
        distance = geographic_distances(queries,radar[:,:2])
        scores = np.where(distance <= 35.,radar[None,:,2],-np.inf)
        has_peak = np.isfinite(scores.max(axis=1))
        radar_features[has_peak] = radar[scores.argmax(axis=1)[has_peak],2:]
    return np.c_[points,method_scores(queries,case['baseline_low'],35.),
                 method_scores(queries,np.c_[pool[:,:2],pool[:,3]].tolist(),35.),
                 radar_features,intersects_xy(coast,points[:,0],points[:,1])]


def collect(archive, directory, mask):
    with gzip.open(archive,'rt') as fd:
        cases = json.load(fd)
    folder = directory/'rtc-512'
    lookup = {c['scene']:c for c in json.loads((folder/'manifest.json').read_text())['cohorts']}
    bounds = json.loads((directory/'screened.json').read_text())['bounds']
    for case in cases:
        cohort = lookup[case['scene']]
        if cohort['region'] != case['region'] or len(cohort['windows']) != case['windows']:
            raise ValueError('Neural proposal cohort and raster cohort differ')
        truth, radar = radar_candidates(folder,cohort,bounds,mask)
        if sorted(map(tuple,truth)) != sorted(map(tuple,case['truth'])):
            raise ValueError('Supported reference points differ')
        case['radar'] = radar
        case['union'] = join_proposals(case,radar,mask['coast'])
        print(case['region'],case['scene'].split('_')[4],len(radar),'contrast peaks',flush=True)
    return cases


def fit(cases):
    features, labels = [], []
    for case in cases:
        rows = case['union']
        if len(rows):
            distance = geographic_distances(rows[:,:3],case['truth'])
            features.append(rows[:,2:])
            labels.append(distance.min(axis=1) <= 100)
    model = make_pipeline(StandardScaler(),LogisticRegression(C=.12,class_weight='balanced',max_iter=400))
    return model.fit(np.concatenate(features),np.concatenate(labels))


def shortlist(primary, fallback, count, radius):
    kept = []
    if primary and count:
        adjacency = geographic_distances(primary,[p[:2] for p in primary]) <= radius
        indices = []
        for i in range(len(primary)):
            if len(indices) == count:
                break
            if not adjacency[i,indices].any():
                indices.append(i)
        kept = [primary[i] for i in indices]
    seen = {tuple(row[:2]) for row in kept}
    for point in fallback:
        if len(kept) == count:
            break
        xy = tuple(point[:2])
        if xy not in seen:
            seen.add(xy)
            kept.append(point)
    # Identical coordinates, if present in the source queue, still consumed a review.
    if len(kept) < count:
        kept.extend(fallback[:count-len(kept)])
    return kept


def evaluate(case, estimator):
    def ordered(rows):
        return sorted(rows,key=lambda point:-point[2])

    incumbent = ordered(case['incumbent'])
    base = ordered(case['baseline_low'])
    radar = case['radar'][:,:3]
    union = case['union']
    score = estimator.decision_function(union[:,2:]) if len(union) else np.empty(0)
    prior = logit(np.clip(union[:,2],.025,.975)) + .5*score
    blended = ordered(np.c_[union[:,:2],prior].tolist())
    methods = {
        'distinct_35m': (base,35.),
        'distinct_65m': (base,65.),
        'contrast_only': (ordered(radar.tolist()),35.),
        'learned_union': (ordered(np.c_[union[:,:2],score].tolist()),35.),
        'map_prior_union': (blended,35.),
        'map_prior_distinct_65m': (blended,65.),
    }
    results = {}
    for mode, reference in (('equal_incumbent',incumbent),('equal_relaxed',base)):
        count = min(case['budget'],len(reference))
        queues = {'map_default':incumbent[:count],'map_lower_threshold':base[:count]}
        queues.update({name:shortlist(rows,reference,count,radius)
                       for name,(rows,radius) in methods.items()})
        results[mode] = {key:matched(value,case['truth'],RADII) for key,value in queues.items()}
    return results


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('development','held-out','cached-neural','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args = parser.parse_args()
    out = args.output
    out.mkdir(exist_ok=False)
    development = args.cached_neural/'development_features.json.gz'
    holdout = args.cached_neural/'fresh_features.json.gz'
    save(out/'protocol.json',dict(
        started=utc_now(),evaluator_sha256=digest(Path(__file__)),
        source_hashes={
            **{p:digest(ROOT/p) for p in ('scripts/score_vn_reference_rtc.py',
              'scripts/evaluate_review_ranking.py','scripts/evaluate_sar_recall_candidates.py',
              'assets/land_mask/vietnam.json.gz','assets/models/sonarnet_baseline.pt',
              'assets/models/sonarnet_slc_vv_20261118.pt')},
            'development_cache':digest(development),'holdout_cache':digest(holdout),
            'development_vv_manifest':digest(args.development/'rtc-512/manifest.json'),
            'held_out_vv_manifest':digest(args.held_out/'rtc-512/manifest.json')},
        features=FEATURES,profiles=PROFILES,match_metres=RADII,
        selection='Leave one development acquisition out. Maximize total matches at 100 m at the same review count. Ties prefer the original order at that review count, then method order.',
        scope='Retrospective follow-up on scenes already scored by other methods. Evaluation scenes are excluded from all fitting and method selection.',
    ))
    _, mask = get_mask(ROOT)
    dev = collect(development,args.development,mask)
    folds = [dict(scene=c['scene'],**evaluate(c,fit(dev[:i]+dev[i+1:]))) for i,c in enumerate(dev)]
    locked = {}
    for mode,preferred in (('equal_incumbent','map_default'),('equal_relaxed','map_lower_threshold')):
        gains = {name:sum(c[mode][name][100]['matched'] for c in folds)
                 for name in folds[0][mode] if name != 'map_default' or mode == 'equal_incumbent'}
        locked[mode] = max(gains,key=lambda name:(gains[name],name == preferred))
        print(mode,locked[mode],gains,flush=True)
    save(out/'selection.json',dict(locked_at=utc_now(),selected=locked,folds=folds))
    held = collect(holdout,args.held_out,mask)
    dev_days = {c['scene'].split('_')[4][:8] for c in dev}
    held_days = {c['scene'].split('_')[4][:8] for c in held}
    if dev_days & held_days:
        raise ValueError('Development and holdout overlap by UTC day')
    model = fit(dev)
    results = []
    for case in held:
        union = case['union']
        full = matched(union[:,:3].tolist(),case['truth'],(100,))[100]
        original = matched(case['baseline_low'],case['truth'],(100,))[100]
        results.append(dict(scene=case['scene'],region=case['region'],windows=case['windows'],
                            all_proposals=dict(low_threshold=original,union=full),**evaluate(case,model)))
    save(out/'results.json',dict(selection_sha256=digest(out/'selection.json'),selected=locked,cases=results))


if __name__ == '__main__':
    main()
