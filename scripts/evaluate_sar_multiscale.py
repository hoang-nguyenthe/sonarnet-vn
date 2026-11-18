"""Select a recall-oriented SLC inference policy on validation, then retest it."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import time

import numpy as np
from PIL import Image
import torch
from torchvision.ops import nms
import ultralytics

from evaluate_opensar_geo import assign_unique_support, open_split, restrict_to_scoring_support, score
from evaluate_ossdd_followup import normalize
from evaluate_sar_review_budget import REVIEW_RATE, prioritise
from prepare_opensar_geo import digest, save

SHAPES = {
    'native_512': ('512',),
    'whole_768': ('768',),
    'whole_1024': ('1024',),
    'dual_scale': ('512', '768'),
    'dual_scale_flip': ('512', '768', '768_flip'),
    'native_and_tiles': ('512', 'tiles'),
    'dual_scale_and_tiles': ('512', '768', 'tiles'),
}
THRESHOLDS = (.005, .01, .025, .05, .1)
BASELINE = ('native_512', .025)
SUPPRESSION_IOU = .45


def detect(model, image, size):
    boxes = model.predict(Image.fromarray(image).convert('RGB'), device='cpu',
                          imgsz=size, conf=min(THRESHOLDS), iou=.7,
                          max_det=1000, verbose=False)[0].boxes
    return boxes.xyxy.cpu().numpy(), boxes.conf.cpu().numpy()


def predict_pass(model, gray, mode):
    if mode == 'tiles':
        # Overlap gives small vessels near an internal border a complete view.
        tiles, scores = [], []
        for top, left in ((0, 0), (0, 192), (192, 0), (192, 192)):
            boxes, conf = detect(model, gray[top:top+320, left:left+320], 640)
            boxes += np.array([left, top, left, top], dtype=boxes.dtype)
            tiles.append(boxes)
            scores.append(conf)
        return np.concatenate(tiles), np.concatenate(scores)
    if mode == '768_flip':
        boxes, scores = detect(model, np.ascontiguousarray(gray[:, ::-1]), 768)
        boxes[:, [0, 2]] = gray.shape[1] - boxes[:, [2, 0]]
        return boxes, scores
    return detect(model, gray, int(mode))


def combine(raw, modes):
    if len(modes) == 1 and modes[0] != 'tiles':
        return raw[modes[0]]
    boxes = np.concatenate([raw[mode][0] for mode in modes])
    scores = np.concatenate([raw[mode][1] for mode in modes])
    keep = nms(torch.from_numpy(boxes), torch.from_numpy(scores), SUPPRESSION_IOU).numpy()
    return boxes[keep], scores[keep]


def infer_policies(rows, images, model, policies):
    modes = tuple(dict.fromkeys(mode for p in policies for mode in SHAPES[p]))
    output = {p: {} for p in policies}
    costs = {p: [] for p in policies}
    first = next(iter(images))
    gray = normalize(images[first], 'log1p')
    for mode in modes:
        predict_pass(model, gray, mode)
    for index, (ident, row) in enumerate(rows.items(), 1):
        start = time.perf_counter()
        gray = normalize(images[ident], 'log1p')
        normalization_ms = (time.perf_counter() - start) * 1000
        raw, elapsed = {}, {}
        for mode in modes:
            start = time.perf_counter()
            raw[mode] = predict_pass(model, gray, mode)
            elapsed[mode] = (time.perf_counter() - start) * 1000
        for p in policies:
            start = time.perf_counter()
            passes = SHAPES[p]
            output[p][ident] = restrict_to_scoring_support(row, *combine(raw, passes))
            costs[p].append(normalization_ms + sum(elapsed[m] for m in passes)
                            + (time.perf_counter() - start) * 1000)
        if index % 50 == 0 or index == len(rows):
            print('Inferred', index, '/', len(rows), flush=True)
    return output, costs


def count_metrics(rows, preds, threshold):
    full, _ = score(rows, preds, threshold)
    shortlist, budgets = prioritise(rows, preds, threshold, REVIEW_RATE, {}, 0.)
    capped, _ = score(rows, shortlist, 0.)
    return dict(full=full, fixed_budget=capped, per_scene_budgets=budgets)


def sort_key(row):
    full = row['full']
    fixed = row['fixed_budget']
    return (fixed['true_positive'], -fixed['false_positive'], full['true_positive'],
            -full['false_positive'], row['threshold'], row['policy'] == BASELINE[0])


def run(args):
    torch.set_num_threads(4)
    reference = json.loads((args.previous/'results.json').read_text())
    if reference['candidate_sha256'] != digest(args.weights):
        raise ValueError('Checkpoint differs from the scored SLC reference')
    previous_protocol = json.loads((args.previous/'protocol.json').read_text())
    tune_path = args.adaptation/'tune_manifest.json'
    cohorts = (
        ('diagnostic', args.diagnostic/'confirmation_manifest.json', args.data/'prepared-confirmation-v1'),
        ('north_sea', args.adaptation/'fresh_manifest.json', args.adaptation/'rasters'),
    )
    manifest_hashes = {name: digest(path) for name, path, _ in cohorts}
    if (previous_protocol['tune_sha256'] != digest(tune_path)
            or previous_protocol['diagnostic_sha256'] != manifest_hashes['diagnostic']
            or previous_protocol['fresh_sha256'] != manifest_hashes['north_sea']):
        raise ValueError('Evaluation manifests differ from the audited reference')
    args.out.mkdir(parents=True, exist_ok=False)
    save(args.out/'protocol.json', dict(
        created_utc=datetime.now(timezone.utc).isoformat(),
        code_sha256=digest(Path(__file__)), weights_sha256=digest(args.weights),
        previous_results_sha256=digest(args.previous/'results.json'),
        tune_sha256=digest(tune_path), test_manifest_sha256=manifest_hashes,
        methods=SHAPES, thresholds=THRESHOLDS, original_operating_point=BASELINE,
        nms_iou=SUPPRESSION_IOU, review_candidates_per_water_km2=REVIEW_RATE,
        validation_rule='Maximize matches at the fixed budget, then reduce unmatched candidates; use unrestricted counts and threshold as tie-breakers.',
        use='Validation scene selects a single policy. Diagnostic and North Sea are previously scored test scenes, kept out of fitting and policy selection.',
        timing='Median and p95 sum of CPU stages after pixel reads. Shared passes computed once; each policy charged for every pass it uses.',
        torch=torch.__version__, ultralytics=ultralytics.__version__, cpu_threads=4,
    ))
    model = ultralytics.YOLO(str(args.weights))
    tune, amp = open_split(tune_path, args.adaptation/'rasters')
    assign_unique_support(tune)
    predictions, _ = infer_policies(tune, amp, model, SHAPES)
    grid = []
    for p, preds in predictions.items():
        for threshold in THRESHOLDS:
            counts = count_metrics(tune, preds, threshold)
            grid.append(dict(policy=p, threshold=threshold, **counts))
    choice = max(grid, key=sort_key)
    point = args.out/'operating_point.json'
    save(point, dict(locked_utc=datetime.now(timezone.utc).isoformat(), selected=choice, validation=grid))
    print('Locked', choice['policy'], choice['threshold'], 'validation shortlist matches',
          choice['fixed_budget']['true_positive'], flush=True)
    del tune, amp, predictions

    report = dict(protocol_sha256=digest(args.out/'protocol.json'), operating_point_sha256=digest(point),
                  selected={'policy': choice['policy'], 'threshold': choice['threshold']}, evaluation={})
    settings = {'baseline': BASELINE, 'candidate': (choice['policy'], choice['threshold'])}
    for cohort, path, root in cohorts:
        print('Retest', cohort, flush=True)
        rows, images = open_split(path, root)
        assign_unique_support(rows)
        policies = tuple(dict.fromkeys(p for p, _ in settings.values()))
        predictions, costs = infer_policies(rows, images, model, policies)
        scores = {}
        for name, (p, threshold) in settings.items():
            file = args.out/f'{cohort}_{name}_predictions.json.gz'
            with gzip.open(file, 'wt') as file_stream:
                json.dump({i: dict(boxes=b.tolist(), scores=s.tolist())
                           for i, (b, s) in predictions[p].items()}, file_stream)
            scores[name] = dict(
                policy=p, threshold=threshold, prediction_sha256=digest(file),
                latency_ms=dict(p50=float(np.median(costs[p])), p95=float(np.percentile(costs[p], 95))),
                **count_metrics(rows, predictions[p], threshold),
            )
            print(cohort, name, 'matches', scores[name]['full']['true_positive'],
                  'shortlisted matches', scores[name]['fixed_budget']['true_positive'], flush=True)
        report['evaluation'][cohort] = dict(chips=len(rows), methods=scores)
        save(args.out/'results.json', report)
        del rows, images, predictions


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('adaptation', 'data', 'diagnostic', 'previous', 'weights', 'out'):
        parser.add_argument('--' + key, required=True, type=Path)
    run(parser.parse_args())
