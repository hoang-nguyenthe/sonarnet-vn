"""Tune a stronger SAR baseline and alternative inference on validation only.

The 503-chip OpenSAR test has already been evaluated in earlier project work.
Any test comparison from this script is a follow-up, not a new independent test.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import platform
import time

import numpy as np
from PIL import Image
from scipy import ndimage
from shapely import intersects_xy

from evaluate_ossdd_followup import normalize
from evaluate_opensar_geo import (assign_unique_support, open_split, restrict_to_scoring_support, score)
from prepare_opensar_geo import ROOT, digest, pixel_xy, save
from sonarnet.evaluation.detection_metrics import box_iou
from sonarnet.evaluation.independent_sar import operational_metrics


CONF = (.025, .05, .075, .1, .15, .2, .25, .35)
CFAR = ((7, 29, 3.2), (7, 29, 3.8), (7, 29, 4.4),
        (11, 41, 3.2), (11, 41, 3.8), (11, 41, 4.4))
NAMES = ('reference', 'contrast', 'tiles', 'full_plus_tiles')


def ring_statistics(values, water, guard, outer):
    """Local mean/stdev from valid water in the ring, never from padding, land or guard."""
    if not (1 <= guard < outer and guard % 2 and outer % 2):
        raise ValueError('Require ordered odd square window widths')
    v = np.where(water, values, 0).astype(np.float64, copy=False)
    def ring(a):
        return (ndimage.uniform_filter(a, outer, mode='constant') * outer**2 -
                ndimage.uniform_filter(a, guard, mode='constant') * guard**2)
    n = ring(np.asarray(water, dtype=float))
    count = np.maximum(n, 1)
    mu = ring(v) / count
    sigma = np.sqrt(np.maximum(ring(v*v) / count - mu*mu, 1.e-6))
    return mu, sigma, n


def cfar_propose(normalized, water, guard, outer, threshold):
    """Guard-ring contrast baseline with morphological grouping, not a calibrated PFA."""
    a = normalized.astype(float) / 255.
    mu, sigma, n = ring_statistics(a, water, guard, outer)
    z = (a - mu) / sigma
    eligible = water & (n >= (outer*outer-guard*guard)*.2)
    hits = eligible & (z >= threshold)
    # Closing links short runs, but retain seed pixels on the raster boundary.
    mask = (hits | ndimage.binary_closing(hits, structure=np.ones((3,3)))) & eligible
    ids, nlabels = ndimage.label(mask, structure=np.ones((3,3)))
    counts = np.bincount(ids.ravel())
    maxima = ndimage.maximum(z, labels=ids, index=np.arange(1, nlabels+1))
    boxes, scores = [], []
    h,w = a.shape
    for i, extent in enumerate(ndimage.find_objects(ids), 1):
        if extent is None or not 4 <= counts[i] <= 900:
            continue
        ys,xs = extent
        if xs.stop-xs.start > 130 or ys.stop-ys.start > 130:
            continue
        b = [max(0,xs.start-3), max(0,ys.start-3), min(w,xs.stop+3), min(h,ys.stop+3)]
        boxes.append(b)
        level = float(maxima[i-1]); scores.append(level / (1 + level))
    return np.asarray(boxes, dtype=float).reshape(-1,4), np.asarray(scores, dtype=float)


def nms(boxes, scores, iou=.45):
    remaining = np.argsort(-scores, kind='stable')
    kept = []
    while len(remaining):
        best = int(remaining[0]); kept.append(best)
        pending = remaining[1:]
        remaining = pending[box_iou(boxes[[best]], boxes[pending])[0] <= iou] if len(pending) else pending
    return boxes[kept], scores[kept]


def patches(im):
    for y in (0,128):
        for x in (0,128):
            yield x, y, im[y:y+384,x:x+384]


def pixels_in_support(row, im):
    y,x=np.indices(im.shape)
    coords=pixel_xy(row['corners_laea_m'],x+.5,y+.5)
    return (im > 0) & intersects_xy(row['sea'],coords[...,0],coords[...,1])


def summarize(rows, pred, threshold):
    nums, failures = operational_metrics(list(rows.values()), pred, threshold)
    close, close_hit = 0, 0
    for f in failures:
        hits = {j for _,j in f['matched_indices']}
        for j, lab in enumerate(rows[f['id']]['target_labels']):
            d=lab['sea_distance_to_shore_m']
            if d is not None and d <= 1000:
                close += 1; close_hit += j in hits
    return dict(count=close,matched=close_hit,**nums)


def choose_candidate(records, max_fp):
    candidates = [r for r in records if r['metrics']['false_positive'] <= max_fp]
    if not candidates:
        raise ValueError('No candidate in validation false-positive budget')
    return max(candidates, key=lambda k:(k['metrics']['matched'], k['metrics']['true_positive'],
        k['metrics']['f1'], -k['metrics']['false_positive'], k['threshold'], -NAMES.index(k['method'])))


def main(args):
    import cv2
    import torch
    from ultralytics import YOLO
    torch.set_num_threads(4); cv2.setNumThreads(1)
    args.output.mkdir(parents=True, exist_ok=False)
    val_path, test_path = (args.audit / (split+'_manifest.json') for split in ('val','test'))
    excluded = json.loads(args.pixel_audit.read_text())['excluded_val_ids']
    save(args.output/'protocol.json', dict(phase='post-initial-test follow-up; candidates chosen on validation only',
        created_utc=datetime.now(timezone.utc).isoformat(), selection='Candidate budget <= frozen original YOLO .10 validation FP ×1.15 (round down). Max matches within 1km, then overall TP/F1, fewer FP, higher confidence, deterministic order. Never tune after observing follow-up test.',
        yolo_conf=CONF, cfar=CFAR, cfar_selection='Highest overall validation F1 with at least one TP preferred; ties fewer FP then harder threshold.',
        data=dict(val=digest(val_path),test=digest(test_path), pixel_audit=digest(args.pixel_audit)),
        methods=NAMES, weights=digest(args.weights), source=digest(Path(__file__)),
        dependencies_sha256={p.name:digest(p) for p in [ROOT/'scripts/evaluate_opensar_geo.py',ROOT/'scripts/evaluate_ossdd_followup.py',ROOT/'scripts/prepare_opensar_geo.py',ROOT/'src/sonarnet/evaluation/independent_sar.py',ROOT/'src/sonarnet/evaluation/detection_metrics.py']},
        device='CPU, torch 4/OpenCV 1 threads', hardware=platform.platform(),
        support='Identical OpenSAR valid-water scoring and HIGH/MEDIUM rules; input mapping held fixed for reference and tiling; contrast variant clips with CLAHE 2.0 tiles 8x8.'))
    model=YOLO(str(args.weights)); clahe=cv2.createCLAHE(clipLimit=2.0,tileGridSize=(8,8))

    def pred(im):
        out=model.predict(Image.fromarray(im).convert('RGB'),device='cpu',imgsz=640,
            conf=.01,iou=.7,max_det=1000,verbose=False)[0]
        return out.boxes.xyxy.cpu().numpy(),out.boxes.conf.cpu().numpy()

    def yolo_raw(im, method):
        if method in ('reference','contrast'):
            return pred(im if method=='reference' else clahe.apply(im))
        detections = [pred(im)] if method == 'full_plus_tiles' else []
        for x,y,tile in patches(im):
            b,s=pred(tile)
            centers=(b[:,:2]+b[:,2:])/2
            # Ignore the internal 12 px halo only when a tile touches a neighbor.
            keep=((centers[:,0]>=12) | (x==0)) & ((centers[:,0] < 372) | (x==128))
            keep&=((centers[:,1]>=12) | (y==0)) & ((centers[:,1] < 372) | (y==128))
            detections.append((b[keep]+[x,y,x,y],s[keep]))
        return nms(np.concatenate([item[0] for item in detections]),np.concatenate([item[1] for item in detections]))

    val, amps=open_split(val_path,args.data/'prepared-v1')
    for i in excluded:
        del val[i],amps[i]
    assign_unique_support(val)
    normalized={i:normalize(a,'log1p') for i,a in amps.items()}
    support={i:pixels_in_support(r,amps[i]) for i,r in val.items()}
    raw_base, records = {}, []
    for method in NAMES:
        preds={i:restrict_to_scoring_support(row,*yolo_raw(normalized[i],method)) for i,row in val.items()}
        if method=='reference': raw_base=preds
        for threshold in CONF:
            m=summarize(val,preds,threshold)
            records.append(dict(method=method,threshold=threshold,metrics=m))
        print('Validation',method,'complete',flush=True)
    reference=summarize(val,raw_base,.1)
    max_fp=math_floor_15_percent(reference['false_positive'])
    winner=choose_candidate(records,max_fp)
    cfar=[]
    for params in CFAR:
        preds={i:restrict_to_scoring_support(row,*cfar_propose(normalized[i],support[i],*params)) for i,row in val.items()}
        cfar.append(dict(parameters=params,metrics=summarize(val,preds,0.)))
        print('Validation CFAR',params,cfar[-1]['metrics']['true_positive'],cfar[-1]['metrics']['false_positive'],flush=True)
    cfar_selected=max(cfar,key=lambda r:(r['metrics']['true_positive']>0,r['metrics']['f1'] or 0,
        -r['metrics']['false_positive'],r['parameters'][-1]))
    frozen=args.output/'frozen_operating_points.json'
    save(frozen,dict(frozen_at=datetime.now(timezone.utc).isoformat(),fp_budget=max_fp,reference=reference,
        selected=winner,cfar_selected=cfar_selected,candidates=records,cfar_candidates=cfar))
    print('Frozen:',winner['method'],winner['threshold'],cfar_selected['parameters'],flush=True)
    if not args.run_test:
        return
    test, test_amp=open_split(test_path,args.data/'prepared-v1')
    assign_unique_support(test)
    report=dict(frozen_sha256=digest(frozen),chips=len(test),models={})
    methods=[('reference','reference',.1),('candidate',winner['method'],winner['threshold']),('guard_ring_cfar','cfar',0.)]
    for name,method,threshold in methods:
        # Mask construction is included only for CFAR (its algorithm input); geo support is shared.
        def infer(i):
            r=test[i]; amp=test_amp[i]; u=normalize(amp,'log1p')
            raw=cfar_propose(u,pixels_in_support(r,amp),*cfar_selected['parameters']) if method=='cfar' else yolo_raw(u,method)
            return restrict_to_scoring_support(r,*raw)
        for _ in range(3): infer(next(iter(test)))
        predictions, elapsed={},[]
        for j,i in enumerate(test,1):
            start=time.perf_counter(); predictions[i]=infer(i); elapsed.append((time.perf_counter()-start)*1000)
            if j%125==0: print(name,j,'/',len(test),flush=True)
        metrics, errors=score(test,predictions,threshold)
        report['models'][name]=dict(method=method,threshold=threshold,metrics=metrics,
            wall_p50_ms=float(np.median(elapsed)),wall_p95_ms=float(np.percentile(elapsed,95)))
        for filename,obj in [(f'{name}_predictions.json.gz',{i:dict(boxes=b.tolist(),scores=s.tolist()) for i,(b,s) in predictions.items()}),
                             (f'{name}_errors.json.gz',errors)]:
            with gzip.open(args.output/filename,'wt') as f: json.dump(obj,f)
        save(args.output/'results.json',report)


def math_floor_15_percent(n):
    return n*115//100


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for a in ('data','audit','pixel-audit','weights','output'):
        p.add_argument('--'+a,type=Path,required=True)
    p.add_argument('--run-test',action='store_true')
    main(p.parse_args())
