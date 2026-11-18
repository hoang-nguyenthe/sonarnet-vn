"""Compare frozen SonarNet weights against two CPU baselines on OSSDD VV.

Consume the cohort downloaded by prepare_ossdd_followup.py. Write the selected
parameters before reading test pixels. This is a transfer benchmark, not a
georeferenced area survey or proof of cross-dataset acquisition independence.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
import zlib

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from sonarnet.evaluation.independent_sar import operational_metrics, sha256
from benchmark_sar_archive import detect

GRID = {'yolo': (.1, .25, .4, .6), 'global_threshold': (.55, .7, .85),
        'local_contrast': (2., 3., 4.)}
GEO_TAGS = {33550, 33922, 34264, 34735, 34736, 34737}
NOMINAL_METRES = 10.


def save(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, allow_nan=False, indent=2) + '\n')


def parse_aabb(text):
    lines = [line.split() for line in text.splitlines() if line.strip()]
    if not lines or len(lines[0]) != 1 or int(lines[0][0]) != len(lines) - 1:
        raise ValueError('AABB header disagrees with row count')
    boxes, indices = [], set()
    for line in lines[1:]:
        if len(line) not in (5, 7):
            raise ValueError('Expected object id, 4 corners and optional 2 center coordinates')
        index = int(line[0])
        x1, y1, x2, y2 = map(float, line[1:5])
        if index in indices or not (0 <= x1 <= x2 <= 512 and 0 <= y1 <= y2 <= 512):
            raise ValueError(f'Invalid AABB row: {line}')
        indices.add(index)
        boxes.append([x1, y1, x2, y2])
    return boxes


def normalize(raw, mode):
    values = np.maximum(raw, 0)
    if mode == 'log1p':
        values = np.log1p(values)
    elif mode != 'linear':
        raise ValueError(f'Unknown normalization: {mode}')
    lo, hi = np.percentile(values, (1., 99.9))
    if lo == hi:
        return np.zeros(raw.shape, dtype=np.uint8)
    return np.rint(np.clip((values - lo) / (hi - lo), 0, 1) * 255).astype(np.uint8)


def difference_hash(values):
    small = np.asarray(Image.fromarray(values).resize((9, 8), Image.Resampling.LANCZOS))
    return sum(int(bit) << i for i, bit in enumerate((small[:, 1:] > small[:, :-1]).flat))


def read_cohort(root, requested, manifest, split):
    rows, images = [], {}
    for pick in (p for p in requested if p['split'] == split):
        ident = Path(pick['file_name']).stem
        if ident in images:
            raise ValueError(f'Duplicate id: {ident}')
        paths = [f'{split}/{ident}/{f}' for f in ('Chip_VV.tif', 'Metadata_aabb.txt')]
        for rel in paths:
            raw = (root / rel).read_bytes()
            entry = manifest[rel]
            if (len(raw) != entry['bytes'] or zlib.crc32(raw) != entry['zip_crc32']
                    or hashlib.sha256(raw).hexdigest() != entry['sha256']):
                raise ValueError(f'Member integrity check failed: {rel}')
        with Image.open(root / paths[0]) as tiff:
            if tiff.mode != 'F' or tiff.size != (512, 512):
                raise ValueError(f'Unexpected raster dimensions/type: {ident}')
            tags = sorted(GEO_TAGS.intersection(tiff.tag_v2))
            values = np.asarray(tiff, dtype='<f4')
        if not np.isfinite(values).all():
            raise ValueError(f'Non-finite raster values: {ident}')
        boxes = parse_aabb((root / paths[1]).read_text())
        kept = [b for b in boxes if b[2] > b[0] and b[3] > b[1]]
        rows.append(dict(id=ident, scene_id=ident.split('_')[0], split=split,
            category=pick['class'], source_land_fraction=float(pick['land_fraction']),
            image=paths[0], annotation=paths[1], image_sha256=manifest[paths[0]]['sha256'],
            annotation_sha256=manifest[paths[1]]['sha256'], boxes_xyxy=kept,
            degenerate_boxes=[b for b in boxes if b not in kept],
            image_pixel_area=512**2, geotiff_tags=tags,
            pixels_sha256=hashlib.sha256(values.tobytes()).hexdigest(),
            log8_dhash=f'{difference_hash(normalize(values, "log1p")):016x}'))
        images[ident] = values
    return rows, images


def duplicate_audit(val, test):
    grouped = {'exact_cross_split': [], 'exact_within_split': [],
               'perceptual_cross_split': [], 'perceptual_within_split': []}
    hashes = [(r, int(r['log8_dhash'], 16)) for r in val + test]
    for i, (row, dhash) in enumerate(hashes):
        for other, other_hash in hashes[:i]:
            scope = 'within_split' if row['split'] == other['split'] else 'cross_split'
            distance = (dhash ^ other_hash).bit_count()
            if row['pixels_sha256'] == other['pixels_sha256']:
                grouped[f'exact_{scope}'].append([other['id'], row['id']])
            elif distance <= 3:
                grouped[f'perceptual_{scope}'].append([other['id'], row['id'], distance])
    return grouped


def gallery(output, name, rows, images, predictions, failures, threshold, mode):
    by_id = {row['id']: row for row in rows}
    chosen = {}
    for key in ('false_positive_indices', 'false_negative_indices'):
        for row in sorted(failures, key=lambda f: (-len(f[key]), f['id']))[:2]:
            if row[key]:
                chosen[row['id']] = row
    for ident, error in chosen.items():
        canvas = Image.new('RGB', (512, 556), '#0d2332')
        canvas.paste(Image.fromarray(normalize(images[ident], mode)).convert('RGB'), (0, 44))
        draw = ImageDraw.Draw(canvas)
        draw.text((10, 5), f'{name} | {ident} | FP={len(error["false_positive_indices"])} '
                  f'FN={len(error["false_negative_indices"])}', fill='white')
        draw.text((10, 22), 'CYAN: source labels | ORANGE: predictions', fill='white')
        for a, b, c, d in by_id[ident]['boxes_xyxy']:
            draw.rectangle((a, b+44, c, d+44), outline='#50e8ff', width=2)
        for (a, b, c, d), score in zip(*predictions[ident]):
            if score >= threshold:
                draw.rectangle((a, b+44, c, d+44), outline='#ffa044', width=2)
        canvas.save(output / f'{name}_{ident}.png')
    return list(chosen)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cohort', type=Path, required=True)
    parser.add_argument('--weights', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    plan, download = (args.cohort / x for x in ('protocol.json', 'download_manifest.json'))
    cohort = json.loads(plan.read_text())
    files = json.loads(download.read_text())['files']
    manifest = {f['path']: f for f in files}
    selected = cohort['selected']
    if (Counter((x['split'], x['class']) for x in selected) != {
            ('val', 'land'): 100, ('val', 'water'): 100, ('test', 'land'): 200, ('test', 'water'): 200}
            or len(manifest) != len(files) or len(files) != 1200):
        raise ValueError('Unexpected frozen selection or duplicate manifest paths')
    scenes = {s: {x['file_name'].split('_')[0] for x in selected if x['split'] == s}
              for s in ('val', 'test')}
    if scenes['val'] & scenes['test']:
        raise ValueError('Source prefix crosses validation and test')
    args.output.mkdir(parents=True, exist_ok=False)
    import torch
    import ultralytics
    torch.set_num_threads(4)
    model = ultralytics.YOLO(str(args.weights))
    protocol = dict(created_at=datetime.now(timezone.utc).isoformat(),
        dataset_revision=cohort['revision'], cohort_sha256=sha256(plan),
        download_manifest_sha256=sha256(download), weights_sha256=sha256(args.weights),
        code_sha256={str(path.relative_to(ROOT)): sha256(path) for path in (
            Path(__file__).resolve(), ROOT / 'scripts/benchmark_sar_archive.py',
            ROOT / 'src/sonarnet/evaluation/independent_sar.py',
            ROOT / 'src/sonarnet/evaluation/detection_metrics.py')},
        grid=GRID, yolo_transforms=['log1p', 'linear'], baseline_transform='log1p',
        transform='Nonnegative VV, optional log1p, clip to per-chip P1–P99.9, round to uint8.',
        selection='Best validation F1 at IoU=.5; ties prefer log1p then higher threshold.',
        device='cpu', threads=4, hardware=platform.platform(), python=sys.version,
        torch=torch.__version__, ultralytics=ultralytics.__version__,
        inference=dict(imgsz=640, conf=.001, nms_iou=.7, max_det=1000),
        latency='Batch=1, three warmups, normalization+inference+NMS (or threshold+components), file I/O excluded.',
        duplicate_rule='Reject any exact cross-split duplicate; report dHash Hamming<=3 for visual triage.',
        aabb_rule='Use source XYXY corners as given. Count but exclude zero-area source annotations.',
        nominal_rule='10m/pixel from published GRD spacing; raster-only area and image-plane errors, not confirmed GSD.')
    save(args.output / 'protocol.json', protocol)

    def infer(raw, method, mode, param):
        im = Image.fromarray(normalize(raw, mode))
        if method != 'yolo':
            return detect(im, method, param)
        r = model.predict(im.convert('RGB'), device='cpu', imgsz=640, conf=.001,
                          iou=.7, max_det=1000, verbose=False)[0]
        return r.boxes.xyxy.cpu().numpy(), r.boxes.conf.cpu().numpy()

    val, val_images = read_cohort(args.cohort, selected, manifest, 'val')
    tuning = []
    for method, grid in GRID.items():
        for mode in (['log1p', 'linear'] if method == 'yolo' else ['log1p']):
            pred = None
            for param in grid:
                if pred is None or method != 'yolo':
                    pred = {r['id']: infer(val_images[r['id']], method, mode, param) for r in val}
                metrics, _ = operational_metrics(val, pred, param if method == 'yolo' else 0.)
                tuning.append(dict(method=method, mode=mode, param=param, metrics=metrics))
            print(f'Validation: {method} / {mode} complete', flush=True)
    control = {m: max((x for x in tuning if x['method'] == m),
                      key=lambda x: (x['metrics']['f1'], x['mode'] == 'log1p', x['param'])) for m in GRID}
    frozen_path = args.output / 'frozen_operating_points.json'
    save(frozen_path, dict(frozen_at=datetime.now(timezone.utc).isoformat(),
                           protocol_sha256=sha256(args.output / 'protocol.json'), tuning=tuning, chosen=control))
    print('Frozen from validation:', [(m, x['mode'], x['param']) for m, x in control.items()], flush=True)
    del val_images
    test, test_images = read_cohort(args.cohort, selected, manifest, 'test')
    audit = duplicate_audit(val, test)
    save(args.output / 'duplication_audit.json', audit)
    if audit['exact_cross_split']:
        raise ValueError('Cross-split exact duplicate detected; test scoring stopped')
    save(args.output / 'cohort_inputs.json', dict(protocol=cohort, files=files, val=val, test=test))
    models = {}
    report = dict(frozen_sha256=sha256(frozen_path), test_n=len(test), val_n=len(val),
        validation_scene_prefixes=sorted(scenes['val']), test_scene_prefixes=sorted(scenes['test']),
        quarantined_source_members=cohort['quarantined_train_shared_prefixes'],
        chip_counts=dict(Counter(r['category'] for r in test)),
        geotagged_test_chips=sum(bool(r['geotiff_tags']) for r in test),
        degenerate_boxes={s:sum(len(r['degenerate_boxes']) for r in rows)
                          for s, rows in [('val', val), ('test', test)]},
        models=models)
    for method, option in control.items():
        mode, param = option['mode'], option['param']
        threshold = param if method == 'yolo' else 0.
        for _ in range(3):
            infer(test_images[test[0]['id']], method, mode, param)
        preds, latency = {}, {}
        for n, row in enumerate(test, 1):
            ident = row['id']
            start = time.perf_counter()
            preds[ident] = infer(test_images[ident], method, mode, param)
            latency[ident] = (time.perf_counter()-start)*1000
            if n % 100 == 0:
                print(f'Test: {method} {n}/{len(test)}', flush=True)
        overall, failures = operational_metrics(test, preds, threshold)
        durations = list(latency.values())
        overall.update(latency_ms_median=float(np.median(durations)),
                       latency_ms_p95=float(np.percentile(durations, 95)))
        nominal = dict(raster_area_km2=overall['evaluated_image_pixels'] * NOMINAL_METRES**2 / 1e6,
            fp_per_full_raster_km2=overall['false_alarms_per_megapixel'] / NOMINAL_METRES**2,
            **{f'{k}_m_median': (overall[f'{k}_px_median'] * NOMINAL_METRES
                  if overall[f'{k}_px_median'] is not None else None)
               for k in ('center_error', 'box_width_error', 'box_height_error')})
        def grouped(key):
            out = {}
            for k in sorted({r[key] for r in test}):
                rows = [r for r in test if r[key] == k]
                metrics, _ = operational_metrics(rows, {r['id']:preds[r['id']] for r in rows}, threshold)
                out[k] = dict(images=len(rows), **metrics)
            return out
        models[method] = dict(mode=mode, param=param, overall=overall, nominal_image_plane=nominal,
                              by_source_land_category=grouped('category'), by_scene_prefix=grouped('scene_id'),
                              gallery=gallery(args.output, method, test, test_images, preds, failures, threshold, mode))
        save(args.output / f'{method}_test_predictions.json', {i: dict(boxes=b.tolist(), scores=s.tolist(),
             latency_ms=latency[i]) for i, (b, s) in preds.items()})
        save(args.output / f'{method}_test_errors.json', failures)
        save(args.output / 'results.json', report)


if __name__ == '__main__':
    main()
