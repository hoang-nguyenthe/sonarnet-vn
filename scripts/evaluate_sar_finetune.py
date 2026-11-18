"""Check whether 640 px fine-tuning improves SLC recall at the same review budget."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path

import numpy as np
import torch
from ultralytics import YOLO

from evaluate_opensar_geo import assign_unique_support, open_split
from evaluate_sar_multiscale import THRESHOLDS, count_metrics, infer_policies, sort_key
from prepare_opensar_geo import digest, save

POLICIES = ('native_512', 'whole_768', 'dual_scale_flip')
CONTROL = ('dual_scale_flip', .005)


def keep_counts(outcome):
    return {key: {
        'labels': value['n_ground_truth'], 'matched': value['true_positive'],
        'unmatched': value['false_positive'], 'recall': value['recall'],
        'nearshore': value['by_distance_to_mapped_shore_m'][500],
    } for key, value in outcome.items() if key in ('full', 'fixed_budget')}


def read_control(path, expected, rows):
    if digest(path) != expected:
        raise ValueError('Frozen comparison predictions differ')
    with gzip.open(path, 'rt') as stream:
        content = json.load(stream)
    if content.keys() != rows.keys():
        raise ValueError('Frozen predictions do not cover exactly the same SLC inputs')
    return {key: (np.asarray(value['boxes']).reshape(-1,4), np.asarray(value['scores']))
            for key,value in content.items()}


def validation_rows(model, checkpoint, rows, images):
    prediction_groups, _ = infer_policies(rows, images, model, POLICIES)
    return [
        dict(checkpoint=checkpoint, policy=policy, threshold=cut, **count_metrics(rows, preds, cut))
        for policy,preds in prediction_groups.items() for cut in THRESHOLDS
    ]


def run(args):
    torch.set_num_threads(4)
    dataset = args.adaptation
    audit = json.loads((dataset/'audit.json').read_text())
    provenance_file = args.training/'provenance.json'
    provenance = json.loads(provenance_file.read_text())
    checkpoints = {key: args.training/f'weights/{key}.pt' for key in ('best','last')}
    reference = json.loads((args.control/'results.json').read_text())
    reference_protocol = json.loads((args.control/'protocol.json').read_text())
    tune_path=dataset/'tune_manifest.json'
    cohorts = (
        ('diagnostic', args.diagnostic/'confirmation_manifest.json', args.data/'prepared-confirmation-v1'),
        ('north_sea', dataset/'fresh_manifest.json', dataset/'rasters'),
    )
    if (not audit['passed'] or provenance['dataset_manifest_sha256'] != digest(dataset/'manifest.json')
        or provenance['training']['imgsz'] != 640 or provenance['best_sha256'] != digest(checkpoints['best'])
        or provenance['initial_sha256'] != reference_protocol['weights_sha256']
        or digest(tune_path) != reference_protocol['tune_sha256']
        or any(digest(p) != reference_protocol['test_manifest_sha256'][key] for key,p,_ in cohorts)):
        raise ValueError('Fine-tune, validation or test assignment differs from declared evidence')
    hashes={name:digest(path) for name,path in checkpoints.items()}
    output=args.out
    output.mkdir(exist_ok=False)
    save(output/'protocol.json',dict(
        frozen_utc=datetime.now(timezone.utc).isoformat(), training_sha256=digest(provenance_file),
        control_sha256=digest(args.control/'results.json'), code_sha256=digest(Path(__file__)),
        checkpoints_sha256=hashes, tune_sha256=digest(tune_path), candidates=POLICIES, thresholds=THRESHOLDS,
        rule='Pick the fine-tuned checkpoint and inference settings using validation matches within the same 1/20 km² budget. Retest frozen samples even if fine-tuning does not improve on validation.',
    ))
    tune, images = open_split(tune_path,dataset/'rasters')
    assign_unique_support(tune)
    grid=[]
    for key,path in checkpoints.items():
        grid.extend(validation_rows(YOLO(str(path)),key,tune,images))
    choice=max(grid,key=sort_key)
    selected={key:choice[key] for key in ('checkpoint','policy','threshold')}
    save(output/'operating_point.json',dict(
        locked_utc=datetime.now(timezone.utc).isoformat(), selected=selected,
        validation=[{**{k:r[k] for k in ('checkpoint','policy','threshold')}, **keep_counts(r)} for r in grid],
    ))
    print('Locked',selected,'shortlist matches',choice['fixed_budget']['true_positive'],flush=True)
    del tune,images
    candidate=YOLO(str(checkpoints[choice['checkpoint']]))
    results={}
    for key,path,root in cohorts:
        rows,images=open_split(path,root)
        assign_unique_support(rows)
        old=reference['evaluation'][key]['methods']['candidate']
        if (old['policy'],old['threshold']) != CONTROL:
            raise ValueError('Unrecognized frozen comparison operating point')
        control=read_control(args.control/f'{key}_candidate_predictions.json.gz',old['prediction_sha256'],rows)
        baseline_outcome=keep_counts(count_metrics(rows,control,CONTROL[1]))
        policy=choice['policy']
        preds,times=infer_policies(rows,images,candidate,(policy,))
        trial_outcome=keep_counts(count_metrics(rows,preds[policy],choice['threshold']))
        prediction_file=output/f'{key}_predictions.json.gz'
        with gzip.open(prediction_file,'wt') as stream:
            json.dump({i:dict(boxes=b.tolist(), scores=s.tolist()) for i,(b,s) in preds[policy].items()}, stream)
        results[key]=dict(baseline=baseline_outcome, fine_tuned=trial_outcome,
                          latency_p50_ms=float(np.median(times[policy])),predictions_sha256=digest(prediction_file))
        save(output/'results.json',dict(selected=selected, evaluation=results))
        print(key,'shortlist matched',baseline_outcome['fixed_budget']['matched'],'→',
              trial_outcome['fixed_budget']['matched'],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('adaptation','training','control','diagnostic','data','out'):
        parser.add_argument('--'+name,required=True,type=Path)
    run(parser.parse_args())
