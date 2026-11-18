"""Prepare a reproducible SLC VV training cohort and independent comparison."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path

import numpy as np
from PIL import Image
from shapely.geometry import Point, Polygon, shape
from shapely.ops import transform, unary_union
import tifffile

from evaluate_ossdd_followup import difference_hash, normalize
from prepare_opensar_confirmation import TRAIN_RASTER_SHA
from prepare_opensar_geo import (
    CHECKSUM, REVISION, archive_members, digest, invalid_runs, laea, land_shapes,
    pixel_rect, pixel_xy, read_annotations, save,
)

SELECTION = {
    'fit': ('2020-04-07', '2020-05-14', '2020-06-30', '2020-07-19',
            '2020-07-24', '2020-08-24', '2020-09-10'),
    'tune': ('2020-05-03',),
    'diagnostic': ('2020-04-21', '2020-05-11', '2020-07-06'),
    'fresh': ('2020-09-28',),
}
PARTITIONS = {'fit': 'train', 'tune': 'val', 'diagnostic': 'train', 'fresh': 'test'}
BUFFER_M = 20_000
MIN_VALID = .95
LABELS = {'HIGH', 'MEDIUM'}


def signed_pixels(raw):
    if raw.shape != (512, 512) or raw.dtype.kind != 'c':
        raise ValueError('Expected complex Sentinel-1 SLC VV 512 × 512')
    valid = np.isfinite(raw) & (raw != 0)
    gray = normalize(np.where(valid, np.abs(raw), 0.), 'log1p')
    return valid, gray, (hashlib.sha256(raw.astype('<c8').tobytes()).hexdigest(), difference_hash(gray))


def points_in_ocean(row, valid, geometry):
    crs, forward, land, coast = geometry
    corners = list(zip(*forward(*zip(*row['corners_wgs84']))))
    nodata = unary_union([pixel_rect(corners, *rect) for rect in invalid_runs(valid)])
    water = pixel_rect(corners, 0, 0, 512, 512).difference(land).difference(nodata)
    if water.area <= 1e6:
        return None
    for lab in row['labels']:
        point = Point(*pixel_xy(corners, *lab['xml_center_px']))
        lab.update(evaluated_sea=bool(water.covers(point)),
                   sea_distance_to_shore_m=point.distance(coast) if not coast.is_empty else None,
                   xml_wgs84_to_corner_transform_residual_m=point.distance(Point(*forward(*lab['xml_center_wgs84']))))
    return dict(crs=crs, corners_laea_m=corners, valid_sea_wkb_hex=water.wkb_hex,
                valid_pixels=int(valid.sum()))


def yolo_labels(row):
    lines = []
    for lab in row['labels']:
        if not lab['is_vessel'] or lab['confidence'] not in LABELS:
            continue
        left, top, right, bottom = lab['box']
        xywh = ((left+right)/1024, (top+bottom)/1024, (right-left)/512, (bottom-top)/512)
        lines.append('0 ' + ' '.join(f'{x:.8f}' for x in xywh))
    return lines


def geometry_filter(annotations, scenes):
    days = {day: (name, shape(row['footprint'])) for name, row in scenes.items() for day in [row['day']]}
    if len(days) != len(scenes):
        raise ValueError('The fixed cohort expects one scene per acquisition day')
    reserved = {}
    for kind in ('tune', 'diagnostic', 'fresh'):
        for date in SELECTION[kind]:
            _, geo = days[date]
            _, forward = laea(geo)
            reserved[date] = (geo, forward, transform(forward, geo))
    training, rejects, minima = {}, {}, {}
    for ident, row in annotations.items():
        if row['day'] not in SELECTION['fit']:
            continue
        geo = Polygon(row['corners_wgs84'])
        distances = {
            date: transform(forward, geo).distance(local)
            for date, (other, forward, local) in reserved.items()
            if geo.distance(other) < 1.5
        }
        row['protected_scene_distances_m'] = {k: round(v, 2) for k, v in distances.items()}
        if any(dist <= BUFFER_M for dist in distances.values()):
            rejects[ident] = row['protected_scene_distances_m']
            continue
        for date, dist in distances.items():
            minima[date] = min(minima.get(date, float('inf')), dist)
        training[ident] = row
    return training, rejects, minima


def process_cohort(data, out, desired, partition, kind, scenes):
    root = out / 'rasters'
    root.mkdir(exist_ok=True)
    images, seen, rejected, geometry, signatures = [], set(), Counter(), {}, {}
    for ident, payload in archive_members(data / f'{partition}_patches.tar.zst',
                                          r'patches/DB_OPENSAR_VD_(\d+)_SLC_VV\.tiff'):
        if ident not in desired:
            continue
        if ident in seen:
            raise ValueError(f'Duplicate raster ID: {ident}')
        seen.add(ident)
        row = desired[ident].copy()
        labels = row['labels']
        if any(lab['box'] is None for lab in labels):
            rejected['invalid_xml_box'] += 1
            continue
        if kind == 'fit' and any(lab['is_vessel'] and lab['confidence'] not in LABELS for lab in labels):
            rejected['uncertain_vessel_label'] += 1
            continue
        valid, gray, signature = signed_pixels(tifffile.imread(BytesIO(payload)))
        if valid.mean() < MIN_VALID:
            rejected['valid_pixels_below_95_percent'] += 1
            continue
        if kind != 'fit':
            sid = row['scene_id']
            if sid not in geometry:
                hull = shape(scenes[sid]['footprint'])
                crs, forward = laea(hull)
                geometry[sid] = (crs, forward, *land_shapes(data/'gshhg-shp-2.3.7.zip', hull, forward))
            support = points_in_ocean(row, valid, geometry[sid])
            if support is None:
                rejected['valid_ocean_le_1_sqkm'] += 1
                continue
            row.update(support)
            raster_path = f'{kind}_{ident}.tiff'
            (root/raster_path).write_bytes(payload)
            row.update(raster_path=raster_path, file_sha256=hashlib.sha256(payload).hexdigest())
        labels_yolo = yolo_labels(row)
        if kind in {'fit', 'tune'}:
            split = 'train' if kind == 'fit' else 'val'
            path = out/'images'/split/f'{ident}.png'
            Image.fromarray(gray).save(path, compress_level=1)
            (out/'labels'/split/f'{ident}.txt').write_text(''.join(line+'\n' for line in labels_yolo))
            row.update(normalized_png_sha256=digest(path), n_training_boxes=len(labels_yolo))
        row.update(pixel_sha256=signature[0], dhash=signature[1])
        images.append(row)
        signatures[ident] = signature
    if seen != desired.keys():
        raise ValueError(f'Archive missing {len(desired.keys()-seen)} selected IDs for {kind}')
    print(kind, 'kept', len(images), 'excluded', dict(rejected), flush=True)
    return images, signatures, dict(rejected)


def pixel_conflicts(earlier, protected):
    return [(a, b) for a, (sha, dh) in earlier.items()
            for b, (other_sha, other_dh) in protected.items()
            if sha == other_sha or (dh ^ other_dh).bit_count() <= 3]


def prepare(data, source_audit, diagnostic, out):
    out.mkdir(parents=True, exist_ok=False)
    hashes = {**CHECKSUM, 'train_patches.tar.zst': TRAIN_RASTER_SHA}
    for name, expected in hashes.items():
        if digest(data/name) != expected:
            raise ValueError('Source SHA-256 mismatch: '+name)
    scenes = json.loads(source_audit.read_text())['scenes']
    annotations = read_annotations(data)
    fit, distance_rejects, distances = geometry_filter(annotations, scenes)
    hold = diagnostic/'confirmation_manifest.json'
    policy = dict(
        locked_utc=datetime.now(timezone.utc).isoformat(), source_revision=REVISION,
        source_screen_sha256=digest(source_audit), diagnostic_manifest_sha256=digest(hold),
        code_sha256=digest(Path(__file__)), archives=hashes, dates=SELECTION, partitions=PARTITIONS,
        minimum_geographic_buffer_m=BUFFER_M, minimum_valid_fraction=MIN_VALID,
        training_targets='HIGH/MEDIUM vessel only. Exclude chips with uncertain vessel labels or invalid boxes, retain eligible background chips.',
        pixel_audit='Complex pixels SHA-256 or normalized amplitude dHash <= 3. Remove fit conflicts; remove tune conflicts with either evaluation set.',
        evaluation='Three previously measured diagnostic scenes and a previously unevaluated North Sea scene. Western Africa test scenes from the prior study are near new training footprints and are excluded.',
    )
    save(out/'data_policy.json', policy)
    for split in ('train', 'val'):
        for subtree in ('images', 'labels'):
            (out/subtree/split).mkdir(parents=True)
    selections = {
        kind: {i:r for i,r in annotations.items() if r['day'] in SELECTION[kind]}
        for kind in ('tune', 'fresh')
    }
    if any(r['split'] != PARTITIONS[kind] for kind, rows in {**selections,'fit':fit}.items() for r in rows.values()):
        raise ValueError('Source partition changed')
    past = json.loads(hold.read_text())['images']
    if set(r['day'] for r in past) != set(SELECTION['diagnostic']):
        raise ValueError('Unexpected three-scene diagnostic cohort')
    protected = {}
    for row in past:
        raw = data/'prepared-confirmation-v1'/row['raster_path']
        if digest(raw) != row['file_sha256']:
            raise ValueError('Diagnostic file SHA-256 mismatch')
        _, _, protected[row['id']] = signed_pixels(tifffile.imread(raw))
    fresh, fresh_sig, fresh_ignored = process_cohort(data, out, selections['fresh'], 'test', 'fresh', scenes)
    protected.update(fresh_sig)
    tune, tune_sig, tune_ignored = process_cohort(data, out, selections['tune'], 'val', 'tune', scenes)
    tune_conflicts = pixel_conflicts(tune_sig, protected)
    tune_quarantine = {a for a, _ in tune_conflicts}
    train, train_sig, train_ignored = process_cohort(data, out, fit, 'train', 'fit', scenes)
    fit_conflicts = pixel_conflicts(train_sig, {**protected, **tune_sig})
    fit_quarantine = {a for a, _ in fit_conflicts}
    for split, quarantine in [('train', fit_quarantine), ('val', tune_quarantine)]:
        for ident in quarantine:
            (out/'images'/split/f'{ident}.png').unlink()
            (out/'labels'/split/f'{ident}.txt').unlink()
    train = [r for r in train if r['id'] not in fit_quarantine]
    tune = [r for r in tune if r['id'] not in tune_quarantine]
    counts = {kind: dict(chips=len(rows), scenes=len({r['scene_id'] for r in rows}),
                         boxes=sum(r['n_training_boxes'] for r in rows),
                         backgrounds=sum(r['n_training_boxes'] == 0 for r in rows))
              for kind, rows in [('fit', train), ('tune', tune)]}
    if any(d['boxes'] < 20 or d['backgrounds'] < 10 for d in counts.values()):
        raise ValueError(f'Insufficient training or validation support: {counts}')
    if not fresh:
        raise ValueError('No fresh scene after quality screening')
    (out/'data.yaml').write_text(
        f'path: {json.dumps(str(out.resolve()))}\ntrain: images/train\nval: images/val\nnames: {{0: vessel}}\n')
    save(out/'manifest.json', dict(train=train, val=tune))
    save(out/'tune_manifest.json', dict(images=tune))
    save(out/'fresh_manifest.json', dict(images=fresh))
    save(out/'audit.json', dict(passed=True, counts=counts, fresh_chips=len(fresh), diagnostic_chips=len(past),
        image_quality_exclusions=dict(train=train_ignored, tune=tune_ignored, fresh=fresh_ignored),
        training_geographic_quarantine=distance_rejects, min_fit_to_protected_scene_m=distances,
        training_pixel_quarantine=fit_conflicts, tuning_pixel_quarantine=tune_conflicts,
        data_policy_sha256=digest(out/'data_policy.json'), manifest_sha256=digest(out/'manifest.json'),
        fresh_manifest_sha256=digest(out/'fresh_manifest.json')))
    print('Audited cohort:', counts, 'fresh', len(fresh), 'diagnostic', len(past), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('data', 'source-audit', 'diagnostic', 'out'):
        parser.add_argument('--'+name, required=True, type=Path)
    args = parser.parse_args()
    prepare(args.data, args.source_audit, args.diagnostic, args.out)
