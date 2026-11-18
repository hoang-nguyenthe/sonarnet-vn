"""Check threshold and coastal-review effects on frozen multiscale predictions."""
import argparse
import gzip
import json
from pathlib import Path

import numpy as np
from pyproj import Transformer
from shapely.geometry import shape

from evaluate_opensar_geo import assign_unique_support, open_split, score
from evaluate_sar_review_budget import REVIEW_RATE, prioritise
from prepare_opensar_geo import digest, land_shapes, save

COASTAL_SHARE = .20


def read_predictions(path, expected, rows):
    if digest(path) != expected:
        raise ValueError('Prediction checksum changed')
    with gzip.open(path, 'rt') as f:
        archive = json.load(f)
    if archive.keys() != rows.keys():
        raise ValueError('Prediction and real-SAR sample IDs differ')
    return {i: (np.asarray(item['boxes']).reshape(-1, 4), np.asarray(item['scores']))
            for i, item in archive.items()}


def run(args):
    path_results = args.evaluation/'results.json'
    report = json.loads(path_results.read_text())
    protocol = json.loads((args.evaluation/'protocol.json').read_text())
    candidate_cut = report['selected']['threshold']
    source = json.loads((args.data/'geo-audit-v3/source_screen.json').read_text())['scenes']
    comparisons = {}
    for cohort, manifest, root in (
            ('diagnostic', args.diagnostic/'confirmation_manifest.json', args.data/'prepared-confirmation-v1'),
            ('north_sea', args.adaptation/'fresh_manifest.json', args.adaptation/'rasters')):
        if digest(manifest) != protocol['test_manifest_sha256'][cohort]:
            raise ValueError('Test manifest differs from frozen protocol')
        rows, _ = open_split(manifest, root)
        assign_unique_support(rows)
        methods = report['evaluation'][cohort]['methods']
        coast = {}
        for row in rows.values():
            sid = row['scene_id']
            if sid not in coast:
                transform = Transformer.from_crs('EPSG:4326', row['crs'], always_xy=True).transform
                _, coast[sid] = land_shapes(args.data/'gshhg-shp-2.3.7.zip',
                                           shape(source[sid]['footprint']), transform)
        comparisons[cohort] = {}
        for name, config in methods.items():
            predictions = read_predictions(args.evaluation/f'{cohort}_{name}_predictions.json.gz',
                                          config['prediction_sha256'], rows)
            if name == 'baseline':
                all_native, _ = score(rows, predictions, candidate_cut)
                shortlist, _ = prioritise(rows, predictions, candidate_cut, REVIEW_RATE, {}, 0.)
                limited_native, _ = score(rows, shortlist, 0.)
                comparisons[cohort]['native_at_candidate_threshold'] = dict(
                    threshold=candidate_cut, full=all_native, fixed_budget=limited_native)
            shortlist, budget = prioritise(rows, predictions, config['threshold'], REVIEW_RATE, coast, COASTAL_SHARE)
            metrics, _ = score(rows, shortlist, 0.)
            comparisons[cohort][name] = dict(coastal_budget=metrics, per_scene_budgets=budget)
            print(cohort, name, 'coast shortlist', metrics['true_positive'],
                  metrics['by_distance_to_mapped_shore_m'][500], flush=True)
    save(args.out, dict(
        purpose='Post-hoc attribution and sensitivity analysis. No change to the configuration selected on validation.',
        base_results_sha256=digest(path_results), code_sha256=digest(Path(__file__)),
        candidates_per_water_km2=REVIEW_RATE, nearshore_reserved_fraction=COASTAL_SHARE,
        evaluation=comparisons,
    ))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('adaptation', 'data', 'diagnostic', 'evaluation', 'out'):
        parser.add_argument('--'+key, required=True, type=Path)
    run(parser.parse_args())
