"""Recount the published equal-cost recall results from the reviewed coordinates."""
import argparse
from hashlib import file_digest
import json
from pathlib import Path

import numpy as np
from pyproj import Geod
from scipy.optimize import linear_sum_assignment

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'reports/final/vietnam_rtc_tta_20261119'
DISTANCES = (50, 100, 150)
GEOD = Geod(ellps='WGS84')
POLICIES = {
    'equal_incumbent': ('map_default', 'distinct_35m'),
    'equal_relaxed': ('map_lower_threshold', 'overlap_only_max'),
}


def sha256(path):
    with path.open('rb') as source:
        return file_digest(source, 'sha256').hexdigest()


def matching(predictions, labels, radius):
    """Maximum cardinality within radius, then minimum total WGS84 distance."""
    if not predictions or not labels:
        return []
    p, lab = np.asarray(predictions)[:, :2], np.asarray(labels)
    shape = (len(p), len(lab), 2)
    left = np.broadcast_to(p[:, None, :], shape).reshape(-1, 2)
    right = np.broadcast_to(lab[None, :, :], shape).reshape(-1, 2)
    _, _, distance = GEOD.inv(left[:, 0], left[:, 1], right[:, 0], right[:, 1])
    metres = np.asarray(distance).reshape(shape[:2])
    if not np.isfinite(metres).all():
        raise ValueError('Non-finite distance between candidate and label')
    penalty = (min(shape[:2])+1)*(radius+1)
    cost = np.where(metres <= radius, metres, penalty)
    i, j = linear_sum_assignment(cost)
    return [(int(a), int(b), float(metres[a,b])) for a,b in zip(i,j) if metres[a,b] <= radius]


def recount(packet, contrast, tta):
    index = [{c['scene']: c for c in x['cases']} for x in (contrast, tta)]
    scenes = [c['scene'] for c in packet['cases']]
    if len(set(scenes)) != len(scenes) or any(set(scenes) != set(d) for d in index):
        raise ValueError('Published scenes and replay scenes differ')
    totals = {mode: {method: {} for method in methods} for mode,methods in POLICIES.items()}
    for case in packet['cases']:
        scene = case['scene']
        labels = case['labels']
        for mode,methods in POLICIES.items():
            expected = index[0 if mode == 'equal_incumbent' else 1][scene][mode]
            queues = case['queues'][mode]
            if set(queues) != set(methods) or len(queues[methods[0]]) != len(queues[methods[1]]):
                raise ValueError(f'Review budget or method mismatch on {scene}')
            for method in methods:
                proposals = queues[method]
                for radius in DISTANCES:
                    count = len(matching(proposals, labels, radius))
                    actual = dict(labels=len(labels), predictions=len(proposals),
                                  matched=count, unmatched=len(proposals)-count)
                    if actual != expected[method][str(radius)]:
                        raise ValueError(f'Replay disagrees on {scene} / {method} / {radius} m')
                    table = totals[mode][method].setdefault(radius, {name: 0 for name in actual})
                    for name,value in actual.items():
                        table[name] += value
    return dict(scenes=len(scenes), policies=totals)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--packet', type=Path, default=EVIDENCE/'review-queues.json')
    p.add_argument('--contrast', type=Path,
                   default=ROOT/'reports/final/vietnam_rtc_contrast_20261119/results.json')
    p.add_argument('--tta', type=Path, default=EVIDENCE/'results.json')
    args = p.parse_args()
    packet = json.loads(args.packet.read_text())
    for key,path in (('contrast_results',args.contrast),('tta_results',args.tta)):
        if sha256(path) != packet['sha256'][key]:
            raise ValueError(f'Saved benchmark checksum differs ({key})')
    report = recount(packet, json.loads(args.contrast.read_text()), json.loads(args.tta.read_text()))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
