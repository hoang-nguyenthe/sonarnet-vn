#!/usr/bin/env python3
"""Refresh declared high-resolution cells, infer once, then publish atomically.

The overview mosaic is never a detection input. This experimental baseline
remains explicitly labelled in the UI; a refresh does not promote the model.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from io import BytesIO
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from sonarnet.data.copernicus import access_token, search_sentinel1_grd, sentinel1_preview
from refresh_global_sentinel_tiles import credentials
from scan_assets import validate_tile


def resolution_m(bbox, size):
    west, south, east, north = bbox
    return max(111320 * (north-south) / size[1],
               111320 * math.cos(math.radians((north+south)/2)) * (east-west) / size[0])


def infer_tile(model, image, bbox, confidence=.35):
    """Keep georeferencing tied to the exact detailed image dimensions."""
    if resolution_m(bbox, image.size) > 25:
        raise ValueError('Image too coarse for vessel inference; use detailed SAR cells')
    rgb = image.convert('RGB')
    prediction = model.predict(rgb, imgsz=1024, conf=confidence, device='cpu', verbose=False)[0]
    annotated = rgb.copy()
    drawing = ImageDraw.Draw(annotated)
    west, south, east, north = bbox
    detections = []
    for i, box in enumerate(prediction.boxes if prediction.boxes is not None else []):
        x1, y1, x2, y2 = map(float, box.xyxy[0].tolist())
        cx, cy = (x1+x2)/2, (y1+y2)/2
        # Transparent no-data cannot support a detection.
        if image.mode == 'RGBA' and image.getpixel((min(image.width-1, int(cx)), min(image.height-1, int(cy))))[3] == 0:
            continue
        candidate = dict(id=i+1, bbox_px=[x1,y1,x2,y2], confidence=float(box.conf[0]),
                         longitude=west+cx/image.width*(east-west), latitude=north-cy/image.height*(north-south))
        detections.append(candidate)
        drawing.rectangle([x1,y1,x2,y2], outline='#ffd166', width=2)
        drawing.text((x1,max(0,y1-14)), f"#{i+1} {candidate['confidence']:.2f}", fill='#ffd166')
    return detections, annotated


def main():
    from ultralytics import YOLO
    report_path = ROOT / 'assets/real_scan/report.json'
    report = json.loads(report_path.read_text())
    weights = ROOT / 'assets/models/sonarnet_baseline.pt'
    weights_hash = hashlib.sha256(weights.read_bytes()).hexdigest()
    model = YOLO(str(weights))
    token = access_token(*credentials())
    end = datetime.now(timezone.utc).date()
    updated, checked, failed = 0, 0, 0
    tiles = []
    for old in report['tiles']:
        try:
            validate_tile(ROOT, old)
            products = search_sentinel1_grd(token, tuple(old['bbox']), end-timedelta(days=30), end, limit=50)
            if not products:
                raise ValueError('No recent catalog acquisition for cell')
            product = max(products, key=lambda item: item.acquired_at)
            checked += 1
            if (old.get('reference_product') == product.product_id and old.get('weights_sha256') == weights_hash):
                tiles.append(old)
                continue
            raw = sentinel1_preview(token, tuple(old['bbox']), product.acquired_at, width=1024)
            image = Image.open(BytesIO(raw)).convert('RGBA')
            image.load()
            if float(np.mean(np.asarray(image)[:,:,3] > 0)) < .9:
                raise ValueError('Less than 90% valid radar coverage; keep previous observation')
            candidates, annotated = infer_tile(model, image, old['bbox'])
            image_hash = hashlib.sha256(raw).hexdigest()
            generation = hashlib.sha256((image_hash+weights_hash).encode()).hexdigest()[:16]
            relative = f"assets/real_scan/published/{generation}/{old['key']}"
            destination = ROOT / relative
            destination.mkdir(parents=True, exist_ok=True)
            (destination/'sar.png').write_bytes(raw)
            annotated.save(destination/'detections.jpg', quality=88)
            tile = dict(old, asset_dir=relative, image_size=list(image.size),
                        reference_product=product.product_id, observation_day_utc=product.acquired_at[:10],
                        image_sha256=image_hash, weights_sha256=weights_hash, device='cpu',
                        generated_at=datetime.now(timezone.utc).isoformat(), detections=candidates)
            validate_tile(ROOT, tile)
            (destination/'manifest.json').write_text(json.dumps(tile, ensure_ascii=False, indent=2)+'\n')
            tiles.append(tile)
            updated += 1
            print(f"Updated {old['key']}: {len(candidates)} experimental candidates on {tile['observation_day_utc']}")
        except Exception as error:
            # One unavailable scene must not erase the last usable evidence.
            tiles.append(old)
            failed += 1
            print(f"Retained {old['key']}: {type(error).__name__}")
    if not checked:
        raise RuntimeError('No catalog checks succeeded; previous report retained')
    if updated:
        report.update(tiles=tiles, generated_at=datetime.now(timezone.utc).isoformat(),
                      observation_day_utc=max(tile['observation_day_utc'] for tile in tiles),
                      date_scope='Each tile retains its own UTC observation day; headline is the newest day.')
        pending = report_path.with_suffix('.pending.json')
        pending.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
        pending.replace(report_path)
    print(f'Catalog checked {checked}/{len(tiles)}; updated {updated}; retained after error {failed}')


if __name__ == '__main__':
    main()
