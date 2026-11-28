"""Paired stage 2 evaluation for the shipped SonarNet fusion and behavior modules."""
import argparse
import csv
from importlib.metadata import version
import json
from pathlib import Path
from dataclasses import replace

import numpy as np
from sklearn.metrics import confusion_matrix, f1_score

from evaluate_ais_trajectories import BASE_UTC, build_trial
from sonarnet.behavior.classifier import BehaviorClassifier
from sonarnet.behavior.features import features_matrix
from sonarnet.config import RunConfig
from sonarnet.data.geo import meters_per_degree
from sonarnet.data.simulator import AIS_MISMATCH, AIS_OK
from sonarnet.data.tracks import generate_track_dataset
from sonarnet.fusion.matching import Detection, SARAISFusion

SEEDS = (101, 203, 307, 409, 503)
CLASSES = ('cau', 'keo_luoi', 'neo_dau', 'qua_canh')
SCENARIOS = ('clean', 'gaps', 'short_noisy', 'overlap')
FUSION_CASES = ('mixed_quality', 'near_crossing', 'position_bias', 'size_noise')
REVIEW_POSITIVE = {'cau', 'keo_luoi'}
VN = {'cau':'Câu', 'keo_luoi':'Kéo lưới', 'neo_dau':'Neo đậu/trôi', 'qua_canh':'Quá cảnh'}


def dataset(tracks_per_class, rng):
    cfg = RunConfig()
    cfg.behavior.n_tracks_per_class = tracks_per_class
    return generate_track_dataset(cfg, rng)


def degraded(track, scenario, rng):
    if scenario == 'clean':
        return track
    count = len(track)
    index = np.arange(count)
    if scenario in ('short_noisy','overlap'):
        length = int(rng.integers(9,20))
        start = int(rng.integers(0,count-length+1))
        index = index[start:start+length]
    missing = {'gaps':.60,'short_noisy':.15,'overlap':.30}[scenario]
    mask = rng.random(len(index)) > missing
    mask[[0,-1]] = True
    if mask.sum() < 5:
        mask[np.linspace(0,len(mask)-1,5,dtype=int)] = True
    index = index[mask]
    deviation = {'gaps':45.,'short_noisy':90.,'overlap':140.}[scenario]
    lat_m,lon_m = meters_per_degree(float(np.mean(track.lats)))
    speeds = track.speeds_kn[index]
    if scenario == 'overlap':
        # Stress the reported SOG channel with vessel-specific gain and drift.
        # Physical motion is supplied separately by the unchanged latent track.
        speeds = speeds*rng.uniform(.32,.82)+rng.uniform(-.5,3.5)
    speed_sigma = {'gaps':.6,'short_noisy':1.,'overlap':1.8}[scenario]
    course_sigma = {'gaps':10.,'short_noisy':20.,'overlap':45.}[scenario]
    return replace(track, times_s=track.times_s[index],
                   lats=track.lats[index]+rng.normal(0,deviation,len(index))/lat_m,
                   lons=track.lons[index]+rng.normal(0,deviation,len(index))/lon_m,
                   speeds_kn=np.maximum(0,speeds+rng.normal(0,speed_sigma,len(index))),
                   courses_deg=(track.courses_deg[index]+rng.normal(0,course_sigma,len(index)))%360)


def snapshot(tracks):
    return np.asarray([[t.speeds_kn[-1]] for t in tracks],dtype=np.float32)


def classify(seed):
    clean_rng, test_rng, augmentation_rng, noise_rng = [
        np.random.default_rng(s) for s in np.random.SeedSequence(seed).spawn(4)
    ]
    train, test = dataset(100,clean_rng), dataset(60,test_rng)
    X,y = features_matrix(train)
    short_ids = np.concatenate([np.flatnonzero(y==c)[:12] for c in CLASSES])
    extra = [degraded(track, SCENARIOS[1+i%3], augmentation_rng) for i,track in enumerate(train)]
    XA,yA = features_matrix(extra)
    Xboth,yboth = np.vstack([X,XA]), np.concatenate([y,yA])
    use_noisy = (np.arange(len(X))%4!=0)[:,None]
    fits = {'snapshot': (snapshot(train),y),
            'history_limited_training':(X[short_ids],y[short_ids]),
            'history_full':(X,y),
            'history_augmented_matched':(np.where(use_noisy,XA,X),y),
            'history_augmented':(Xboth,yboth)}
    models = {name:BehaviorClassifier(backend='xgboost',seed=seed).fit(*data)
              for name,data in fits.items()}
    for scenario in SCENARIOS:
        samples = [degraded(t,scenario,noise_rng) for t in test]
        XX, truth = features_matrix(samples)
        for name, model in models.items():
            pred = model.predict(snapshot(samples) if name=='snapshot' else XX)
            target = np.isin(truth,list(REVIEW_POSITIVE))
            predicted_target = np.isin(pred,list(REVIEW_POSITIVE))
            cm = confusion_matrix(truth,pred,labels=CLASSES)
            per_class = f1_score(truth,pred,average=None,labels=CLASSES,zero_division=0)
            yield dict(seed=seed,scenario=scenario,model=name,n_train=len(fits[name][1]),
                       test_tracks=len(test),macro_f1=float(per_class.mean()),
                       per_class_f1=dict(zip(CLASSES,per_class.tolist())),confusion=cm.tolist(),
                       review_targets=int(target.sum()),review_missed=int((target & ~predicted_target).sum()),
                       review_false_flags=int((~target & predicted_target).sum()))
    return models['history_augmented']


def mock_radar(rng, scenario):
    raw, points, truth = build_trial(rng, 'mixed_quality' if scenario=='size_noise' else scenario)
    length = {ident:float(rng.uniform(35,110)) for ident in truth if ident is not None}
    altered = {ident for ident in length if rng.random()<.33}
    for packet in raw:
        ident = packet['mmsi']
        packet['declared_length_m'] = length[ident]*(2.25 if ident in altered else 1.)
    sigma = .33 if scenario=='size_noise' else .09
    detections = [Detection(i,lat,lon,max(5.,length[ident]*(1+rng.normal(0,sigma))),
                            15.,(0,0,8,2)) for i,((lat,lon),ident) in enumerate(zip(points,truth))]
    return raw,detections,truth,altered


def fusion_rows(seed):
    cfg = RunConfig()
    methods = {k:SARAISFusion(cfg,use_kalman=k) for k in (False,True)}
    for index,scenario in enumerate(FUSION_CASES):
        rng=np.random.default_rng(np.random.SeedSequence([seed,310,index]))
        summary={}
        for _ in range(60):
            records,detections,truth,altered = mock_radar(rng,scenario)
            for kalman,fusion in methods.items():
                estimates=fusion.interpolate_ais(records,BASE_UTC)
                matches,_,reasons=fusion.match_with_reasons(detections,estimates)
                full=fusion.classify_states(detections,matches,estimates,reasons)
                for size in (False,True):
                    key=(kalman,size)
                    row=summary.setdefault(key,dict(seed=seed,scenario=scenario,kalman=kalman,
                        size_check=size,n=0,id_correct=0,id_wrong=0,id_abstained=0,valid_declared_pairs=0,
                        mismatches_on_valid_pairs=0,mod_mismatch_true=0,mod_mismatch_missed=0,
                        mod_mismatch_false=0,downstream_blocked=0))
                    for i,ident in enumerate(truth):
                        matched=matches.get(i)
                        valid_pair=matched==ident
                        state=full[i] if size else (AIS_OK if matched is not None else full[i])
                        row['n']+=1
                        row['id_correct']+=int(valid_pair)
                        row['id_wrong']+=int(matched is not None and not valid_pair)
                        row['id_abstained']+=int(matched is None)
                        row['downstream_blocked']+=int(state!=AIS_OK)
                        if valid_pair:
                            actual=ident in altered
                            flag=state==AIS_MISMATCH
                            row['valid_declared_pairs']+=1
                            row['mismatches_on_valid_pairs']+=int(actual)
                            row['mod_mismatch_true']+=int(actual and flag)
                            row['mod_mismatch_missed']+=int(actual and not flag)
                            row['mod_mismatch_false']+=int(not actual and flag)
        for row in summary.values():
            yield row


def study_bank(model):
    rng=np.random.default_rng(2026112801)
    cfg=RunConfig()
    cfg.behavior.n_tracks_per_class=160
    tracks=generate_track_dataset(cfg,rng)
    scenarios=['short_noisy' if i%2==0 else 'overlap' for i in range(len(tracks))]
    samples=[degraded(t,s,rng) for t,s in zip(tracks,scenarios)]
    pred=model.predict(features_matrix(samples)[0])
    candidates=list(zip(samples,scenarios,pred))
    used=set()
    rows=[]
    for pack in ('A','B'):
        # Include one misleading alert and one misleading omission when
        # available. This case set is a stress-test, not a prevalence sample.
        wrong_slots={priority:1 for priority in (False,True)}
        classes=CLASSES if pack=='A' else tuple(reversed(CLASSES))
        for c in classes:
            for scenario in ('short_noisy','overlap'):
                priority=c in REVIEW_POSITIVE
                pool=[(i,t,suggested) for i,(t,s,suggested) in enumerate(candidates)
                      if i not in used and t.behaviour==c and s==scenario]
                wrong_first=scenario=='overlap' and wrong_slots[priority]>0
                preferred=[item for item in pool if ((item[2] in REVIEW_POSITIVE)!=priority)==wrong_first]
                i,track,suggested=(preferred or pool)[0]
                wrong_slots[priority]-=int((suggested in REVIEW_POSITIVE)!=priority)
                used.add(i)
                lat_m,lon_m=meters_per_degree(float(track.lats[0]))
                rows.append(dict(id=f'Q{len(rows)+1:02d}',pack=pack,scenario=scenario,
                    elapsed_min=np.round((track.times_s-track.times_s[0])/60,1).tolist(),
                    east_m=np.round((track.lons-track.lons[0])*lon_m,1).tolist(),
                    north_m=np.round((track.lats-track.lats[0])*lat_m,1).tolist(),
                    speed_kn=np.round(track.speeds_kn,1).tolist(),
                    course_deg=np.round(track.courses_deg).astype(int).tolist(),
                    reference_class=c,priority=priority,hint_class=VN[suggested],
                    hint_priority=suggested in REVIEW_POSITIVE))
    return rows


def write_csv(rows,path):
    fields=[key for key,value in rows[0].items() if not isinstance(value,(list,dict))]
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore',lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def write_json(path,obj):
    path.write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False)+'\n')


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--output', type=Path, default=Path('reports/final/chang2'))
    options=cli.parse_args()
    output=options.output
    output.mkdir(exist_ok=True,parents=True)
    behavior,fusion=[],[]
    for seed in SEEDS:
        step=classify(seed)
        while True:
            try:
                behavior.append(next(step))
            except StopIteration as finished:
                model=finished.value
                break
        fusion.extend(fusion_rows(seed))
        print(f'Seed {seed} complete',flush=True)
        if seed==SEEDS[0]:
            write_json(output/'study-cases.json',study_bank(model))
    write_csv(behavior,output/'behavior.csv')
    write_csv(fusion,output/'fusion.csv')
    write_json(output/'results.json',dict(seeds=list(SEEDS),behavior=behavior,fusion=fusion,
               versions={name:version(name) for name in ('numpy','scikit-learn','xgboost')},
               scope='Synthetic tracks and synthetic detections. No field behavior labels.'))


if __name__=='__main__':
    main()
