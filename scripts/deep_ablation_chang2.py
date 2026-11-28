"""Factorial paired ablations for SonarNet Stage 2 (synthetic stress tests)."""
import argparse
from collections import Counter, defaultdict
from dataclasses import replace
from importlib.metadata import version
from pathlib import Path

import numpy as np
from sklearn.metrics import confusion_matrix, f1_score

from evaluate_ais_trajectories import BASE_UTC, SCENARIOS as FUSION_CASES, build_trial
from evaluate_chang2 import CLASSES, REVIEW_POSITIVE, dataset, degraded, snapshot, write_csv, write_json
from sonarnet.behavior.classifier import BehaviorClassifier
from sonarnet.behavior.features import features_matrix
from sonarnet.config import RunConfig
from sonarnet.data.simulator import AIS_MISMATCH, AIS_OK
from sonarnet.fusion.matching import Detection, SARAISFusion
from sonarnet.fusion.status import MISSING_DATA

SEEDS = (101, 203, 307, 409, 503, 601, 701, 809, 907, 1009)
SCENARIOS = ('clean', 'gaps', 'short_noisy', 'overlap', 'block_gap')
SCALES = {'missing':None,'valid':1.,'plus_30':1.30,'plus_60':1.60,
          'plus_80':1.80,'plus_125':2.25,'minus_45':.55}
SCALE_KEYS = tuple(SCALES)
N_SCENES = 90
FUSION_NAMES = (*FUSION_CASES, 'size_noise')
BEHAVIOR_MODELS = {
    'speed_clean_400':(False,False,100), 'speed_mixed_400':(False,True,100),
    'history_clean_48':(True,False,12), 'history_mixed_48':(True,True,12),
    'history_clean_400':(True,False,100), 'history_mixed_400':(True,True,100),
    'history_clean_800':(True,False,200), 'history_mixed_800':(True,True,200),
}
COMPARISONS = {
    'history_given_clean_400':('speed_clean_400','history_clean_400'),
    'history_given_mixed_400':('speed_mixed_400','history_mixed_400'),
    'mix_given_history_400':('history_clean_400','history_mixed_400'),
    'mix_given_speed_400':('speed_clean_400','speed_mixed_400'),
    'volume_clean_48_400':('history_clean_48','history_clean_400'),
    'volume_mixed_48_400':('history_mixed_48','history_mixed_400'),
    'volume_clean_400_800':('history_clean_400','history_clean_800'),
    'volume_mixed_400_800':('history_mixed_400','history_mixed_800'),
}


def block_gap(track, rng):
    n = len(track)
    start = int(rng.integers(12,n-65))
    idx = np.r_[0:start,start+55:n][::2]
    # A prolonged contiguous outage is deliberately absent during training.
    return replace(track,times_s=track.times_s[idx],lats=track.lats[idx],lons=track.lons[idx],
                   speeds_kn=np.maximum(0,track.speeds_kn[idx]+rng.normal(0,.8,len(idx))),
                   courses_deg=(track.courses_deg[idx]+rng.normal(0,16,len(idx)))%360)


def behavioral(seed):
    train_rng,test_rng,mix_rng,noise_rng = (
        np.random.default_rng(s) for s in np.random.SeedSequence([seed,8649]).spawn(4)
    )
    train,test = dataset(200,train_rng),dataset(60,test_rng)
    X,y = features_matrix(train)
    order = {label:np.flatnonzero(y==label) for label in CLASSES}
    mixed = list(train)
    for label in CLASSES:
        for j,i in enumerate(order[label]):
            mixed[i] = degraded(train[i],SCENARIOS[j%4],mix_rng)
    Xmix,_ = features_matrix(mixed)
    clean_speed,mixed_speed = snapshot(train),snapshot(mixed)
    models = {}
    for name,(history,mix,n_class) in BEHAVIOR_MODELS.items():
        ids = np.concatenate([order[c][:n_class] for c in CLASSES])
        X_train = (Xmix if mix else X) if history else (mixed_speed if mix else clean_speed)
        models[name] = BehaviorClassifier(backend='xgboost',seed=seed).fit(X_train[ids],y[ids])
    scores = []
    for scenario in SCENARIOS:
        sample = [block_gap(t,noise_rng) if scenario=='block_gap'
                  else degraded(t,scenario,noise_rng) for t in test]
        data,truth = features_matrix(sample)
        speed = snapshot(sample)
        positive = np.isin(truth,sorted(REVIEW_POSITIVE))
        for name,(history,mix,n_class) in BEHAVIOR_MODELS.items():
            pred = models[name].predict(data if history else speed)
            flagged = np.isin(pred,sorted(REVIEW_POSITIVE))
            cm = confusion_matrix(truth,pred,labels=CLASSES).tolist()
            f1 = f1_score(truth,pred,labels=CLASSES,average=None,zero_division=0)
            scores.append(dict(seed=seed,scenario=scenario,model=name,n_train=4*n_class,
                               n_test=len(truth),macro_f1=float(f1.mean()),
                               class_f1=dict(zip(CLASSES,f1.tolist())),confusion=cm,
                               review_missed=int((positive&~flagged).sum()),
                               review_false_flags=int((~positive&flagged).sum()),
                               review_positives=int(positive.sum())))
    return scores


def simulate_fusion(seed):
    cfg = RunConfig()
    estimators = {k:SARAISFusion(cfg,use_kalman=k) for k in (False,True)}
    pairs, sizes, joint, noise_pairs = [], [], [], []
    for idx,scenario in enumerate(FUSION_NAMES):
        rng = np.random.default_rng(np.random.SeedSequence([seed,7134,idx]))
        outcomes = [Counter() for _ in range(N_SCENES)]
        counts = defaultdict(Counter)
        states = defaultdict(Counter)
        reason_counts = defaultdict(Counter)
        paired_noise = defaultdict(Counter)
        for n in range(N_SCENES):
            layout = 'mixed_quality' if scenario=='size_noise' else scenario
            raw,points,truth = build_trial(rng,layout)
            lengths = {v:float(rng.uniform(30,110)) for v in truth if v is not None}
            # Balanced support around the 0.42 mismatch threshold, including missing length.
            labels = {v:str(rng.choice(SCALE_KEYS,p=[.09,.36,.11,.11,.11,.11,.11])) for v in lengths}
            sig = .33 if scenario=='size_noise' else .09
            eps = [float(rng.normal()) for _ in truth]
            detections = [Detection(i,lat,lon,max(5.,lengths.get(ident,50.)*(1+sig*eps[i])),
                                    15.,(0,0,8,2)) for i,((lat,lon),ident) in enumerate(zip(points,truth))]
            for packet in raw:
                v = packet['mmsi']
                multiplier = SCALES[labels[v]]
                packet['declared_length_m'] = lengths[v]*multiplier if multiplier is not None else None
            joined = {}
            for kalman,fusion in estimators.items():
                estimates = fusion.interpolate_ais(raw,BASE_UTC)
                matches,_,reasons = fusion.match_with_reasons(detections,estimates)
                full = fusion.classify_states(detections,matches,estimates,reasons)
                joined[kalman] = matches
                if kalman:
                    clean_boxes = [replace(d,length_m=max(5.,lengths.get(v,50.)*(1+.09*eps[i])))
                                   for i,(d,v) in enumerate(zip(detections,truth))]
                    noisy_boxes = [replace(d,length_m=max(5.,lengths.get(v,50.)*(1+.33*eps[i])))
                                   for i,(d,v) in enumerate(zip(detections,truth))]
                    light = fusion.classify_states(clean_boxes,matches,estimates,reasons)
                    heavy = fusion.classify_states(noisy_boxes,matches,estimates,reasons)
                    for i,v in enumerate(truth):
                        if v is None or matches.get(i)!=v:
                            continue
                        actual = labels[v]
                        flag_state = MISSING_DATA if actual=='missing' else AIS_MISMATCH
                        x,y = light[i]==flag_state,heavy[i]==flag_state
                        row = paired_noise[actual]
                        row['n']+=1
                        row['flagged_light']+=int(x)
                        row['flagged_heavy']+=int(y)
                        row['only_light']+=int(x and not y)
                        row['only_heavy']+=int(y and not x)
                for i,v in enumerate(truth):
                    m = matches.get(i)
                    actual = labels[v] if v is not None else 'clutter'
                    right = m is not None and m==v
                    if m is None:
                        reason_counts[kalman][reasons[i]]+=1
                    for size in (False,True):
                        state = full[i] if size or m is None else AIS_OK
                        j = states[kalman,size]
                        j['n']+=1
                        j['targets']+=int(v is not None)
                        j['matched_correct']+=int(right)
                        j['wrong_target']+=int(m is not None and v is not None and m!=v)
                        j['target_unmatched']+=int(m is None and v is not None)
                        j['clutter_linked']+=int(m is not None and v is None)
                        if right:
                            d = counts[kalman,size,actual]
                            d['n']+=1
                            d['flagged']+=int(state==AIS_MISMATCH)
                            d['blocked_missing']+=int(state==MISSING_DATA)
                        if m is not None and state==AIS_OK:
                            j['passed_clean_truth']+=int(right and actual=='valid')
                            j['passed_bad_size_truth']+=int(right and actual not in ('valid','missing'))
                            j['passed_missing_truth']+=int(right and actual=='missing')
                            j['passed_wrong_identity']+=int(not right)
            scene = outcomes[n]
            for i,v in enumerate(truth):
                a,b = (joined[k].get(i) for k in (False,True))
                for j,m in enumerate((a,b)):
                    scene[f'correct_{j}']+=int(m is not None and m==v)
                    scene[f'wrong_{j}']+=int(m is not None and m!=v)
                if v is not None:
                    scene['targets']+=1
                    scene['only_linear']+=int(a==v and b!=v)
                    scene['only_kalman']+=int(b==v and a!=v)
                    scene['both_correct']+=int(a==v and b==v)
                    scene['neither_correct']+=int(a!=v and b!=v)
        for kalman,size in states:
            counts_by = states[kalman,size]
            joint.append(dict(seed=seed,scenario=scenario,kalman=kalman,size_check=size,
                              **counts_by,rejection_reasons=dict(reason_counts[kalman])))
        for kalman,size,category in counts:
            sizes.append(dict(seed=seed,scenario=scenario,kalman=kalman,size_check=size,
                              category=category,**counts[kalman,size,category]))
        pairs.extend(dict(seed=seed,scenario=scenario,trial=i,**row)
                     for i,row in enumerate(outcomes))
        noise_pairs.extend(dict(seed=seed,scenario=scenario,category=key,**row)
                           for key,row in paired_noise.items())
    return pairs,sizes,joint,noise_pairs


def interval(values, rng):
    values = np.asarray(values)
    resampled = values[rng.integers(len(values),size=(4000,len(values)))].mean(axis=1)
    return dict(mean=float(values.mean()),sd=float(values.std(ddof=1)),
                minimum=float(values.min()),maximum=float(values.max()),
                ci_95=np.percentile(resampled,[2.5,97.5]).tolist(),
                positive_seeds=int((values>0).sum()),negative_seeds=int((values<0).sum()))


def summarize(behavior,pairs):
    rng = np.random.default_rng(740219)
    lookup={(r['seed'],r['scenario'],r['model']):r for r in behavior}
    contrasts = []
    for case in SCENARIOS:
        for name,(a,b) in COMPARISONS.items():
            old,new = ([lookup[seed,case,model] for seed in SEEDS] for model in (a,b))
            delta = [b['macro_f1']-a['macro_f1'] for a,b in zip(old,new)]
            contrasts.append(dict(scenario=case,contrast=name,baseline=a,candidate=b,
                                  **interval(delta,rng),
                                  miss_before=sum(r['review_missed'] for r in old),
                                  miss_after=sum(r['review_missed'] for r in new),
                                  fp_before=sum(r['review_false_flags'] for r in old),
                                  fp_after=sum(r['review_false_flags'] for r in new)))
    fusion = []
    for case in ('all',*FUSION_NAMES):
        subset=[r for r in pairs if case=='all' or r['scenario']==case]
        group=defaultdict(Counter)
        for row in subset:
            group[row['seed']].update({k:v for k,v in row.items() if k not in ('seed','scenario','trial')})
        fields=Counter()
        for counter in group.values():
            fields.update(counter)
        for row in group.values():
            assert row['only_linear']+row['only_kalman']+row['both_correct']+row['neither_correct']==row['targets']
        delta=[(r['correct_1']-r['correct_0'])/r['targets'] for r in group.values()]
        wrong=[(r['wrong_1']-r['wrong_0'])/r['targets'] for r in group.values()]
        fusion.append(dict(scenario=case,scenes=len(subset),**fields,
                           delta_correct_rate=interval(delta,rng),delta_wrong_rate=interval(wrong,rng)))
    return contrasts,fusion


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=Path('reports/final/chang2'))
    args=parser.parse_args()
    args.out.mkdir(exist_ok=True,parents=True)
    behavior,pairs,sizes,joint,noise = [],[],[],[],[]
    for seed in SEEDS:
        behavior.extend(behavioral(seed))
        p,s,j,n = simulate_fusion(seed)
        pairs.extend(p); sizes.extend(s); joint.extend(j); noise.extend(n)
        print(f'Finished seed {seed}',flush=True)
    contrasts,fusion=summarize(behavior,pairs)
    cfg=RunConfig()
    write_csv(pairs,args.out/'fusion-paired-scenes.csv')
    write_csv(sizes,args.out/'size-by-factor.csv')
    write_csv(noise,args.out/'paired-size-noise.csv')
    write_csv(behavior,args.out/'behavior-factorial.csv')
    write_json(args.out/'deep-ablation.json',
               dict(seeds=SEEDS,bootstrap_seed=740219,bootstrap_resamples=4000,
                    scenes_per_scenario_seed=N_SCENES,size_threshold=cfg.fusion.size_mismatch_ratio,
                    size_factors=SCALES,versions={n:version(n) for n in ('numpy','scikit-learn','xgboost')},
                    fusion_paired=fusion,fusion_joint=joint,size_by_factor=sizes,paired_size_noise=noise,
                    behavior=behavior,behavior_contrasts=contrasts))


if __name__ == '__main__':
    main()
