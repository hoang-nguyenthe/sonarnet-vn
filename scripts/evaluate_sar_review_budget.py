"""Replay frozen SLC predictions with an explicit per-acquisition review budget."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import gzip
import json
import math
from pathlib import Path

import numpy as np
from pyproj import Transformer
from shapely.geometry import Point, shape

from evaluate_opensar_geo import assign_unique_support, open_split, score
from prepare_opensar_geo import digest, land_shapes, pixel_xy, save

REVIEW_RATE = .05


def prioritise(rows, predictions, threshold, rate, coast_by_scene, nearshore_share):
    areas = defaultdict(float)
    ranking = defaultdict(list)
    selected = {ident: [] for ident in rows}
    for ident, row in rows.items():
        scene = row['scene_id']
        areas[scene] += row['sea'].area/1e6
        boxes, scores = predictions[ident]
        for i, confidence in enumerate(scores):
            if confidence >= threshold:
                nearshore = False
                coast = coast_by_scene.get(scene)
                if coast is not None and not coast.is_empty:
                    b = boxes[i]
                    xy = pixel_xy(row['corners_laea_m'], (b[0]+b[2])/2, (b[1]+b[3])/2)
                    nearshore = Point(*xy).distance(coast) <= 500
                ranking[scene].append((float(confidence), ident, i, nearshore))
    budgets = {}
    for scene, area in areas.items():
        limit = math.floor(area*rate)
        ranked = sorted(ranking[scene], key=lambda record: (-record[0], int(record[1]), record[2]))
        nearshore_limit = math.floor(limit*nearshore_share)
        priority = [record for record in ranked if record[3]][:nearshore_limit]
        earmarked = {(ident, i) for _, ident, i, _ in priority}
        remaining = [record for record in ranked if (record[1], record[2]) not in earmarked]
        shortlist = priority + remaining[:limit-len(priority)]
        for _, ident, i, _ in shortlist:
            selected[ident].append(i)
        budgets[scene] = dict(area_km2=area, candidate_limit=limit, available=len(ranked),
                             shortlisted=len(shortlist), earmarked_nearshore=len(priority))
    return {ident: (boxes[selected[ident]], scores[selected[ident]])
            for ident, (boxes, scores) in predictions.items()}, budgets


def run(args):
    base = args.evaluation/'results.json'
    initial = json.loads(base.read_text())
    output = args.out
    output.mkdir(parents=True, exist_ok=False)
    save(output/'protocol.json', dict(
        created_utc=datetime.now(timezone.utc).isoformat(), scored_reference_sha256=digest(base),
        code_sha256=digest(Path(__file__)), max_candidates_per_water_km2=REVIEW_RATE,
        design='Retrospective sensitivity after the first scored comparison. Reuse exact frozen predictions and confidence. Top confidence per acquisition, integer limit=floor(assigned water area x .05). Assign a reserved share to candidates <=500 m from GSHHG shoreline when requested. Do not use shortlist results to refit or promote the detector.',
        nearshore_reserved_fraction=args.nearshore_share,
    ))
    source = json.loads((args.data/'geo-audit-v3/source_screen.json').read_text())['scenes']
    comparison = {}
    for cohort, manifest, root in (
            ('diagnostic', args.diagnostic/'confirmation_manifest.json', args.data/'prepared-confirmation-v1'),
            ('north_sea', args.adaptation/'fresh_manifest.json', args.adaptation/'rasters')):
        rows, _ = open_split(manifest, root)
        assign_unique_support(rows)
        coast_by_scene = {}
        if args.nearshore_share:
            for row in rows.values():
                sid = row['scene_id']
                if sid not in coast_by_scene:
                    transform = Transformer.from_crs('EPSG:4326', row['crs'], always_xy=True).transform
                    _, coast_by_scene[sid] = land_shapes(args.data/'gshhg-shp-2.3.7.zip',
                                                        shape(source[sid]['footprint']), transform)
        threshold = initial['evaluation'][cohort]['models']['adapted_slc_vv']['threshold']
        path = args.evaluation/f'{cohort}_adapted_slc_vv_predictions.json.gz'
        with gzip.open(path, 'rt') as f:
            archive = json.load(f)
        if rows.keys() != archive.keys():
            raise ValueError('Prediction gallery and independent cohort IDs differ')
        predictions = {ident: (np.asarray(row['boxes']).reshape(-1, 4), np.asarray(row['scores']))
                       for ident, row in archive.items()}
        short, budgets = prioritise(rows, predictions, threshold, REVIEW_RATE, coast_by_scene, args.nearshore_share)
        metrics, errors = score(rows, short, threshold)
        data = dict(metrics=metrics, per_acquisition=budgets, predictions_sha256=digest(path))
        comparison[cohort] = data
        with gzip.open(output/f'{cohort}_errors.json.gz', 'wt') as f:
            json.dump(errors, f)
        print(cohort, metrics['true_positive'], '/', metrics['n_ground_truth'], 'unmatched',
              metrics['false_positive'], 'per km2', metrics['benchmark_unmatched_per_km2'], flush=True)
    save(output/'results.json', dict(shortlist_max_per_km2=REVIEW_RATE,
                                     nearshore_reserved_fraction=args.nearshore_share, evaluation=comparison))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('data', 'adaptation', 'diagnostic', 'evaluation', 'out'):
        parser.add_argument('--'+name, required=True, type=Path)
    parser.add_argument('--nearshore-share', type=float, default=0.)
    args = parser.parse_args()
    if not 0 <= args.nearshore_share <= 1:
        parser.error('--nearshore-share must be between zero and one')
    run(args)
