"""Compact, resumable detailed-SAR work plan over published observation regions.

A 720 px world-region preview is not a detector input. Each planned cell must
be fetched separately at <=25 m/px before inference. Plans distinguish missing
imagery and missing shoreline masks from completed work; neither is a zero-
vessel observation. Planning performs no network calls and no inference.
"""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image
from shapely import prepare
from shapely.geometry import box
from shapely.ops import unary_union

GRID_STEP = 0.1
IMAGE_WIDTH = 1024
PLAN_VERSION = 'detailed-sar-0.1deg-v1'


def distributed_queue(candidates):
    """Round-robin one-degree latitude bands; retain every pending cell."""
    bands = defaultdict(deque)
    for cell in candidates:
        bands[math.floor((cell['bbox'][1]+cell['bbox'][3])/2)].append(cell)
    result = []
    while any(bands.values()):
        for band in sorted(bands, reverse=True):
            if bands[band]:
                result.append(bands[band].popleft())
    return result


def cells(bbox, step=GRID_STEP):
    """Cover every point of a region, including fractional edge cells."""
    w, s, e, n = map(float, bbox)
    if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
        raise ValueError('Invalid region bounds; split date-line regions first')
    if not 0 < step <= 0.2:
        raise ValueError('Cell step must preserve detailed radar resolution')
    columns = math.ceil(round((e-w)/step, 10))
    rows = math.ceil(round((n-s)/step, 10))
    for row in range(rows):
        for column in range(columns):
            bounds = [round(w+column*step, 8), round(s+row*step, 8),
                      round(min(e, w+(column+1)*step), 8), round(min(n, s+(row+1)*step), 8)]
            key = hashlib.sha256(json.dumps(bounds, separators=(',', ':')).encode()).hexdigest()[:16]
            yield {'key': f'grid_{key}', 'bbox': bounds, 'row': row, 'column': column}


def image_has_observation(alpha, region_bbox, cell_bbox):
    w, s, e, n = region_bbox
    a, b, c, d = cell_bbox
    height, width = alpha.shape
    x1, x2 = max(0, math.floor((a-w)/(e-w)*width)), min(width, math.ceil((c-w)/(e-w)*width))
    y1, y2 = max(0, math.floor((n-d)/(n-s)*height)), min(height, math.ceil((n-b)/(n-s)*height))
    return bool(np.any(alpha[y1:y2, x1:x2]))


def published_regions(root):
    """Use only verified local images, with source metadata but no secrets."""
    assets = root / 'assets'
    records = []
    national = assets / 'sentinel1_vietnam_latest.json'
    if national.exists():
        records.append(dict(json.loads(national.read_text()), key='vietnam', label='Việt Nam',
                            asset='sentinel1_vietnam_latest.png'))
    global_manifest = assets / 'sentinel1_global/latest.json'
    if global_manifest.exists():
        records.extend(json.loads(global_manifest.read_text()).get('tiles', []))
    for record in records:
        path = (assets / record['asset']).resolve()
        if not path.is_relative_to(assets.resolve()):
            continue
        try:
            with Image.open(path) as image:
                image.load()
                alpha = np.asarray(image.convert('RGBA'))[:, :, 3] > 0
            yield record, alpha
        except (OSError, ValueError):
            continue


def prepare_mask(data, geometries):
    coverage = box(*data['coverage_bbox'])
    excluded = unary_union([geometries['land'], geometries['coast']])
    prepare(excluded)
    return coverage, excluded


def cell_state(cell, record, alpha, coverage, excluded, completed, deferred=frozenset()):
    footprint = box(*cell['bbox'])
    if not image_has_observation(alpha, record['bbox'], cell['bbox']):
        return 'no_observation'
    if coverage is None or not coverage.covers(footprint):
        return 'blocked_missing_mask'
    if excluded.covers(footprint):
        return 'excluded_land_coast'
    if cell['key'] in completed:
        return 'processed'
    if cell['key'] in deferred:
        return 'retry_later'
    return 'pending'


def build_plan(root, report, mask=None, limit=12, region_key=None):
    """Summarize all regions, retaining only a bounded next-work queue.

    `processed` means a verified published detail cell exists, not that every
    pixel of today's overview mosaic has been checked. Acquisition dates are
    retained in the detailed evidence and completion never implies live AIS.
    """
    from scan_assets import validate_tile
    completed, valid_tiles = set(), []
    for tile in report.get('tiles', []):
        if tile.get('status') != 'processed':
            continue
        try:
            validate_tile(root, tile)
            valid_tiles.append(tile)
            completed.add(tile['key'])
        except (OSError, KeyError, ValueError, TypeError):
            continue
    if mask is None:
        try:
            from land_mask import get_mask
            mask = get_mask(root)
        except (OSError, ValueError, KeyError):
            mask = None
    coverage, excluded = prepare_mask(*mask) if mask else (None, None)
    now = datetime.now(timezone.utc)
    deferred = set()
    for key, attempt in report.get('scan_attempts', {}).items():
        try:
            if datetime.fromisoformat(attempt['retry_after']) > now:
                deferred.add(key)
        except (ValueError, KeyError, TypeError):
            continue
    regions, queue, claimed = [], [], set()
    for record, alpha in published_regions(root):
        counts = Counter()
        for cell in cells(record['bbox']):
            state = cell_state(cell, record, alpha, coverage, excluded, completed, deferred)
            counts[state] += 1
            if (state == 'pending' and cell['key'] not in claimed
                    and (region_key is None or record['key'] == region_key)):
                queue.append(dict(cell, region_key=record['key'], region_label=record.get('label', record['key'])))
                claimed.add(cell['key'])
        region_geometry = box(*record['bbox'])
        evidence = [tile for tile in valid_tiles if region_geometry.intersects(box(*tile['bbox']))]
        regions.append({
            'key': record['key'], 'label': record.get('label', record['key']), 'bbox': record['bbox'],
            'overview_newest_catalog_at': record.get('newest_catalog_acquired_at'),
            'planned_cells': sum(counts.values()), 'states': dict(counts),
            'published_detail_cells': len(evidence),
            'latest_detail_day_utc': max((t['observation_day_utc'] for t in evidence), default=None),
        })
    return {
        'version': PLAN_VERSION, 'generated_at': datetime.now(timezone.utc).isoformat(),
        'cell_degrees': GRID_STEP, 'requested_image_width': IMAGE_WIDTH, 'maximum_metres_per_pixel': 25,
        'scope': 'Published observation regions only; this is not complete global Sentinel-1 coverage.',
        'completion_scope': 'Verified detailed cells; timestamps differ by cell. Pending means not scanned, not no vessels.',
        'mask_version': mask[0]['version'] if mask else None,
        'regions': regions, 'next_cells': distributed_queue(queue)[:limit],
    }


def write_plan(root, report, **kwargs):
    plan = build_plan(root, report, **kwargs)
    path = root / 'assets/real_scan/coverage.json'
    pending = path.with_suffix('.pending.json')
    pending.write_text(json.dumps(plan, ensure_ascii=False, indent=2)+'\n')
    pending.replace(path)
    return plan


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--region', default=None)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    report = json.loads((root/'assets/real_scan/report.json').read_text())
    plan = write_plan(root, report, region_key=args.region)
    print(json.dumps({'regions': len(plan['regions']), 'states': dict(sum(
        (Counter(region['states']) for region in plan['regions']), Counter()))}, indent=2))
