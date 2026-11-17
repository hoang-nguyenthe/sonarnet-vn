"""Auditable independent SAR benchmark. Missing metadata is not a measured zero."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image

from .detection_metrics import evaluate_multi_iou, box_iou


def sha256(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def audit_manifest(manifest, base):
    """Require independently documented scene, region and date groups.

    Date is acquisition UTC date, region is a predeclared geographic holdout
    group. Neither can be inferred from a random tile number. All three must
    remain disjoint. Perceptual similarity triggers manual review, not a
    statement that two SAR images are necessarily duplicates.
    """
    rows = manifest.get('images', [])
    errors, warnings, hashes, perceptual = [], [], {}, []
    groups = {k: {} for k in ('scene_id', 'region_id', 'acquired_date_utc')}
    ids = set()
    if not rows:
        errors.append('No image records')
    if not manifest.get('metadata_source'):
        errors.append('Missing metadata_source provenance')
    for row in rows:
        ident, split = row.get('id'), row.get('split')
        if not ident or ident in ids:
            errors.append(f'Duplicate/missing image id: {ident}')
        ids.add(ident)
        if split not in {'train', 'val', 'test'}:
            errors.append(f'{ident}: invalid split')
        if row.get('annotation_status') != 'reviewed':
            errors.append(f'{ident}: labels must be independently reviewed')
        for key in groups:
            value = row.get(key)
            if not value:
                errors.append(f'{ident}: missing {key}')
            elif value in groups[key] and groups[key][value] != split:
                errors.append(f'{key} crosses splits: {value}')
            else:
                groups[key][value] = split
        path = Path(base) / row.get('image', '')
        try:
            raw_hash = sha256(path)
            if raw_hash != row.get('sha256'):
                errors.append(f'{ident}: image checksum mismatch')
            with Image.open(path) as im:
                rgb = im.convert('RGB')
                pixel_hash = hashlib.sha256(str(rgb.size).encode() + rgb.tobytes()).hexdigest()
                small = np.asarray(rgb.convert('L').resize((9, 8)), dtype=np.int16)
                bits = small[:, 1:] > small[:, :-1]
                dhash = sum(int(v) << i for i, v in enumerate(bits.ravel()))
                width, height = im.size
            if pixel_hash in hashes and hashes[pixel_hash][1] != split:
                errors.append(f'{ident}: identical pixels cross splits with {hashes[pixel_hash][0]}')
            hashes[pixel_hash] = (ident, split)
            perceptual.append((ident, split, dhash))
            labels = row.get('boxes_xyxy')
            if not isinstance(labels, list):
                errors.append(f'{ident}: boxes_xyxy required, [] for reviewed background')
            else:
                for box in labels:
                    if len(box) != 4 or not all(np.isfinite(box)) or not (0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height):
                        errors.append(f'{ident}: invalid box')
            coastal = row.get('nearshore_gt')
            if coastal is not None and (len(coastal) != len(labels or []) or not all(isinstance(x, bool) for x in coastal)):
                errors.append(f'{ident}: nearshore_gt must be a boolean per ground-truth box')
            for key in ('valid_area_km2', 'gsd_x_m', 'gsd_y_m'):
                if row.get(key) is not None and (not np.isfinite(row[key]) or row[key] <= 0):
                    errors.append(f'{ident}: invalid {key}')
        except (OSError, ValueError, TypeError) as exc:
            errors.append(f'{ident}: {exc}')
    # O(N^2) intended for modest independently reviewed evaluation cohorts.
    for i, (ident, split, dhash) in enumerate(perceptual):
        for other, other_split, other_hash in perceptual[:i]:
            if split != other_split and (dhash ^ other_hash).bit_count() <= 3:
                warnings.append(f'Near-duplicate candidate across splits: {other} / {ident}')
    if {r.get('split') for r in rows} != {'train', 'val', 'test'}:
        errors.append('Manifest must document train, val and test, including training lineage')
    return {'passed': not errors and not warnings, 'errors': sorted(set(errors)),
            'review_required': warnings, 'images': len(rows),
            'split_counts': {s: sum(r.get('split') == s for r in rows) for s in ('train','val','test')},
            'rule': 'scene, region, acquisition date and exact pixels disjoint; dHash distance <=3 requires review'}


def operational_metrics(rows, predictions, threshold=0.25):
    truth = {r['id']: np.asarray(r['boxes_xyxy']).reshape(-1, 4) for r in rows}
    metric = evaluate_multi_iou(predictions, truth, score_threshold=threshold).to_dict()
    if not metric['n_ground_truth']:
        for key in ('mAP@0.5', 'mAP@0.5:0.95', 'recall', 'f1'):
            metric[key] = None
    fp, area, coast_total, coast_tp = 0, 0., 0, 0
    centers, widths, heights, failures = [], [], [], []
    centers_px, widths_px, heights_px = [], [], []
    total_pixels = sum(r.get('image_pixel_area', 0) for r in rows)
    have_pixel_area = bool(rows) and all(r.get('image_pixel_area', 0) > 0 for r in rows)
    have_area = all(r.get('valid_area_km2') for r in rows)
    have_coast = all(r.get('nearshore_gt') is not None for r in rows)
    for row in rows:
        gt = truth[row['id']]
        boxes, scores = predictions.get(row['id'], (np.empty((0, 4)), np.array([])))
        boxes, scores = np.asarray(boxes).reshape(-1, 4), np.asarray(scores)
        order = np.argsort(-scores, kind='stable')
        chosen = order[scores[order] >= threshold]
        overlap = box_iou(boxes, gt)
        used, pairs, false = set(), [], []
        for i in chosen:
            available = [j for j in range(len(gt)) if j not in used]
            j = max(available, key=lambda j: overlap[i,j]) if available else None
            if j is not None and overlap[i,j] >= .5:
                used.add(j)
                pairs.append((int(i), j))
            else:
                false.append(int(i))
        missing = [j for j in range(len(gt)) if j not in used]
        fp += len(false)
        area += row.get('valid_area_km2') or 0
        coast = row.get('nearshore_gt')
        if coast is not None:
            coast_total += sum(coast)
            coast_tp += sum(coast[j] for _, j in pairs)
        sx, sy = row.get('gsd_x_m'), row.get('gsd_y_m')
        for i, j in pairs:
            a, b = boxes[i], gt[j]
            centers_px.append(float(np.linalg.norm((a[:2]+a[2:]-b[:2]-b[2:])/2)))
            widths_px.append(float(abs((a[2]-a[0])-(b[2]-b[0]))))
            heights_px.append(float(abs((a[3]-a[1])-(b[3]-b[1]))))
        if sx and sy:
            for i, j in pairs:
                a, b = boxes[i], gt[j]
                centers.append(float(np.hypot(((a[0]+a[2])-(b[0]+b[2]))/2*sx, ((a[1]+a[3])-(b[1]+b[3]))/2*sy)))
                widths.append(float(abs((a[2]-a[0])-(b[2]-b[0]))*sx))
                heights.append(float(abs((a[3]-a[1])-(b[3]-b[1]))*sy))
        failures.append({'id':row['id'], 'scene_id':row.get('scene_id'),
                         'false_positive_indices':false, 'false_negative_indices':missing, 'matched_indices':pairs})
    metric.update(false_alarms_per_km2=fp/area if have_area and area else None,
                  nearshore_recall=coast_tp/coast_total if have_coast and coast_total else None,
                  nearshore_ground_truth=coast_total if have_coast else None,
                  center_error_m_median=float(np.median(centers)) if centers else None,
                  box_width_error_m_median=float(np.median(widths)) if widths else None,
                  box_height_error_m_median=float(np.median(heights)) if heights else None,
                  georeferenced_matches=len(centers),
                  false_alarms_per_megapixel=fp/(total_pixels/1e6) if have_pixel_area else None,
                  evaluated_image_pixels=total_pixels if have_pixel_area else None,
                  center_error_px_median=float(np.median(centers_px)) if centers_px else None,
                  center_error_px_p95=float(np.percentile(centers_px,95)) if centers_px else None,
                  box_width_error_px_median=float(np.median(widths_px)) if widths_px else None,
                  box_height_error_px_median=float(np.median(heights_px)) if heights_px else None,
                  localized_matches=len(centers_px))
    return metric, failures
