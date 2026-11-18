"""Export deterministic diagnostic images without changing the frozen scores."""
import argparse
import gzip
import json
from pathlib import Path

import matplotlib
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from evaluate_opensar_geo import open_split, assign_unique_support, normalize
from prepare_opensar_geo import save


def main(args):
    errors = json.loads((args.evaluation/'yolo_failures.json').read_text())
    with gzip.open(args.evaluation/'yolo_predictions.json.gz','rt') as f:
        preds = json.load(f)
    rows, amp = open_split(args.audit/'test_manifest.json', args.data/'prepared-v1')
    assign_unique_support(rows)
    result = json.loads((args.evaluation/'results.json').read_text())
    threshold = result['models']['yolo']['param']
    chosen = {}
    for k, why in [('false_positive_indices','most_unmatched_predictions'),('false_negative_indices','most_missed_vessel_labels')]:
        f = sorted(errors,key=lambda t:(-len(t[k]),int(t['id'])))[0]
        if f[k]:
            chosen.setdefault(f['id'], [f, []])[1].append(why)
    def near_misses(f):
        count = 0
        for j in f['false_negative_indices']:
            dist = rows[f['id']]['target_labels'][j]['sea_distance_to_shore_m']
            count += dist is not None and dist <= 500
        return count
    f = sorted(errors,key=lambda t:(-near_misses(t),int(t['id'])))[0]
    if near_misses(f):
        chosen.setdefault(f['id'],[f,[]])[1].append('most_misses_within_500m_of_mapped_shore')
    args.output.mkdir(parents=True,exist_ok=True)
    fontpath=Path(matplotlib.get_data_path())/'fonts/ttf/DejaVuSans.ttf'
    big, small=(ImageFont.truetype(str(fontpath), size) for size in (16,13))
    gallery=[]
    for ident,(f,why) in chosen.items():
        r=rows[ident]
        img=Image.new('RGB',(512,604),'#102b40')
        img.paste(Image.fromarray(normalize(amp[ident],'log1p')).convert('RGB'),(0,67))
        d=ImageDraw.Draw(img)
        d.text((12,8),f'OpenSAR Insight | SLC VV | tile {ident}',font=big,fill='white')
        d.text((12,32),f"{r['day']} UTC | FP={len(f['false_positive_indices'])} | FN={len(f['false_negative_indices'])}",font=small,fill='#b9d9e3')
        d.text((12,583),'CYAN labels  /  ORANGE matched  /  RED unmatched prediction',font=small,fill='white')
        def rectangle(box, color):
            x,y,c,e=box
            d.rectangle([float(np.clip(x,0,511)),float(np.clip(y,0,511))+67,float(np.clip(c,0,511)),float(np.clip(e,0,511))+67],outline=color,width=2)
        for xyxy in r['boxes_xyxy']:
            rectangle(xyxy,'#50e8ff')
        missed=set(f['false_positive_indices'])
        for j,(xyxy,conf) in enumerate(zip(preds[ident]['boxes'],preds[ident]['scores'])):
            if conf >= threshold:
                rectangle(xyxy,'#ff475e' if j in missed else '#ffb453')
        filename=f'error_slc_{ident}.png'
        img.save(args.output/filename)
        gallery.append(dict(id=ident,file=filename,scene=r['scene_id'],reasons=why,
                            fp=len(missed),fn=len(f['false_negative_indices']),nearshore_missed=near_misses(f)))
    save(args.output/'gallery.json',gallery)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for opt in ('data','audit','evaluation','output'):
        p.add_argument('--'+opt,type=Path,required=True)
    main(p.parse_args())
