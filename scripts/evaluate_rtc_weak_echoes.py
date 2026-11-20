"""Compare weak-echo proposals and spatial ranking at identical review counts."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path

import numpy as np
from PIL import Image
from shapely import intersects_xy
from shapely.geometry import GeometryCollection, box
import torch
from ultralytics import YOLO

from evaluate_review_ranking import save
from evaluate_rtc_contrast_recall import RADII, shortlist
from evaluate_rtc_map_tta import ranked_views
from land_mask import get_mask
from prepare_opensar_geo import unique_water_support
from refresh_detailed_scan import allowed_pixels
from score_vn_reference_rtc import ROOT, digest, geographic_distances, matched, raster_points, valid_water
from sonarnet.data.planetary import gray_rgba

FLOOR = .01
CAP = 1000
MODES = {'equal_incumbent': 'incumbent', 'equal_relaxed': 'baseline_low'}
WEIGHTS = ROOT / 'assets/models/sonarnet_baseline.pt'
POLICIES = {
    'stronger_zoom': ('zoom',),
    'weak_full_and_zoom': ('full', 'zoom'),
    'coastal_review': ('coast',),
    'all_proposals': ('full', 'zoom', 'coast'),
    'less_redundancy': (),
    'zoom_less_redundancy': ('zoom',),
    'view_consensus': ('zoom',),
}


def detect(model, images, size):
    return model.predict(images, imgsz=size, conf=FLOOR, iou=.7,
                         max_det=CAP, device='cpu', verbose=False)


def place(prediction, origin, core, bbox, shape, support, exclusion, coast=None):
    boxes = prediction.boxes
    rows = boxes.xyxy.cpu().numpy() + [*origin, *origin]
    rows[:, [0, 2]] = np.clip(rows[:, [0, 2]], 0, shape[1])
    rows[:, [1, 3]] = np.clip(rows[:, [1, 3]], 0, shape[0])
    centers = (rows[:, :2] + rows[:, 2:]) / 2
    lon, lat = raster_points(centers, bbox, shape)
    eligible = intersects_xy(support, lon, lat)
    if core is not None:
        left, top, right, bottom = core
        x, y = centers.T
        eligible &= (x >= left) & (x < right) & (y >= top) & (y < bottom)
    if coast is not None:
        eligible &= intersects_xy(coast, lon, lat)
    west, north = raster_points(rows[:, :2], bbox, shape)
    east, south = raster_points(rows[:, 2:], bbox, shape)
    scores = boxes.conf.cpu().numpy()
    return [(float(lon[i]), float(lat[i]), float(scores[i])) for i in np.flatnonzero(eligible)
            if west[i] < east[i] and south[i] < north[i]
            and not exclusion.intersects(box(west[i], south[i], east[i], north[i]))]


def zoom_images(gray, allowed, halo=48):
    height, width = gray.shape
    y_edges = np.linspace(0, height, 4, dtype=int)
    x_edges = np.linspace(0, width, 4, dtype=int)
    chips = []
    for top, bottom in zip(y_edges, y_edges[1:]):
        for left, right in zip(x_edges, x_edges[1:]):
            if not allowed[top:bottom, left:right].any():
                continue
            x = max(0, left - halo)
            y = max(0, top - halo)
            crop = gray[y:bottom + halo, x:right + halo]
            chips.append((Image.fromarray(crop).convert('RGB'),
                          (x, y), (left, top, right, bottom)))
    return chips


def infer_views(model, gamma, bbox, support, mask):
    rgba = gray_rgba(np.ma.masked_less_equal(gamma, 0))
    original = Image.fromarray(rgba)
    allowed, exclusion = allowed_pixels(original, bbox, mask)
    result = {'full': [], 'zoom': [], 'coast': []}
    if allowed.any():
        gray = np.where(allowed, rgba[:, :, 0], 0)
        p, = detect(model, [Image.fromarray(gray).convert('RGB')], 1024)
        result['full'] = place(p, (0, 0), None, bbox, gray.shape, support, exclusion)
        chips = zoom_images(gray, allowed)
        # Use a fixed 640-pixel letterbox regardless of the batch composition.
        predictions = model.predict([image for image, _, _ in chips], imgsz=640,
                                    conf=FLOOR, iou=.7, max_det=CAP, rect=False,
                                    device='cpu', verbose=False)
        for prediction, (_, origin, core) in zip(predictions, chips, strict=True):
            result['zoom'].extend(place(prediction, origin, core, bbox, gray.shape, support, exclusion))
    coast = mask[1]['coast'].intersection(support)
    if not coast.is_empty:
        land_mask = mask[0], {**mask[1], 'coast': GeometryCollection()}
        wet, land = allowed_pixels(original, bbox, land_mask)
        gray = np.where(wet, rgba[:, :, 0], 0)
        p, = detect(model, [Image.fromarray(gray).convert('RGB')], 1024)
        result['coast'] = place(p, (0, 0), None, bbox, gray.shape, support, land, coast)
    return result


def collect(model, case, cohort, folder, region, mask):
    if cohort['region'] != case['region'] or len(cohort['windows']) != case['windows']:
        raise ValueError('Radar and candidate cohorts differ')
    chips = []
    for window in sorted(cohort['windows'], key=lambda row: row['window_id']):
        path = folder / window['file']
        if digest(path) != window['sha256']:
            raise ValueError('Raster checksum differs')
        with np.load(path, allow_pickle=False) as source:
            gamma = source['gamma0']
        bbox = window['bbox']
        chips.append((gamma, bbox, valid_water(gamma, bbox, region, mask[1]['land'])))
    supports = unique_water_support([row[2] for row in chips])
    proposals = {'full': [], 'zoom': [], 'coast': []}
    for (gamma, bbox, _), support in zip(chips, supports, strict=True):
        if support.is_empty:
            continue
        for name, rows in infer_views(model, gamma, bbox, support, mask).items():
            proposals[name].extend(rows)
    return proposals


def soft_diversity(ordered, count):
    """Discount redundant proposals progressively beyond hard 35 m suppression."""
    if not ordered or count == 0:
        return []
    rows = np.asarray(ordered)
    distance = geographic_distances(rows, rows[:, :2])
    weights = rows[:, 2].copy()
    kept = []
    while len(kept) < count and np.isfinite(weights).any():
        best = int(np.argmax(weights))
        kept.append(ordered[best])
        separation = distance[best]
        weights *= .45 + .55 * np.minimum(separation / 115., 1.)
        weights[separation <= 35.] = -np.inf
    return kept


def queues(case, overlap, new):
    modes = {}
    for mode, baseline in MODES.items():
        original = sorted(case[baseline], key=lambda row: -row[2])
        low = case['baseline_low']
        prior = {} if mode == 'equal_incumbent' else {'overlap': overlap}
        count = min(len(original), case['budget'])
        champion = ranked_views(low, prior, 'max')
        entries = {'map': original[:count], 'previous_best': shortlist(champion, original, count, 35.)}
        for policy, views in POLICIES.items():
            others = {**prior, **{view: new[view] for view in views}}
            # Coastal extras carry less weight because bright fixed structures
            # are common near the shore. Land and invalid pixels remain excluded.
            if 'coast' in others:
                others['coast'] = [[x, y, score * .7] for x, y, score in others['coast']]
            ordered = ranked_views(low, others, 'vote' if policy == 'view_consensus' else 'max')
            primary = soft_diversity(ordered, count) if policy.endswith('redundancy') else ordered
            entries[policy] = shortlist(primary, original, count, 35.)
        if any(len(items) != count for items in entries.values()):
            raise ValueError('Review counts differ')
        modes[mode] = entries
    return modes


def measure(case, views, proposals, coast):
    truth = case['truth']
    runs = queues(case, views, proposals)
    summary = {mode: {key: matched(rows, truth, RADII) for key, rows in methods.items()}
               for mode, methods in runs.items()}
    search = {
        'previous': matched(case['baseline_low'] + views, truth, RADII),
        'expanded': matched(case['baseline_low'] + views + [p for cells in proposals.values() for p in cells],
                            truth, RADII),
    }
    return dict(scene=case['scene'], region=case['region'], windows=case['windows'],
                nearshore_labels=int(np.count_nonzero(intersects_xy(coast, *np.asarray(truth).T))),
                raw_candidates={key: len(rows) for key, rows in proposals.items()}, coverage=search, **summary), runs


def run_group(inputs, model, mask, cache):
    source, detector_cache, old_views = inputs
    with gzip.open(detector_cache, 'rt') as file:
        cases = json.load(file)
    augmented = json.loads(old_views.read_text())
    folder = source / 'rtc-512'
    cohorts = {row['scene']: row for row in json.loads((folder/'manifest.json').read_text())['cohorts']}
    regions = json.loads((source/'screened.json').read_text())['bounds']
    existing = json.loads(cache.read_text()) if cache.exists() else {}
    for case in cases:
        scene = case['scene']
        if scene not in existing:
            region = box(*regions[case['region']])
            existing[scene] = collect(model, case, cohorts[scene], folder, region, mask)
            save(cache, existing)
        score, details = measure(case, augmented[scene]['overlap'], existing[scene], mask[1]['coast'])
        print(scene.split('_')[4], case['windows'], score['raw_candidates'],
              {k: score['coverage'][k][100]['matched'] for k in score['coverage']}, flush=True)
        yield score, dict(scene=scene, labels=case['truth'], queues=details)


def day(case):
    return case['scene'].split('_')[4][:8]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('development', 'held-out', 'confirmation', 'cached-neural', 'tta', 'confirmation-cache', 'out'):
        parser.add_argument('--' + flag, type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(exist_ok=False)
    torch.set_num_threads(4)
    groups = {
        'development': (args.development, args.cached_neural/'development_features.json.gz',
                        args.tta/'development-views.json'),
        'held_out': (args.held_out, args.cached_neural/'fresh_features.json.gz',
                     args.tta/'held-out-views.json'),
        'confirmation': (args.confirmation, args.confirmation_cache/'baseline.json.gz',
                         args.confirmation_cache/'views.json'),
    }
    save(args.out/'protocol.json', dict(
        started_at=datetime.now(timezone.utc).isoformat(), evaluator_sha256=digest(Path(__file__)),
        weights_sha256=digest(WEIGHTS), coast_mask_sha256=digest(ROOT/'assets/land_mask/vietnam.json.gz'),
        versions={'torch': torch.__version__, 'numpy': np.__version__},
        zoom={'grid': [3, 3], 'halo_pixels': 48, 'input_pixels': 640},
        floor=FLOOR, policies=POLICIES, match_metres=RADII,
        selection='Choose the strongest per budget on development at 100 m. Ties preserve the previous best. Evaluate on separate days. No tuning on held-out or confirmation dates.',
        scope='Retrospective on acquisition dates previously used in other locked experiments.',
        inputs={key: dict(manifest_sha256=digest(source/'rtc-512/manifest.json'),
                          cache_sha256=digest(cache), prior_views_sha256=digest(views))
                for key, (source, cache, views) in groups.items()},
    ))
    model, mask = YOLO(str(WEIGHTS)), get_mask(ROOT)
    all_splits, audit, known_days = {}, {}, set()
    for key, inputs in groups.items():
        rows, raw = zip(*run_group(inputs, model, mask, args.out/f'{key}-views.json'), strict=True)
        days = {day(row) for row in rows}
        if known_days & days:
            raise ValueError('Development and scoring dates overlap')
        known_days.update(days)
        if key == 'development':
            scores = {mode: {policy: sum(row[mode][policy][100]['matched'] for row in rows)
                             for policy in ('previous_best', *POLICIES)}
                      for mode in MODES}
            selected = {mode: max(counts, key=lambda k: (counts[k], k == 'previous_best'))
                        for mode, counts in scores.items()}
            save(args.out/'selection.json', dict(selected=selected, development_totals=scores, cases=rows))
            print('Locked', selected, scores, flush=True)
        else:
            all_splits[key] = rows
            audit[key] = [{**row, 'queues': {
                mode: {policy: row['queues'][mode][policy]
                       for policy in dict.fromkeys(('map', 'previous_best', selected[mode]))}
                for mode in MODES}} for row in raw]
            save(args.out/'results.json', dict(selected=selected, test=all_splits,
                 selection_sha256=digest(args.out/'selection.json')))
            save(args.out/'review-queues.json', dict(results_sha256=digest(args.out/'results.json'), test=audit))


if __name__ == '__main__':
    main()
