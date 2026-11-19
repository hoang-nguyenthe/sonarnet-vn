"""Evaluate augmentation and overlapping chips with the actual map checkpoint."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path

import numpy as np
from PIL import Image
from shapely import intersects_xy
from shapely.geometry import box
import torch
from ultralytics import YOLO

from evaluate_rtc_contrast_recall import RADII, shortlist
from evaluate_review_ranking import save
from evaluate_sar_multiscale import detect
from land_mask import get_mask
from prepare_opensar_geo import unique_water_support
from refresh_detailed_scan import allowed_pixels
from score_vn_reference_rtc import ROOT, digest, geographic_distances, matched, raster_points, valid_water
from sonarnet.data.planetary import gray_rgba

VIEWS = ('rot90', 'flip', 'scale768', 'overlap')
POLICIES = {
    'flip_rotation': ('flip','rot90'),
    'overlap_only': ('overlap',),
    'scale_only': ('scale768',),
    'all_views': VIEWS,
}
MINIMUM_CONFIDENCE = .05
MERGE_RADIUS_M = 35.


def infer_view(model, gray, view):
    h,w = gray.shape
    if view == 'flip':
        boxes, scores = detect(model,np.ascontiguousarray(gray[:,::-1]),1024)
        return np.c_[w-boxes[:,2],boxes[:,1],w-boxes[:,0],boxes[:,3]], scores
    if view == 'rot90':
        boxes, scores = detect(model,np.ascontiguousarray(np.rot90(gray)),1024)
        return np.c_[w-boxes[:,3],boxes[:,0],w-boxes[:,1],boxes[:,2]], scores
    if view == 'scale768':
        return detect(model,gray,768)
    if view == 'overlap':
        output = []
        # Use a 64 px halo around each 256 px quadrant. Rim contacts are
        # attributed to the single quadrant that contains their center.
        for top in (0,256):
            for left in (0,256):
                x0,y0 = max(0,left-64),max(0,top-64)
                chip = gray[y0:min(h,top+320),x0:min(w,left+320)]
                boxes, scores = detect(model,chip,896)
                boxes = boxes + [x0,y0,x0,y0]
                cx,cy = ((boxes[:,:2]+boxes[:,2:])/2).T
                inside = (left <= cx) & (cx < left+256) & (top <= cy) & (cy < top+256)
                output.append((boxes[inside],scores[inside]))
        return np.concatenate([p[0] for p in output]),np.concatenate([p[1] for p in output])
    raise ValueError(f'Unexpected view {view}')


def infer_window(model, gamma, bbox, support, mask):
    rgba = gray_rgba(np.ma.masked_less_equal(gamma,0))
    allowed, exclusion = allowed_pixels(Image.fromarray(rgba),bbox,mask)
    gray = np.where(allowed,rgba[:,:,0],0)
    pooled = {}
    for view in VIEWS:
        pooled[view] = []
        if not allowed.any():
            continue
        boxes, scores = infer_view(model,gray,view)
        boxes = np.clip(boxes,0,512)
        centers = (boxes[:,:2]+boxes[:,2:])/2
        lon, lat = raster_points(centers,bbox,gray.shape)
        keep = (scores >= MINIMUM_CONFIDENCE) & intersects_xy(support,lon,lat)
        x1,y1 = raster_points(boxes[:,:2],bbox,gray.shape)
        x2,y2 = raster_points(boxes[:,2:],bbox,gray.shape)
        for i in np.flatnonzero(keep):
            if x2[i] > x1[i] and y1[i] > y2[i] and not exclusion.intersects(box(x1[i],y2[i],x2[i],y1[i])):
                pooled[view].append((float(lon[i]),float(lat[i]),float(scores[i])))
    return pooled


def collect(model, cache, root, mask, resume):
    with gzip.open(cache,'rt') as fd:
        rows = json.load(fd)
    folder = root/'rtc-512'
    bounds = json.loads((root/'screened.json').read_text())['bounds']
    lookup = {c['scene']:c for c in json.loads((folder/'manifest.json').read_text())['cohorts']}
    existing = json.loads(resume.read_text()) if resume.is_file() else {}
    for case in rows:
        scene = case['scene']
        if scene not in existing:
            cohort = lookup[scene]
            if cohort['region'] != case['region'] or len(cohort['windows']) != case['windows']:
                raise ValueError('Augmentation and baseline cohorts differ')
            region = box(*bounds[case['region']])
            chips = []
            for item in sorted(cohort['windows'],key=lambda w:w['window_id']):
                path = folder/item['file']
                if digest(path) != item['sha256']:
                    raise ValueError('RTC source checksum changed')
                with np.load(path,allow_pickle=False) as source:
                    gamma = source['gamma0']
                if gamma.shape != (512,512):
                    raise ValueError('Expected a 512 by 512 raster')
                bbox = item['bbox']
                chips.append((bbox,gamma,valid_water(gamma,bbox,region,mask[1]['land'])))
            parts = list(unique_water_support([p[2] for p in chips]))
            result = {name:[] for name in VIEWS}
            for idx, ((bbox,gamma,_), support) in enumerate(zip(chips,parts),1):
                if support.is_empty:
                    continue
                for name,items in infer_window(model,gamma,bbox,support,mask).items():
                    result[name].extend(items)
                if idx % 8 == 0:
                    print(scene.split('_')[4],idx,'/',len(chips),flush=True)
            existing[scene] = result
            save(resume,existing)
        case['augmented'] = existing[scene]
        print(scene.split('_')[4],{name:len(l) for name,l in case['augmented'].items()},flush=True)
    return rows


def ranked_views(original, others, mode):
    proposals = defaultdict(list)
    proposals['original'] = original
    proposals.update(others)
    if mode == 'max':
        return sorted((p for rows in proposals.values() for p in rows),key=lambda row:-row[2])
    # Vote once per distinct transformation, so a single overlapping view
    # cannot increase its influence through several neighboring boxes.
    points = np.array([p for rows in proposals.values() for p in rows]).reshape(-1,3)
    if not len(points):
        return []
    scores = []
    for rows in proposals.values():
        if not rows:
            continue
        distances = geographic_distances(points,[p[:2] for p in rows])
        values = np.asarray(rows)[:,2]
        scores.append(np.where(distances <= MERGE_RADIUS_M,values[None,:],0.).max(axis=1))
    consensus = .72*np.max(scores,axis=0)+.28*np.sum(scores,axis=0)/len(proposals)
    return np.c_[points[:,:2],consensus][np.argsort(-consensus,kind='stable')].tolist()


def measure(case):
    orig = sorted(case['incumbent'],key=lambda row:-row[2])
    low = sorted(case['baseline_low'],key=lambda row:-row[2])
    policies = {f'{name}_{fusion}':ranked_views(low,{key:case['augmented'][key] for key in views},fusion)
                for name,views in POLICIES.items() for fusion in ('max','vote')}
    results = {}
    for mode, reference in (('equal_incumbent',orig),('equal_relaxed',low)):
        count = min(len(reference),case['budget'])
        queues = {'map_default':orig[:count],'map_lower_threshold':low[:count]}
        queues.update({name:shortlist(rows,reference,count,MERGE_RADIUS_M) for name,rows in policies.items()})
        results[mode] = {name:matched(rows,case['truth'],RADII) for name,rows in queues.items()}
    return results


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('development','held-out','cached-neural','output'):
        p.add_argument('--'+name,type=Path,required=True)
    args = p.parse_args()
    out = args.output
    out.mkdir(exist_ok=False)
    torch.set_num_threads(3)
    checkpoint = ROOT/'assets/models/sonarnet_baseline.pt'
    save(out/'protocol.json',dict(
        started=utc_now(),evaluator_sha256=digest(Path(__file__)),weights_sha256=digest(checkpoint),
        packages={'torch':torch.__version__},fusion_modes=['max','vote'],policies=POLICIES,
        normalized_db_range=[-25,5],merge_radius_m=MERGE_RADIUS_M,minimum_conf=MINIMUM_CONFIDENCE,
        match_metres=RADII,development_manifest_sha256=digest(args.development/'rtc-512/manifest.json'),
        held_out_manifest_sha256=digest(args.held_out/'rtc-512/manifest.json'),
        neural_cache_sha256={s:digest(args.cached_neural/f'{s}_features.json.gz') for s in ('development','fresh')},
        selection='Maximize one-to-one 100 m matches at the chosen exact review count on five acquisitions. Ties prefer the baseline.',
        scope='Held-out acquisitions exclude all development days. Previously used for other methods.',
    ))
    model, mask = YOLO(str(checkpoint)),get_mask(ROOT)
    dev = collect(model,args.cached_neural/'development_features.json.gz',args.development,mask,out/'development-views.json')
    cases = [dict(scene=c['scene'],**measure(c)) for c in dev]
    locked = {}
    for mode, baseline in (('equal_incumbent','map_default'),('equal_relaxed','map_lower_threshold')):
        scores = {name:sum(c[mode][name][100]['matched'] for c in cases)
                  for name in cases[0][mode] if name != 'map_default' or mode == 'equal_incumbent'}
        locked[mode] = max(scores,key=lambda name:(scores[name],name==baseline))
        print(mode,locked[mode],scores,flush=True)
    save(out/'selection.json',dict(locked_utc=utc_now(),selected=locked,development=cases))
    held = collect(model,args.cached_neural/'fresh_features.json.gz',args.held_out,mask,out/'held-out-views.json')
    if {c['scene'].split('_')[4][:8] for c in held} & {c['scene'].split('_')[4][:8] for c in dev}:
        raise ValueError('Development and held-out acquisition dates overlap')
    save(out/'results.json',dict(selection_sha256=digest(out/'selection.json'),selected=locked,
         cases=[dict(scene=c['scene'],region=c['region'],windows=c['windows'],**measure(c)) for c in held]))


if __name__ == '__main__':
    main()
