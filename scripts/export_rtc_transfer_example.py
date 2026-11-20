"""Create the xView3 before-and-after image from its locked review queues."""
import argparse
import json
from pathlib import Path

from export_rtc_review_evidence import illustration
from replay_rtc_transfer import EVIDENCE, sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--font', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, default=EVIDENCE)
    args = parser.parse_args()
    directory = args.evidence/'xview3'
    summary = json.loads((args.evidence/'summary.json').read_text())['datasets']['held_out']
    protocol = json.loads((directory/'protocol.json').read_text())
    manifest = args.source/'rtc-512/manifest.json'
    if sha256(manifest) != protocol['inputs']['held_out']['vv_manifest_sha256']:
        raise ValueError('Source raster manifest does not match the benchmark')
    result = json.loads((directory/'results.json').read_text())
    path = directory/'review-queues.json'
    audit = json.loads(path.read_text())
    if audit['results_sha256'] != sha256(directory/'results.json'):
        raise ValueError('Saved result does not match the queue file')
    mode = max(summary['modes'], key=lambda mode: summary['modes'][mode]['xview3']['matched']
               - summary['modes'][mode]['previous_best']['matched'])
    before, after = (summary['modes'][mode][key]['matched'] for key in ('previous_best','xview3'))
    if after <= before:
        raise ValueError('Neither locked procedure improves the held-out total')
    selected = result['selected'][mode]
    source_rows = {row['scene']: row for row in result['test']['held_out']}
    # Reuse the established rendering pipeline for a different pair of queues.
    cases = [dict(scene=row['scene'], region=source_rows[row['scene']]['region'], labels=row['labels'],
                  queues={'equal_relaxed': {
                      'map_lower_threshold': row['queues'][mode]['previous_best'],
                      'overlap_only_max': row['queues'][mode][selected]}})
             for row in audit['test']['held_out']]
    example = illustration(args.source, cases, args.font, directory)
    example.update(review_mode=mode, method=selected, prior_method='previous_best', queue_sha256=sha256(path))
    for when in ('before', 'after'):
        example[f'{when}_image_sha256'] = sha256(directory/f'recovered-{when}.png')
    (directory/'recovered-example.json').write_text(json.dumps(example, ensure_ascii=False, indent=2)+'\n')
    print(f"{example['window_id']}: {example['before_matches']} → {example['after_matches']} at {example['scene_reviews']}")


if __name__ == '__main__':
    main()
