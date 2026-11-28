"""Validate and aggregate paired SonarNet trials using independently stored case truth."""
import argparse
from collections import Counter
from hashlib import file_digest
import json
from pathlib import Path
from statistics import median
from datetime import datetime
import re

LAYOUTS = ((('A','control'),('B','ai')), (('B','ai'),('A','control')),
           (('A','ai'),('B','control')), (('B','control'),('A','ai')))
EXPERIENCE = {'maritime','sar_ais','student','other'}
EXPERT = {'maritime','sar_ais'}
DECISIONS = {'priority','not_priority','insufficient'}


def summarize(payload, cases, checksum, *, test=False):
    if payload.get('schema') != 1 or payload.get('bank_sha256') != checksum:
        raise ValueError('Phiếu không thuộc phiên bản ca thử hiện tại.')
    person = payload['participant']
    if payload.get('qa_fixture') and not test:
        raise ValueError('Phiếu tự động chỉ dùng để kiểm tra kỹ thuật.')
    if person['consent'] is not True or person['experience'] not in EXPERIENCE:
        raise ValueError('Thiếu sự đồng ý hoặc nhóm chuyên môn.')
    code = person['code']
    if not re.fullmatch(r'R\d{2,4}',code) or int(code[1:]) < 1:
        raise ValueError('Mã người rà không hợp lệ.')
    layout = (int(code[1:])-1)%len(LAYOUTS)
    if type(payload['layout']) is not int or payload['layout']!=layout+1:
        raise ValueError('Phiếu không khớp lượt phân công.')
    started = datetime.fromisoformat(payload['started_at'])
    finished = datetime.fromisoformat(payload['finished_at'])
    if not started.tzinfo or not finished.tzinfo or finished <= started:
        raise ValueError('Mốc thời gian của phiếu không hợp lệ.')
    responses = payload['responses']
    if len(responses)!=16 or {r['case_id'] for r in responses} != cases.keys():
        raise ValueError('Cần đủ 16 ca khác nhau.')
    summary = {}
    total_time = 0
    for index,(pack,condition) in enumerate(LAYOUTS[layout],1):
        selected=responses[(index-1)*8:index*8]
        counts = Counter()
        seconds = []
        for row in selected:
            case = cases[row['case_id']]
            if (row['block'],row['pack'],row['condition']) != (index,pack,condition) or case['pack']!=pack:
                raise ValueError('Ca không khớp lượt hoặc điều kiện phân công.')
            duration = row['time_ms']
            switches = row['tab_hidden_events']
            decision = row['decision']
            if (type(duration) is not int or duration<0 or type(switches) is not int
                    or switches<0 or decision not in DECISIONS):
                raise ValueError('Thời lượng hoặc lựa chọn không hợp lệ.')
            total_time+=duration
            if switches==0:
                seconds.append(duration/1000)
            counts['missed']+=int(case['priority'] and decision!='priority')
            counts['false_flags']+=int(not case['priority'] and decision=='priority')
            counts['insufficient']+=int(decision=='insufficient')
            counts['positive']+=int(case['priority'])
            counts['timing_excluded']+=int(switches>0)
        summary[condition]=dict(median_time_s=median(seconds) if seconds else None,n=8,**dict(counts))
    if total_time > (finished-started).total_seconds()*1000+1000:
        raise ValueError('Tổng thời lượng từng ca vượt thời lượng phiếu.')
    control,ai=summary['control'],summary['ai']
    delta_time=None
    if all(v['median_time_s'] is not None for v in (control,ai)):
        delta_time=round(ai['median_time_s']-control['median_time_s'],3)
    return {'code':code,'experience':person['experience'],'layout':layout+1,**summary,
            'delta_ai_minus_control_seconds':delta_time,
            'delta_ai_minus_control_missed':ai['missed']-control['missed']}


def aggregate(rows):
    experts=[row for row in rows if row['experience'] in EXPERT]
    pilots=[row for row in rows if row['experience'] not in EXPERT]
    result={}
    for name,group in (('specialists_self_reported',experts),('other_pilot',pilots)):
        paired=[row['delta_ai_minus_control_seconds'] for row in group
                if row['delta_ai_minus_control_seconds'] is not None]
        sides={}
        for condition in ('control','ai'):
            sides[condition]={key:sum(row[condition][key] for row in group)
                              for key in ('n','positive','missed','false_flags','insufficient','timing_excluded')}
        result[name]=dict(n=len(group),n_timing_pairs=len(paired),
            median_paired_delta_seconds=median(paired) if paired else None,**sides)
    return result


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('files',nargs='*',type=Path)
    cli.add_argument('--cases',type=Path,required=True)
    cli.add_argument('--output',type=Path,required=True)
    cli.add_argument('--test-fixture',action='store_true',help='Testing only, excluded from competition evidence')
    args=cli.parse_args()
    if args.test_fixture and not args.output.name.startswith('qa-'):
        cli.error('Kết quả kiểm thử tự động cần tên tệp bắt đầu bằng qa-.')
    with args.cases.open('rb') as stream:
        checksum=file_digest(stream,'sha256').hexdigest()
    cases={r['id']:r for r in json.loads(args.cases.read_text())}
    assert len(cases)==16
    rows=[summarize(json.loads(path.read_text()),cases,checksum,test=args.test_fixture) for path in args.files]
    if len(rows)!=len({r['code'] for r in rows}):
        cli.error('Có trùng mã người rà.')
    report=dict(version=1,bank_sha256=checksum,qa_fixture_only=args.test_fixture,
                measures='Misses count insufficient evidence on a positive case. Timing drops hidden-tab trials.',
                groups=aggregate(rows),paired=rows)
    args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')


if __name__=='__main__':
    main()
