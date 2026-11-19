"""Evaluate weak-box transfer from a real SAR checkpoint to Vietnamese RTC."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
from PIL import Image
from shapely import intersects_xy
import torch
from ultralytics import YOLO

from evaluate_rtc_point_detector import MODES, METHODS, VALIDATION_DAYS, day, read_cases, score_case
from evaluate_review_ranking import save
from evaluate_sar_multiscale import detect
from land_mask import get_mask
from score_vn_reference_rtc import ROOT, digest, raster_points

INITIAL = ROOT/'assets/models/sonarnet_ls_ssdd_20261117.pt'
BOX_PIXELS = 7
SEED = 20261119


def grey(chip):
    return np.rint(chip['input'][0]*255).astype(np.uint8)


def write_dataset(root, development):
    entries = []
    for row in development:
        split = 'val' if day(row) in VALIDATION_DAYS else 'train'
        images = root/'images'/split
        labels = root/'labels'/split
        images.mkdir(parents=True,exist_ok=True)
        labels.mkdir(parents=True,exist_ok=True)
        for number,chip in enumerate(row['chips']):
            name = f'{day(row)}-{number:03}'
            h,w = chip['water'].shape
            centres = chip['xy'] + .5
            eligible = np.all((centres >= BOX_PIXELS/2) & (centres <= [w-BOX_PIXELS/2,h-BOX_PIXELS/2]),axis=1)
            centres = centres[eligible]
            image, label = images/f'{name}.png', labels/f'{name}.txt'
            Image.fromarray(grey(chip)).save(image)
            label.write_text(''.join(f'0 {cx/w:.7f} {cy/h:.7f} {BOX_PIXELS/w:.7f} {BOX_PIXELS/h:.7f}\n'
                                     for cx,cy in centres))
            entries.append(dict(scene=row['scene'],split=split,image=image.relative_to(root).as_posix(),
                                points=len(centres),image_sha256=digest(image),label_sha256=digest(label)))
    config = root/'data.yaml'
    config.write_text(f'path: "{root.resolve()}"\ntrain: images/train\nval: images/val\nnames: {{0: ship}}\n')
    save(root/'inputs.json',entries)
    return config, entries


def proposals(model, case):
    output = []
    for chip in case['chips']:
        if chip['support'].is_empty or not chip['water'].any():
            continue
        boxes,scores = detect(model,grey(chip),640)
        xy = (boxes[:,:2]+boxes[:,2:])/2
        h,w = chip['water'].shape
        indices = np.clip(xy.astype(int),[0,0],[w-1,h-1])
        lon,lat = raster_points(xy,chip['bbox'],(h,w))
        keep = chip['water'][indices[:,1],indices[:,0]] & intersects_xy(chip['support'],lon,lat)
        output.extend(np.c_[lon[keep],lat[keep],scores[keep]].tolist())
    return sorted(output,key=lambda row:-row[2])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('development','held-out','confirmation','cached-neural','confirmation-cache','out'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--epochs',type=int,default=8)
    args = p.parse_args()
    out = args.out
    out.mkdir(exist_ok=False)
    device = 'mps' if torch.backends.mps.is_available() else 'cpu'
    torch.set_num_threads(3)
    mask=get_mask(ROOT)
    groups = {'development':(args.development,args.cached_neural/'development_features.json.gz'),
              'held_out':(args.held_out,args.cached_neural/'fresh_features.json.gz'),
              'confirmation':(args.confirmation,args.confirmation_cache)}
    development=list(read_cases(*groups['development'],lambda c:True,mask))
    config,entries=write_dataset(out/'dataset',development)
    training=dict(data=str(config.resolve()),epochs=args.epochs,imgsz=512,batch=8,device=device,workers=0,
                  freeze=7,warmup_epochs=1,lr0=.001,optimizer='AdamW',seed=SEED,deterministic=True,amp=False,
                  hsv_h=0,hsv_s=0,hsv_v=.08,degrees=0,translate=.08,scale=.1,flipud=.5,fliplr=.5,
                  mosaic=0,mixup=0,plots=False,project=str(out.resolve()),name='train',exist_ok=True)
    save(out/'protocol.json',dict(
        started_utc=datetime.now(timezone.utc).isoformat(),source_sha256=digest(Path(__file__)),
        heatmap_dependencies_sha256=digest(ROOT/'scripts/evaluate_rtc_point_detector.py'),
        initialization=INITIAL.name,initial_sha256=digest(INITIAL),
        dataset_sha256=digest(config.with_name('inputs.json')),training=training,
        target='7x7 px proxy box around each published center point, not a measured hull box',
        selector='Select review strategy using two development days at the same review count. Ties prefer the smaller YOLO replacement quota.',
        validation_days=VALIDATION_DAYS,
        inputs={key:dict(raster_manifest_sha256=digest(root/'rtc-512/manifest.json'),baseline_cache_sha256=digest(cache))
                for key,(root,cache) in groups.items()},
        counts={split:{'images':sum(e['split']==split for e in entries),
                       'point_labels':sum(e['points'] for e in entries if e['split']==split)}
                for split in ('train','val')},
    ))
    YOLO(str(INITIAL)).train(**training)
    checkpoint=out/'train/weights/best.pt'
    model=YOLO(str(checkpoint))
    validation=[score_case(row,proposals(model,row)) for row in development if day(row) in VALIDATION_DAYS]
    selected={}
    for mode in MODES:
        totals={method:sum(row[mode][method][100]['matched'] for row in validation)
                for method in ('baseline',*METHODS)}
        selected[mode]=max(reversed(METHODS),key=totals.__getitem__)
        print(mode,selected[mode],totals,flush=True)
    save(out/'selection.json',dict(selected=selected,checkpoint_sha256=digest(checkpoint),
                                  locked_at=datetime.now(timezone.utc).isoformat(),validation=validation))
    result=dict(selection_sha256=digest(out/'selection.json'),selected=selected,test={})
    used={day(row) for row in development}
    for group,(root,cache) in groups.items():
        if group=='development':
            continue
        cases=[]
        for row in read_cases(root,cache,lambda c:True,mask):
            if day(row) in used:
                raise ValueError('Acquisition day reused in testing')
            score=score_case(row,proposals(model,row))
            cases.append(score)
            print(group,day(row),[(mode,score[mode][selected[mode]][100]['matched']) for mode in MODES],flush=True)
        result['test'][group]=cases
        save(out/'results.json',result)


if __name__=='__main__':
    main()
