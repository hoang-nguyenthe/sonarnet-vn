"""Compare review allocation across acquisition dates at a fixed total cost."""
import argparse
import gzip
import json
from pathlib import Path

from evaluate_rtc_contrast_recall import RADII, shortlist
from evaluate_rtc_map_tta import ranked_views
from evaluate_review_ranking import save
from score_vn_reference_rtc import digest, matched

MODES={'equal_incumbent':'incumbent','equal_relaxed':'baseline_low'}
POLICIES=('global_confidence','global_overlap_max','global_overlap_vote',
          'overlap_max_half_floor','overlap_vote_half_floor')


def load(cache,views):
    with gzip.open(cache,'rt') as fd:
        records=json.load(fd)
    all_views=json.loads(views.read_text())
    if set(all_views) != {case['scene'] for case in records}:
        raise ValueError('Predictions and labels do not refer to same acquisitions')
    for case in records:
        case['overlap']=all_views[case['scene']]['overlap']
    return records


def scored(row,mode,prior):
    base=sorted(row[prior],key=lambda p:-p[2])
    low=sorted(row['baseline_low'],key=lambda p:-p[2])
    limit=min(row['budget'],len(base))
    combined=ranked_views(low,{'overlap':row['overlap']},'max')
    vote=ranked_views(low,{'overlap':row['overlap']},'vote')
    strong=shortlist(low if mode=='equal_incumbent' else combined,base,limit,35.)
    pools={name:shortlist(items,base,row['budget'],35.)
           for name,items in (('confidence',low),('max',combined),('vote',vote))}
    return base[:limit],strong,pools


def allocate(pools,limits,policy):
    total=sum(limits)
    floor=[n//2 if policy.endswith('_floor') else 0 for n in limits]
    if any(n>len(q) for n,q in zip(floor,pools)):
        raise ValueError('Insufficient candidates for the declared floor')
    result=[queue[:n] for queue,n in zip(pools,floor)]
    shared=sorted([(point[2],idx,point) for idx,queue in enumerate(pools)
                   for point in queue[floor[idx]:]],key=lambda row:-row[0])
    for _,idx,point in shared[:total-sum(floor)]:
        result[idx].append(point)
    if sum(map(len,result))!=total:
        raise ValueError('Same combined review budget must be fully spent')
    return result


def evaluate(cases):
    result={}
    for mode,prior in MODES.items():
        prepared=[scored(row,mode,prior) for row in cases]
        limits=[len(row[0]) for row in prepared]
        queues={'baseline':[row[0] for row in prepared],
                'strong_baseline':[row[1] for row in prepared]}
        for method,key in zip(POLICIES,('confidence','max','vote','max','vote')):
            queues[method]=allocate([row[2][key] for row in prepared],limits,method)
        result[mode]={method:[dict(scene=case['scene'],region=case['region'],
                                  scores=matched(points,case['truth'],RADII))
                              for case,points in zip(cases,proposals)]
                      for method,proposals in queues.items()}
    return result


def total(out, field='matched', radius=100):
    return sum(c['scores'][radius][field] for c in out)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('cached-neural','confirmation-cache','tta','confirmation-views','out'):
        p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args()
    out=args.out
    out.mkdir(exist_ok=False)
    pairs={'development':(args.cached_neural/'development_features.json.gz',args.tta/'development-views.json'),
           'held_out':(args.cached_neural/'fresh_features.json.gz',args.tta/'held-out-views.json'),
           'confirmation':(args.confirmation_cache,args.confirmation_views)}
    save(out/'protocol.json',dict(
        code_sha256=digest(Path(__file__)),budget='Same total review count across dates. Same per-area ceiling. Optional floor of half the baseline count per date.',
        selection='Maximize matched points on development at 100 m. Ties prefer a floor and earlier method order.',
        scope='Historical follow-up; area allocation changes by acquisition and is not a same-cost comparison for individual dates.',
        references={k:dict(cached_neural=digest(p),augmented_views=digest(q)) for k,(p,q) in pairs.items()}))
    data=load(*pairs['development'])
    dev_days={row['scene'].split('_')[4][:8] for row in data}
    dev=evaluate(data)
    locked={}
    for mode in MODES:
        totals={m:total(rows) for m,rows in dev[mode].items()}
        locked[mode]=max(POLICIES,key=lambda m:(totals[m],m.endswith('_floor')))
        print(mode,locked[mode],totals,flush=True)
    save(out/'selection.json',dict(selected=locked,development=dev))
    groups={}
    for group,pair in pairs.items():
        if group=='development':
            continue
        rows=load(*pair)
        if {row['scene'].split('_')[4][:8] for row in rows} & dev_days:
            raise ValueError('Development and scoring acquisitions overlap')
        groups[group]=evaluate(rows)
        for mode in MODES:
            print(group,mode,{m:total(values) for m,values in groups[group][mode].items()},flush=True)
    save(out/'results.json',dict(selected=locked,selection_sha256=digest(out/'selection.json'),test=groups))


if __name__=='__main__':
    main()
