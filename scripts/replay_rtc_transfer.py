"""Verify and summarize the two RTC follow-ups from their exported coordinates."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from replay_rtc_equal_review import DISTANCES, matching, sha256

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'reports/final/vietnam_rtc_transfer_20261119'
SPLITS = ('held_out', 'confirmation')
MODES = ('equal_incumbent', 'equal_relaxed')
COUNTS = ('labels', 'matched', 'predictions', 'unmatched')


def read(path):
    return json.loads(path.read_text())


def total(cases, mode, method, radius=100):
    return {key: sum(row[mode][method][str(radius)][key] for row in cases) for key in COUNTS}


def replay(directory, all_methods):
    result_path = directory/'results.json'
    selection_path = directory/'selection.json'
    audit = read(directory/'review-queues.json')
    result = read(result_path)
    selection = read(selection_path)
    if (sha256(result_path) != audit['results_sha256'] or sha256(selection_path) != result['selection_sha256']
            or selection['selected'] != result['selected']):
        raise ValueError(f'Broken results or development tie-back at {directory}')
    if set(result['test']) != set(SPLITS) or set(audit['test']) != set(SPLITS):
        raise ValueError('Expected both held-out groups')
    comparisons = 0
    seen_days = {case['scene'].split('_')[4][:8] for case in selection['cases']}
    for key in SPLITS:
        source = result['test'][key]
        coordinate_rows = audit['test'][key]
        verified = {row['scene']: row for row in coordinate_rows}
        days = {row['scene'].split('_')[4][:8] for row in source}
        if seen_days & days or len(verified) != len(source) or len(verified) != len(coordinate_rows):
            raise ValueError('Split overlaps or audit does not match case list')
        if set(verified) != {row['scene'] for row in source}:
            raise ValueError('Source scene IDs differ from exported coordinate scenes')
        seen_days.update(days)
        for row in source:
            coordinates = verified[row['scene']]
            labels = coordinates['labels']
            for mode in MODES:
                wanted = set(row[mode]) if all_methods else {'map', 'previous_best', result['selected'][mode]}
                queues = coordinates['queues'][mode]
                if set(queues) != wanted:
                    raise ValueError('Wrong methods in coordinate export')
                count = len(queues['map'])
                for name, points in queues.items():
                    if len(points) != count:
                        raise ValueError('Review counts differ')
                    for radius in DISTANCES:
                        count_matches = len(matching(points, labels, radius))
                        score = dict(labels=len(labels), predictions=count, matched=count_matches,
                                     unmatched=count-count_matches)
                        if score != row[mode][name][str(radius)]:
                            raise ValueError(f'Wrong score for {row["scene"]} / {mode} / {name} / {radius} m')
                        comparisons += 1
    return result, comparisons


def verify_example(directory):
    example = read(directory/'recovered-example.json')
    queue_path = directory/'review-queues.json'
    if sha256(queue_path) != example['queue_sha256']:
        raise ValueError('Example uses a different review queue')
    for side in ('before', 'after'):
        if sha256(directory/f'recovered-{side}.png') != example[f'{side}_image_sha256']:
            raise ValueError(f'Example image checksum differs for {side}')
    case, = (row for row in read(queue_path)['test']['held_out'] if row['scene'] == example['scene'])
    selected = read(directory/'selection.json')['selected'][example['review_mode']]
    if selected != example['method']:
        raise ValueError('Example method was not the selected method')
    queues = case['queues'][example['review_mode']]
    previous = queues[example['prior_method']]
    candidate = queues[selected]
    if len(previous) != len(candidate) or len(candidate) != example['scene_reviews']:
        raise ValueError('Example review counts differ')
    labels = case['labels']
    before, after = (matching(rows, labels, 100) for rows in (previous, candidate))
    if (len(before), len(after)) != (example['before_matches'], example['after_matches']):
        raise ValueError('Example source-scene match counts differ')
    previously_matched = {j for _, j, _ in before}
    recovered = {(tuple(labels[j]), tuple(candidate[i][:2]), round(distance, 2))
                 for i, j, distance in after if j not in previously_matched}
    shown = {(tuple(row['label']), tuple(row['candidate']), row['distance_m'])
             for row in example['recovered']}
    if not shown or not shown <= recovered:
        raise ValueError('An illustrated point does not match a recovered reference')


def verify(directory):
    weak, n_weak = replay(directory/'weak_echoes', False)
    transfer, n_transfer = replay(directory/'xview3', True)
    summary = {'comparisons': n_weak+n_transfer, 'datasets': {}}
    for key in SPLITS:
        weak_cases = weak['test'][key]
        transfer_cases = transfer['test'][key]
        if [row['scene'] for row in weak_cases] != [row['scene'] for row in transfer_cases]:
            raise ValueError('Follow-up scenes differ')
        dataset = summary['datasets'][key] = {'scenes': len(transfer_cases), 'modes': {}}
        for mode in MODES:
            for a, b in zip(weak_cases, transfer_cases, strict=True):
                for name in ('map', 'previous_best'):
                    if a[mode][name] != b[mode][name]:
                        raise ValueError('Common review controls differ')
            dataset['modes'][mode] = {
                'map': total(transfer_cases, mode, 'map'),
                'previous_best': total(transfer_cases, mode, 'previous_best'),
                'weak_echoes': total(weak_cases, mode, weak['selected'][mode]),
                'xview3': total(transfer_cases, mode, transfer['selected'][mode]),
            }
        dataset['coverage'] = {name: {field: sum(row[section][method]['100'][field] for row in rows)
                                     for field in COUNTS}
                               for name, section, method, rows in (
                                   ('previous', 'coverage', 'previous', weak_cases),
                                   ('weak_echoes', 'coverage', 'expanded', weak_cases),
                                   ('xview3', 'source_candidate_coverage', 'xview3', transfer_cases),
                                   ('combined', 'source_candidate_coverage', 'combined', transfer_cases))}
        dataset['missing_vh_windows'] = sum(len(row['missing_vh_windows']) for row in transfer_cases)
        dataset['windows'] = sum(row['windows'] for row in transfer_cases)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, default=EVIDENCE)
    parser.add_argument('--write-summary', action='store_true')
    args = parser.parse_args()
    report = verify(args.evidence)
    destination = args.evidence/'summary.json'
    if args.write_summary:
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    else:
        if read(destination) != report:
            raise ValueError('Saved summary disagrees with replay')
        verify_example(args.evidence/'xview3')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
