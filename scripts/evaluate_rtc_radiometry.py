"""Compare alternate dB displays using the same deployed YOLO and exact review counts."""
import argparse
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

from evaluate_review_ranking import save
from evaluate_rtc_contrast_recall import RADII, shortlist
from land_mask import get_mask
from prepare_opensar_geo import unique_water_support
from score_vn_reference_rtc import ROOT, digest, infer_map, matched, valid_water

RANGES = {'subtle_echoes':(-34.,2.),'suppress_background':(-21.,5.),'adaptive': None}
MODES = {'equal_incumbent':'incumbent','equal_relaxed':'baseline_low'}
WEIGHTS = ROOT/'assets/models/sonarnet_baseline.pt'


def make_preview(gamma, profile):
    valid = np.isfinite(gamma) & (gamma > 0)
    out = np.zeros(gamma.shape,dtype=np.uint8)
    if valid.any():
        db = 10*np.log10(gamma[valid])
        limits = RANGES[profile]
        low,high = np.percentile(db,(5,99.7)) if limits is None else limits
        out[valid] = np.rint(255*np.clip((db-low)/max(6.,high-low),0,1)).astype(np.uint8)
    return Image.fromarray(np.dstack((out,out,out,valid.astype(np.uint8)*255)))


def generate(case, cohort, folder, bounds, model, mask):
    land = mask[1]['land']
    region = box(*bounds[case['region']])
    chips = []
    for w in sorted(cohort['windows'], key=lambda r:r['window_id']):
        path = folder/w['file']
        if digest(path) != w['sha256']:
            raise ValueError('RTC input checksum changed')
        with np.load(path,allow_pickle=False) as file:
            gamma = file['gamma0']
        chips.append((gamma,w['bbox'],valid_water(gamma,w['bbox'],region,land)))
    supports = unique_water_support([area for _,_,area in chips])
    output = {key:[] for key in RANGES}
    for (gamma,bbox,_),support in zip(chips,supports):
        if support.is_empty:
            continue
        for profile in RANGES:
            rows=infer_map(model,make_preview(gamma,profile),bbox,.05,mask)
            output[profile].extend([list(p) for p in rows if intersects_xy(support,*p[:2])])
    return output


def score(case, proposals):
    results={}
    for mode,key in MODES.items():
        base=sorted(case[key],key=lambda row:-row[2])
        low=case['baseline_low']
        count=min(case['budget'],len(base))
        results[mode]={'baseline':matched(base[:count],case['truth'],RADII)}
        for profile,rows in proposals.items():
            pooled=sorted(low+rows,key=lambda p:-p[2])
            selected=shortlist(pooled,base,count,35.)
            if len(selected)!=count:
                raise ValueError('Review counts differ')
            results[mode][profile]=matched(selected,case['truth'],RADII)
    return dict(scene=case['scene'],region=case['region'],windows=case['windows'],**results)


def run_group(pair, model, mask):
    root,cache=pair
    folder=root/'rtc-512'
    cohorts={row['scene']:row for row in json.loads((folder/'manifest.json').read_text())['cohorts']}
    bounds=json.loads((root/'screened.json').read_text())['bounds']
    with gzip.open(cache,'rt') as fd:
        inputs=json.load(fd)
    output=[]
    for case in inputs:
        cohort=cohorts[case['scene']]
        if cohort['region']!=case['region'] or len(cohort['windows'])!=case['windows']:
            raise ValueError('RTC and baseline case differ')
        output.append(score(case,generate(case,cohort,folder,bounds,model,mask)))
        print(case['scene'].split('_')[4],case['windows'],flush=True)
    return output


def day(case):
    return case['scene'].split('_')[4][:8]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('development','held-out','confirmation','cached-neural','confirmation-cache','out'):
        p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args()
    out=args.out
    out.mkdir(exist_ok=False)
    torch.set_num_threads(3)
    groups={'development':(args.development,args.cached_neural/'development_features.json.gz'),
            'held_out':(args.held_out,args.cached_neural/'fresh_features.json.gz'),
            'confirmation':(args.confirmation,args.confirmation_cache)}
    save(out/'protocol.json',dict(
         started=datetime.now(timezone.utc).isoformat(),code_sha256=digest(Path(__file__)),
         weights_sha256=digest(WEIGHTS),ranges=RANGES,adaptive_percentiles=[5,99.7],
         minimum_db_span=6,method='Union with ordinary detections; same area, same mask, rank by YOLO confidence; suppress nearby centers within 35 m.',
         selection='Choose one challenger per review count on five development days, then apply to separate dates. No model training.',
         references={kind:dict(raster_manifest_sha256=digest(path/'rtc-512/manifest.json'),cache_sha256=digest(cache))
                       for kind,(path,cache) in groups.items()}))
    model=YOLO(str(WEIGHTS))
    mask=get_mask(ROOT)
    dev=run_group(groups['development'],model,mask)
    selected={}
    for mode in MODES:
        totals={m:sum(row[mode][m][100]['matched'] for row in dev) for m in ('baseline',*RANGES)}
        selected[mode]=max(RANGES,key=totals.__getitem__)
        print(mode,selected[mode],totals,flush=True)
    save(out/'selection.json',dict(selected=selected,development=dev))
    result=dict(selection_sha256=digest(out/'selection.json'),selected=selected,test={})
    for kind,pair in groups.items():
        if kind=='development':
            continue
        rows=run_group(pair,model,mask)
        if {day(row) for row in rows} & {day(row) for row in dev}:
            raise ValueError('Evaluation dates overlap')
        result['test'][kind]=rows
        save(out/'results.json',result)


if __name__=='__main__':
    main()
