"""Check radar box dimensions against historical NOAA vessel metadata."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

import numpy as np
import pandas as pd

from confirm_rtc_rank_with_ais import load_preview, read
from evaluate_coincident_sar_ais import extract_sar
from evaluate_multiscene_sar_ais import stable_window, visible
from evaluate_noaa_ais_replay import read_day
from evaluate_review_ranking import save
from replay_rtc_equal_review import GEOD, matching
from score_vn_reference_rtc import ROOT, digest


HOLDOUT = ROOT / 'reports/final/vietnam_rtc_transfer_20261119/rank_fusion/ais-holdout'
RADIUS = 100
CONFIDENCES = {'0.35': .35, '0.05': .05}


def dimension_values(track):
    numeric = track[['Length', 'Width']].apply(pd.to_numeric, errors='coerce')
    valid = numeric[np.isfinite(numeric).all(axis=1) & (numeric['Width'] > 0)
                    & (numeric['Length'] >= numeric['Width'])]
    if len(valid) < 2:
        return None, 'fewer_than_two_complete_reports'
    unique = valid.drop_duplicates()
    if len(unique) != 1:
        return None, 'reported_dimensions_disagree'
    return unique.iloc[0].to_list(), 'ok'


def read_reference(source, item, samples, land, schedule, frozen):
    anchor = datetime.fromisoformat(item['acquired_at'])
    day, timestamp = anchor.date().isoformat(), anchor.timestamp()
    archive = source / f"AIS_{day.replace('-', '_')}.zip"
    frame, provenance = read_day(archive, day, [timestamp], include_dimensions=True)
    west, south, east, north = item['bounds']
    regional = frame[frame['LON'].between(west-.03, east+.03)
                     & frame['LAT'].between(south-.03, north+.03)]
    masks = [sample[1] for sample in samples]
    rule = schedule['stationary_reference']
    positions, identifiers, _, accepted = stable_window(
        regional[['MMSI', 'LAT', 'LON', 'second']], timestamp, rule,
        lambda point: visible(point, item['tiles_wsen'], masks, land),
    )
    locations = [[point.lon, point.lat] for point, keep in zip(positions, accepted, strict=True) if keep]
    if locations != frozen['truth'] or provenance != frozen['source']:
        raise ValueError('AIS anchors or archive differ from the frozen ranking study')
    close = regional[(regional['second']-timestamp).abs() <= rule['holdout_s']]
    dimensions = []
    for identifier, keep in zip(identifiers, accepted, strict=True):
        if not keep:
            continue
        track = close.loc[close['MMSI'] == identifier].drop_duplicates()
        track = track[~track.duplicated('second', keep=False)]
        measured, status = dimension_values(track)
        dimensions.append(dict(size=measured, status=status))
    return dict(scene=item['product'], anchors=locations, dimensions=dimensions, source=provenance)


def axes_metres(box, bounds, side):
    west, south, east, north = bounds
    x1, y1, x2, y2 = box
    lon1 = west + x1 / side * (east - west)
    lon2 = west + x2 / side * (east - west)
    lat1 = north - y1 / side * (north - south)
    lat2 = north - y2 / side * (north - south)
    lon, lat = (lon1 + lon2) / 2, (lat1 + lat2) / 2
    dx = GEOD.inv(lon1, lat, lon2, lat)[2]
    dy = GEOD.inv(lon, lat1, lon, lat2)[2]
    return sorted((dx, dy), reverse=True)


def evaluate(detections, item, reference, width, confidence):
    filtered = [(tile, score, point) for tile, score, point in detections if score >= confidence]
    pairs = []
    for i, j, distance in matching([(point.lon, point.lat, score) for _, score, point in filtered],
                                  reference['anchors'], RADIUS):
        tile, score, point = filtered[i]
        dimensions = reference['dimensions'][j]
        estimate = axes_metres(point.bbox, item['tiles_wsen'][tile], width)
        pairs.append(dict(anchor=j, tile=tile, confidence=score, point=[point.lon, point.lat],
                          distance_m=distance, box_axes_m=estimate,
                          noaa_dimensions_m=dimensions['size'], dimension_status=dimensions['status']))
    return dict(candidates=len(filtered), pairs=pairs)


def statistics(values):
    if not values:
        return None
    array = np.asarray(values)
    absolute = np.abs(array)
    return dict(n=len(array), bias_m=float(array.mean()), mae_m=float(absolute.mean()),
                median_absolute_m=float(np.median(absolute)), p90_absolute_m=float(np.percentile(absolute, 90)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'coast', 'yolo', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    schedule_path = args.source/'protocol.json'
    schedule = read(schedule_path)
    prior = read(HOLDOUT/'protocol.json')
    if (digest(schedule_path) != prior['schedule_sha256']
            or digest(args.coast) != prior['coast_sha256']
            or digest(args.yolo) != prior['yolo_sha256']):
        raise ValueError('Schedule, coastline, or YOLO checkpoint differs from the frozen release')
    args.output.mkdir(exist_ok=False)
    save(args.output/'protocol.json', dict(
        locked_utc=datetime.now(timezone.utc).isoformat(), code_sha256=digest(Path(__file__)),
        source_schedule_sha256=digest(schedule_path), reference_sha256=digest(HOLDOUT/'references.json'),
        prior_candidates_sha256=digest(HOLDOUT/'candidates.json.gz'),
        coast_sha256=prior['coast_sha256'], yolo_sha256=prior['yolo_sha256'],
        noaa_metadata='https://www.fisheries.noaa.gov/inport/item/73064',
        dimensions='Both fields finite and 0 < Width <= Length on at least two distinct valid seconds in the held window. All such reports must agree.',
        physical_proxy='WGS84 lengths of two axes of the clipped radar rectangle; compare the larger with NOAA Length and smaller with Width.',
        match_m=RADIUS, confidences=CONFIDENCES,
    ))
    references = []
    for item, frozen in zip(schedule['products'], read(HOLDOUT/'references.json'), strict=True):
        if item['product'] != frozen['scene']:
            raise ValueError('Scene order differs from the frozen study')
        _, _, land, samples = load_preview(args.source, schedule, item, args.coast)
        ref = read_reference(args.source, item, samples, land, schedule, frozen)
        references.append(ref)
        print(item['area'], item['acquired_at'][:10],
              dict(Counter(dim['status'] for dim in ref['dimensions'])), flush=True)
    save(args.output/'references.json', references)

    with gzip.open(HOLDOUT/'candidates.json.gz', 'rt') as f:
        cached = {case['scene']: case['baseline_low'] for case in json.load(f)}
    scenes = []
    for item, reference in zip(schedule['products'], references, strict=True):
        path, preview, land, _ = load_preview(args.source, schedule, item, args.coast)
        parameters = dict(schedule['raster'], confidence=CONFIDENCES['0.05'])
        config = dict(tiles_wsen=item['tiles_wsen'], render=parameters, detector=parameters)
        start = perf_counter()
        _, _, detections = extract_sar(SimpleNamespace(input=path), preview, config, land, args.yolo)
        elapsed = perf_counter() - start
        observed = [[point.lon, point.lat, score] for _, score, point in detections]
        if np.shape(observed) != np.shape(cached[item['product']]) or not np.allclose(
                observed, cached[item['product']], rtol=0, atol=1e-6):
            raise ValueError('Radar centers or scores differ from the frozen ranking study')
        modes = {key: evaluate(detections, item, reference, parameters['width'], confidence)
                 for key, confidence in CONFIDENCES.items()}
        scenes.append(dict(scene=item['product'], utc=item['acquired_at'], area=item['area'],
                           anchors=len(reference['anchors']), elapsed_cpu_seconds=elapsed, modes=modes))
    totals = {}
    for key in CONFIDENCES:
        results = [scene['modes'][key] for scene in scenes]
        pairs = [pair for result in results for pair in result['pairs']]
        usable = [pair for pair in pairs if pair['noaa_dimensions_m'] is not None]
        totals[key] = dict(
            candidates=sum(result['candidates'] for result in results), matched=len(pairs),
            anchors=sum(scene['anchors'] for scene in scenes), size_pairs=len(usable),
            anchor_distance=statistics([pair['distance_m'] for pair in pairs]),
            length_error=statistics([pair['box_axes_m'][0]-pair['noaa_dimensions_m'][0] for pair in usable]),
            width_error=statistics([pair['box_axes_m'][1]-pair['noaa_dimensions_m'][1] for pair in usable]),
        )
    save(args.output/'results.json', dict(protocol_sha256=digest(args.output/'protocol.json'),
         references_sha256=digest(args.output/'references.json'), scenes=scenes, totals=totals))
    print(json.dumps(totals, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
