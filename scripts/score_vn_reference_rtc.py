"""Compare detector recall against independently published local Sentinel-1 point labels."""
from collections import defaultdict
import argparse
from datetime import datetime, timezone
from hashlib import file_digest
import json
from pathlib import Path

import numpy as np
from PIL import Image
from pyproj import Geod
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import maximum_bipartite_matching
from shapely import intersects_xy
from shapely import orient_polygons
from shapely.geometry import GeometryCollection, box
from shapely.ops import unary_union
import torch
from ultralytics import YOLO

from evaluate_ossdd_followup import normalize
from evaluate_sar_multiscale import combine, predict_pass
from land_mask import get_mask
from prepare_opensar_geo import ROOT, invalid_runs, unique_water_support
from refresh_detailed_scan import allowed_pixels, infer_tile
from sonarnet.data.planetary import gray_rgba

RADII = (50, 100, 150)
BUDGET = .05
DEV_DAY = '20220406'
METHODS = (
    'map_default', 'map_lower_threshold', 'map_land_only', 'map_land_only_sensitive',
    'slc_512', 'slc_multiscale', 'slc_multiscale_log_stretch',
)
HYBRIDS = ('fill_with_coastal_map', 'fill_with_slc', 'fill_with_agreement')
NEAR_DUPLICATE_M = 35
AGREEMENT_M = 65
GEOD = Geod(ellps='WGS84')


def digest(path):
    with path.open('rb') as file:
        return file_digest(file, 'sha256').hexdigest()


def raster_points(coords, bbox, shape):
    w, s, e, n = bbox
    h, width = shape
    xy = np.asarray(coords).reshape(-1, 2)
    return tuple((w + xy[:, 0]/width*(e-w), n - xy[:, 1]/h*(n-s)))


def valid_water(gamma, bbox, region, land):
    tile = box(*bbox).intersection(region).difference(land)
    valid = gamma > 0
    holes = []
    for x0, y0, x1, y1 in invalid_runs(valid):
        xs, ys = raster_points([(x0,y1),(x1,y0)],bbox,gamma.shape)
        holes.append(box(xs[0],ys[0],xs[1],ys[1]))
    return tile.difference(unary_union(holes))


def infer_map(model, image, bbox, confidence, mask):
    detections, _ = infer_tile(model,image,bbox,confidence=confidence,mask=mask)
    return [(r['longitude'],r['latitude'],r['confidence']) for r in detections]


def infer_slc(model, gray, bbox, native, floor):
    passes = ('512',) if native else ('512','768','768_flip')
    raw = {mode: predict_pass(model,gray,mode) for mode in passes}
    boxes, scores = combine(raw, passes)
    good = scores >= floor
    selected = boxes[good]
    lon, lat = raster_points((selected[:, :2]+selected[:, 2:])/2,bbox,gray.shape)
    return list(zip(lon,lat,scores[good]))


def geographic_distances(start, end):
    left = np.asarray(start, dtype=np.float64).reshape(-1, 3)[:, :2]
    right = np.asarray(end, dtype=np.float64).reshape(-1, 2)
    n, m = len(left), len(right)
    if not (n and m):
        return np.empty((n, m))
    start = np.broadcast_to(left[:,None,:], (n,m,2))
    end = np.broadcast_to(right, (n,m,2))
    _, _, distance = GEOD.inv(start[:,:,0].ravel(), start[:,:,1].ravel(),
                              end[:,:,0].ravel(), end[:,:,1].ravel())
    return np.asarray(distance).reshape(n,m)


def refill(primary, extra, budget, agreeing=None):
    """Keep incumbent shortlist first, then add spatially distinct proposals."""
    kept = list(primary[:budget])
    if len(kept) == budget or not extra:
        return kept
    overlaps = geographic_distances(extra, [row[:2] for row in kept])
    candidates = [row for idx,row in enumerate(extra) if not np.any(overlaps[idx] <= NEAR_DUPLICATE_M)]
    if agreeing is not None and candidates:
        agreement = geographic_distances(candidates, [row[:2] for row in agreeing])
        matching = np.any(agreement <= AGREEMENT_M, axis=1)
        candidates = [item for item, supported in zip(candidates, matching) if supported]
    for candidate in candidates:
        if len(kept) == budget:
            break
        if kept:
            distance = geographic_distances([candidate], [row[:2] for row in kept])
            if np.any(distance <= NEAR_DUPLICATE_M):
                continue
        kept.append(candidate)
    return kept


def matched(predictions, ground, radii):
    number, truth = len(predictions), len(ground)
    distance = geographic_distances(predictions, ground)
    scores = {}
    for radius in radii:
        if not (number and truth):
            n = 0
        else:
            n = int(np.count_nonzero(maximum_bipartite_matching(csr_matrix(distance <= radius)) != -1))
        scores[radius] = dict(matched=n,labels=truth,predictions=number,unmatched=number-n)
    return scores


def score_cohort(cohort, root, bounds, baseline, slc, mask, hybrids):
    region = box(*bounds[cohort['region']])
    meta, shapes = mask
    land_only = (meta,{**shapes,'coast':GeometryCollection()})
    entries = sorted(cohort['windows'],key=lambda w:w['window_id'])
    prepared = []
    for window in entries:
        f = root / window['file']
        if digest(f) != window['sha256']:
            raise ValueError('Cached raster differs from declared SHA-256')
        with np.load(f,allow_pickle=False) as input_file:
            gamma = input_file['gamma0']
        prepared.append((window,gamma,valid_water(gamma,window['bbox'],region,shapes['land'])))
    support = list(unique_water_support([p for _,_,p in prepared]))
    overall = unary_union(support)
    points = np.array(cohort['points']).reshape(-1,2)
    ground = points[intersects_xy(overall,points[:,0],points[:,1])]
    coast = intersects_xy(shapes['coast'],ground[:,0],ground[:,1])
    area = sum(abs(GEOD.geometry_area_perimeter(orient_polygons(p))[0]) for p in support)/1e6
    budget = int(BUDGET*area)
    if not len(ground) or not budget:
        raise ValueError('Required labelled-water support is missing')
    candidates = defaultdict(list)
    for idx, ((window,gamma,_), supported) in enumerate(zip(prepared,support),1):
        if supported.is_empty:
            continue
        bbox = window['bbox']
        rgba = gray_rgba(np.ma.masked_less_equal(gamma,0))
        image = Image.fromarray(rgba)
        allowed, _ = allowed_pixels(image,bbox,land_only)
        gray = rgba[:,:,0].copy()
        gray[~allowed] = 0
        enhanced = normalize(np.sqrt(gamma),'log1p')
        enhanced[~allowed] = 0
        rows = {
            'map_default': infer_map(baseline,image,bbox,.35,mask),
            'map_lower_threshold': infer_map(baseline,image,bbox,.05,mask),
            'map_land_only': infer_map(baseline,image,bbox,.35,land_only),
            'map_land_only_sensitive': infer_map(baseline,image,bbox,.05,land_only),
            'slc_512': infer_slc(slc,gray,bbox,True,.025),
            'slc_multiscale': infer_slc(slc,gray,bbox,False,.005),
            'slc_multiscale_log_stretch': infer_slc(slc,enhanced,bbox,False,.005),
        }
        for name, points in rows.items():
            if points:
                scored = np.asarray(points,dtype=np.float64)
                selected = intersects_xy(supported,scored[:,0],scored[:,1])
                candidates[name].extend(scored[selected].tolist())
        if idx % 10 == 0:
            print(cohort['region'],idx,'/',len(entries),flush=True)
    counts = {}
    ranked = {m: sorted(candidates[m], key=lambda row: -row[2]) for m in METHODS}
    if hybrids:
        primary = ranked['map_default']
        ranked['fill_with_coastal_map'] = refill(primary, ranked['map_land_only_sensitive'], budget)
        ranked['fill_with_slc'] = refill(primary, ranked['slc_multiscale'], budget)
        ranked['fill_with_agreement'] = refill(primary, ranked['map_land_only_sensitive'], budget,
                                               agreeing=ranked['slc_multiscale'])
    for m,full in ranked.items():
        short = full[:budget]
        counts[m] = {
            'all':matched(full,ground,RADII),
            'fixed_budget':matched(short,ground,RADII),
            'nearshore_label_matches_using_full_candidates':matched(full,ground[coast],(100,))[100]['matched'],
            'nearshore_label_count':int(coast.sum()),
        }
    print(cohort['region'],len(ground),'water points over',round(area),'km²',flush=True)
    return dict(region=cohort['region'],n_source_labels=len(cohort['points']), n_evaluated_labels=len(ground),
                area_km2=area,budget=budget,windows=len(entries), results=counts)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('benchmark',type=Path)
    parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--hybrids', action='store_true')
    args=parser.parse_args()
    torch.set_num_threads(4)
    raw=args.benchmark/'rtc-512'
    manifest=json.loads((raw/'manifest.json').read_text())
    bounds=json.loads((args.benchmark/'screened.json').read_text())['bounds']
    mask=get_mask(ROOT)
    weights=ROOT/'assets/models'
    baseline_path=weights/'sonarnet_baseline.pt'
    slc_path=weights/'sonarnet_slc_vv_20261118.pt'
    baseline=YOLO(str(baseline_path))
    slc=YOLO(str(slc_path))
    out=args.out
    out.mkdir(exist_ok=False)
    methods = METHODS + HYBRIDS if args.hybrids else METHODS
    protocol=dict(
        frozen_utc=datetime.now(timezone.utc).isoformat(), script_sha256=digest(Path(__file__)),
        inputs_sha256=digest(raw/'manifest.json'), map_weights_sha256=digest(baseline_path),
        slc_weights_sha256=digest(slc_path), methods=methods, match_distance_m=RADII,
        hybrid_duplicate_m=NEAR_DUPLICATE_M, hybrid_agreement_m=AGREEMENT_M,
        hybrid_scope='Follow-up on the previously scored scenes. Rules selected on development. Hybrid predictions are limited by the declared review budget.',
        main_distance_m=100, budget_per_km2=BUDGET, development_acquisition_day=DEV_DAY,
        method_selection='Maximize development matches at fixed budget, break ties by fewer unmatched within budget, then fewer total unmatched and original model.',
        support='Same valid image pixels and ocean support. Original map masks land and additional 500 m shore band. Largest bipartite matching by distance on source points. Source labels need not be complete.',
        scope='Historical Sentinel-1 GRD/RTC comparisons on previously unused external Vietnamese coastal image annotations, not verified identity ground truth.',
    )
    (out/'protocol.json').write_text(json.dumps(protocol,indent=2))
    data=sorted(manifest['cohorts'],key=lambda cohort:DEV_DAY not in cohort['scene'])
    if len(data)!=5 or any(not c['windows'] or c.get('failed_windows') for c in data):
        raise ValueError('Expected full reference window coverage from five source acquisitions')
    all_results={}
    for i,cohort in enumerate(data):
        result=score_cohort(cohort,raw,bounds,baseline,slc,mask,args.hybrids)
        all_results[cohort['scene']]=result
        if i==0:
            if DEV_DAY not in cohort['scene']:
                raise ValueError('Required development acquisition is missing')
            counts=result['results']
            def key(m):
                c=counts[m]
                at_cap=c['fixed_budget'][100]
                return (at_cap['matched'],-at_cap['unmatched'],-c['all'][100]['unmatched'],m=='map_default')
            choice=max(methods,key=key)
            (out/'selected.json').write_text(json.dumps({'locked_utc':datetime.now(timezone.utc).isoformat(),
                                                          'selected':choice,'development':result},indent=2))
            print('Locked',choice,flush=True)
        (out/'results.json').write_text(json.dumps({'selected':choice,'development_day':DEV_DAY,'per_acquisition':all_results},indent=2))


if __name__=='__main__':
    main()
