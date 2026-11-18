"""Lock the SLC detector on geographic validation before scoring held-out scenes."""
import argparse
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import platform
import time

import numpy as np
from PIL import Image

from evaluate_opensar_geo import assign_unique_support, open_split, restrict_to_scoring_support, score
from evaluate_ossdd_followup import normalize
from evaluate_sar_recall_candidates import cfar_propose, pixels_in_support
from prepare_opensar_geo import ROOT, digest, save
from sonarnet.evaluation.independent_sar import operational_metrics

CONFIDENCE = (.025, .05, .075, .10, .15, .20, .30, .40, .50)
REFERENCE_CONF = .10
MIN_CONF = .01
THREADS = 4
RING = (7, 29, 4.4)


def infer_split(rows, amplitudes, model=None, size=None):
    def infer(ident):
        amplitude = amplitudes[ident]
        gray = normalize(amplitude, 'log1p')
        if model is None:
            boxes, scores = cfar_propose(gray, pixels_in_support(rows[ident], amplitude), *RING)
        else:
            result = model.predict(Image.fromarray(gray).convert('RGB'), device='cpu', imgsz=size,
                                   conf=MIN_CONF, iou=.7, max_det=1000, verbose=False)[0]
            boxes, scores = result.boxes.xyxy.cpu().numpy(), result.boxes.conf.cpu().numpy()
        return restrict_to_scoring_support(rows[ident], boxes, scores)

    first = next(iter(rows))
    for _ in range(3):
        infer(first)
    predictions, durations = {}, []
    for i, ident in enumerate(rows, start=1):
        start = time.perf_counter()
        predictions[ident] = infer(ident)
        durations.append((time.perf_counter()-start)*1000)
        if i % 100 == 0:
            print('Scored inputs', i, '/', len(rows), flush=True)
    return predictions, dict(p50=float(np.median(durations)), p95=float(np.percentile(durations, 95)))


def compare(rows, amplitudes, model, size, threshold, out, name):
    predictions, latency = infer_split(rows, amplitudes, model, size)
    metrics, failures = score(rows, predictions, threshold)
    per_scene = {}
    for sid in sorted({row['scene_id'] for row in rows.values()}):
        subset = {i:row for i, row in rows.items() if row['scene_id'] == sid}
        per_scene[sid], _ = score(subset, {i:predictions[i] for i in subset}, threshold)
    with gzip.open(out/f'{name}_predictions.json.gz', 'wt') as stream:
        json.dump({i:dict(boxes=b.tolist(), scores=s.tolist()) for i,(b,s) in predictions.items()}, stream)
    with gzip.open(out/f'{name}_errors.json.gz', 'wt') as stream:
        json.dump(failures, stream)
    return dict(threshold=threshold, imgsz=size, metrics=metrics, per_scene=per_scene, latency_ms=latency)


def evaluate(args):
    import torch
    import ultralytics
    torch.set_num_threads(THREADS)
    audit = json.loads((args.adaptation/'audit.json').read_text())
    phase = json.loads((args.adaptation/'data_policy.json').read_text())
    fresh_path = args.adaptation/'fresh_manifest.json'
    tune_path = args.adaptation/'tune_manifest.json'
    diagnostic_path = args.diagnostic/'confirmation_manifest.json'
    if (not audit['passed'] or audit['fresh_manifest_sha256'] != digest(fresh_path)
            or phase['diagnostic_manifest_sha256'] != digest(diagnostic_path)):
        raise ValueError('Held-out cohort differs from its pretraining audit')
    provenance = json.loads((args.candidate.parent.parent/'provenance.json').read_text())
    if provenance.get('best_sha256') != digest(args.candidate):
        raise ValueError('Candidate is not the recorded best checkpoint of a finished run')
    if provenance['dataset_manifest_sha256'] != audit['manifest_sha256']:
        raise ValueError('Training lineage does not match the audited cohort')
    size = provenance['training']['imgsz']
    candidates = {'best_ap': args.candidate, 'last_epoch': args.candidate.with_name('last.pt')}
    candidate_hashes = {name: digest(path) for name, path in candidates.items()}
    args.out.mkdir(parents=True, exist_ok=False)
    protocol=dict(
        created_utc=datetime.now(timezone.utc).isoformat(), candidate_hashes=candidate_hashes,
        old_ls_ssdd_sha256=digest(args.reference), training_provenance_sha256=digest(args.candidate.parent.parent/'provenance.json'),
        train_audit_sha256=digest(args.adaptation/'audit.json'), tune_sha256=digest(tune_path),
        fresh_sha256=digest(fresh_path), diagnostic_sha256=digest(diagnostic_path),
        code_sha256={p.name:digest(p) for p in [Path(__file__), ROOT/'scripts/evaluate_opensar_geo.py',
            ROOT/'scripts/evaluate_sar_recall_candidates.py', ROOT/'scripts/evaluate_ossdd_followup.py',
            ROOT/'src/sonarnet/evaluation/independent_sar.py', ROOT/'src/sonarnet/evaluation/detection_metrics.py']},
        note='Three already reported diagnostic scenes remain outside fitting and tuning. North Sea is a fresh acquisition. The old LS-SSDD lineage overlaps its geographic buffer; use CFAR as the clean comparator there.',
        candidate_grid=CONFIDENCE, selection='Best training AP checkpoint and final checkpoint are compared on the one separated validation scene. Highest IoU 0.50 F1, then higher confidence, then best AP checkpoint.',
        cpu_threads=THREADS, batch=1, warmups=3, latency_scope='after reading pixels, normalize through geographical filtering',
        candidate_imgsz=size, reference_imgsz=640, cfar_ring=RING,
        hardware=platform.platform(), torch=torch.__version__, ultralytics=ultralytics.__version__,
    )
    save(args.out/'protocol.json', protocol)
    tune, images = open_split(tune_path, args.adaptation/'rasters')
    assign_unique_support(tune)
    grid = []
    for checkpoint, path in candidates.items():
        model = ultralytics.YOLO(str(path))
        predictions, _ = infer_split(tune, images, model, size)
        for threshold in CONFIDENCE:
            metrics, _ = operational_metrics(list(tune.values()), predictions, threshold)
            grid.append(dict(checkpoint=checkpoint, confidence=threshold, f1=metrics['f1'],
                             recall=metrics['recall'], precision=metrics['precision'],
                             tp=metrics['true_positive'], fp=metrics['false_positive']))
    choice = max(grid, key=lambda row:(row['f1'], row['confidence'], row['checkpoint'] == 'best_ap'))
    frozen = args.out/'operating_point.json'
    save(frozen, dict(locked_utc=datetime.now(timezone.utc).isoformat(), selected=choice, validation=grid))
    del predictions, tune, images
    model = ultralytics.YOLO(str(candidates[choice['checkpoint']]))
    print('Locked operating point', choice, flush=True)

    report = dict(protocol_sha256=digest(args.out/'protocol.json'), operating_point_sha256=digest(frozen),
                  candidate_sha256=candidate_hashes[choice['checkpoint']], evaluation={})
    comparisons = (
        ('diagnostic', diagnostic_path, args.data/'prepared-confirmation-v1',
         ('reference_ls_ssdd', ultralytics.YOLO(str(args.reference)), 640, REFERENCE_CONF)),
        ('north_sea', fresh_path, args.adaptation/'rasters', ('guard_ring_cfar', None, None, 0.)),
    )
    for label, manifest, root, reference in comparisons:
        print('Evaluating', label, flush=True)
        rows, images = open_split(manifest, root)
        assign_unique_support(rows)
        comparison = dict(chips=len(rows), scenes=len({r['scene_id'] for r in rows.values()}), models={})
        report['evaluation'][label] = comparison
        for name, detector, imgsz, cut in (
                ('adapted_slc_vv', model, size, choice['confidence']), reference):
            outcome = compare(rows, images, detector, imgsz, cut, args.out, f'{label}_{name}')
            comparison['models'][name] = outcome
            m = outcome['metrics']
            print(label, name, 'match', m['true_positive'], '/', m['n_ground_truth'],
                  'unmatched', m['false_positive'], flush=True)
        save(args.out/'results.json', report)
        del rows, images


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('data', 'adaptation', 'diagnostic', 'out', 'candidate', 'reference'):
        parser.add_argument('--'+name, required=True, type=Path)
    evaluate(parser.parse_args())
