"""Build the compact Streamlit evidence from the published Chặng 2 results."""
from collections import defaultdict
import csv
import json

from build_chang2_evidence import (
    OUT, FUSION_DEEP, FUTURE, MODEL_DEEP, TRACK_DEEP, behavior_deep_rows, chain_miss_rows,
    chain_rows, comparison_data, comparison_group_rows, external_rows, fusion_deep_rows,
    gate_deep_rows, proxy_comparison, proxy_rows, proxy_time_rows, robustness_rows,
    sar_rows, size_deep_rows, tile_rows, transfer_rows,
)

SOURCE = 'https://github.com/hoang-nguyenthe/sonarnet-vn/tree/chang-2/reports/final/chang2'


def read(name):
    return json.loads((OUT / name).read_text())


def kalman_seeds():
    groups = defaultdict(lambda: [0, 0, 0])
    with (OUT / 'fusion-paired-scenes.csv').open() as source:
        for row in csv.DictReader(source):
            seed = int(row['seed'])
            for scenario in (row['scenario'], 'all'):
                totals = groups[scenario, seed]
                for index, key in enumerate(('correct_0','correct_1','targets')):
                    totals[index] += int(row[key])
    result = defaultdict(list)
    for (scenario, seed), totals in sorted(groups.items()):
        result[FUSION_DEEP.get(scenario, 'Tất cả')].append([seed, *totals])
    return result


def index_cases(review):
    keep = ('id','reference','scenario_label','messages','duration_minutes','hint_priority',
            'hint_class','priority','counts','errors','improved','worsened')
    return {case['id']:{key:case[key] for key in keep} for case in review['cases']}


def main():
    deep = read('deep-ablation.json')
    ais = read('real-ais.json')
    chain = read('chain-ablation.json')
    robust = read('ais-robustness.json')
    transfer = read('gfw-transfer.json')
    sar = read('sar-tile-4048.json')
    proxy = read('proxy-study.json')
    stress = read('proxy-study-challenge-16.json')
    review = comparison_data(proxy, read('review-bank-200.json'))
    challenge = comparison_data(stress, read('study-cases.json'))
    kalman = next(row for row in deep['fusion_paired'] if row['scenario']=='all')
    policies = proxy['policies']
    comparable = {
        'history_given_clean_400':'Đổi từ tốc độ sang quỹ đạo · học sạch · 400',
        'history_given_mixed_400':'Đổi từ tốc độ sang quỹ đạo · học hỗn hợp · 400',
        'mix_given_history_400':'Đổi từ học sạch sang học hỗn hợp · quỹ đạo · 400',
        'mix_given_speed_400':'Đổi từ học sạch sang học hỗn hợp · tốc độ · 400',
        'volume_clean_48_400':'Thêm dữ liệu sạch · 48 lên 400',
        'volume_mixed_48_400':'Thêm dữ liệu hỗn hợp · 48 lên 400',
        'volume_clean_400_800':'Thêm dữ liệu sạch · 400 lên 800',
        'volume_mixed_400_800':'Thêm dữ liệu hỗn hợp · 400 lên 800',
    }
    contrast = next(row for row in deep['behavior_contrasts']
                    if (row['scenario'],row['contrast'])==('overlap','mix_given_history_400'))
    gfw_9 = transfer['suites']['9']
    gfw_5 = transfer['suites']['5']
    payload = {
        'source':SOURCE,
        'seeds':len(deep['seeds']),
        'kalman':{key:kalman[key] for key in ('correct_0','correct_1','targets','scenes','only_linear','only_kalman')},
        'ais':{key:ais['vessel_held_out'][key]['macro_f1'] for key in ('speed_snapshot','speed_history','history')},
        'ais_ci':ais['vessel_held_out']['paired_vessel_bootstrap']['macro_f1_delta_ci'],
        'review':{
            'cases':proxy['unique_cases'],'rules':len(policies),'sessions':proxy['sessions'],
            'human_responses':proxy['human_survey_responses'],'browser_decisions':proxy['browser_decisions'],
            'positive_pairs':sum(policy['control']['positive'] for policy in policies),
            'missed':[sum(p[c]['missed'] for p in policies) for c in ('control','ai')],
            'false_flags':[sum(p[c]['false_flags'] for p in policies) for c in ('control','ai')],
            **proxy_comparison(proxy),
            'case_details':{**index_cases(review), **index_cases(challenge)},
            'examples':[review['default_case'],*review['exception_cases']],
        },
        'clicks':{
            'pairs':proxy['browser_click_time_ms']['delta']['n'],
            'medians':[proxy['browser_click_time_ms'][c]['median_ms'] for c in ('control','ai')],
            'paired_delta':proxy['browser_click_time_ms']['delta']['median_ms'],
        },
        'tables':{
            'kalman':fusion_deep_rows(deep),'size':size_deep_rows(deep),'size_gate':gate_deep_rows(deep),
            'behavior':behavior_deep_rows(deep),'chain':chain_rows(chain),'chain_misses':chain_miss_rows(chain),
            'denmark':external_rows(ais),'robustness':robustness_rows(robust),'gfw':transfer_rows(transfer),
            'rules':proxy_rows(proxy),'timing':proxy_time_rows(proxy),'review_groups':comparison_group_rows(review),
            'sar_tile':tile_rows(sar),'sar_scenes':sar_rows(sar),
            'limits':[['Phần cần kiểm chứng','Giới hạn đã quan sát','Phép thử tiếp theo'],*FUTURE],
        },
        'kalman_seeds':kalman_seeds(),
        'behavior_seeds':[
            [row['seed'],TRACK_DEEP[row['scenario']],MODEL_DEEP[row['model']],row['macro_f1'],
             *(row['class_f1'][label] for label in ('cau','keo_luoi','neo_dau','qua_canh')),row['review_missed'],row['review_false_flags']]
            for row in deep['behavior']
        ],
        'behavior_contrasts':{
            TRACK_DEEP[scenario]:[
                [comparable[name], row['mean'], *row['ci_95'], row['positive_seeds'],row['negative_seeds']]
                for row in deep['behavior_contrasts'] if row['scenario']==scenario
                for name in [row['contrast']]
            ] for scenario in TRACK_DEEP
        },
        'behavior_highlight':contrast['mean'],
        'duration':robust['duration'],
        'gfw_9':{key:gfw_9[key] for key in ('windows','vessels','positive')},
        'gfw_5':{key:gfw_5[key] for key in ('windows','vessels','positive')},
    }
    (OUT / 'streamlit-summary.json').write_text(
        json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(',', ':')) + '\n'
    )
    print(f"Exported {len(payload['tables'])} tables, {len(payload['behavior_seeds'])} training rows "
          f"and {len(payload['review']['case_details'])} individual review cases.")


if __name__=='__main__':
    main()
