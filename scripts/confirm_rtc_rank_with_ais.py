"""Check frozen SAR ranking policies on newly drawn historical harbour scenes."""

import argparse
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
from types import SimpleNamespace

import torch
from ultralytics import YOLO

from evaluate_coincident_sar_ais import extract_sar, land_geometry
from evaluate_review_ranking import save
from evaluate_rtc_rank_fusion import DUPLICATE_METRES, MODES, score, totals
from evaluate_rtc_stationary_ais_reference import RULE, collect_reference, local_chips, rendered_masks
from evaluate_rtc_xview3_transfer import CHECKSUM, REVISION, load_checkpoint
from evaluate_xview3_stationary_ais import capture
from score_vn_reference_rtc import digest


ROOT = Path(__file__).resolve().parents[1]
AIS_RELEASE = ROOT / 'reports/final/stationary_ais_detection_20261120/protocol.json'


def read(path):
    return json.loads(path.read_text())


def check_schedule(source, schedule):
    catalogue = source / 'catalogue-screen.json'
    if digest(catalogue) != schedule['catalogue_sha256']:
        raise ValueError('Catalogue archive differs from the frozen selection')
    previously_seen = set(schedule['excluded_utc_days'])
    for group, selected in zip(read(catalogue), schedule['products'], strict=True):
        first = next(product for product in group['eligible']
                     if product['coverage_fraction'] >= .999
                     and product['acquired_at'][:10] not in previously_seen)
        if selected != first:
            raise ValueError('Acquisition differs from the frozen catalogue rule')
        previously_seen.add(selected['acquired_at'][:10])


def load_preview(source, schedule, item, coast):
    folder = source / item['product']
    preview = read(folder / 'raster_provenance.json')
    if (preview['source_acquired_at'] != item['acquired_at']
            or preview['source_item_url'] != item['source_item_url']
            or preview['source_asset_url'] != item['source_asset_url']):
        raise ValueError('Radar preview differs from the frozen scene')
    land = land_geometry(coast, item['bounds'])
    samples = rendered_masks(item, folder, preview, land, schedule['raster'])
    return folder, preview, land, samples


def load_dual_band(source, schedule, item, preview):
    folder = source / 'dual-band' / item['product']
    raw = read(folder / 'manifest.json')
    if (raw['product'] != item['product'] or raw['utc'] != item['acquired_at']
            or raw['source_item'] != item['source_item_url']
            or raw['source_assets']['vv'] != item['source_asset_url']
            or [tile['bbox'] for tile in raw['windows']] != item['tiles_wsen']
            or any(tile['width'] != schedule['raster']['width'] for tile in raw['windows'])
            or [tile['preview_sha256'] for tile in raw['windows']]
            != [tile['sha256'] for tile in preview['images']]):
        raise ValueError('Dual-band manifests differ from the frozen scene or preview hashes')
    return folder, raw

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'coast', 'yolo', 'xview3-checkout', 'xview3-weights', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    frozen = args.source / 'protocol.json'
    schedule = read(frozen)
    check_schedule(args.source, schedule)
    release = read(AIS_RELEASE)
    coast_sha, yolo_sha = digest(args.coast), digest(args.yolo)
    if (coast_sha != release['coast_sha256'] or yolo_sha != release['weights_sha256']
            or schedule['previous_protocol_sha256'] != release['source_sha256']
            or RULE != release['decision']):
        raise ValueError('Archive protocol, reference rules, coastline or YOLO checkpoint differ from the previous release')
    args.output.mkdir(exist_ok=False)
    save(args.output / 'protocol.json', {
        'started_utc': datetime.now(timezone.utc).isoformat(),
        'schedule_sha256': digest(frozen),
        'coast_sha256': coast_sha,
        'yolo_sha256': yolo_sha,
        'xview3_revision': REVISION,
        'xview3_weights_sha256': CHECKSUM,
        'code_sha256': digest(Path(__file__)),
        'ranking_code_sha256': digest(Path(__file__).with_name('evaluate_rtc_rank_fusion.py')),
        'policy': schedule['confirm'],
        'match': 'One-to-one WGS84 distances at 50, 100 and 150 m. The primary radius is 100 m.',
        'review_counts': 'Original per-scene YOLO counts at 0.35 and 0.05. Same count for every comparison.',
        'duplicate_distance_m': DUPLICATE_METRES,
    })

    references = []
    for item in schedule['products']:
        _, _, land, samples = load_preview(args.source, schedule, item, args.coast)
        points, ais = collect_reference(args.source, item, samples, land, schedule)
        references.append(dict(scene=item['product'], truth=points, source=ais))
        print(item['area'], item['acquired_at'][:10], len(points), 'frozen AIS references', flush=True)
    save(args.output / 'references.json', references)

    torch.set_num_threads(4)
    yolo = YOLO(str(args.yolo))
    xview = load_checkpoint(args.xview3_checkout, args.xview3_weights)
    cases, source_receipts = [], []
    for item, reference in zip(schedule['products'], references, strict=True):
        preview_dir, preview, land, samples = load_preview(args.source, schedule, item, args.coast)
        raw_dir, raw = load_dual_band(args.source, schedule, item, preview)
        raster = dict(schedule['raster'], confidence=RULE['relaxed_confidence'])
        settings = dict(tiles_wsen=item['tiles_wsen'], render=raster, detector=raster)
        _, _, detections = extract_sar(SimpleNamespace(input=preview_dir), preview, settings, land, args.yolo)
        original = [[point.lon, point.lat, confidence] for _, confidence, point in detections]
        overlap = local_chips(yolo, samples, item['tiles_wsen'])
        transfer, dual_band_valid = capture(xview, raw_dir, raw, land)
        cases.append(dict(scene=item['product'], windows=len(samples), truth=reference['truth'],
                          incumbent=[row for row in original if row[2] >= RULE['base_confidence']],
                          baseline_low=original, overlap=overlap, transfer=transfer, budget=len(original)))
        source_receipts.append(dict(scene=item['product'], area=item['area'], utc=item['acquired_at'],
                                    dual_band_manifest_sha256=digest(raw_dir / 'manifest.json'),
                                    preview_manifest_sha256=digest(preview_dir / 'raster_provenance.json'),
                                    both_bands_valid_fraction_by_tile=dual_band_valid))
        print(item['area'], item['acquired_at'][:10], len(original), len(overlap), len(transfer),
              'candidates in map, overlapping chips and xView3', flush=True)

    cache = args.output / 'candidates.json.gz'
    with cache.open('wb') as raw_cache, gzip.GzipFile(fileobj=raw_cache, mode='wb', mtime=0) as compressed:
        compressed.write(json.dumps(cases, ensure_ascii=False, separators=(',', ':')).encode())

    rows, queues = score(cases)
    aggregate = totals(rows)
    for row, receipt in zip(rows, source_receipts, strict=True):
        row.update(receipt)
    result_path = args.output / 'results.json'
    save(result_path, {
        'protocol_sha256': digest(args.output / 'protocol.json'),
        'references_sha256': digest(args.output / 'references.json'),
        'candidates_sha256': digest(cache),
        'scenes': rows, 'totals': aggregate,
    })
    save(args.output / 'review-queues.json', {'results_sha256': digest(result_path), 'scenes': queues})
    for mode in MODES:
        print(mode, {policy: aggregate[mode][policy][100] for policy in
                     ('published', 'rank_60', 'rank_60_keep_75')}, flush=True)


if __name__ == '__main__':
    main()
