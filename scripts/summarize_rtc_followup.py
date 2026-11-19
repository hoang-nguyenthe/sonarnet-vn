"""Verify and summarize locked RTC follow-ups for the public evidence panel."""
from hashlib import file_digest
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT/'reports/final'
FOLLOWUP = REPORTS/'vietnam_rtc_followup_20261119'
MODES = ('equal_incumbent','equal_relaxed')
RUNS = {
    'point': ('Heatmap học từ nhãn tâm', 'evaluate_rtc_point_detector.py','code_sha256'),
    'weak_boxes': ('Tinh chỉnh YOLO với nhãn tâm', 'train_rtc_weak_boxes.py','source_sha256'),
    'radiometry': ('Đổi dải cường độ radar đầu vào', 'evaluate_rtc_radiometry.py','code_sha256'),
    'centers': ('Hiệu chỉnh vị trí tâm theo heatmap', 'evaluate_rtc_center_refinement.py','code_sha256'),
    'allocation': ('Phân bổ lại lượt rà giữa các cảnh', 'evaluate_rtc_queue_allocation.py','code_sha256'),
}


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as stream:
        return file_digest(stream,'sha256').hexdigest()


def checked_run(folder,key,source,source_field):
    protocol,selected,results = (folder/f'{name}.json' for name in ('protocol','selection','results'))
    if read(protocol)[source_field] != sha(ROOT/'scripts'/source):
        raise ValueError(f'Script changed after evaluation ({key})')
    result=read(results)
    if result['selection_sha256'] != sha(selected):
        raise ValueError(f'Selection checksum mismatch ({key})')
    locked=read(selected)['selected']
    if key=='point':
        for mode in MODES:
            checkpoint=folder/locked[mode]['checkpoint']
            if sha(checkpoint)!=locked[mode]['checkpoint_sha256']:
                raise ValueError('Point checkpoint checksum mismatch')
            if any(row['modes'][mode]['method']!=locked[mode]['method']
                   for scenes in result['test'].values() for row in scenes):
                raise ValueError('Locked point policy mismatch')
    else:
        if locked != result['selected']:
            raise ValueError(f'Locked policy mismatch ({key})')
    if key=='weak_boxes' and sha(folder/'train/weights/best.pt')!=read(selected)['checkpoint_sha256']:
        raise ValueError('YOLO checkpoint checksum mismatch')
    return result


def counts(result,run_name,group,mode):
    selection=result['test'][group]
    if run_name=='point':
        rows=[c['modes'][mode] for c in selection]
        values=[r['counts'][r['method']]['100'] for r in rows]
    elif run_name=='allocation':
        values=[r['scores']['100'] for r in selection[mode][result['selected'][mode]]]
    else:
        values=[c[mode][result['selected'][mode]]['100'] for c in selection]
    return {key:sum(v[key] for v in values) for key in ('matched','labels','predictions')}


def summary():
    contrast=read(REPORTS/'vietnam_rtc_contrast_20261119/results.json')
    tta=read(REPORTS/'vietnam_rtc_tta_20261119/results.json')
    confirmation=read(REPORTS/'vietnam_rtc_tta_20261119/confirmation/results.json')['cases']
    group_baselines={}
    confirmation_counts={mode:{k:sum(c[mode]['baseline']['100'][k] for c in confirmation)
                               for k in ('labels','predictions')} for mode in MODES}
    prior=[]
    for mode,experiment in zip(MODES,(contrast,tta)):
        initial='map_default' if mode==MODES[0] else 'map_lower_threshold'
        rows=experiment['cases']
        original=[row[mode][initial]['100'] for row in rows]
        best=[row[mode][experiment['selected'][mode]]['100'] for row in rows]
        group_baselines[mode]={k:sum(c[k] for c in original) for k in ('matched','labels','predictions')}
        prior.append(dict(mode=mode,**{k:sum(c[k] for c in best) for k in ('matched','labels','predictions')}))
    trials=[]
    point_pool={}
    for key,(label,source,field) in RUNS.items():
        folder=FOLLOWUP/key
        data=checked_run(folder,key,source,field)
        values={group:{mode:counts(data,key,group,mode) for mode in MODES}
                for group in ('held_out','confirmation')}
        for mode in MODES:
            base=group_baselines[mode]
            row=values['held_out'][mode]
            if (row['predictions'],row['labels']) != (base['predictions'],base['labels']):
                raise ValueError(f'Review count or label denominator mismatch ({key})')
            if any(values['confirmation'][mode][k]!=expected
                   for k,expected in confirmation_counts[mode].items()):
                raise ValueError(f'Confirmation count mismatch ({key})')
        if key=='point':
            pools=[row['modes'][MODES[0]]['candidate_pool'] for row in data['test']['held_out']]
            point_pool={k:sum(row[k] for row in pools) for k in ('matched','labels','predictions')}
        trials.append(dict(name=label,results=values,artifact_sha256=sha(folder/'results.json')))
    return dict(review_modes=MODES, prior_best=prior, map_baselines=group_baselines, trials=trials,
                point_pool=point_pool, held_out_scenes=len(contrast['cases']),
                confirmation_scenes=len(confirmation))


if __name__=='__main__':
    out=summary()
    (FOLLOWUP/'summary.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    for row in out['trials']:
        print(row['name'],[row['results']['held_out'][mode]['matched'] for mode in MODES])
