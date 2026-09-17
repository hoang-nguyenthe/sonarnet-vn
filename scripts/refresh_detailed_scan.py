#!/usr/bin/env python3
"""Refresh declared high-resolution cells, infer once, then publish atomically.

The overview mosaic is never a detection input. This experimental baseline
remains explicitly labelled in the UI; a refresh does not promote the model.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from io import BytesIO
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw
from shapely import intersects_xy, prepare
from shapely.geometry import box as geometry_box
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from sonarnet.data.copernicus import access_token, search_sentinel1_grd, sentinel1_mosaic_preview
from refresh_global_sentinel_tiles import credentials
from scan_assets import validate_tile

INFERENCE_PIPELINE = 'detailed-vv-preview-land-coast-masked-v2'


def resolution_m(bbox, size):
    west, south, east, north = bbox
    return max(111320 * (north-south) / size[1],
               111320 * math.cos(math.radians((north+south)/2)) * (east-west) / size[0])


def allowed_pixels(image, bbox, mask):
    """Fail closed outside the shoreline mask; never alter the source image."""
    data, geometries = mask
    footprint = geometry_box(*bbox)
    if not geometry_box(*data['coverage_bbox']).covers(footprint):
        raise ValueError('Shoreline mask unavailable for this cell')
    # Clip first: unioning an entire country's full-resolution coastline on
    # every 11 km cell costs far more than the actual inference.
    exclusion = unary_union([geometries['land'].intersection(footprint),
                             geometries['coast'].intersection(footprint)])
    prepare(exclusion)
    w, s, e, n = bbox
    xs = w + (np.arange(image.width) + .5) / image.width * (e-w)
    ys = n - (np.arange(image.height) + .5) / image.height * (n-s)
    allowed = ~intersects_xy(exclusion, xs[None, :], ys[:, None])
    if image.mode == 'RGBA':
        allowed &= np.asarray(image)[:, :, 3] > 0
    return allowed, exclusion


def infer_tile(model, image, bbox, confidence=.35, mask=None, device='cpu', audit=None):
    """Keep georeferencing tied to the exact detailed image dimensions."""
    if resolution_m(bbox, image.size) > 25:
        raise ValueError('Image too coarse for vessel inference; use detailed SAR cells')
    rgb = image.convert('RGB')
    if mask is None:
        from land_mask import get_mask
        mask = get_mask(ROOT)
    allowed, exclusion = allowed_pixels(image, bbox, mask)
    inference_pixels = np.asarray(rgb).copy()
    inference_pixels[~allowed] = 0
    if audit is not None:
        audit.update(input_mask_version=mask[0]['version'], input_mask_buffer_m=mask[0]['coastal_buffer_m'],
                     allowed_pixel_fraction=float(np.mean(allowed)), excluded_candidates=[])
    # Entirely excluded cells do not invoke the network at all. Mixed cells
    # contain black excluded pixels; exact geographic bbox rejection below
    # also removes detections that straddle the mask edge.
    if not np.any(allowed):
        return [], rgb
    prediction = model.predict(Image.fromarray(inference_pixels), imgsz=1024, conf=confidence, device=device, verbose=False)[0]
    annotated = rgb.copy()
    drawing = ImageDraw.Draw(annotated)
    west, south, east, north = bbox
    detections = []
    for i, box in enumerate(prediction.boxes if prediction.boxes is not None else []):
        x1, y1, x2, y2 = map(float, box.xyxy[0].tolist())
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(image.width, x2), min(image.height, y2)
        if not all(math.isfinite(v) for v in (x1, y1, x2, y2)) or x2 <= x1 or y2 <= y1:
            continue
        cx, cy = (x1+x2)/2, (y1+y2)/2
        # Transparent no-data cannot support a detection.
        if image.mode == 'RGBA' and image.getpixel((min(image.width-1, int(cx)), min(image.height-1, int(cy))))[3] == 0:
            continue
        candidate = dict(id=i+1, bbox_px=[x1,y1,x2,y2], confidence=float(box.conf[0]),
                         longitude=west+cx/image.width*(east-west), latitude=north-cy/image.height*(north-south))
        footprint = geometry_box(west+x1/image.width*(east-west), north-y2/image.height*(north-south),
                                 west+x2/image.width*(east-west), north-y1/image.height*(north-south))
        if exclusion.intersects(footprint):
            if audit is not None:
                audit['excluded_candidates'].append(dict(candidate, reason='land_or_coastal_exclusion'))
            continue
        detections.append(candidate)
        drawing.rectangle([x1,y1,x2,y2], outline='#ffd166', width=2)
        drawing.text((x1,max(0,y1-14)), f"#{i+1} {candidate['confidence']:.2f}", fill='#ffd166')
    return detections, annotated


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan-only', action='store_true', help='No network or YOLO; update coverage queue only')
    parser.add_argument('--max-new-cells', type=int, default=0, help='Bounded expansion, 0 by default; max 24 per run')
    parser.add_argument('--region', default='vietnam', help='Published region to expand; default Vietnam')
    parser.add_argument('--device', choices=['cpu', 'mps'], default='cpu')
    args = parser.parse_args(argv)
    if not 0 <= args.max_new_cells <= 24:
        parser.error('--max-new-cells must be between 0 and 24')
    from land_mask import get_mask
    from scan_coverage import write_plan
    report_path = ROOT / 'assets/real_scan/report.json'
    report = json.loads(report_path.read_text())
    mask = get_mask(ROOT)
    plan = write_plan(ROOT, report, mask=mask, limit=args.max_new_cells, region_key=args.region)
    if args.plan_only:
        print(f"Prepared {len(plan['regions'])} observation-region plans; no images fetched or inferred")
        return
    from ultralytics import YOLO
    weights = ROOT / 'assets/models/sonarnet_baseline.pt'
    weights_hash = hashlib.sha256(weights.read_bytes()).hexdigest()
    model = YOLO(str(weights))
    token = access_token(*credentials())
    end = datetime.now(timezone.utc).date()
    updated, checked, failed = 0, 0, 0
    tiles = []
    existing_keys = {tile['key'] for tile in report['tiles']}
    work = list(report['tiles']) + [cell for cell in plan['next_cells'] if cell['key'] not in existing_keys]
    policy = hashlib.sha256((INFERENCE_PIPELINE + mask[0]['version']
                            + hashlib.sha256(mask[1]['land'].wkb + mask[1]['coast'].wkb).hexdigest()).encode()).hexdigest()
    attempts = dict(report.get('scan_attempts', {}))
    for old in work:
        existing = old['key'] in existing_keys
        try:
            if existing:
                validate_tile(ROOT, old)
            if not geometry_box(*mask[0]['coverage_bbox']).covers(geometry_box(*old['bbox'])):
                raise ValueError('No validated shoreline mask for this area')
            products = search_sentinel1_grd(token, tuple(old['bbox']), end-timedelta(days=30), end, limit=50)
            # The current baseline has only a VV input contract. HH imagery
            # remains visible as imagery, not mislabelled as scanned evidence.
            products = [product for product in products if product.polarization in {'DV', 'SV', 'VV'}]
            if not products:
                raise ValueError('No recent catalog acquisition for cell')
            product = max(products, key=lambda item: item.acquired_at)
            checked += 1
            attempts.pop(old['key'], None)
            if (old.get('reference_product') == product.product_id and old.get('weights_sha256') == weights_hash
                    and old.get('inference_policy_sha256') == policy):
                tiles.append(old)
                continue
            if existing and old.get('reference_product') == product.product_id:
                raw = (ROOT / old['asset_dir'] / 'sar.png').read_bytes()
            else:
                acquired_day = date.fromisoformat(product.acquired_at[:10])
                raw = sentinel1_mosaic_preview(token, tuple(old['bbox']), acquired_day, acquired_day,
                                              width=1024, polarization=product.polarization)
            image = Image.open(BytesIO(raw)).convert('RGBA')
            image.load()
            if float(np.mean(np.asarray(image)[:,:,3] > 0)) < .9:
                raise ValueError('Less than 90% valid radar coverage; keep previous observation')
            inference_audit = {}
            candidates, annotated = infer_tile(model, image, old['bbox'], mask=mask, device=args.device, audit=inference_audit)
            image_hash = hashlib.sha256(raw).hexdigest()
            generation = hashlib.sha256((image_hash+weights_hash+policy).encode()).hexdigest()[:16]
            relative = f"assets/real_scan/published/{generation}/{old['key']}"
            destination = ROOT / relative
            destination.mkdir(parents=True, exist_ok=True)
            (destination/'sar.png').write_bytes(raw)
            annotated.save(destination/'detections.jpg', quality=88)
            tile = dict(old, asset_dir=relative, image_size=list(image.size), status='processed',
                        source='Copernicus Data Space · Sentinel-1 GRD', band='VV',
                        time_scope='Daily VV Process API mosaic; reference product is not exact per-pixel attribution',
                        reference_product=product.product_id, observation_day_utc=product.acquired_at[:10],
                        image_sha256=image_hash, weights_sha256=weights_hash, device=args.device,
                        confidence_threshold=.35, inference_policy_sha256=policy,
                        inference_pipeline=INFERENCE_PIPELINE, inference_audit=inference_audit,
                        validation='Synthetic-SAR-trained baseline; candidates require human verification. Real-domain accuracy not validated.',
                        generated_at=datetime.now(timezone.utc).isoformat(), detections=candidates)
            validate_tile(ROOT, tile)
            (destination/'manifest.json').write_text(json.dumps(tile, ensure_ascii=False, indent=2)+'\n')
            tiles.append(tile)
            updated += 1
            print(f"Updated {old['key']}: {len(candidates)} experimental candidates on {tile['observation_day_utc']}", flush=True)
        except Exception as error:
            # One unavailable scene must not erase the last usable evidence.
            if existing:
                tiles.append(old)
            failed += 1
            now = datetime.now(timezone.utc)
            attempts[old['key']] = {'last_checked_at': now.isoformat(),
                                    'retry_after': (now+timedelta(hours=6)).isoformat(),
                                    'status': 'retry_later', 'error_type': type(error).__name__}
            print(f"Retained {old['key']}: {type(error).__name__}", flush=True)
    if updated:
        report.update(tiles=tiles, generated_at=datetime.now(timezone.utc).isoformat(),
                      observation_day_utc=max(tile['observation_day_utc'] for tile in tiles),
                      date_scope='Each tile retains its own UTC observation day; headline is the newest day.')
    report['scan_attempts'] = attempts
    pending = report_path.with_suffix('.pending.json')
    pending.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    pending.replace(report_path)
    write_plan(ROOT, report, mask=mask, limit=12, region_key=args.region)
    print(f'Catalog checked {checked}/{len(tiles)}; updated {updated}; retained after error {failed}')
    if not checked:
        raise RuntimeError('No catalog checks succeeded; previous image evidence retained')


if __name__ == '__main__':
    main()
