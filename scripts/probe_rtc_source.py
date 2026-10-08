"""Cloud-only bounded integration test: read a cell, run existing model/mask.

Writes diagnostic artifacts only. Does not publish or replace observations.
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from sonarnet.data.planetary import search_rtc, render_rtc, provenance
from refresh_detailed_scan import infer_tile, resolution_m
from land_mask import get_mask


def main():
    from ultralytics import YOLO
    bbox = [109.2, 13.2, 109.3, 13.3]
    today = datetime.now(timezone.utc).date()
    products = search_rtc(bbox, today-timedelta(days=30), today)
    if not products:
        raise RuntimeError('No recent VV RTC scene at probe cell')
    product = products[0]
    raw = render_rtc(product, bbox)
    image = Image.open(BytesIO(raw)).convert('RGBA')
    image.load()
    fraction = float(np.mean(np.asarray(image)[:,:,3] > 0))
    if fraction < .5 or resolution_m(bbox, image.size) > 25:
        raise RuntimeError('Probe has insufficient valid pixels or pixel spacing')
    mask = get_mask(ROOT)
    audit = {}
    weights = ROOT/'assets/models/sonarnet_baseline.pt'
    rows, annotated = infer_tile(YOLO(str(weights)), image, bbox, mask=mask, audit=audit)
    output = ROOT/'artifacts/rtc-probe'
    output.mkdir(parents=True, exist_ok=True)
    (output/'sar.png').write_bytes(raw)
    annotated.save(output/'detections.jpg')
    result = dict(provenance(product), bbox=bbox, image_size=list(image.size),
                  valid_pixel_fraction=fraction, image_sha256=hashlib.sha256(raw).hexdigest(),
                  weights_sha256=hashlib.sha256(weights.read_bytes()).hexdigest(),
                  detections=rows, inference_audit=audit,
                  validation='Source/inference integration only, NOT detector accuracy validation',
                  checked_at=datetime.now(timezone.utc).isoformat())
    (output/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({k:result[k] for k in ('source_acquired_at','valid_pixel_fraction','image_size','image_sha256')}))
    print(f'Existing detector returned {len(rows)} candidates; no publication performed')


if __name__ == '__main__':
    main()
