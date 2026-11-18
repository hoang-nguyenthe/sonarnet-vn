"""Measure same-CPU SLC vessel detection on valid ocean, with published XML geometry."""
import argparse
from collections import Counter
from datetime import datetime, timezone
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

import numpy as np
from PIL import Image
from pyproj import Transformer, Geod
from shapely import from_wkb, intersects_xy
import tifffile

from benchmark_sar_archive import detect
from evaluate_ossdd_followup import normalize, difference_hash
from prepare_opensar_geo import ROOT, digest, pixel_xy, save, unique_water_support
from sonarnet.evaluation.detection_metrics import box_iou
from sonarnet.evaluation.independent_sar import operational_metrics

GRID = {'yolo': (.05, .1, .25, .4, .6), 'global_threshold': (.7, .85, .93),
        'local_contrast': (3., 4., 5.)}


def open_split(path, root):
    manifest = json.loads(path.read_text())
    rows = {}
    images = {}
    for r in manifest['images']:
        i = r['id']
        filename = root / r['raster_path']
        if digest(filename) != r['file_sha256'] or i in rows:
            raise ValueError(f'Input integrity error: {i}')
        raw = tifffile.imread(filename)
        valid = np.isfinite(raw) & (raw != 0)
        if int(valid.sum()) != r['valid_pixels']:
            raise ValueError(f'Unexpected mask: {i}')
        amp = np.where(valid, np.abs(raw), 0.)
        images[i] = amp
        r['pixel_sha256'] = hashlib.sha256(raw.astype('<c8').tobytes()).hexdigest()
        r['dhash'] = difference_hash(normalize(amp, 'log1p'))
        r['sea'] = from_wkb(bytes.fromhex(r.pop('valid_sea_wkb_hex')))
        labels = [s for s in r['labels'] if s['evaluated_sea'] and s['is_vessel'] and s['confidence'] in {'HIGH', 'MEDIUM'}]
        r['target_labels'] = labels
        r['boxes_xyxy'] = [s['box'] for s in labels]
        r['ignore_boxes'] = [s['box'] for s in r['labels'] if s['evaluated_sea'] and s['is_vessel'] and s['confidence'] not in {'HIGH', 'MEDIUM'}]
        r['image_pixel_area'] = raw.size
        rows[i] = r
    return rows, images


def leakage(val, test):
    exact, near = [], []
    for a in val.values():
        for b in test.values():
            if a['pixel_sha256'] == b['pixel_sha256']:
                exact.append([a['id'], b['id']])
            elif (a['dhash'] ^ b['dhash']).bit_count() <= 3:
                near.append([a['id'], b['id']])
    return dict(exact=exact, near=near)


def assign_unique_support(rows):
    """Assign shared valid area to the lowest numeric tile ID of an acquisition."""
    for scene in sorted({r['scene_id'] for r in rows.values()}):
        group = sorted((r for r in rows.values() if r['scene_id'] == scene), key=lambda r:int(r['id']))
        for r, sea in zip(group, unique_water_support([r['sea'] for r in group])):
            r['sea'] = sea
            points = [(lab, pixel_xy(r['corners_laea_m'], *lab['xml_center_px'])) for lab in r['labels'] if lab['evaluated_sea']]
            positive = [lab for lab, pt in points if intersects_xy(r['sea'], *pt) and lab['is_vessel']]
            r['target_labels'] = [lab for lab in positive if lab['confidence'] in {'HIGH', 'MEDIUM'}]
            r['boxes_xyxy'] = [lab['box'] for lab in r['target_labels']]
            r['ignore_boxes'] = [lab['box'] for lab in positive if lab['confidence'] not in {'HIGH', 'MEDIUM'}]


def restrict_to_scoring_support(row, boxes, scores):
    if not len(boxes):
        return boxes, scores
    centers = pixel_xy(row['corners_laea_m'], (boxes[:, 0]+boxes[:, 2])/2, (boxes[:, 1]+boxes[:, 3])/2)
    keep = intersects_xy(row['sea'], centers[:, 0], centers[:, 1])
    if row['ignore_boxes']:
        ignore = (box_iou(boxes, np.asarray(row['ignore_boxes'])).max(axis=1) >= .5)
        known = (box_iou(boxes, np.asarray(row['boxes_xyxy'])).max(axis=1) >= .5
                 if row['boxes_xyxy'] else np.zeros(len(boxes), dtype=bool))
        keep &= ~ignore | known
    return boxes[keep], scores[keep]


def dimensions(corner, box):
    a, b, c, d = box
    mid_x, mid_y = (a+c)/2, (b+d)/2
    ab = pixel_xy(corner, [a, c], mid_y)
    cd = pixel_xy(corner, mid_x, [b, d])
    return np.array([np.linalg.norm(ab[1]-ab[0]), np.linalg.norm(cd[1]-cd[0])])


@lru_cache
def geographic_inverse(crs):
    return Transformer.from_crs(crs, 'EPSG:4326', always_xy=True)


def score(rows, preds, threshold):
    metrics, failure = operational_metrics(list(rows.values()), preds, threshold)
    centers, widths, heights, wgs_errors, residuals = [], [], [], [], []
    g = Geod(ellps='WGS84')
    coast_counts = {500: Counter(), 1000: Counter(), 2000: Counter()}
    for f in failure:
        r = rows[f['id']]
        coords = r['corners_laea_m']
        matched = {j for _, j in f['matched_indices']}
        for j, lab in enumerate(r['target_labels']):
            residuals.append(lab['xml_wgs84_to_corner_transform_residual_m'])
            d = lab['sea_distance_to_shore_m']
            for cutoff, count in coast_counts.items():
                if d is not None and d <= cutoff:
                    count['labels'] += 1
                    count['matched'] += j in matched
        inverse = geographic_inverse(r['crs'])
        for i, j in f['matched_indices']:
            pred = preds[r['id']][0][i]
            lab = r['target_labels'][j]
            ref = np.asarray(lab['box'])
            xy = pixel_xy(coords, *(pred[:2]+pred[2:])/2)
            target = pixel_xy(coords, *(ref[:2]+ref[2:])/2)
            centers.append(float(np.linalg.norm(xy-target)))
            w, h = np.abs(dimensions(coords, pred)-dimensions(coords, ref))
            widths.append(float(w)); heights.append(float(h))
            ll = inverse.transform(*xy)
            wgs_errors.append(g.inv(*ll, *lab['xml_center_wgs84'])[2])
    def stats(series):
        return dict(n=len(series), median=float(np.median(series)) if series else None,
                    p95=float(np.percentile(series, 95)) if series else None)
    supports = {}
    for scene in sorted({r['scene_id'] for r in rows.values()}):
        geometries = [r['sea'] for r in rows.values() if r['scene_id'] == scene]
        supports[scene] = sum(g.area for g in geometries)/1e6
    area = sum(supports.values())
    metrics.update(evaluated_water_scene_km2=area, valid_ocean_area_by_scene_km2=supports,
        benchmark_unmatched_per_km2=metrics['false_positive']/area if area else None,
        by_distance_to_mapped_shore_m={k: dict(labels=c['labels'], matched=c['matched'],
            recall=c['matched']/c['labels'] if c['labels'] else None) for k,c in coast_counts.items()},
        projected_box_center_error_m=stats(centers), projected_box_width_error_m=stats(widths),
        projected_box_height_error_m=stats(heights), error_to_source_wgs84_centroid_m=stats(wgs_errors),
        transform_residual_at_source_centroid_m=stats(residuals))
    return metrics, failure


def main(args):
    import torch
    import ultralytics
    torch.set_num_threads(4)
    args.output.mkdir(parents=True, exist_ok=False)
    val_path, test_path = (args.audit / (s+'_manifest.json') for s in ('val', 'test'))
    method_files = [Path(__file__), ROOT/'scripts/benchmark_sar_archive.py', ROOT/'scripts/evaluate_ossdd_followup.py',
                    ROOT/'scripts/prepare_opensar_geo.py',
                    ROOT/'src/sonarnet/evaluation/independent_sar.py', ROOT/'src/sonarnet/evaluation/detection_metrics.py']
    protocol = dict(created_utc=datetime.now(timezone.utc).isoformat(), val_sha256=digest(val_path),
        test_sha256=digest(test_path), code_sha256={p.name:digest(p) for p in method_files}, weights_sha256=digest(args.weights),
        grid=GRID, torch=torch.__version__, ultralytics=ultralytics.__version__, hardware=platform.platform(),
        cpu_threads=4, imgsz=640, nms_iou=.7, min_yolo_conf=.001,
        selection='Maximum validation IoU50 F1. Tie: larger threshold. Same log1p/P1–P99.9 SLC amplitude conversion for all methods.',
        leakage_rule='Pixel SHA-256 and 64-bit dHash distance <=3 cross-split. Quarantine flagged validation chips before inference; never tune with test.',
        denominator='Union of valid mapped ocean footprint per acquisition, summed across acquisitions. Overlap assigned to lowest numeric tile ID for both scoring and denominator. Land, zeros and nonfinite pixels outside support; estimates inherit map and corner interpolation error.',
        labels='Evaluate HIGH/MEDIUM publisher vessels with centers within valid water; ignore overlap >=0.5 with LOW/unknown vessel unless also overlaps a target. Other predictions unmatched against supplied labels; dataset is not proven exhaustive.',
        latency='4 CPU threads, batch 1, 3 warmups; process and mask but no file I/O.')
    save(args.output/'protocol.json', protocol)
    val, val_amp = open_split(val_path, args.data/'prepared-v1')
    test, test_amp = open_split(test_path, args.data/'prepared-v1')
    audit = leakage(val, test)
    skip = sorted({pair[0] for cat in ('exact','near') for pair in audit[cat]})
    save(args.output/'pixel_audit.json', dict(**audit, excluded_val_ids=skip))
    for i in skip:
        del val[i], val_amp[i]
    assign_unique_support(val)
    assign_unique_support(test)
    if not val or not test or not sum(len(r['boxes_xyxy']) for r in val.values()):
        raise ValueError('Need nonempty validation targets and test images')
    model = ultralytics.YOLO(str(args.weights))

    def infer(amp, row, method, param):
        im = Image.fromarray(normalize(amp, 'log1p'))
        if method == 'yolo':
            r = model.predict(im.convert('RGB'), device='cpu', imgsz=640, conf=.001,
                              iou=.7, max_det=1000, verbose=False)[0]
            boxes, scores = r.boxes.xyxy.cpu().numpy(), r.boxes.conf.cpu().numpy()
        else:
            boxes, scores = detect(im, method, param)
        return restrict_to_scoring_support(row, boxes, scores)

    def infer_split(rows, amp, method, param, stage):
        first = next(iter(rows))
        for _ in range(3):
            infer(amp[first], rows[first], method, param)
        predictions, timing = {}, []
        for j, (i,r) in enumerate(rows.items(), 1):
            start = time.perf_counter()
            predictions[i] = infer(amp[i], r, method, param)
            timing.append((time.perf_counter()-start)*1000)
            if j % 150 == 0:
                print(stage, method, j, '/', len(rows), flush=True)
        return predictions, timing

    choices, tuning = {}, {}
    for method, grid in GRID.items():
        tuning[method] = []
        pred = None
        for p in grid:
            if pred is None or method != 'yolo':
                pred, _ = infer_split(val, val_amp, method, p, 'val')
            summary, _ = operational_metrics(list(val.values()), pred, p if method == 'yolo' else 0.)
            tuning[method].append(dict(param=p, f1=summary['f1'], metrics=summary))
        choices[method] = max(tuning[method], key=lambda row:(row['f1'], row['param']))['param']
    frozen = args.output/'operating_points.json'
    save(frozen, dict(locked_utc=datetime.now(timezone.utc).isoformat(), choices=choices, tuning=tuning))
    print('Frozen', choices, 'validation', len(val), 'test', len(test), flush=True)
    report = dict(val_chips=len(val), test_chips=len(test), test_scene_count=len({r['scene_id'] for r in test.values()}),
                  frozen_sha256=digest(frozen), models={})
    for method, param in choices.items():
        pred, timing = infer_split(test, test_amp, method, param, 'test')
        threshold = param if method == 'yolo' else 0.
        m, failure = score(test, pred, threshold)
        m.update(latency_ms_p50=float(np.median(timing)), latency_ms_p95=float(np.percentile(timing,95)))
        per_scene = {}
        for sid in sorted({r['scene_id'] for r in test.values()}):
            rows = {i:r for i,r in test.items() if r['scene_id'] == sid}
            per_scene[sid], _ = score(rows, {i:pred[i] for i in rows}, threshold)
        with gzip.open(args.output/f'{method}_predictions.json.gz', 'wt') as f:
            json.dump({i:dict(boxes=b.tolist(), scores=s.tolist()) for i,(b,s) in pred.items()}, f)
        save(args.output/f'{method}_failures.json', failure)
        report['models'][method] = dict(param=param, metrics=m, per_scene=per_scene)
        save(args.output/'results.json', report)
    print('Completed locked test comparison', flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for opt in ('data','audit','output','weights'):
        p.add_argument('--'+opt, type=Path, required=True)
    main(p.parse_args())
