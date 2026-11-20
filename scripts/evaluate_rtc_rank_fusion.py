"""Replay equal-count reciprocal rank fusion from public historical proposals."""
import argparse
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path

import numpy as np

from replay_rtc_equal_review import DISTANCES, GEOD, matching, sha256


ROOT = Path(__file__).resolve().parents[1]
TRANSFER = ROOT / 'reports/final/vietnam_rtc_transfer_20261119'
MODES = {'equal_incumbent': 'incumbent', 'equal_relaxed': 'baseline_low'}
POLICIES = ('published', 'rank_60', 'rank_scaled', 'rank_60_keep_75')
DUPLICATE_METRES = 35


def distance(points, neighbours):
    shape = (len(points), len(neighbours), 2)
    a = np.broadcast_to(np.asarray(points)[:, None, :2], shape).reshape(-1, 2)
    b = np.broadcast_to(np.asarray(neighbours)[None, :, :2], shape).reshape(-1, 2)
    _, _, metres = GEOD.inv(a[:, 0], a[:, 1], b[:, 0], b[:, 1])
    return np.asarray(metres).reshape(shape[:2])


def keep_distinct(points, budget, prefix=()):
    retained = list(prefix)
    if not points or len(retained) == budget:
        return retained
    collisions = distance(points, points) <= DUPLICATE_METRES
    blocked = (distance(points, retained) <= DUPLICATE_METRES).any(axis=1) if retained else np.zeros(len(points), dtype=bool)
    selected = []
    for i, point in enumerate(points):
        if len(retained) == budget:
            break
        if not blocked[i] and not collisions[i, selected].any():
            retained.append(point)
            selected.append(i)
    return retained


def complete(kept, fallback, count):
    # Preserve the archived study's exact workload even when several original
    # proposals shared a location and consumed more than one review.
    seen = {tuple(point[:2]) for point in kept}
    for row in fallback:
        if len(kept) == count:
            return kept
        xy = tuple(row[:2])
        if xy not in seen:
            kept.append(row)
            seen.add(xy)
    return kept + fallback[:count-len(kept)]


def ordered(rows):
    return sorted(rows, key=lambda point: -point[2])


def ranks(first, second, constant):
    points = first + second
    if not points:
        return []
    score = np.zeros(len(points))
    for family in (first, second):
        if family:
            agrees = distance(points, family) <= DUPLICATE_METRES
            score += np.max(agrees / (constant + np.arange(1, len(family)+1)), axis=1)
    return [(*points[i][:2], float(score[i])) for i in np.argsort(-score, kind='stable')]


def measure(rows, labels):
    result = {}
    for radius in DISTANCES:
        hits = len(matching(rows, labels, radius))
        result[radius] = dict(labels=len(labels), matched=hits, predictions=len(rows), unmatched=len(rows)-hits)
    return result


def score(cases, expected=None):
    reports, records = [], []
    for case in cases:
        scene, labels = case['scene'], case['truth']
        report = dict(scene=scene, windows=case['windows'], modes={})
        record = dict(scene=scene, labels=labels, modes={})
        for mode, source in MODES.items():
            initial = ordered(case[source])
            count = min(len(initial), case['budget'])
            yolo = case['baseline_low'] + (case['overlap'] if mode == 'equal_relaxed' else [])
            transfer = case['transfer']
            prior = complete(keep_distinct(ordered(yolo), count), initial, count)
            if mode == 'equal_relaxed':
                baseline = complete(keep_distinct(ordered(yolo + transfer), count), prior, count)
                reference = 'xview3_fused_tta'
            else:
                baseline = prior
                reference = 'previous_best'
            if expected is not None:
                original = expected[scene]
                if labels != original['labels'] or baseline != original['queues'][mode][reference]:
                    raise ValueError('The published baseline or label list differs')
            first = keep_distinct(ordered(yolo), len(yolo))
            second = keep_distinct(ordered(transfer), len(transfer))
            rank_60 = ranks(first, second, 60)
            prefix = baseline[:max(0, count - max(1, count//4))]
            queues = {
                'published': baseline,
                'rank_60': complete(keep_distinct(rank_60, count), baseline, count),
                'rank_scaled': complete(keep_distinct(ranks(first, second, max(1, count/2)), count), baseline, count),
                'rank_60_keep_75': complete(keep_distinct(rank_60 + baseline, count, prefix), baseline, count),
            }
            if any(len(queue) != count for queue in queues.values()):
                raise ValueError('Review counts differ')
            report['modes'][mode] = {key: measure(points, labels) for key, points in queues.items()}
            full = measure(yolo + transfer, labels)
            report['modes'][mode]['pool_ceiling'] = {
                radius: min(count, full[radius]['matched']) for radius in DISTANCES
            }
            record['modes'][mode] = queues
        reports.append(report)
        records.append(record)
    return reports, records


def totals(rows):
    metrics = ('matched', 'predictions', 'labels', 'unmatched')
    return {
        mode: {
            key: {radius: {field: sum(row['modes'][mode][key][radius][field] for row in rows)
                           for field in metrics} for radius in DISTANCES}
            for key in POLICIES
        } | {'pool_ceiling': {radius: sum(row['modes'][mode]['pool_ceiling'][radius] for row in rows)
                              for radius in DISTANCES}}
        for mode in MODES
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=TRANSFER/'rank_fusion/candidates.json.gz')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with gzip.open(args.input, 'rt') as stream:
        inputs = json.load(stream)['data']
    release = TRANSFER/'xview3/review-queues.json'
    published = json.loads(release.read_text())['test']
    args.output.mkdir(exist_ok=False)

    def write(filename, item):
        (args.output/filename).write_text(json.dumps(item, ensure_ascii=False, indent=2)+'\n')

    write('protocol.json', {
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'code_sha256': sha256(Path(__file__)),
        'input_sha256': sha256(args.input),
        'published_queue_sha256': sha256(release),
        'rationale_reference': 'https://doi.org/10.1145/1571941.1572114',
        'matching': 'One-to-one WGS84 at 50, 100 and 150 m. Every method has the same number of reviews per acquisition.',
        'ranks': 'Suppress duplicates within 35 m per detector and add at most one reciprocal rank from each detector.',
        'lock_scope': 'Retrospective: development and scoring dates are disjoint. All scoring acquisitions have been used in earlier SonarNet experiments.',
        'guarded_scope': 'The guarded method was designed after observing the unguarded results on these historical scoring acquisitions. It is exploratory.',
        'pool_ceiling': 'Upper bound: min(review count, matches in the complete candidate pool), per acquisition.',
    })
    dev, _ = score(inputs['development'])
    scores = totals(dev)
    pure = POLICIES[:-1]
    chosen = {mode: max(pure, key=lambda key: scores[mode][key][100]['matched']) for mode in MODES}
    write('selection.json', {'selected_unguarded': chosen, 'totals': scores})
    previous_days = {item['scene'].split('_')[4][:8] for item in dev}
    results, evidence = {}, {}
    for group in ('held_out', 'confirmation'):
        known = {item['scene']: item for item in published[group]}
        if {item['scene'] for item in inputs[group]} != set(known):
            raise ValueError('The tested acquisitions differ from the published comparison')
        rows, packets = score(inputs[group], known)
        days = {item['scene'].split('_')[4][:8] for item in rows}
        if days & previous_days:
            raise ValueError('Acquisition dates overlap')
        previous_days.update(days)
        results[group] = dict(scenes=rows, totals=totals(rows))
        evidence[group] = packets
    write('results.json', {'selection_sha256':sha256(args.output/'selection.json'), 'test':results})
    write('review-queues.json', {'results_sha256':sha256(args.output/'results.json'), 'test':evidence})


if __name__ == '__main__':
    main()
