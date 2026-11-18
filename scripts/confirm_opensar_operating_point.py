"""Evaluate the already-frozen YOLO and ring baseline on fresh geographic support."""
import argparse
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import platform
import time

import numpy as np
from PIL import Image

from prepare_opensar_geo import ROOT, digest, save
from evaluate_ossdd_followup import normalize
from evaluate_opensar_geo import assign_unique_support, leakage, open_split, restrict_to_scoring_support, score
from evaluate_sar_recall_candidates import cfar_propose, pixels_in_support


def run(args):
    import torch
    import ultralytics
    torch.set_num_threads(4)
    preflight_path=args.prior/'frozen_operating_points.json'
    frozen=json.loads(preflight_path.read_text())
    pick=frozen['selected']
    if pick['method']!='reference':
        raise ValueError('This fixed confirmation protocol only implements the retained reference.')
    cut=float(pick['threshold']); ring=tuple(frozen['cfar_selected']['parameters'])
    manifest=args.fresh/'confirmation_manifest.json'
    prep=args.fresh/'selection.json'
    args.output.mkdir(parents=True,exist_ok=False)
    protocol=dict(issued_utc=datetime.now(timezone.utc).isoformat(), selected_before_confirmation=digest(preflight_path),
        exact_fixed_choice=dict(yolo_conf=cut, cfar=ring), confirmation_manifest_sha256=digest(manifest),
        confirmation_selection_sha256=digest(prep), old_val_sha256=digest(args.audit/'val_manifest.json'),
        old_test_sha256=digest(args.audit/'test_manifest.json'), weights_sha256=digest(args.weights),
        code_sha256={p.name:digest(p) for p in [Path(__file__),ROOT/'scripts/evaluate_opensar_geo.py',
          ROOT/'scripts/evaluate_sar_recall_candidates.py',ROOT/'scripts/prepare_opensar_confirmation.py',
          ROOT/'scripts/prepare_opensar_geo.py', ROOT/'scripts/evaluate_ossdd_followup.py',
          ROOT/'src/sonarnet/evaluation/independent_sar.py',ROOT/'src/sonarnet/evaluation/detection_metrics.py']},
        claim='Publisher train designation is unrelated to this checkpoint. No fit or model/threshold selection on these tiles. Check against all previously used val/test chips for exact decoded SLC and dHash <=3.',
        limits='Only SLC VV archive and supplied weak/incomplete labels; no independent GPS; no national or multi-sensor generalizability claim. No training on OpenSAR.',
        environment=dict(cpu_threads=4,platform=platform.platform(),torch=torch.__version__,ultralytics=ultralytics.__version__))
    save(args.output/'protocol.json',protocol)
    rows, imgs=open_split(manifest,args.data/'prepared-confirmation-v1')
    historic={}
    for split in ('val','test'):
        prior, prior_img=open_split(args.audit/f'{split}_manifest.json',args.data/'prepared-v1')
        historic.update({i:dict(id=i,dhash=r['dhash'],pixel_sha256=r['pixel_sha256']) for i,r in prior.items()})
        del prior, prior_img
    leak=leakage(historic,rows)
    exact, near = ({p[1] for p in leak[key]} for key in ('exact','near'))
    save(args.output/'pixel_audit.json',dict(**leak,excluded_confirmation_ids=sorted(exact|near)))
    for i in (exact|near): del rows[i],imgs[i]
    if not rows or len({r['scene_id'] for r in rows.values()})<2:
        raise ValueError('Insufficient independent confirmation after audit.')
    assign_unique_support(rows)
    print('Locked confirmation:',len(rows),'chips from',len({r['scene_id'] for r in rows.values()}),'scenes; excluded:',len(exact|near),flush=True)
    model=ultralytics.YOLO(str(args.weights))
    report=dict(test_chips=len(rows),test_scene_count=len({r['scene_id'] for r in rows.values()}),
        frozen_sha256=digest(preflight_path),protocol_sha256=digest(args.output/'protocol.json'),models={})
    for name,threshold in (('yolo',cut),('guard_ring_cfar',0.)):
        def infer(ident):
            r=rows[ident]; amplitude=imgs[ident]; gray=normalize(amplitude,'log1p')
            if name=='yolo':
                p=model.predict(Image.fromarray(gray).convert('RGB'),device='cpu',imgsz=640,
                    conf=.01,iou=.7,max_det=1000,verbose=False)[0]
                raw=p.boxes.xyxy.cpu().numpy(),p.boxes.conf.cpu().numpy()
            else:
                raw=cfar_propose(gray,pixels_in_support(r,amplitude),*ring)
            return restrict_to_scoring_support(r,*raw)
        for _ in range(3): infer(next(iter(rows)))
        preds,times={},[]
        for j,ident in enumerate(rows,1):
            ts=time.perf_counter(); preds[ident]=infer(ident); times.append((time.perf_counter()-ts)*1000)
            if j%100==0: print(name,j,'/',len(rows),flush=True)
        m, failures=score(rows,preds,threshold)
        per_scene={}
        for sid in {r['scene_id'] for r in rows.values()}:
            local={i:r for i,r in rows.items() if r['scene_id']==sid}
            per_scene[sid],_=score(local,{i:preds[i] for i in local},threshold)
        report['models'][name]=dict(metrics=m,per_scene=per_scene,threshold=threshold,
            latency_ms_p50=float(np.median(times)), latency_ms_p95=float(np.percentile(times,95)))
        for suffix,value in [('predictions', {i:dict(boxes=b.tolist(),scores=s.tolist()) for i,(b,s) in preds.items()}),
                             ('failures',failures)]:
            with gzip.open(args.output/f'{name}_{suffix}.json.gz','wt') as f: json.dump(value,f)
        save(args.output/'results.json',report)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('data','audit','fresh','prior','output','weights'):
        p.add_argument('--'+name,required=True,type=Path)
    run(p.parse_args())
