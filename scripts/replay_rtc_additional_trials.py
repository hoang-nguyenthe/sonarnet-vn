"""Recount the additional historical RTC and stationary AIS tests from coordinates."""
from pathlib import Path

from replay_rtc_equal_review import DISTANCES, matching, sha256
from replay_rtc_transfer import read

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT/'reports/final'
EXTENSION = REPORTS/'vietnam_rtc_transfer_20261119/extension'
AIS = REPORTS/'stationary_ais_detection_20261120'
FIELDS = ('labels', 'predictions', 'matched', 'unmatched')


def compare(queues, labels, expected):
    for name, points in queues.items():
        for radius in DISTANCES:
            n = len(matching(points, labels, radius))
            row = dict(labels=len(labels), predictions=len(points), matched=n, unmatched=len(points)-n)
            if row != expected[name][str(radius)]:
                raise ValueError(f'Unexpected score for {name} within {radius} m')
    return len(queues)*len(DISTANCES)


def summarize(cases, field, methods):
    return {name:{str(radius):{key:sum(case[field][name][str(radius)][key] for case in cases)
                              for key in FIELDS} for radius in DISTANCES} for name in methods}


def verify_extension(path, original):
    result = read(path/'results.json')
    artifact = read(path/'review-queues.json')
    selection = read(path/'selection.json')
    protocol = read(path/'protocol.json')
    original_result = original.parent/'results.json'
    if (result['selection_sha256'] != sha256(path/'selection.json') or
            artifact['results_sha256'] != sha256(path/'results.json') or
            protocol['original_sha256'] != dict(coordinates=sha256(original),results=sha256(original_result))):
        raise ValueError('Extension provenance or original review list disagrees')
    base = read(original)
    winner = selection['selected']
    if result['selected'] != winner:
        raise ValueError('Scored policy differs from development choice')
    verified = 0
    for split in ('held_out','confirmation'):
        cases = result['test'][split]['cases']
        scored = artifact['test'][split]
        IDs = [row['scene'] for row in cases]
        if IDs != [row['scene'] for row in scored] or len(set(IDs))!=len(IDs):
            raise ValueError('Extension includes wrong scenes')
        original_scenes = {row['scene']:row for row in base['test'][split]}
        for case,audit in zip(cases,scored,strict=True):
            queues = audit['queues']
            if set(queues) != {'initial','lower_threshold',winner}:
                raise ValueError('Wrong extension methods')
            prior = original_scenes[case['scene']]
            if audit['labels'] != prior['labels'] or queues['initial'] != prior['queues']['equal_relaxed'][protocol['prior']]:
                raise ValueError('Extension changed the published shortlist or labels')
            count = len(queues['initial'])
            expanded = len(queues['lower_threshold'])
            for key in {'lower_threshold',winner}:
                if len(queues[key]) != expanded or queues[key][:count] != queues['initial']:
                    raise ValueError('Extension did not preserve the initial order or review count')
            verified += compare(queues,audit['labels'],case['measures'])
        totals = result['test'][split]['totals']
        if summarize(cases,'measures',totals) != totals:
            raise ValueError('Extension aggregate does not match per-scene scores')
    return verified


def verify_ais(path):
    result = read(path/'results.json')
    audit = read(path/'review-queues.json')
    references = read(path/'reference.json')
    if (result['protocol_sha256'] != sha256(path/'protocol.json') or
            result['references_sha256'] != sha256(path/'reference.json') or
            audit['results_sha256'] != sha256(path/'results.json')):
        raise ValueError('AIS evidence provenance differs')
    scenes = result['scenes']
    if len(scenes) != 6 or len({s['product'] for s in scenes})!=6:
        raise ValueError('AIS evaluation requires six unique scenes')
    verified = 0
    for row, points, ref in zip(scenes,audit['scenes'],references,strict=True):
        if row['product'] != points['product'] or row['product'] != ref['product']:
            raise ValueError('AIS references are for a different scene')
        ref_labels = ref['labels']
        if len(ref_labels)!=ref['reference_count']:
            raise ValueError('AIS reference count disagrees')
        queues = points['queues']
        narrow, wide = len(queues['base_at_035']), len(queues['base_at_005'])
        if (set(queues) != set(row['counts']) or
                len(queues['same_count_remove_duplicates']) != narrow or
                len(queues['same_count_overlap']) != narrow or
                len(queues['same_wide_count_overlap']) != wide):
            raise ValueError('AIS methods do not preserve their stated review counts')
        verified += compare(queues,ref_labels,row['counts'])
    if summarize(scenes,'counts',result['totals']) != result['totals']:
        raise ValueError('AIS aggregate does not match per-scene scores')
    return verified


if __name__=='__main__':
    original = EXTENSION.parent/'xview3/review-queues.json'
    counts = (verify_extension(EXTENSION,original),verify_ais(AIS))
    print(f'Independent matching verified {counts[0]} extension and {counts[1]} stationary AIS scores.')
