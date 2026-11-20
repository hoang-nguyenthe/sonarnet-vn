"""Test a published xView3 VV/VH checkpoint on later Vietnamese RTC acquisitions."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import importlib
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter

import numpy as np
from scipy.ndimage import maximum_filter
from scipy.special import expit
from shapely import intersects_xy
from shapely.geometry import box
import torch

from evaluate_review_ranking import save
from evaluate_rtc_contrast_recall import RADII, shortlist
from evaluate_rtc_map_tta import ranked_views
from evaluate_rtc_weak_echoes import MODES
from land_mask import get_mask
from prepare_opensar_geo import unique_water_support
from score_vn_reference_rtc import ROOT, digest, matched, raster_points, valid_water

REVISION = '558c15a979f889851b86a797518268944866e820'
WEIGHT_URL = ('https://github.com/selimsef/xview3_solution/releases/download/weights/'
              'val_only_TimmUnet_resnet34_77_xview')
CHECKSUM = 'e8996b174d0e8f352a6e4a9f7bf84f3cf5dbcb418498b4cead403aa687b8fda8'
MODES_LABELS = {
    'map': 'Bản đồ',
    'previous_best': 'Lọc 35 m hoặc chia ô chồng lấn',
    'xview3_center': 'xView3 · điểm tâm',
    'xview3_vessel': 'xView3 · điểm tâm và xác suất tàu',
    'xview3_vessel_tta': 'xView3 · trung bình ảnh gốc và xoay 180°',
    'xview3_fused_tta': 'xView3 xoay 180° kết hợp YOLO',
}
PEAK_FLOOR = 40


def load_checkpoint(upstream, checkpoint):
    revision = subprocess.check_output(['git', '-C', str(upstream), 'rev-parse', 'HEAD'], text=True).strip()
    modified = subprocess.check_output(['git', '-C', str(upstream), 'status', '--porcelain', '--untracked-files=no'],
                                      text=True)
    if revision != REVISION or modified or digest(checkpoint) != CHECKSUM:
        raise ValueError('Upstream code or checkpoint differs from the locked release')
    sys.path.insert(0, str(upstream))
    zoo = importlib.import_module('zoo')
    scalar = np._core.multiarray.scalar
    globals_for_metadata = [(scalar, 'numpy.core.multiarray.scalar'), np.dtype,
                            type(np.dtype('float32')), type(np.dtype('float64'))]
    with torch.serialization.safe_globals(globals_for_metadata):
        state = torch.load(checkpoint, map_location='cpu', weights_only=True)['state_dict']
    state = {key.removeprefix('module.'): value for key, value in state.items()}
    # The published checkpoint has two retired heads. The current upstream
    # inference code drops them before strict loading. Keep all other tensors.
    state = {key: value for key, value in state.items() if not key.startswith(('object_mask.', 'conf_mask.'))}
    model = zoo.TimmUnet(encoder='resnet34', in_chans=2, pretrained=False, channels_last=False)
    model.load_state_dict(state, strict=True)
    return model.eval()


def normalize(gamma):
    valid = np.isfinite(gamma) & (gamma > 0)
    values = np.zeros(gamma.shape, dtype=np.float32)
    values[valid] = (10 * np.log10(gamma[valid]) + 40.) / 15.
    return values


def peaks(center, vessel, valid, bbox, support):
    center = np.clip(center, 0., 255.)
    local = maximum_filter(center, size=7, mode='constant')
    y, x = np.where(valid & (center >= PEAK_FLOOR) & (center == local))
    lon, lat = raster_points(np.c_[x+.5, y+.5], bbox, center.shape)
    kept = intersects_xy(support, lon, lat)
    return np.c_[lon, lat, center[y, x] / 255., vessel[y, x]][kept].tolist()


def infer(model, vv, vh, bbox, support):
    combined = np.stack([normalize(vv), normalize(vh)])
    tensor = torch.from_numpy(combined)[None]
    with torch.inference_mode():
        single = model(tensor)
        rotated = model(torch.rot90(tensor, 2, dims=(2, 3)))
    center = single['center_mask'][0, 0].numpy()
    vessel = expit(single['vessel_mask'][0, 0].numpy())
    center_tta = (center + np.rot90(rotated['center_mask'][0, 0].numpy(), 2)) / 2.
    vessel_tta = (vessel + np.rot90(expit(rotated['vessel_mask'][0, 0].numpy()), 2)) / 2.
    valid = (vv > 0) & (vh > 0)
    return (peaks(center, vessel, valid, bbox, support), peaks(center_tta, vessel_tta, valid, bbox, support))


def read_band(path, window):
    file = path / window['file']
    if digest(file) != window['sha256']:
        raise ValueError('Radar raster checksum differs')
    with np.load(file, allow_pickle=False) as raw:
        return raw['gamma0']


def collect(case, vv, vh, source, region, mask, model):
    if vv['region'] != case['region'] or len(vv['windows']) != case['windows']:
        raise ValueError('Radar and baseline cohorts differ')
    vv_folder = source / 'rtc-512'
    vh_folder = source / 'rtc-vh-512'
    vh_windows = {row['window_id']: row for row in vh['windows']}
    vv_rows = sorted(vv['windows'], key=lambda row: row['window_id'])
    vv_gamma = [read_band(vv_folder, window) for window in vv_rows]
    supports = unique_water_support([valid_water(gamma, window['bbox'], region, mask['land'])
                                     for window, gamma in zip(vv_rows, vv_gamma, strict=True)])
    normal, augmented, missing = [], [], []
    for window, gamma, support in zip(vv_rows, vv_gamma, supports, strict=True):
        band = vh_windows.get(window['window_id'])
        if band is None:
            missing.append(window['window_id'])
            continue
        if band['bbox'] != window['bbox']:
            raise ValueError('VV and VH grids differ')
        if support.is_empty:
            continue
        vh_gamma = read_band(vh_folder, band)
        direct, tta = infer(model, gamma, vh_gamma, window['bbox'], support)
        normal.extend(direct)
        augmented.extend(tta)
    return dict(direct=normal, tta=augmented, missing_vh_windows=missing)


def score_rows(points, vessel):
    if vessel:
        return [(lon, lat, c * float(np.sqrt(v))) for lon, lat, c, v in points]
    return [(lon, lat, c) for lon, lat, c, _ in points]


def measure(case, detection, overlap):
    raw = case['baseline_low']
    center = score_rows(detection['direct'], False)
    vessel = score_rows(detection['direct'], True)
    vessel_tta = score_rows(detection['tta'], True)
    order = lambda rows: sorted(rows, key=lambda p: -p[2])
    methods = dict(xview3_center=order(center), xview3_vessel=order(vessel), xview3_vessel_tta=order(vessel_tta))
    outcomes = {}
    for mode, base in MODES.items():
        original = order(case[base])
        count = min(len(original), case['budget'])
        views = {} if mode == 'equal_incumbent' else {'overlap': overlap}
        previous = ranked_views(raw, views, 'max')
        fused = ranked_views(raw, {**views, 'xview3': vessel_tta}, 'max')
        candidates = {'map': original[:count], 'previous_best': shortlist(previous, original, count, 35.)}
        candidates.update({name: shortlist(pool, candidates['previous_best'], count, 35.)
                           for name, pool in {**methods, 'xview3_fused_tta': fused}.items()})
        if any(len(queue) != count for queue in candidates.values()):
            raise ValueError('Review counts differ')
        outcomes[mode] = candidates
    truth = case['truth']
    metrics = {mode: {name: matched(rows, truth, RADII) for name, rows in queues.items()}
               for mode, queues in outcomes.items()}
    summary = dict(scene=case['scene'], region=case['region'], windows=case['windows'],
                   missing_vh_windows=detection['missing_vh_windows'],
                   raw_candidate_counts={k: len(v) for k, v in methods.items()},
                   source_candidate_coverage={
                       'previous': matched(raw + overlap, truth, RADII),
                       'xview3': matched(vessel_tta, truth, RADII),
                       'combined': matched(raw + overlap + vessel_tta, truth, RADII),
                   }, **metrics)
    return summary, dict(scene=case['scene'], labels=truth, queues=outcomes)


def read_manifest(path):
    return {cohort['scene']: cohort for cohort in json.loads(path.read_text())['cohorts']}


def run_group(source, cache, prior, model, mask, output):
    vv = read_manifest(source/'rtc-512/manifest.json')
    vh = read_manifest(source/'rtc-vh-512/manifest.json')
    bounds = json.loads((source/'screened.json').read_text())['bounds']
    views = json.loads(prior.read_text())
    with gzip.open(cache, 'rt') as file:
        cases = json.load(file)
    detections = {}
    for case in cases:
        scene = case['scene']
        start = perf_counter()
        detection = collect(case, vv[scene], vh[scene], source, box(*bounds[case['region']]), mask, model)
        detection['elapsed_s'] = round(perf_counter() - start, 3)
        detections[scene] = detection
        save(output, detections)
        summary, coordinates = measure(case, detection, views[scene]['overlap'])
        print(scene.split('_')[4], f"{detection['elapsed_s']:.1f}s",
              {k: summary['source_candidate_coverage'][k][100]['matched']
               for k in summary['source_candidate_coverage']}, flush=True)
        yield summary, coordinates


def input_record(source, cache, prior):
    return dict(vv_manifest_sha256=digest(source/'rtc-512/manifest.json'),
                vh_manifest_sha256=digest(source/'rtc-vh-512/manifest.json'),
                yolo_cache_sha256=digest(cache), yolo_overlap_sha256=digest(prior))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('upstream', 'checkpoint', 'development', 'held-out', 'confirmation',
                 'cached-neural', 'confirmation-cache', 'tta', 'out'):
        parser.add_argument('--'+flag, type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(exist_ok=False)
    torch.set_num_threads(4)
    model = load_checkpoint(args.upstream, args.checkpoint)
    mask = get_mask(ROOT)[1]
    groups = dict(
        development=(args.development, args.cached_neural/'development_features.json.gz', args.tta/'development-views.json'),
        held_out=(args.held_out, args.cached_neural/'fresh_features.json.gz', args.tta/'held-out-views.json'),
        confirmation=(args.confirmation, args.confirmation_cache/'baseline.json.gz', args.confirmation_cache/'views.json'),
    )
    save(args.out/'protocol.json', dict(
        locked_utc=datetime.now(timezone.utc).isoformat(), evaluator_sha256=digest(Path(__file__)),
        upstream_revision=REVISION, weight_url=WEIGHT_URL, weight_sha256=CHECKSUM,
        torch_version=torch.__version__, timm_version=sys.modules['timm'].__version__,
        native_input='VV then VH, g0 dB mapped (dB+40)/15, invalid 0',
        tta='Mean original and inverse-transformed 180-degree rotation. Local maxima in 7×7 window, floor 40/255.',
        shortlist='Each method keeps the same count as the original map on each acquisition. Suppress centers within 35 m and refill from the previous best if needed.',
        metrics='One-to-one WGS84 distances across original valid-water support including windows whose VH is missing.',
        selection='Maximize number of matches at 100 m on the five development acquisitions. On ties prefer previous best; otherwise prefer no rotation and earlier methods.',
        scope='Single released xView3 checkpoint transfer. Ai2 dates postdate the xView3 challenge. Both evaluation groups were used in prior SonarNet experiments; excluded from all decisions in this transfer.',
        inputs={group: input_record(*items) for group, items in groups.items()},
    ))
    results, evidence, known_days = {}, {}, set()
    for group, (source, cache, prior) in groups.items():
        rows, coordinates = zip(*run_group(source, cache, prior, model, mask, args.out/f'{group}-candidates.json'),
                                strict=True)
        days = {case['scene'].split('_')[4][:8] for case in rows}
        if known_days & days:
            raise ValueError('Development and scoring dates overlap')
        known_days.update(days)
        if group == 'development':
            scores = {mode: {policy: sum(row[mode][policy][100]['matched'] for row in rows)
                             for policy in MODES_LABELS if policy != 'map'} for mode in MODES}
            selected = {mode: max(counts, key=lambda key: (counts[key], key == 'previous_best'))
                        for mode, counts in scores.items()}
            save(args.out/'selection.json', dict(selected=selected, totals=scores, cases=rows))
            print('Locked', selected, scores, flush=True)
            continue
        results[group] = rows
        evidence[group] = coordinates
        save(args.out/'results.json', dict(selected=selected, test=results,
             selection_sha256=digest(args.out/'selection.json')))
        save(args.out/'review-queues.json', dict(results_sha256=digest(args.out/'results.json'), test=evidence))


if __name__ == '__main__':
    main()
