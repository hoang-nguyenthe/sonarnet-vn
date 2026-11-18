"""Compare qualified-first and assigned-first matching on historical AIS fixes."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np

from evaluate_ais_matching import legacy
from evaluate_ais_trajectories import BASE_UTC, REPEATS, SCENARIOS, SEED, build_trial, count_trial
from evaluate_noaa_ais_replay import (AREAS, DAYS, HOURS, add_counts, complete_counts,
                                      digest, read_day, sample_window)
from sonarnet.config import RunConfig
from sonarnet.data.geo import haversine_m
from sonarnet.fusion.matching import Detection, SARAISFusion

GROUPS = ('overall', 'neighbor_250m', 'separated', 'has_history', 'no_history')
LOCKED_METHOD = 'assign_then_veto_200m'


def build_policies():
    policies = {}
    for name, preserve, guard in (
        ('gate_first',False,0.), ('gate_first_100m',False,100.),
        ('assign_then_veto',True,0.), ('assign_then_veto_25m',True,12.5),
        ('assign_then_veto_100m',True,50.), ('assign_then_veto_200m',True,100.),
    ):
        cfg = RunConfig()
        cfg.fusion.preserve_proposed_pair = preserve
        cfg.fusion.systematic_bias_guard_m = guard
        policies[name] = SARAISFusion(cfg)
    return policies


def methods(points, estimates, policies):
    return {'distance':legacy(points,estimates),
            **{name:fusion.match(points,estimates)[0] for name,fusion in policies.items()}}


def evaluate(day, archive, policies):
    data, source = read_day(archive,day)
    counts = {}
    start = int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp())
    windows = []
    for area, (w,s,e,n) in AREAS.items():
        local = data[data['LAT'].between(s-.03,n+.03) & data['LON'].between(w-.03,e+.03)]
        for hour in HOURS:
            when = start+hour*3600
            points, ids, history, _ = sample_window(local,(w,s,e,n),when)
            if not points:
                continue
            estimates = policies[LOCKED_METHOD].interpolate_ais(history,when)
            lat,lon = np.array([p.lat for p in points]),np.array([p.lon for p in points])
            spacing = haversine_m(lat[:,None],lon[:,None],lat[None,:],lon[None,:])
            np.fill_diagonal(spacing,np.inf)
            neighbor = (spacing <= 250).any(axis=1)
            outcomes = methods(points,estimates,policies)
            plain = outcomes['distance']
            extra_reroutes = {}
            for name, outcome in outcomes.items():
                group = counts.setdefault(name,{tag:Counter() for tag in GROUPS})
                add_counts(group,outcome,ids,estimates.keys(),neighbor)
                altered = {i:j for i,j in outcome.items() if plain.get(i) != j}
                extra_reroutes[name] = dict(altered=len(altered), wrong=sum(ids[i]!=j for i,j in altered.items()))
            windows.append(dict(area=area,hour_utc=hour,reroutes=extra_reroutes))
    results = {k:{tag:complete_counts(c) for tag,c in groups.items()} for k,groups in counts.items()}
    reroutes = {name:{tag:sum(w['reroutes'][name][tag] for w in windows) for tag in ('altered','wrong')}
                for name in counts}
    return dict(source=source,windows=len(windows),results=results,reroutes=reroutes)


def synthetic(policies):
    rng = np.random.default_rng(SEED)
    by_scenario = {}
    for name in SCENARIOS:
        results = {}
        for _ in range(REPEATS):
            raw, positions, truth = build_trial(rng,name)
            points = [Detection(i,lat,lon,80.,20.,(0,0,8,2))
                      for i,(lat,lon) in enumerate(positions)]
            estimates = policies[LOCKED_METHOD].interpolate_ais(raw,BASE_UTC)
            for policy, matches in methods(points,estimates,policies).items():
                count_trial(results.setdefault(policy,Counter()),matches,truth)
        by_scenario[name] = results
    return dict(seed=SEED,repeats=REPEATS,results=by_scenario)


def run(args):
    days = ('2024-12-13',) if args.held_out else DAYS
    if args.held_out:
        past = json.loads(args.held_out.read_text())
        if tuple(past['days']) != DAYS or past.get('selected_method') != LOCKED_METHOD:
            raise ValueError('Require the locked development comparison before opening the held-out day')
    report = dict(code_sha256=digest(Path(__file__)), input_filter_sha256=digest(Path(__file__).with_name('evaluate_noaa_ais_replay.py')),
                  fusion_code_sha256=digest(Path(__file__).resolve().parents[1]/'src/sonarnet/fusion/matching.py'),
                  development_report_sha256=digest(args.held_out) if args.held_out else None,
                  selected_method=LOCKED_METHOD,
                  selection='Pair-first policy with 200 m added separation margin. Among tested pair-first policies, only this variant preserved zero wrong links on both previous systematic-offset synthetic scenarios. Retain this choice before checking the separate historical AIS day.',
                  scope='Withheld NOAA positions as location proxies; no SAR or verified vessel identity in these hourly windows.',
                  policy='Distance Hungarian first, then veto pairs failing age, uncertainty, radius or reciprocal nearest with a distance margin. Never change the proposed partner after a veto.',
                  days={})
    policies = build_policies()
    if not args.held_out:
        report['synthetic'] = synthetic(policies)
    for day,archive in zip(days,args.archives,strict=True):
        if archive.stem != 'AIS_'+day.replace('-','_'):
            raise ValueError('Input file does not match fixed day')
        report['days'][day] = evaluate(day,archive,policies)
        day_result = report['days'][day]
        print(day, {m:d['overall'] for m,d in day_result['results'].items()},day_result['reroutes'],flush=True)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as f:
        json.dump(report,f,indent=2,allow_nan=False)
        f.write('\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archives',type=Path,nargs='+',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--held-out',type=Path,help='Reference to the two-day development report.')
    run(parser.parse_args())
