"""Explore inference resolution using validation images only.

This follow-up is motivated by known weaknesses of the initial held-out run.
It does not turn that already inspected test set into a fresh confirmation set.
Existing model weights and historical evaluation outputs are never overwritten.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import sys
import time

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from sonarnet.evaluation.independent_sar import operational_metrics, sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--weights', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    sizes, thresholds = [640, 800, 1024], [.1, .25, .4, .6]
    manifest = json.loads(args.manifest.read_text())
    rows = [r for r in manifest['images'] if r['split'] == 'val']
    assert rows and all(r['split'] == 'val' for r in rows)
    protocol = dict(created_at=datetime.now(timezone.utc).isoformat(), split='val',
        image_count=len(rows), image_ids=[r['id'] for r in rows],
        manifest_sha256=sha256(args.manifest), weights_sha256=sha256(args.weights),
        code_sha256=sha256(Path(__file__)), sizes=sizes, confidence_grid=thresholds,
        nms_iou=.7, max_det=1000, device='cpu', threads=4,
        selection='Maximum validation F1; ties prefer smaller input size then higher confidence.',
        disclosure='Post-test exploratory follow-up; no new test results or independent confirmation claim.',
        hardware=platform.platform(), latency='Single image preprocessing, inference and NMS; excludes file I/O; 3 warmups.')
    (args.output/'protocol.json').write_text(json.dumps(protocol, indent=2))
    # Only the selected validation files are opened, never train/test pixels.
    for row in rows:
        path = args.manifest.parent/row['image']
        if sha256(path) != row['sha256']:
            raise ValueError('Validation image checksum mismatch: '+row['id'])
        with Image.open(path) as image:
            row['image_pixel_area'] = image.width*image.height
    import torch
    from ultralytics import YOLO
    torch.set_num_threads(4)
    model = YOLO(str(args.weights))
    report = dict(protocol=protocol, candidates=[])
    for size in sizes:
        def predict(image):
            result = model.predict(image, imgsz=size, device='cpu', conf=.001,
                iou=.7, max_det=1000, verbose=False)[0]
            return result.boxes.xyxy.cpu().numpy(), result.boxes.conf.cpu().numpy()
        with Image.open(args.manifest.parent/rows[0]['image']) as image:
            for _ in range(3):
                predict(image.convert('RGB'))
        predictions, latencies = {}, []
        for i, row in enumerate(rows):
            with Image.open(args.manifest.parent/row['image']) as source:
                image = source.convert('RGB')
            start = time.perf_counter()
            predictions[row['id']] = predict(image)
            latencies.append((time.perf_counter()-start)*1000)
            if i % 100 == 0:
                print(f'{size}px: {i}/{len(rows)}', flush=True)
        for threshold in thresholds:
            metrics, _ = operational_metrics(rows, predictions, threshold)
            report['candidates'].append(dict(input_size=size, confidence=threshold,
                metrics=metrics, latency_ms_median=float(np.median(latencies)),
                latency_ms_p95=float(np.percentile(latencies, 95))))
        (args.output/f'validation_{size}_predictions.json').write_text(json.dumps({
            ident:dict(boxes=boxes.tolist(), scores=scores.tolist())
            for ident,(boxes,scores) in predictions.items()}))
        (args.output/'results.json').write_text(json.dumps(report, indent=2, allow_nan=False))
    report['selected'] = max(report['candidates'], key=lambda r:(r['metrics']['f1'], -r['input_size'], r['confidence']))
    (args.output/'results.json').write_text(json.dumps(report, indent=2, allow_nan=False))
    print(json.dumps(report['selected'], indent=2), flush=True)


if __name__ == '__main__':
    main()
