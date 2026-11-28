"""Measure how paired fusion and behavior ablations propagate to a review queue."""
import argparse
from collections import Counter, defaultdict
from dataclasses import replace
from itertools import product
from pathlib import Path

import numpy as np

from deep_ablation_chang2 import SEEDS, SCALES, SCALE_KEYS, block_gap, interval
from evaluate_ais_trajectories import BASE_UTC, SCENARIOS, coordinates
from evaluate_chang2 import CLASSES, REVIEW_POSITIVE, dataset, degraded, write_csv, write_json
from sonarnet.behavior.classifier import BehaviorClassifier
from sonarnet.behavior.features import features_matrix
from sonarnet.config import RunConfig
from sonarnet.data.geo import meters_per_degree
from sonarnet.data.simulator import AIS_OK
from sonarnet.fusion.matching import Detection, SARAISFusion

CASES = {
    'mixed_quality':'gaps', 'near_crossing':'short_noisy',
    'keep_two_crossing_tracks_when_separated':'clean',
    'unlabeled_clutter_near_track':'clean', 'sparse_one_sided':'block_gap',
    'position_bias':'overlap', 'position_bias_beyond_guard':'overlap',
    'size_noise':'short_noisy',
}
MODES = ('without_behavior','clean_training','mixed_training')
N_SCENES = 55
FUSION_KEYS = ('n_targets','n_clutter','positives','reviewed','hits','false_priorities',
               'wrong_id_priority','cleanly_excluded_negatives','miss_unmatched','miss_wrong_id',
               'miss_size_gate','miss_behavior','misses')
CONFIGS = tuple(product((False,True),(False,True),MODES))


def train_models(seed):
    train_rng,aug_rng=(np.random.default_rng(s) for s in np.random.SeedSequence([seed,240095]).spawn(2))
    train=dataset(100,train_rng)
    profiles=dict.fromkeys(CLASSES,0)
    mixed=[]
    conditions=('clean','gaps','short_noisy','overlap')
    for t in train:
        mixed.append(degraded(t,conditions[profiles[t.behaviour]%4],aug_rng))
        profiles[t.behaviour]+=1
    return {name:BehaviorClassifier(backend='xgboost',seed=seed).fit(*features_matrix(samples))
            for name,samples in (('clean_training',train),('mixed_training',mixed))}


def placed_track(track, east, north):
    lat,lon=coordinates((east,north))
    capture=-2
    native_mlat,native_mlon=meters_per_degree(float(track.lats[capture]))
    dst_mlat,dst_mlon=meters_per_degree(lat)
    return replace(track,
                   times_s=track.times_s-track.times_s[capture],
                   lats=lat+(track.lats-track.lats[capture])*native_mlat/dst_mlat,
                   lons=lon+(track.lons-track.lons[capture])*native_mlon/dst_mlon)


def past_observation(track, condition, rng):
    past=track.times_s<=0
    history=replace(track,**{key:getattr(track,key)[past] for key in
                             ('lats','lons','times_s','speeds_kn','courses_deg')})
    return block_gap(history,rng) if condition=='block_gap' else degraded(history,condition,rng)


def make_scene(tracks, scenario, rng):
    template='mixed_quality' if scenario=='size_noise' else scenario
    centers,states=SCENARIOS[template]
    positions=np.asarray(centers)+rng.normal(0,8,(4,2))
    records,detections,truth,histories=[],[],{},{}
    for i,(base,position,state) in enumerate(zip(tracks,positions,states)):
        ident=100+i
        track=placed_track(base,*position)
        truth[ident]=track.behaviour in REVIEW_POSITIVE
        detections.append(Detection(i,*coordinates(position+rng.normal(0,7,2)),
                                    1.,15.,(0,0,8,2)))
        length=float(rng.uniform(30,110))
        sigma=.33 if scenario=='size_noise' else .09
        detections[-1].length_m=max(5.,length*(1+rng.normal(0,sigma)))
        factor=SCALES[str(rng.choice(SCALE_KEYS,p=[.09,.36,.11,.11,.11,.11,.11]))]
        if state=='missing':
            continue
        histories[ident]=past_observation(track,CASES[scenario],rng)
        times={'stale':(-470,-402,-365,-321,-271),
               'one_sided':(-333,-281,-229,-163,-121)}.get(state,(-136,-79,-38,37,84,144))
        mlat,mlon=meters_per_degree(float(track.lats[-2]))
        position_offset=0.
        if state.startswith('biased_'):
            bounds=(208.,242.) if scenario=='position_bias_beyond_guard' else (128.,185.)
            position_offset=float(rng.uniform(*bounds))*(1 if state=='biased_east' else -1)
        uncertainty=220 if state=='noisy' else 12
        for dt in times:
            offset=dt+int(rng.integers(-12,13))
            lat=float(np.interp(offset,track.times_s,track.lats)+rng.normal(0,uncertainty)/mlat)
            lon=float(np.interp(offset,track.times_s,track.lons)
                      +(position_offset+rng.normal(0,uncertainty))/mlon)
            records.append(dict(timestamp=BASE_UTC+offset,lat=lat,lon=lon,mmsi=ident,
                                declared_length_m=length*factor if factor is not None else None))
    if scenario=='unlabeled_clutter_near_track':
        point=positions[0]+[rng.uniform(12,48),rng.uniform(-15,15)]
        detections.append(Detection(4,*coordinates(point),60.,15.,(0,0,8,2)))
    return records,detections,truth,histories


def score_scene(truth,n_detections,matches,flags,requires_size,states):
    counts=Counter(dict.fromkeys(FUSION_KEYS,0))
    counts.update(n_targets=len(truth),n_clutter=n_detections-len(truth),positives=sum(truth.values()))
    for i in range(n_detections):
        ident=100+i
        positive=truth.get(ident,False)
        actual_match=matches.get(i)
        right=actual_match==ident and ident in truth
        if actual_match is None:
            reason='miss_unmatched'
        elif not right:
            reason='miss_wrong_id'
        elif requires_size and states[i]!=AIS_OK:
            reason='miss_size_gate'
        else:
            reason='miss_behavior'
        sent=(actual_match is not None and (not requires_size or states[i]==AIS_OK)
              and flags.get(actual_match,False))
        hit=sent and right and positive
        counts['reviewed']+=int(sent)
        counts['hits']+=int(hit)
        counts['false_priorities']+=int(sent and not hit)
        counts['wrong_id_priority']+=int(sent and not right)
        counts['cleanly_excluded_negatives']+=int(ident in truth and not positive and not sent)
        if positive and not hit:
            counts['misses']+=1
            counts[reason]+=1
    assert counts['misses']==sum(counts[k] for k in
        ('miss_unmatched','miss_wrong_id','miss_size_gate','miss_behavior'))
    assert counts['reviewed']==counts['hits']+counts['false_priorities']
    return counts


def one_seed(seed):
    rngs=np.random.SeedSequence([seed,39178]).spawn(len(CASES)+1)
    models=train_models(seed)
    test=dataset(N_SCENES*len(CASES),np.random.default_rng(rngs[0]))
    by_class={c:[t for t in test if t.behaviour==c] for c in CLASSES}
    estimators={k:SARAISFusion(RunConfig(),use_kalman=k) for k in (False,True)}
    result=[]
    for si,(case,_) in enumerate(CASES.items()):
        rng=np.random.default_rng(rngs[si+1])
        scenes=[]; samples=[]
        for j in range(N_SCENES):
            tracks=[by_class[c][si*N_SCENES+j] for c in rng.permutation(CLASSES)]
            records,detections,truth,history=make_scene(tracks,case,rng)
            scenes.append((records,detections,truth,list(history)))
            samples.extend(history.values())
        data,_=features_matrix(samples)
        predicted={name:np.isin(model.predict(data),sorted(REVIEW_POSITIVE))
                   for name,model in models.items()}
        blocks={conf:Counter() for conf in CONFIGS}
        start=0
        for records,detections,truth,ids in scenes:
            end=start+len(ids)
            labels={name:dict(zip(ids,flagged[start:end])) for name,flagged in predicted.items()}
            labels['without_behavior']=dict.fromkeys(ids,True)
            start=end
            for kalman,match in estimators.items():
                estimates=match.interpolate_ais(records,BASE_UTC)
                proposed,_,reasons=match.match_with_reasons(detections,estimates)
                states=match.classify_states(detections,proposed,estimates,reasons)
                for size,model in product((False,True),MODES):
                    blocks[kalman,size,model].update(
                        score_scene(truth,len(detections),proposed,labels[model],size,states)
                    )
        assert start==len(samples)
        for (kalman,size,model),counts in blocks.items():
            result.append(dict(seed=seed,scenario=case,kalman=kalman,size_check=size,
                               behavior=model,**counts))
    return result


def aggregate(rows):
    grouped=defaultdict(Counter)
    for row in rows:
        by=(row['kalman'],row['size_check'],row['behavior'])
        values={k:row[k] for k in FUSION_KEYS}
        for scenario in ('all',row['scenario']):
            grouped[scenario,*by].update(values)
    return [dict(scenario=case,kalman=k,size_check=s,behavior=m,**counts,
                 recall=counts['hits']/counts['positives'],
                 precision=counts['hits']/counts['reviewed'] if counts['reviewed'] else 0.)
            for (case,k,s,m),counts in grouped.items()]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=Path('reports/final/chang2'))
    args=parser.parse_args()
    args.out.mkdir(exist_ok=True,parents=True)
    rows=[]
    for seed in SEEDS:
        rows.extend(one_seed(seed))
        print(f'Finished seed {seed}',flush=True)
    by_seed=defaultdict(Counter)
    for item in rows:
        by_seed[item['seed'],item['kalman'],item['size_check'],item['behavior']].update(
            {k:item[k] for k in FUSION_KEYS})
    p=(True,True,'mixed_training')
    references={'kalman':(False,True,'mixed_training'),'size_gate':(True,False,'mixed_training'),
                'mixed_training':(True,True,'clean_training'),
                'with_behavior':(True,True,'without_behavior')}
    contrasts={}
    rng=np.random.default_rng(49102)
    for name,ref in references.items():
        per_seed=[(by_seed[seed,*ref],by_seed[seed,*p]) for seed in SEEDS]
        contrasts[name]={key:interval([(b[key]-a[key])/a[den] for a,b in per_seed],rng)
                         for key,den in (('hits','positives'),('reviewed','n_targets'),
                                         ('false_priorities','n_targets'))}
    write_csv(rows,args.out/'chain-ablation.csv')
    write_json(args.out/'chain-ablation.json',dict(
        seeds=SEEDS,scenes_per_scenario_seed=N_SCENES,scenarios=CASES,
        aggregate=aggregate(rows),contrasts=contrasts,
        note='Synthetic paired review queue, using precomputed SAR candidates. A hit requires '
             'a flagged positive target with the correct associated vessel.'))


if __name__=='__main__':
    main()
