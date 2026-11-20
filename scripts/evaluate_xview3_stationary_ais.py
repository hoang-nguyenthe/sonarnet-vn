"""Test transferred dual-band SAR rankings against held stationary AIS positions."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from time import monotonic, sleep

import numpy as np
from shapely.geometry import box
import torch

from evaluate_coincident_sar_ais import land_geometry
from evaluate_review_ranking import save
from evaluate_rtc_contrast_recall import RADII, shortlist
from evaluate_rtc_map_tta import ranked_views
from evaluate_rtc_xview3_transfer import CHECKSUM, REVISION, infer, load_checkpoint, read_band, score_rows
from score_vn_reference_rtc import digest, matched

MODES = {
    'narrow': ('base_at_035', 'same_count_remove_duplicates', 'base_at_005'),
    'wide': ('base_at_005', 'same_wide_count_overlap', 'same_wide_count_overlap'),
}


def capture(model, folder, block, land):
    centres = []
    paired_pixels = []
    for tile in block['windows']:
        vv, vh = [read_band(folder, {'file':tile['files'][name]['name'],
                                    'sha256':tile['files'][name]['sha256']}) for name in ('vv','vh')]
        if vv.shape != (tile['width'], tile['width']) or vh.shape != vv.shape:
            raise ValueError('Dual-band dimensions do not match the fixed grid')
        surface = box(*tile['bbox']).difference(land)
        _, rotated = infer(model, vv, vh, tile['bbox'], surface)
        centres.extend(score_rows(rotated, True))
        paired_pixels.append(float(np.mean((vh > 0) & (vv > 0))))
    return centres, paired_pixels


def rank_archive(raw, transfer):
    outcomes = {}
    for mode, (base, before, pool) in MODES.items():
        prior = raw[before]
        size = len(raw[base])
        if len(prior) != size:
            raise ValueError('Prior ranking used a different review count')
        candidates = ranked_views(raw[pool], {'xview3':transfer}, 'max')
        appended = shortlist(candidates, prior, size, 35.)
        xview3_first = shortlist(sorted(transfer,key=lambda row:-row[2]),prior,size,35.)
        outcomes[mode] = {'original':raw[base], 'prior':prior, 'fused_xview3':appended, 'xview3_first':xview3_first}
        if any(len(queue)!=size for queue in outcomes[mode].values()):
            raise ValueError('Candidate list length differs from the fixed review count')
    return outcomes


def counts(cases):
    return {mode:{method:{str(radius):{field:sum(case['scores'][mode][method][radius][field] for case in cases)
                                        for field in ('matched','labels','predictions','unmatched')}
                            for radius in RADII} for method in cases[0]['scores'][mode]} for mode in MODES}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('source','raster','coast','ais-evidence','upstream','weights','output'):
        parser.add_argument('--'+flag,type=Path,required=True)
    parser.add_argument('--wait-seconds', type=int, default=0,
                        help='Time to wait for the complete manifest of each in-progress scene.')
    args=parser.parse_args()
    args.output.mkdir(exist_ok=False)
    protocol=args.source/'protocol.json'
    frozen=json.loads(protocol.read_text())
    prior_path=args.ais_evidence/'results.json'
    prior=json.loads(prior_path.read_text())
    prior_protocol_path=args.ais_evidence/'protocol.json'
    prior_protocol=json.loads(prior_protocol_path.read_text())
    coordinate_path=args.ais_evidence/'review-queues.json'
    coordinate=json.loads(coordinate_path.read_text())
    reference_path=args.ais_evidence/'reference.json'
    references=json.loads(reference_path.read_text())
    if (prior['protocol_sha256']!=digest(prior_protocol_path)
            or prior_protocol['source_sha256']!=digest(protocol)
            or prior_protocol['coast_sha256']!=digest(args.coast)
            or prior['references_sha256']!=digest(reference_path)
            or coordinate['results_sha256']!=digest(prior_path)):
        raise ValueError('Previously frozen scene, mask, reference or baseline differs')
    save(args.output/'protocol.json',dict(
        locked_utc=datetime.now(timezone.utc).isoformat(), code_sha256=digest(Path(__file__)),
        weights_sha256=CHECKSUM, upstream_revision=REVISION, raster_protocol_sha256=digest(protocol),
        reference_sha256=digest(reference_path), baseline_queues_sha256=digest(coordinate_path),
        baseline_results_sha256=digest(prior_path), match_metres=RADII,
        mode=MODES,
        comparison='Same per-scene review counts. Primary transfer combines scores by max, then suppresses within 35 m. Transfer-first is diagnostic. No tuning on any AIS references.',
        scope='Independent, stationary AIS position proxies chosen without radar detections in the earlier study. Coastal civilian archive, not live tracking or identity validation.'))
    torch.set_num_threads(4)
    model=load_checkpoint(args.upstream,args.weights)
    results, review = [], []
    for item, held, baseline in zip(frozen['products'],references,coordinate['scenes'],strict=True):
        scene=item['product']
        folder=args.raster/scene
        manifest_path=folder/'manifest.json'
        deadline = monotonic()+args.wait_seconds
        while not manifest_path.is_file() and monotonic()<deadline:
            sleep(3)
        manifest=json.loads(manifest_path.read_text())
        previous_path=args.source/scene/'raster_provenance.json'
        previous=json.loads(previous_path.read_text())
        if (len(manifest['windows'])!=len(item['tiles_wsen'])
                or scene!=held['product'] or scene!=baseline['product'] or scene!=manifest['product']
                or manifest['utc']!=item['acquired_at'] or manifest['source_item']!=item['source_item_url']
                or manifest['source_assets']['vv']!=item['source_asset_url']
                or [w['bbox'] for w in manifest['windows']]!=item['tiles_wsen']
                or [w['preview_sha256'] for w in manifest['windows']]!=[w['sha256'] for w in previous['images']]):
            raise ValueError('Dual-band manifest or original coordinate dataset differs from the frozen scene')
        coast=land_geometry(args.coast,item['bounds'])
        points, valid=capture(model,folder,manifest,coast)
        queues=rank_archive(baseline['queues'],points)
        scores={mode:{name:matched(queue,held['labels'],RADII) for name,queue in methods.items()}
                for mode,methods in queues.items()}
        results.append(dict(product=scene,area=item['area'],utc=item['acquired_at'],
                            raster_manifest_sha256=digest(manifest_path),xview3_proposals=len(points),
                            both_bands_valid_fraction_by_window=valid,scores=scores))
        review.append(dict(product=scene,queues=queues))
        print(item['area'],item['acquired_at'][:10],len(points),'xView3 points',
              {k:{m:r[100]['matched'] for m,r in v.items()} for k,v in scores.items()},flush=True)
    save(args.output/'results.json',dict(protocol_sha256=digest(args.output/'protocol.json'),
         totals=counts(results),scenes=results))
    save(args.output/'review-queues.json',dict(result_sha256=digest(args.output/'results.json'),scenes=review))
    print('Aggregate', {k:{m:v['100'] for m,v in totals.items()}
                        for k,totals in counts(results).items()},flush=True)


if __name__=='__main__':
    main()
