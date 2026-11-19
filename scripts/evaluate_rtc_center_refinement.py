"""Test whether an independent radar heatmap can refine existing candidate centers."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
from shapely import intersects_xy
from shapely.ops import unary_union
import torch

from evaluate_rtc_contrast_recall import shortlist
from evaluate_rtc_map_tta import ranked_views
from evaluate_rtc_point_detector import PointDetector, VALIDATION_DAYS, day, propose, read_cases
from evaluate_review_ranking import save
from land_mask import get_mask
from score_vn_reference_rtc import ROOT, digest, geographic_distances, matched

MODES = ('equal_incumbent','equal_relaxed')
PROFILES = {'halfway_45m': (45.,.5), 'peak_45m': (45.,1.), 'halfway_75m': (75.,.5), 'peak_75m': (75.,1.)}
RADII = (50,100,150)


def refine(rows, points, radius, weight, support):
    if not rows or not points:
        return rows
    a,b = np.array(rows),np.array(points)
    distances = geographic_distances(rows,b[:,:2])
    quality = np.where(distances<=radius,b[None,:,2],-np.inf)
    best = np.argmax(quality,axis=1)
    supported = np.isfinite(np.max(quality,axis=1))
    predicted = a[supported,:2] + weight*(b[best[supported],:2]-a[supported,:2])
    valid = intersects_xy(support,predicted[:,0],predicted[:,1])
    a[np.flatnonzero(supported)[valid],:2] = predicted[valid]
    return a.tolist()


def score(case, point, overlap):
    full = sorted(case['baseline_low'],key=lambda p:-p[2])
    res = {}
    support = unary_union([chip['support'] for chip in case['chips']])
    for mode,prior in zip(MODES,('incumbent','baseline_low')):
        original = sorted(case[prior],key=lambda p:-p[2])
        count = min(len(original),case['budget'])
        p = full if mode=='equal_incumbent' else ranked_views(full,{'overlap':overlap},'max')
        baseline = shortlist(p,original,count,35.)
        res[mode] = {'baseline':matched(baseline,case['truth'],RADII)}
        for name,(radius,weight) in PROFILES.items():
            res[mode][name]=matched(refine(baseline,point,radius,weight,support),case['truth'],RADII)
    return dict(scene=case['scene'],region=case['region'],windows=case['windows'],**res)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for flag in ('development','held-out','confirmation','cached-neural','confirmation-cache','tta',
                 'confirmation-views','heatmap','out'):
        p.add_argument('--'+flag,type=Path,required=True)
    args=p.parse_args()
    out=args.out
    out.mkdir(exist_ok=False)
    torch.set_num_threads(3)
    pick=json.loads((args.heatmap/'selection.json').read_text())['selected']['equal_relaxed']
    checkpoint=args.heatmap/pick['checkpoint']
    if digest(checkpoint)!=pick['checkpoint_sha256']:
        raise ValueError('Locked point model differs')
    groups = {
        'development':(args.development,args.cached_neural/'development_features.json.gz',
                       args.tta/'development-views.json'),
        'held_out':(args.held_out,args.cached_neural/'fresh_features.json.gz',args.tta/'held-out-views.json'),
        'confirmation':(args.confirmation,args.confirmation_cache,args.confirmation_views),
    }
    save(out/'protocol.json',dict(
        started=datetime.now(timezone.utc).isoformat(),code_sha256=digest(Path(__file__)),
        model_sha256=digest(checkpoint),profiles=PROFILES,baseline={'equal_incumbent':'35 m suppression','equal_relaxed':'overlap + 35 m suppression'},
        selection='Maximize matches at exact review counts on the two development dates held away from heatmap training.',
        validation_days=VALIDATION_DAYS,
        inputs={group:dict(image_manifest=digest(root/'rtc-512/manifest.json'),neural_cache=digest(cache),views=digest(views))
                for group,(root,cache,views) in groups.items()},
    ))
    model=PointDetector()
    model.load_state_dict(torch.load(checkpoint,map_location='cpu',weights_only=True))
    mask=get_mask(ROOT)
    test={}
    for group,(root,cache,views) in groups.items():
        aug=json.loads(views.read_text())
        cases = []
        for case in read_cases(root,cache,lambda c:group!='development' or day(c) in VALIDATION_DAYS,mask):
            points,_=propose(model,case,'cpu')
            result=score(case,points,aug[case['scene']]['overlap'])
            cases.append(result)
            print(group,day(case),flush=True)
        if group=='development':
            selected={}
            for mode in MODES:
                totals={name:sum(case[mode][name][100]['matched'] for case in cases)
                        for name in ('baseline',*PROFILES)}
                selected[mode]=max(PROFILES,key=totals.__getitem__)
                print(mode,selected[mode],totals,flush=True)
            save(out/'selection.json',dict(selected=selected,development=cases))
        else:
            test[group]=cases
            save(out/'results.json',dict(selected=selected,selection_sha256=digest(out/'selection.json'),test=test))


if __name__=='__main__':
    main()
