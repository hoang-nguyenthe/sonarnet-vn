"""Publish reproducible, explicitly experimental YOLO evidence on real SAR."""
import hashlib
import argparse
import json
import sys
import tomllib
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
import torch
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from sonarnet.data.copernicus import access_token, sentinel1_preview


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bbox', nargs=4, type=float, default=[107.86, 10.40, 107.94, 10.48])
    parser.add_argument('--output', default='assets/real_evidence')
    parser.add_argument('--width', type=int, default=768)
    parser.add_argument('--device', default='auto')
    parser.add_argument('--reuse-image', action='store_true')
    args = parser.parse_args()
    device = ('mps' if torch.backends.mps.is_available() else 'cpu') if args.device == 'auto' else args.device
    bbox = args.bbox
    reference = json.loads((ROOT / 'assets/sentinel1_binh_thuan_20260912.json').read_text())
    if args.reuse_image:
        prior = json.loads((ROOT / args.output / 'manifest.json').read_text())
        if prior['bbox'] != bbox:
            raise ValueError('Cached image bounds do not match the requested AOI')
        raw = (ROOT / args.output / 'sar.png').read_bytes()
    else:
        with (ROOT / '.streamlit/secrets.toml').open('rb') as handle:
            config = tomllib.load(handle)['copernicus']
        token = access_token(config['client_id'], config['client_secret'])
        raw = sentinel1_preview(token, tuple(bbox), reference['acquired_at'], width=args.width)
    rgba = Image.open(BytesIO(raw)).convert('RGBA')
    rgba.load()
    if np.mean(np.array(rgba)[:, :, 3] > 0) < .9:
        raise RuntimeError('Insufficient valid SAR pixels; do not publish')
    weights = ROOT / 'sonarnet_run/runs/yolo_sar/weights/best.pt'
    model = YOLO(str(weights))
    rgb = rgba.convert('RGB')
    result = model.predict(rgb, conf=.35, imgsz=args.width, device=device, verbose=False)[0]
    destination = ROOT / args.output
    destination.mkdir(exist_ok=True, parents=True)
    rgba.save(destination / 'sar.png')
    annotated = rgb.copy()
    drawing = ImageDraw.Draw(annotated)
    boxes = []
    for index, box in enumerate(result.boxes):
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        x, y = (x1+x2)/2, (y1+y2)/2
        drawing.rectangle([x1,y1,x2,y2], outline='#ffd36a', width=2)
        drawing.text((x1,max(0,y1-14)), f'#{index+1} {float(box.conf[0]):.2f}', fill='#ffd36a')
        boxes.append({'id': index+1, 'bbox_px': [x1,y1,x2,y2],
                      'confidence': float(box.conf[0]),
                      'longitude': bbox[0]+x/rgb.width*(bbox[2]-bbox[0]),
                      'latitude': bbox[3]-y/rgb.height*(bbox[3]-bbox[1])})
    annotated.save(destination / 'detections.jpg')
    metadata = {'source': 'Copernicus Data Space · Sentinel-1 GRD', 'device': device,
                'reference_product': reference['product_id'],
                'observation_day_utc': reference['acquired_at'][:10],
                'time_scope': 'Daily Process API mosaic; reference product is not an exact per-pixel attribution',
                'bbox': bbox, 'image_size': list(rgb.size), 'confidence_threshold': .35,
                'weights_sha256': hashlib.sha256(weights.read_bytes()).hexdigest(),
                'image_sha256': hashlib.sha256(raw).hexdigest(),
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'validation': 'Model trained on synthetic SAR; real-domain accuracy not validated. Candidates only, not confirmed vessels or fishing classification.',
                'detections': boxes}
    (destination / 'manifest.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
    print(f'Published experimental inference: {len(boxes)} candidates, {rgb.size}')


if __name__ == '__main__':
    main()
