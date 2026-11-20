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


def verify_dual_band(path, prior):
    protocol = read(path/'protocol.json')
    results = read(path/'results.json')
    audit = read(path/'review-queues.json')
    prior_queues = read(prior/'review-queues.json')
    references = read(prior/'reference.json')
    if (results['protocol_sha256'] != sha256(path/'protocol.json') or
            audit['result_sha256'] != sha256(path/'results.json') or
            protocol['reference_sha256'] != sha256(prior/'reference.json') or
            protocol['baseline_queues_sha256'] != sha256(prior/'review-queues.json') or
            protocol['baseline_results_sha256'] != sha256(prior/'results.json')):
        raise ValueError('Dual-band result or source references differ')
    evaluator = ROOT/'scripts/evaluate_xview3_stationary_ais.py'
    if protocol['code_sha256'] != sha256(evaluator):
        raise ValueError('Dual-band evaluator code differs from recorded trial')
    slices = results['scenes']
    if len(slices)!=6 or len({row['product'] for row in slices})!=6:
        raise ValueError('Dual-band experiment requires six unique scenes')
    verified = 0
    for row, packet, label, old in zip(slices,audit['scenes'],references,prior_queues['scenes'],strict=True):
        if len({case['product'] for case in (row,packet,label,old)}) != 1:
            raise ValueError('Cross-check includes different scenes')
        manifest = path/'source-bands'/f"{row['product']}.json"
        if sha256(manifest) != row['raster_manifest_sha256']:
            raise ValueError('Dual-band window manifest differs')
        source = read(manifest)
        if source['product'] != row['product'] or source['utc'] != row['utc']:
            raise ValueError('Dual-band COG metadata and measured image differ')
        fractions = row['both_bands_valid_fraction_by_window']
        if len(source['windows']) != len(fractions) or any(not 0 <= f <= 1 for f in fractions):
            raise ValueError('Dual-band coverage is inconsistent with its raster inventory')
        for mode, (base, prior_name, _) in protocol['mode'].items():
            entries = packet['queues'][mode]
            if (entries['original'] != old['queues'][base] or
                    entries['prior'] != old['queues'][prior_name] or
                    set(entries)!=set(row['scores'][mode]) or
                    any(len(queue)!=len(entries['original']) for queue in entries.values())):
                raise ValueError('Transferred rank changed the fixed baseline or review count')
            verified += compare(entries,label['labels'],row['scores'][mode])
    for mode, methods in results['totals'].items():
        values = [{'counts':row['scores'][mode]} for row in slices]
        if summarize(values,'counts',methods) != methods:
            raise ValueError('Dual-band aggregate disagrees with per-scene results')
    example_path = path/'example.json'
    if example_path.is_file():
        verify_dual_band_example(read(example_path), results, audit, references, path)
    return verified


def verify_dual_band_example(example, results, audit, references, path):
    identifier = example['product']
    if example['review_queues_sha256'] != sha256(path/'review-queues.json'):
        raise ValueError('Illustration has a different review queue')
    for image in example['images'].values():
        if sha256(path/image['name']) != image['sha256']:
            raise ValueError('Illustration pixels differ')
    result, = (row for row in results['scenes'] if row['product']==identifier)
    packet, = (row for row in audit['scenes'] if row['product']==identifier)
    labels, = (row['labels'] for row in references if row['product']==identifier)
    tile = read(path/'source-bands'/f'{identifier}.json')['windows'][example['tile']]
    if (example['source_preview_sha256']!=tile['preview_sha256'] or
            (example['before'], example['after']) != tuple(
                result['scores']['narrow'][method]['100']['matched'] for method in ('prior','fused_xview3'))):
        raise ValueError('Illustration scene result or image source differs')
    queues=packet['queues']['narrow']
    before,after=(matching(queues[method],labels,100) for method in ('prior','fused_xview3'))
    known={j for _,j,_ in before}
    recovered={(tuple(labels[j]),tuple(queues['fused_xview3'][i][:2]),round(distance,2))
               for i,j,distance in after if j not in known}
    if (tuple(example['reference']),tuple(example['candidate']),example['distance_m']) not in recovered:
        raise ValueError('Highlighted marker does not represent a recovered match')


if __name__=='__main__':
    original = EXTENSION.parent/'xview3/review-queues.json'
    counts = (verify_extension(EXTENSION,original),verify_ais(AIS))
    print(f'Independent matching verified {counts[0]} extension and {counts[1]} stationary AIS scores.')
    dual_band = AIS/'dual-band'
    if (dual_band/'results.json').is_file():
        print(f'Independent matching verified {verify_dual_band(dual_band,AIS)} dual-band scores.')
