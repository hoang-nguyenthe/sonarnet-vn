"""Post-hoc localization/score diagnostics on fixed predictions; never select a model."""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path

import numpy as np
from shapely import from_wkb

from evaluate_opensar_geo import assign_unique_support, pixel_xy
from prepare_opensar_geo import digest, save
from sonarnet.evaluation.detection_metrics import box_iou, evaluate_detections


def diagnose(manifest, audit, predictions):
    src=json.loads(manifest.read_text())
    excluded=set(json.loads(audit.read_text())['excluded_confirmation_ids'])
    rows={r['id']:{**r,'sea':from_wkb(bytes.fromhex(r['valid_sea_wkb_hex']))} for r in src['images']
          if r['id'] not in excluded}
    assign_unique_support(rows)
    with gzip.open(predictions,'rt') as f:
        pred=json.load(f)
    if set(pred)!=set(rows): raise ValueError('Missing or unexpected prediction IDs')
    gt={i:np.array(r['boxes_xyxy']).reshape(-1,4) for i,r in rows.items()}
    scored={i:(np.array(r['boxes']).reshape(-1,4),np.array(r['scores'])) for i,r in pred.items()}
    grid={}
    for conf in (.01,.05,.10):
        for iou in (.25,.50):
            m=evaluate_detections(scored,gt,iou_threshold=iou,score_threshold=conf).to_dict()
            grid[f'conf_{conf:.2f}_iou_{iou:.2f}']={k:m[k] for k in ('true_positive','false_positive','false_negative','precision','recall')}
    near={}
    n=0
    by_scene={}
    for i,r in rows.items():
        stat=by_scene.setdefault(r['scene_id'],Counter())
        b,s=scored[i]; x=gt[i]
        if not len(x):continue
        stat['all_labels']+=len(x); n+=len(x)
        for level in (.01,.10):
            bb=b[s>=level]
            if not len(bb): continue
            xyz=pixel_xy(r['corners_laea_m'],*(np.transpose(x.reshape(-1,2,2).mean(1))))
            pp=pixel_xy(r['corners_laea_m'],*(np.transpose(bb.reshape(-1,2,2).mean(1))))
            distances=np.linalg.norm(xyz[:,None,:]-pp[None,:,:],axis=-1).min(axis=1)
            for metres in (25,50,100):
                k=f'within_{metres}m_after_conf_{level:.2f}'
                stat[k]+=int(np.count_nonzero(distances<=metres))
                near[k]=near.get(k,0)+int(np.count_nonzero(distances<=metres))
    return dict(disclosure='Post-hoc; no candidate chosen or promoted. Nearest centers allow one detection to count for several labels, are not a matching metric, and use the same corner transform as the labels.',
        inputs_sha256={x.name:digest(x) for x in [manifest,audit,predictions]}, labels=n,
        box_iou_sensitivity=grid, nearest_centers_any_overlap=near, by_scene=by_scene)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('manifest','audit','predictions','output'):p.add_argument('--'+key,required=True,type=Path)
    a=p.parse_args();save(a.output,diagnose(a.manifest,a.audit,a.predictions))
