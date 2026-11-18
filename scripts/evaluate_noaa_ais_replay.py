"""Compare association policies using withheld real AIS fixes as position proxies."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd

from evaluate_ais_matching import legacy
from sonarnet.config import RunConfig
from sonarnet.data.geo import haversine_m
from sonarnet.fusion.matching import Detection, SARAISFusion

DAYS = ('2024-07-14', '2024-10-01')
CONFIRMATION_DAY = '2024-12-15'
GUARD_OPTIONS_M = (0., 25., 50., 75., 100.)
AREAS = {
    'Los Angeles / Long Beach': (-118.30, 33.64, -118.09, 33.75),
    'Galveston / Houston Ship Channel': (-94.85, 29.29, -94.62, 29.47),
    'New York Harbor': (-74.11, 40.48, -73.96, 40.66),
}
HOURS = range(1, 24)
ANCHOR_S = 20
HISTORY_S = 600
NEAR_NEIGHBOR_M = 250.
NOAA = 'https://coast.noaa.gov/htdata/CMSP/AISDataHandler/2024/'
FIELDS = ['MMSI', 'BaseDateTime', 'LAT', 'LON']


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def read_day(path, day, window_centers=None):
    """Read and CRC-check the entire daily member, retaining only relevant fixes."""
    expected = path.stem + '.csv'
    base = int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp())
    windows = np.array([base+h*3600 for h in HOURS] if window_centers is None else window_centers)
    selected = []
    with ZipFile(path) as z:
        if z.namelist() != [expected]:
            raise ValueError(f'Unexpected NOAA members for {day}')
        info = z.getinfo(expected)
        with z.open(info) as data:
            for chunk in pd.read_csv(data, usecols=FIELDS, chunksize=300_000,
                                     dtype={'LAT':'float64', 'LON':'float64', 'MMSI':'Int64'}):
                in_area = np.zeros(len(chunk), dtype=bool)
                for w,s,e,n in AREAS.values():
                    pad = .03
                    in_area |= (chunk['LON'].between(w-pad,e+pad) & chunk['LAT'].between(s-pad,n+pad)).to_numpy()
                chunk = chunk.loc[in_area & chunk['MMSI'].between(100_000_000,999_999_999).fillna(False)]
                time = pd.to_datetime(chunk['BaseDateTime'], utc=True, errors='raise')
                seconds = time.to_numpy(dtype='datetime64[s]').astype(np.int64)
                off = np.abs(seconds[:,None]-windows).min(axis=1)
                if np.any(off <= HISTORY_S):
                    selected.append(chunk.assign(second=seconds).loc[off <= HISTORY_S,
                                    ['MMSI','LAT','LON','second']])
    if not selected:
        raise ValueError(f'No accepted AIS observations for {day}')
    return pd.concat(selected, ignore_index=True), dict(
        source=NOAA+path.name, sha256=digest(path), compressed_bytes=path.stat().st_size,
        csv_crc32=f'{info.CRC:08x}')


def sample_window(frame, bounds, when):
    w,s,e,n = bounds
    span = frame[(frame['second']-when).abs() <= HISTORY_S]
    in_bounds = span['LAT'].between(s,n) & span['LON'].between(w,e)
    # Where distinct coordinates shared a reported second, discard all fixes at
    # that second for that vessel. Remove any verbatim duplicated fixes first.
    span = span.drop_duplicates()
    span = span[~span.duplicated(['MMSI','second'], keep=False)]
    offset = (span['second']-when).abs()
    withheld = span.loc[(offset <= ANCHOR_S) & in_bounds.reindex(span.index)].assign(offset=offset)
    withheld = withheld.sort_values(['MMSI','offset','second']).drop_duplicates('MMSI')
    history = span.loc[offset > ANCHOR_S].sort_values(['second','MMSI'])
    proxies = [Detection(i, float(r.LAT), float(r.LON), np.nan, np.nan, (0,0,0,0))
               for i,r in enumerate(withheld.itertuples())]
    ids = [int(r.MMSI) for r in withheld.itertuples()]
    history = [dict(mmsi=int(r.MMSI),timestamp=int(r.second),lat=float(r.LAT),lon=float(r.LON))
               for r in history.itertuples()]
    return proxies, ids, history, withheld['offset'].to_numpy()


def add_counts(c, result, truth, history_ids, neighboring):
    for i, expected in enumerate(truth):
        groups = ('overall', 'neighbor_250m' if neighboring[i] else 'separated',
                  'has_history' if expected in history_ids else 'no_history')
        for group in groups:
            score = c[group]
            score['targets'] += 1
            assigned = result.get(i)
            score['correct'] += assigned == expected
            score['wrong'] += assigned is not None and assigned != expected
            score['unassigned'] += assigned is None


def complete_counts(counter):
    return {name:counter[name] for name in ('targets','correct','wrong','unassigned')}


def select_guard(by_day):
    """Prefer fewer errors only if the loss of correct assignments stays bounded."""
    supported = []
    for distance in GUARD_OPTIONS_M[1:]:
        method = f'guard_{distance:.0f}m'
        count = [d[method]['overall'] for d in by_day.values()]
        reference = [d['guard_0m']['overall'] for d in by_day.values()]
        if all(m['wrong'] < b['wrong'] and (b['correct']-m['correct']) <= .05*b['targets']
               for m,b in zip(count, reference)):
            supported.append((sum(m['wrong'] for m in count), distance))
    return min(supported)[1] if supported else None


def run(args):
    if args.output.exists():
        raise FileExistsError(args.output)
    policies = {}
    for distance in GUARD_OPTIONS_M:
        cfg = RunConfig()
        cfg.fusion.systematic_bias_guard_m = distance
        cfg.fusion.preserve_proposed_pair = False
        policies[f'guard_{distance:.0f}m'] = SARAISFusion(cfg)
    names = ('distance_only', *policies)
    frozen = json.loads(args.confirmation.read_text()) if args.confirmation else None
    days = (CONFIRMATION_DAY,) if frozen else DAYS
    if frozen and tuple(frozen['sources']) != DAYS:
        raise ValueError('Expected the two development dates before confirmation')
    sources, windows, splits = {}, [], {}
    for day in days:
        f, src = read_day(args.archives/f"AIS_{day.replace('-','_')}.zip", day)
        sources[day] = src
        per_day = {name:{group:Counter() for group in
                         ('overall','neighbor_250m','separated','has_history','no_history')} for name in names}
        base = int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp())
        for region, bounds in AREAS.items():
            w,s,e,n = bounds
            area = f[f['LAT'].between(s-.03,n+.03) & f['LON'].between(w-.03,e+.03)]
            for hour in HOURS:
                ts = base + 3600*hour
                points, truth, history, offsets = sample_window(area, bounds, ts)
                if not points:
                    continue
                estimates = policies['guard_100m'].interpolate_ais(history, ts)
                lat = np.array([p.lat for p in points])
                lon = np.array([p.lon for p in points])
                geo = haversine_m(lat[:,None],lon[:,None],lat[None,:],lon[None,:])
                np.fill_diagonal(geo, np.inf)
                neighbor = (geo <= NEAR_NEIGHBOR_M).any(axis=1)
                outputs = (legacy(points, estimates), *(method.match(points, estimates)[0]
                           for method in policies.values()))
                row = dict(day=day, region=region, hour_utc=hour, points=len(points),
                           histories=len(estimates), near_neighbors=int(neighbor.sum()),
                           anchor_offset_s_median=float(np.median(offsets)))
                for name, outcome in zip(names, outputs):
                    local = {key:Counter() for key in per_day[name]}
                    add_counts(local, outcome, truth, estimates.keys(), neighbor)
                    for group, count in local.items():
                        per_day[name][group].update(count)
                    row[name] = complete_counts(local['overall'])
                windows.append(row)
        splits[day] = per_day
        print(day, 'retained fixes', len(f), 'windows with anchors',
              sum(w['day']==day for w in windows), flush=True)
    if not windows:
        raise ValueError('Fixed audit windows did not contain held-out records')
    aggregate = {}
    for name in names:
        aggregate[name] = {group:complete_counts(sum((d[name][group] for d in splits.values()), Counter()))
                           for group in next(iter(splits.values()))[name]}
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(
        dataset_type='withheld_real_ais_fixes_as_position_proxies', sources=sources,
        design=dict(areas_wsen=AREAS, hours_utc=list(HOURS), anchor_time_tolerance_s=ANCHOR_S,
                    history_window_s=HISTORY_S, near_neighbor_m=NEAR_NEIGHBOR_M,
                    gates=vars(policies['guard_100m'].cfg.fusion), sensitivity_grid_m=GUARD_OPTIONS_M,
                    same_source_limit='Held-out AIS fixes share a data source with the input histories. No radar positions or surveyed ground truth in this replay.',
                    code_sha256={p.name:digest(p) for p in (Path(__file__),
                        Path(__file__).resolve().parents[1]/'src/sonarnet/fusion/matching.py',
                        Path(__file__).resolve().parents[1]/'src/sonarnet/fusion/kalman.py')}),
        results=aggregate, per_day=splits, windows=windows,
        selection=dict(
            rule='Only candidates yielding fewer wrong assignments and losing no more than 5 percentage points of correct assignments on each development day are eligible. Choose fewest wrong overall, then narrower guard.',
            selected_guard_m=frozen['selection']['selected_guard_m'] if frozen else select_guard(splits),
            development_report_sha256=digest(args.confirmation) if frozen else None))
    (args.output/'results.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    print(json.dumps(aggregate, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archives','output'):
        parser.add_argument('--'+name, required=True, type=Path)
    parser.add_argument('--confirmation', type=Path, help='Run the separate date, loading the frozen development choice.')
    run(parser.parse_args())
