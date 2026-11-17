"""Evaluate frozen YOLO weights and a validation-tuned baseline on one audited SAR holdout."""
import argparse
import csv
from datetime import datetime,timezone
import json
import platform
from pathlib import Path
import sys
import time
import numpy as np
from PIL import Image, ImageDraw, ImageFont
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from sonarnet.evaluation.independent_sar import audit_manifest,operational_metrics,sha256
from benchmark_sar_archive import detect


def export_error_gallery(output, name, base, rows, predictions, failures, threshold):
    """Deterministically show both worst false-alarm and worst missed-ship images."""
    by_id={r['id']:r for r in rows}
    import matplotlib
    font=ImageFont.truetype(str(Path(matplotlib.get_data_path())/'fonts/ttf/DejaVuSans.ttf'),14)
    selected=[]
    for key in ['false_positive_indices','false_negative_indices']:
        for failure in sorted(failures,key=lambda f:(-len(f[key]),f['id']))[:3]:
            if failure['id'] not in {f['id'] for f in selected} and failure[key]: selected.append(failure)
    gallery=[]
    for f in selected:
        row=by_id[f['id']]
        with Image.open(base/row['image']) as source: picture=source.convert('RGB')
        canvas=Image.new('RGB',(picture.width,picture.height+60),'#10283a');canvas.paste(picture,(0,60))
        draw=ImageDraw.Draw(canvas)
        draw.text((12,10),f"{name} | {f['id']} | FP={len(f['false_positive_indices'])} FN={len(f['false_negative_indices'])}",fill='white',font=font)
        draw.text((12,32),'CYAN: source labels | ORANGE: predictions above selected threshold',fill='white',font=font)
        def shifted(b):return [float(b[0]),float(b[1])+60,float(b[2]),float(b[3])+60]
        for box in row['boxes_xyxy']:draw.rectangle(shifted(box),outline='#4de4ee',width=2)
        boxes,scores=predictions[row['id']]
        for box,score in zip(boxes,scores):
            if score>=threshold:draw.rectangle(shifted(box),outline='#ff9944',width=2)
        path=output/f'{name}_error_{row["id"]}.png';canvas.save(path)
        gallery.append(dict(id=row['id'],scene_id=row['scene_id'],file=path.name,
            false_positives=len(f['false_positive_indices']),missed_ships=len(f['false_negative_indices']),
            selection='Top three false alarms or missed ground-truth boxes; ties by image id'))
    return gallery


def run(args):
    manifest=json.loads(args.manifest.read_text());base=args.manifest.parent
    audit=audit_manifest(manifest,base)
    if not audit['passed']: raise ValueError('Dataset audit has not passed')
    from ultralytics import YOLO
    import torch
    torch.set_num_threads(4)
    model=YOLO(str(args.weights))
    val=[r for r in manifest['images'] if r['split']=='val']
    test=[r for r in manifest['images'] if r['split']=='test']
    # Derive exact raster area from the files. Do not alter the frozen manifest
    # or infer physical metres from an assumed sensor resolution.
    for row in val+test:
        with Image.open(base/row['image']) as im:row['image_pixel_area']=im.width*im.height
    args.output.mkdir(parents=True,exist_ok=True)
    def predict(im):
        r=model.predict(im,imgsz=args.imgsz,device='cpu',conf=.001,iou=.7,max_det=1000,verbose=False)[0]
        return r.boxes.xyxy.cpu().numpy(),r.boxes.conf.cpu().numpy()
    report=dict(created_at=datetime.now(timezone.utc).isoformat(),hardware=platform.platform(),
        device='cpu',threads=4,weights_sha256=sha256(args.weights),manifest_sha256=sha256(args.manifest),
        evaluator_sha256=sha256(Path(__file__)),
        metric_code_sha256=sha256(ROOT/'src/sonarnet/evaluation/independent_sar.py'),
        ap_code_sha256=sha256(ROOT/'src/sonarnet/evaluation/detection_metrics.py'),
        audit=audit,counts={'val':len(val),'test':len(test)},
        ap_definition='Single-class VOC integral AP, averaged over IoU .50:.05:.95. Not identical to COCO/Ultralytics AP.',
        latency_definition='Single-image wall time including preprocessing/inference/NMS; excludes file I/O, three warmups.',
        models={},limitations=[manifest.get('metric_limits',''),manifest.get('nearshore_definition',''),
            'Pixel localization errors are conditional on IoU>=0.5 true positives; missed ships are counted separately.',
            'False alarms per megapixel use the full image raster including land; this is not maritime km2.'])
    for name in ['global_threshold','yolo_rebuilt']:
        predictions={}
        grid=[.55,.7,.85] if name=='global_threshold' else [.1,.25,.4,.6]
        tuning=[]
        if name=='yolo_rebuilt':
            for row in val:
                with Image.open(base/row['image']) as im: predictions[row['id']]=predict(im.convert('RGB'))
        for threshold in grid:
            if name=='global_threshold':
                predictions={}
                for row in val:
                    with Image.open(base/row['image']) as im:
                        predictions[row['id']]=detect(im,name,threshold)
            metrics,_=operational_metrics(val,predictions,0 if name=='global_threshold' else threshold)
            tuning.append((metrics['f1'],threshold))
        selected=max(tuning)[1]
        predictions={};latencies=[]
        with Image.open(base/test[0]['image']) as im:
            for _ in range(3): predict(im.convert('RGB')) if name=='yolo_rebuilt' else detect(im,name,selected)
        for n,row in enumerate(test):
            with Image.open(base/row['image']) as im: image=im.convert('RGB')
            start=time.perf_counter()
            predictions[row['id']]=predict(image) if name=='yolo_rebuilt' else detect(image,name,selected)
            latencies.append((time.perf_counter()-start)*1000)
            if n%200==0: print(f'{name}: {n}/{len(test)}',flush=True)
        metrics,failures=operational_metrics(test,predictions,selected if name=='yolo_rebuilt' else 0)
        metrics.update(latency_ms_median=float(np.median(latencies)),latency_ms_p95=float(np.percentile(latencies,95)))
        scene_rows=[]
        for scene in sorted({r['scene_id'] for r in test}):
            subset=[r for r in test if r['scene_id']==scene]
            scene_predictions={r['id']:predictions[r['id']] for r in subset}
            sm,_=operational_metrics(subset,scene_predictions,selected if name=='yolo_rebuilt' else 0)
            scene_rows.append(dict(scene_id=scene,images=len(subset),**sm))
        gallery=export_error_gallery(args.output,name,base,test,predictions,failures,selected if name=='yolo_rebuilt' else 0)
        report['models'][name]=dict(validation_grid=tuning,selected_threshold=selected,metrics=metrics,
                                   per_scene=scene_rows,error_gallery=gallery)
        with (args.output/f'{name}_per_scene.csv').open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(scene_rows[0]));writer.writeheader();writer.writerows(scene_rows)
        (args.output/f'{name}_failures.json').write_text(json.dumps(failures,indent=2))
        (args.output/f'{name}_predictions.json').write_text(json.dumps({k:{'boxes':v[0].tolist(),'scores':v[1].tolist()} for k,v in predictions.items()}))
        (args.output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,required=True);p.add_argument('--weights',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--imgsz',type=int,default=640)
    run(p.parse_args())
