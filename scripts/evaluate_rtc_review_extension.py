"""Measure extra recall from appending candidates to the fixed published shortlist."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import json
import math
from pathlib import Path

from evaluate_review_ranking import save
from evaluate_rtc_contrast_recall import RADII, shortlist
from evaluate_rtc_map_tta import ranked_views
from evaluate_rtc_xview3_transfer import score_rows
from score_vn_reference_rtc import digest, matched, refill

BASE = 'xview3_fused_tta'
MODE = 'equal_relaxed'
PROFILES = {
    'lower_threshold': {},
    'add_zoom': {'zoom': .8},
    'add_xview3': {'xview3': .4},
    'add_zoom_and_xview3': {'zoom': .8, 'xview3': .4},
    'add_coast': {'coast': .5},
}


def ranked(rows):
    return sorted(rows, key=lambda row: -row[2])


def queues(case, overlap, weak, transfer):
    yolos = ranked(case['baseline_low'])
    centers = score_rows(transfer['tta'], True)
    base_count = min(len(yolos), case['budget'])
    # Reproduce the public shortlist from the same score pools.
    prior = shortlist(ranked_views(yolos, {'overlap': overlap, 'xview3': centers}, 'max'),
                      shortlist(ranked_views(yolos, {'overlap': overlap}, 'max'), yolos, base_count, 35.),
                      base_count, 35.)
    provisional_limit = min(case['budget'], base_count + max(2, math.ceil(base_count*.5)))
    control_pool = [*yolos, *overlap, *weak['full']]
    control = refill(prior, ranked(control_pool), provisional_limit)
    review_limit = len(control)
    sources = {'xview3': centers, 'zoom': weak['zoom'], 'coast': weak['coast']}
    outcomes = {'initial': prior, 'lower_threshold': control}
    for policy, weights in PROFILES.items():
        if policy == 'lower_threshold':
            continue
        candidates = [*control_pool]
        candidates.extend([x,y,score*weight] for name,weight in weights.items()
                          for x,y,score in sources[name])
        extra = refill(prior, ranked(candidates), review_limit)
        if len(extra) < review_limit:
            # If deduplication consumed the added pool, refill with the same
            # control candidates that cost an extra review in the comparison.
            seen = {tuple(row[:2]) for row in extra}
            extra.extend([row for row in control[base_count:] if tuple(row[:2]) not in seen]
                         [:review_limit-len(extra)])
        if len(extra) != review_limit or extra[:base_count] != prior:
            raise ValueError('Appended review list changed the initial queue or exact count')
        outcomes[policy] = extra
    return outcomes


def inputs(neural, tta, confirmation, weak, transfer):
    group = {}
    for name, cache, base in (
            ('development', neural/'development_features.json.gz', tta/'development-views.json'),
            ('held_out', neural/'fresh_features.json.gz', tta/'held-out-views.json'),
            ('confirmation', confirmation/'baseline.json.gz', confirmation/'views.json')):
        group[name] = dict(cache=cache, base=base, weak=weak/f'{name}-views.json',
                           transfer=transfer/f'{name}-candidates.json')
    return group


def run_group(files, existing):
    with gzip.open(files['cache'], 'rt') as archive:
        cases = json.load(archive)
    base, weak, transfer = (json.loads(files[key].read_text()) for key in ('base','weak','transfer'))
    initial = {row['scene']: row['queues'][MODE][BASE] for row in existing}
    results, replay = [], []
    for case in cases:
        scene, labels = case['scene'], case['truth']
        scored = queues(case, base[scene]['overlap'], weak[scene], transfer[scene])
        if initial and [tuple(row) for row in scored['initial']] != [tuple(row) for row in initial[scene]]:
            raise ValueError('Recomputed initial list differs from published coordinate export')
        measures = {policy: matched(rows, labels, RADII) for policy, rows in scored.items()}
        results.append(dict(scene=scene, region=case['region'], windows=case['windows'], measures=measures))
        replay.append(dict(scene=scene, labels=labels, queues=scored))
    return results, replay


def totals(rows, policy):
    return {radius:{field:sum(row['measures'][policy][radius][field] for row in rows)
                    for field in ('labels','matched','predictions','unmatched')} for radius in RADII}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('cached-neural','tta','confirmation-cache','weak-echoes','transfer','out'):
        parser.add_argument('--'+flag, type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(exist_ok=False)
    recordings = inputs(args.cached_neural,args.tta,args.confirmation_cache,args.weak_echoes,args.transfer)
    original_packet = args.transfer/'review-queues.json'
    original_results = args.transfer/'results.json'
    packet = json.loads(original_packet.read_text())
    result = json.loads(original_results.read_text())
    if packet['results_sha256'] != digest(original_results) or result['selected'][MODE] != BASE:
        raise ValueError('The original public evaluation differs')
    save(args.out/'protocol.json', dict(
        locked_utc=datetime.now(timezone.utc).isoformat(), code_sha256=digest(Path(__file__)),
        prior=BASE, match_metres=RADII, mix_weights=PROFILES,
        scope='Retrospective check on acquisition days used for previous SonarNet evaluations.',
        limit='Keep all 191 published suggestions. Allow at most max(2, ceil(0.5 * baseline count)) more per scene under its prior area cap. Control eligible count sets the exact total for every method.',
        selection='Compare 100 m matched labels on the five development acquisitions, then apply across different UTC days. Ties prefer the lower-threshold control.',
        original_sha256={'coordinates':digest(original_packet),'results':digest(original_results)},
        inputs={key:{name:digest(path) for name,path in paths.items()} for key,paths in recordings.items()},
    ))
    dev, _ = run_group(recordings['development'],[])
    scores = {name:totals(dev,name)[100]['matched'] for name in PROFILES}
    selected = max(scores,key=lambda key:(scores[key],key == 'lower_threshold'))
    save(args.out/'selection.json', dict(selected=selected, development=scores, cases=dev))
    print('Selected',selected,scores,flush=True)
    days = {row['scene'].split('_')[4][:8] for row in dev}
    test, audit = {}, {}
    for group in ('held_out','confirmation'):
        results, raw = run_group(recordings[group], packet['test'][group])
        dates = {row['scene'].split('_')[4][:8] for row in results}
        if dates & days:
            raise ValueError('Evaluation UTC days overlap')
        days.update(dates)
        stats = {name:totals(results,name) for name in ('initial',*PROFILES)}
        test[group] = dict(cases=results, totals=stats)
        audit[group] = [dict(scene=row['scene'], labels=row['labels'], queues={
            name:row['queues'][name] for name in dict.fromkeys(('initial','lower_threshold',selected))})
            for row in raw]
        print(group,{name:value[100] for name,value in stats.items()},flush=True)
    save(args.out/'results.json', dict(selected=selected, test=test,
         selection_sha256=digest(args.out/'selection.json')))
    save(args.out/'review-queues.json', dict(test=audit, results_sha256=digest(args.out/'results.json')))


if __name__ == '__main__':
    main()
