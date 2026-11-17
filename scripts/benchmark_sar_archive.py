"""Reproducible classical baselines on real CAESAR Sentinel imagery.

This benchmark is NOT evaluation of the unavailable fine-tuned YOLO weights.
No invented acquisition coordinates, coastal truth, or physical resolution.
"""
import argparse, hashlib, json, platform, re, sys, time, zipfile
from collections import Counter
from io import BytesIO
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from sonarnet.evaluation.independent_sar import operational_metrics
from sonarnet.evaluation.detection_metrics import box_iou

EXPECTED='6a185fbf2f51408d19ca941745581a8e1aabbacd33db6494985621086495481e'

def detect(image, kind, threshold):
    a=np.asarray(image.convert('L'),dtype=float)/255
    if kind=='local_contrast':
        mean=ndimage.uniform_filter(a,21)
        variance=np.maximum(ndimage.uniform_filter(a*a,21)-mean*mean,1e-5)
        signal=(a-mean)/np.sqrt(variance)
    else:
        signal=a
    mask=ndimage.binary_closing(signal>threshold,iterations=1)
    labels,count=ndimage.label(mask)
    boxes,scores=[],[]
    for i,sl in enumerate(ndimage.find_objects(labels),1):
        if sl is None: continue
        ys,xs=sl; component=labels[sl]==i
        if component.sum()<3 or component.sum()>3000: continue
        boxes.append([max(0,xs.start-2),max(0,ys.start-2),min(a.shape[1],xs.stop+2),min(a.shape[0],ys.stop+2)])
        scores.append(float(signal[sl][component].mean()))
    scores=np.asarray(scores)
    # Positive monotonic mapping for ranked AP, independent of labels.
    scores=scores/(1+scores)
    return np.asarray(boxes).reshape(-1,4),scores

def run(archive,output,limit):
    output.mkdir(parents=True,exist_ok=True)
    with archive.open('rb') as f: digest=hashlib.file_digest(f,'sha256').hexdigest()
    if digest!=EXPECTED: raise ValueError('Source checksum differs')
    with zipfile.ZipFile(archive) as z:
        names=sorted(n for n in z.namelist() if '/Sen_' in n and n.endswith('.jpg'))
        rows=[]; seen={}; skipped=Counter(); counts=Counter()
        for name in names:
            m=re.search(r'_0(20\d{6})',name)
            if not m: skipped['missing_date']+=1;continue
            day=m.group(1); bucket=int(hashlib.sha256(day.encode()).hexdigest()[:8],16)%100
            split='test' if bucket<15 else 'val' if bucket<30 else 'train'
            raw=z.read(name); im=Image.open(BytesIO(raw)).convert('RGB')
            pixel_hash=hashlib.sha256(im.tobytes()).hexdigest()
            if pixel_hash in seen: skipped['exact_duplicate']+=1;continue
            seen[pixel_hash]=split; counts[split]+=1
            if split=='train' or sum(r['split']==split for r in rows)>=limit:continue
            w,h=im.size; boxes=[]
            for line in z.read(str(Path(name).with_suffix('.txt'))).decode().splitlines():
                cls,x,y,bw,bh=map(float,line.split())
                boxes.append([(x-bw/2)*w,(y-bh/2)*h,(x+bw/2)*w,(y+bh/2)*h])
            rows.append(dict(id=Path(name).stem,archive_member=name,split=split,date_group=day,
                             sha256_pixels=pixel_hash,boxes_xyxy=boxes))
        images={r['id']:Image.open(BytesIO(z.read(r['archive_member']))).convert('RGB') for r in rows}
    val=[r for r in rows if r['split']=='val']; test=[r for r in rows if r['split']=='test']
    report=dict(dataset='Real CAESAR Sentinel subset',archive_sha256=digest,
        source='https://github.com/CAESAR-Radi/SAR-Ship-Dataset/tree/2021-04-update',
        hardware=platform.platform()+' / '+platform.machine(),python=sys.version,
        cohort_counts=dict(counts),evaluated_counts={'val':len(val),'test':len(test)},skipped=dict(skipped),
        split='SHA256 filename acquisition-date token; exact pixel deduplication; first N sorted per split',
        limitations=['Scene/region metadata unavailable; date is inferred from filename.',
            'No physical GSD/valid-area/nearshore labels; corresponding metrics are null.',
            'Classical baseline comparison only. Fine-tuned YOLO checkpoint unavailable.',
            'No claim that scene/region split or near-duplicate audit has passed.'],models={})
    for kind,grid in [('global_threshold',[.55,.7,.85]),('local_contrast',[2.,3.,4.])]:
        tuning=[]
        for threshold in grid:
            pred={r['id']:detect(images[r['id']],kind,threshold) for r in val}
            metrics,_=operational_metrics(val,pred,0.)
            tuning.append((metrics['f1'],threshold))
        best=max(tuning)[1]; prediction={}; times=[]
        detect(images[test[0]['id']],kind,best) # warm-up excluded
        for row in test:
            start=time.perf_counter(); prediction[row['id']]=detect(images[row['id']],kind,best)
            times.append((time.perf_counter()-start)*1000)
        metrics,failures=operational_metrics(test,prediction,0.)
        metrics.update(latency_ms_median=float(np.median(times)),latency_ms_p95=float(np.percentile(times,95)))
        report['models'][kind]=dict(threshold=best,validation_grid=tuning,metrics=metrics)
        (output/(kind+'_failures.json')).write_text(json.dumps(failures,indent=2))
        samples=sorted(failures,key=lambda r:len(r['false_positive_indices'])+len(r['false_negative_indices']),reverse=True)[:4]
        for idx,f in enumerate(samples):
            im=images[f['id']].copy(); draw=ImageDraw.Draw(im)
            truth=next(r['boxes_xyxy'] for r in test if r['id']==f['id'])
            for box in truth:draw.rectangle(box,outline='lime',width=2)
            for box in prediction[f['id']][0]:draw.rectangle(box.tolist(),outline='red',width=1)
            im.save(output/f'{kind}_error_{idx}.png')
        (output/(kind+'_predictions.json')).write_text(json.dumps({k:dict(boxes=v[0].tolist(),scores=v[1].tolist()) for k,v in prediction.items()}))
    (output/'cohort.json').write_text(json.dumps(rows,indent=2))
    (output/'results.json').write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False))
    print(json.dumps(report,indent=2,ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--archive',type=Path,default=Path('data_external/sar_ship/legacy_v0.zip'));p.add_argument('--output',type=Path,default=Path('reports/final/sar_baselines'));p.add_argument('--limit',type=int,default=300)
    args=p.parse_args();run(args.archive,args.output,args.limit)
