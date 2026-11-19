"""Check the locked equal-review methods on additional acquisition dates."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import torch
from ultralytics import YOLO

from evaluate_review_ranking import cache_group, save
from evaluate_rtc_contrast_recall import RADII, shortlist
from evaluate_rtc_map_tta import collect, ranked_views, MERGE_RADIUS_M
from land_mask import get_mask
from score_vn_reference_rtc import ROOT, digest, matched


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for flag in ('source','development','previously-scored','evidence','output'):
        p.add_argument('--'+flag,type=Path,required=True)
    args = p.parse_args()
    out = args.output
    out.mkdir(exist_ok=False)
    days = set()
    for path in (args.development,args.previously_scored):
        screened = json.loads((path/'screened.json').read_text())['regions']
        days.update(scene.split('_')[4][:8] for scenes in screened.values() for scene in scenes)
    manifest = args.source/'rtc-512/manifest.json'
    new_rows = json.loads(manifest.read_text())['cohorts']
    if any(c['scene'].split('_')[4][:8] in days for c in new_rows):
        raise ValueError('Confirmation includes a previously screened acquisition day')
    contrast = args.evidence/'vietnam_rtc_contrast_20261119/selection.json'
    tta = args.evidence/'vietnam_rtc_tta_20261119/selection.json'
    if json.loads(contrast.read_text())['selected'] != {'equal_incumbent':'distinct_35m','equal_relaxed':'distinct_35m'}:
        raise ValueError('Wrong prespecified duplicate suppression policy')
    if json.loads(tta.read_text())['selected']['equal_relaxed'] != 'overlap_only_max':
        raise ValueError('Wrong prespecified overlapping chip policy')
    weights = [ROOT/'assets/models'/name for name in ('sonarnet_baseline.pt','sonarnet_slc_vv_20261118.pt')]
    save(out/'protocol.json',dict(
         locked_utc=datetime.now(timezone.utc).isoformat(),input_manifest_sha256=digest(manifest),
         weights_sha256={p.name:digest(p) for p in weights},selection_sha256={p.parent.name:digest(p) for p in (contrast,tta)},
         excluded_utc_days=sorted(days),match_metres=RADII,
         policy='Only the 35 m suppression and overlapping chip policies are compared. Preserve exact per-acquisition review counts. All covered source labels are scored. No fitting.',
    ))
    torch.set_num_threads(3)
    baseline, slc = [YOLO(str(path)) for path in weights]
    mask = get_mask(ROOT)
    cache = out/'baseline.json.gz'
    cache_group(args.source,cache,baseline,slc,mask)
    cases = collect(baseline,cache,args.source,mask,out/'views.json')
    evaluated = []
    for case in cases:
        original = sorted(case['incumbent'],key=lambda p:-p[2])
        low = sorted(case['baseline_low'],key=lambda p:-p[2])
        extra = ranked_views(low,{'overlap':case['augmented']['overlap']},'max')
        results = {}
        for mode, reference in (('equal_incumbent',original),('equal_relaxed',low)):
            count = min(len(reference),case['budget'])
            methods = {'baseline': reference[:count], 'distinct_35m': shortlist(low,reference,count,35.)}
            if mode == 'equal_relaxed':
                methods['overlap_only_max'] = shortlist(extra,reference,count,MERGE_RADIUS_M)
            results[mode] = {key:matched(rows,case['truth'],RADII) for key,rows in methods.items()}
        evaluated.append(dict(scene=case['scene'],region=case['region'],windows=case['windows'],**results))
    save(out/'results.json',dict(cases=evaluated,excluded_scenes_without_supported_labels=
         sorted({c['scene'] for c in new_rows}-{c['scene'] for c in evaluated})))
    for case in evaluated:
        print(case['scene'].split('_')[4],
              {mode:{m:s[100] for m,s in case[mode].items()} for mode in ('equal_incumbent','equal_relaxed')},
              flush=True)


if __name__ == '__main__':
    main()
