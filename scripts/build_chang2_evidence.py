"""Build the Vietnamese report, web evidence and reproducibility bundle."""
from collections import Counter, defaultdict
from hashlib import file_digest
from html import escape
import json
from pathlib import Path
from statistics import mean, stdev
from xml.sax.saxutils import escape as markup_escape
from zipfile import ZIP_DEFLATED, ZipFile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                                PageBreak, Image)

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/final/chang2'
WEB=ROOT/'web/chang2'
PAGE='https://hoang-nguyenthe.github.io/sonarnet-vn/chang2/'
SOURCE='https://github.com/hoang-nguyenthe/sonarnet-vn/tree/chang-2'
REPORT='SonarNet_Bao_cao_cai_tien_Chang2.pdf'
ZIP='SonarNet_Minh_chung_Chang2.zip'
SCENARIOS={'clean':'Đủ bản tin','gaps':'Mất bản tin','short_noisy':'Cửa sổ ngắn','overlap':'Tín hiệu chồng lấn'}
MODELS={
    'snapshot':'SOG mới nhất · 400',
    'history_limited_training':'Quỹ đạo sạch · 48',
    'history_full':'Quỹ đạo sạch · 400',
    'history_augmented_matched':'Quỹ đạo có nhiễu · 400',
    'history_augmented':'Sạch và nhiễu · 800',
}
FUSION={'mixed_quality':'AIS hỗn hợp','near_crossing':'Tàu cắt nhau',
        'position_bias':'Lệch vị trí','size_noise':'Nhiễu kích thước'}


def fst(value,places=3):
    return f'{value:.{places}f}'.replace('.',',')


def count(n):
    return f'{n:,}'.replace(',','.')


def checksum(path):
    with path.open('rb') as f:
        return file_digest(f,'sha256').hexdigest()


def metrics(raw,study):
    groups=defaultdict(list)
    for item in raw['behavior']:
        groups[item['scenario'],item['model']].append(item)
    behavior={}
    for key, rows in groups.items():
        values=[r['macro_f1'] for r in rows]
        behavior[key]=dict(mean=mean(values),sd=stdev(values),minimum=min(values),maximum=max(values),
                    misses=sum(r['review_missed'] for r in rows),false_flags=sum(r['review_false_flags'] for r in rows),
                    positives=sum(r['review_targets'] for r in rows))
    fusion=defaultdict(dict)
    keys=('n','id_correct','id_wrong','id_abstained','valid_declared_pairs','mismatches_on_valid_pairs',
          'mod_mismatch_true','mod_mismatch_missed','mod_mismatch_false','downstream_blocked')
    for scenario in ('all',*FUSION):
        for k,s in ((False,False),(False,True),(True,False),(True,True)):
            selection=[r for r in raw['fusion'] if r['kalman']==k and r['size_check']==s
                       and (scenario=='all' or r['scenario']==scenario)]
            fusion[scenario][k,s]={key:sum(row[key] for row in selection) for key in keys}
    return behavior,fusion,study['groups']


def figure(behavior):
    fig,ax=plt.subplots(figsize=(9,3.65),layout='constrained')
    fig.patch.set_facecolor('#f9fcfc')
    ax.set_facecolor('#f9fcfc')
    lines=[
        ('snapshot','SOG mới nhất · 400','#79654c','o'),
        ('history_full','Quỹ đạo sạch · 400','#bb5639','s'),
        ('history_augmented_matched','Quỹ đạo có nhiễu · 400','#00786b','D'),
    ]
    for model,label,color,marker in lines:
        ax.errorbar(range(4),[behavior[s,model]['mean'] for s in SCENARIOS],
                    yerr=[behavior[s,model]['sd'] for s in SCENARIOS],
                    marker=marker,capsize=3,label=label,color=color,linewidth=2)
    ax.set(xticks=range(4),xticklabels=SCENARIOS.values(),ylim=(.12,1.055),ylabel='Macro-F1 (4 lớp)')
    ax.grid(axis='y',alpha=.24)
    ax.spines[['top','right']].set_visible(False)
    ax.legend(loc='lower left',ncols=1,frameon=False,fontsize=9)
    fig.savefig(WEB/'behavior.png',dpi=145,facecolor=fig.get_facecolor())
    plt.close(fig)


def label(k,s):
    return ('Kalman' if k else 'Tuyến tính')+' · '+('có' if s else 'tắt')+' kích thước'


def external_rows(external):
    frozen = external['synthetic_only']
    held = external['vessel_held_out']
    rows = [['Cấu hình', 'Macro-F1', 'Recall', 'Precision', 'Bỏ sót', 'Cờ nhầm']]
    for label, group in [('Chỉ học mô phỏng · 5 seed', frozen),
                         ('Học AIS · tốc độ gần nhất', [held['speed_snapshot']]),
                         ('Học AIS · chuỗi tốc độ', [held['speed_history']]),
                         ('Học AIS · toàn quỹ đạo', [held['history']])]:
        scores = [fst(mean(item[key] for item in group)) for key in ('macro_f1','recall','precision')]
        errors = [str(group[0][key]) if len(group)==1 else
                  f'{min(item[key] for item in group)}–{max(item[key] for item in group)}'
                  for key in ('fn','fp')]
        rows.append([label, *scores, *errors])
    return rows


def proxy_rows(proxy):
    return [['Quy tắc mô phỏng', 'Bỏ sót không / có AI', 'Cờ nhầm không / có AI',
             'Chưa đủ dữ liệu không / có AI']] + [
        [row['name'], *[f"{row['control'][key]} / {row['ai'][key]}"
                       for key in ('missed','false_flags','insufficient')]]
        for row in proxy['policies']
    ]


ROBUST_MODELS={
    'xgboost':'XGBoost gốc',
    'augmented':'Học thêm chuỗi thiếu',
    'quality_routed':'Chọn theo chất lượng',
    'nested_macro':'Chọn mô hình theo F1',
    'nested_recall':'Chọn mô hình theo recall',
}
ROBUST_SCENARIOS={'clean':'Dữ liệu gốc','gap':'Khuyết 3 mốc liền','half':'Khuyết khoảng 1/2 mốc'}
TRANSFER_MODELS={
    'synthetic':'Chỉ học mô phỏng · 5 seed',
    'denmark_to_gfw':'Học ở Đan Mạch',
    'denmark_augmented_to_gfw':'Đan Mạch + chuỗi thiếu',
    'denmark_aligned':'Tính lại tốc độ và hướng từ tọa độ',
    'denmark_aligned_balanced':'Tính lại và cân bằng nhãn học',
    'denmark_native_balanced':'Kênh gốc và cân bằng nhãn học',
    'gfw_held_gear_multisource':'Học đa nguồn, giữ riêng nhóm nghề',
    'gfw_held_vessel':'Học trên GFW, giữ riêng tàu',
}


def robustness_summary(robust):
    groups=defaultdict(list)
    for row in robust['repeated_results']:
        groups[row['model'],row['scenario']].append(row)
    return groups


def robustness_rows(robust):
    groups=robustness_summary(robust)
    rows=[['Cấu hình',*ROBUST_SCENARIOS.values()]]
    for key,name in ROBUST_MODELS.items():
        results=[groups[key,scenario] for scenario in ROBUST_SCENARIOS]
        rows.append([name,*[f"{fst(mean(r['fn'] for r in vals),1)} / {fst(mean(r['fp'] for r in vals),1)}"
                            for vals in results]])
    return rows


def transfer_rows(transfer):
    base=transfer['suites']['9']['models']
    rows=[['Huấn luyện / cách chấm','Macro-F1','Recall','Precision','Bỏ sót','Cờ nhầm']]
    for key,label in TRANSFER_MODELS.items():
        group=[m for name,m in base.items() if name.startswith('synthetic_only_')] if key=='synthetic' else [base[key]]
        scores=[fst(mean(row[k] for row in group)) for k in ('macro_f1','recall','precision')]
        errors=[fst(mean(row[k] for row in group),1 if len(group)>1 else 0) for k in ('fn','fp')]
        rows.append([label,*scores,*errors])
    return rows


def robustness_plot(robust):
    groups=robustness_summary(robust)
    fig,ax=plt.subplots(figsize=(9.0,3.4))
    x=range(len(ROBUST_SCENARIOS))
    styles=[('xgboost','#5b7480'),('augmented','#b06030'),('quality_routed','#00786e')]
    for j,(model,color) in enumerate(styles):
        sample=[[r['fn'] for r in groups[model,case]] for case in ROBUST_SCENARIOS]
        heights=[mean(vals) for vals in sample]
        rect=ax.bar([i+(j-1)*.24 for i in x],heights,width=.21,yerr=[stdev(vals) for vals in sample],
                    capsize=3,color=color,label=ROBUST_MODELS[model])
        ax.bar_label(rect,labels=[fst(value,1) for value in heights],label_type='center',
                     color='white',fontsize=9,fontweight='bold')
    ax.set(xticks=list(x),xticklabels=list(ROBUST_SCENARIOS.values()),
           ylabel='Ca khai thác bỏ sót',ylim=(0,83))
    ax.spines[['top','right']].set_visible(False)
    ax.set_axisbelow(True)
    ax.grid(axis='y',alpha=.2)
    ax.legend(loc='upper center',bbox_to_anchor=(.5,1.18),ncol=3,frameon=False,fontsize=9)
    fig.savefig(WEB/'robustness.png',dpi=145,bbox_inches='tight',facecolor='white')
    plt.close(fig)


SAR_NAMES={
    'reference_ls_ssdd':'YOLO học LS-SSDD',
    'adapted_slc_vv':'YOLO học SLC VV',
    'guard_ring_cfar':'CFAR vòng nền',
    'review-budget':'Giới hạn danh sách rà',
    'coastal-budget':'Giới hạn có ưu tiên ven bờ',
}
FUTURE=[
    ('Nhãn AIS ở Việt Nam',
     'Mô hình học Đan Mạch đạt F1 0,415 khi chuyển sang GFW. Tập Đan Mạch chỉ có hai trạng thái.',
     'Thu quỹ đạo có nhật ký hoặc quan sát độc lập, hai người gán nhãn bốn lớp. Giữ riêng tàu, ngày và vùng chấm. Báo macro-F1 và recall từng lớp, kể cả ca chuyển trạng thái.'),
    ('Mất bản tin',
     'Khi mất nửa số mốc, tăng cường làm giảm bỏ sót và tăng cờ nhầm.',
     'Kiểm tra trên mất tín hiệu tự nhiên. Đo recall, cờ nhầm và tỷ lệ trả “chưa đủ dữ liệu” theo số mốc và khoảng trống.'),
    ('Hộp SAR và khối lượng rà',
     'Một dự đoán có thể đúng vùng tàu nhưng IoU thấp hoặc lặp trên cùng một nhãn.',
     'Giữ IoU 0,50 làm chuẩn. Đo thêm sai số tâm theo mét và phân loại hộp trùng, sai kích thước, điểm ngoài nhãn. Chọn ngưỡng và lọc trùng trên cảnh phát triển riêng.'),
    ('Ghép SAR–AIS và kích thước',
     'Bật Kalman giảm lỗi ghép trong mô phỏng. Nhiễu kích thước vẫn tạo cờ nhầm.',
     'Đối chiếu cảnh SAR và AIS/VMS đồng thời với nhãn tàu độc lập. Báo ghép sai, từ chối, sai số vị trí và cờ kích thước theo khoảng cách tới bờ.'),
    ('Thời gian ra quyết định',
     'Thời gian 32 phiên phản ánh thao tác bấm của trình duyệt. Chưa có phép đo thời gian suy nghĩ của người rà.',
     'Đối chiếu hai giao diện trên cùng ca. Nếu cần kiểm chứng trên người, dùng bài thử chéo A/B và báo thời gian cùng bỏ sót, cờ nhầm.'),
]


def sar_rows(sar):
    titles={'diagnostic':'3 cảnh đối chiếu','north_sea':'Cảnh Biển Bắc giữ riêng'}
    return [['Tập ảnh','Phương pháp','Khớp / tổng','Bỏ sót','Ngoài cặp khớp','Precision']]+[
        [titles[row['cohort']],SAR_NAMES[row['method']],
         f"{row['true_positive']}/{row['n_ground_truth']}",
         row['n_ground_truth']-row['true_positive'],row['false_positive'],
         fst(row['precision'])] for row in sar['comparison']
    ]


def tile_rows(sar):
    reasons={'matched':'Được ghép một–một','duplicate':'Hộp trùng trên nhãn đã ghép',
             'below_iou':'Chồng lên nhãn dưới ngưỡng','no_overlap':'Không chồng nhãn nào'}
    return [['Mô hình','Hộp theo thứ tự điểm','IoU lớn nhất','Kết quả']]+[
        [SAR_NAMES[model],row['index']+1,fst(max(row['overlap_with_label'])),reasons[row['status']]]
        for model,data in sar['tile']['models'].items()
        for row in data['predictions'] if row['status'] in reasons
    ]


FUSION_DEEP = {
    'mixed_quality':'AIS hỗn hợp', 'near_crossing':'Hai tàu sát nhau',
    'keep_two_crossing_tracks_when_separated':'Tàu cắt hướng, còn tách vị trí',
    'unlabeled_clutter_near_track':'Điểm nhiễu cạnh tàu',
    'sparse_one_sided':'Bản tin một phía',
    'position_bias':'Lệch vị trí',
    'position_bias_beyond_guard':'Lệch vượt vùng bảo vệ',
    'size_noise':'Nhiễu đo kích thước',
}
SIZE_DEEP = {'valid':'Khai báo đúng','plus_30':'+30%','plus_60':'+60%','plus_80':'+80%',
             'plus_125':'+125%','minus_45':'−45%','missing':'Thiếu khai báo'}
TRACK_DEEP = {**SCENARIOS,'block_gap':'Mất liên tục'}
MODEL_DEEP = {
    'speed_clean_400':'Tốc độ · sạch · 400', 'speed_mixed_400':'Tốc độ · hỗn hợp · 400',
    'history_clean_48':'Quỹ đạo · sạch · 48','history_mixed_48':'Quỹ đạo · hỗn hợp · 48',
    'history_clean_400':'Quỹ đạo · sạch · 400','history_mixed_400':'Quỹ đạo · hỗn hợp · 400',
    'history_clean_800':'Quỹ đạo · sạch · 800','history_mixed_800':'Quỹ đạo · hỗn hợp · 800',
}


def pp(value):
    return fst(100*value,2)


def fusion_deep_rows(deep):
    rows = [['Kịch bản','Tuyến tính đúng','Kalman đúng','Chỉ tuyến tính đúng',
             'Chỉ Kalman đúng','Ghép sai¹']]
    for r in deep['fusion_paired']:
        rows.append([FUSION_DEEP.get(r['scenario'],'Tất cả'),count(r['correct_0']),
                     count(r['correct_1']),count(r['only_linear']),count(r['only_kalman']),
                     f"{r['wrong_0']} → {r['wrong_1']}"])
    return rows


def size_deep_rows(deep):
    counts = defaultdict(Counter)
    for r in deep['paired_size_noise']:
        counts[r['category']].update({k:r[k] for k in ('n','flagged_light','flagged_heavy',
                                                       'only_light','only_heavy')})
    rows=[['Chiều dài khai báo','Cặp đúng chung','Cờ · nhiễu 9%','Cờ · nhiễu 33%',
           'Chỉ cờ 9%','Chỉ cờ 33%']]
    for key,wording in SIZE_DEEP.items():
        c=counts[key]
        rows.append([wording,*[count(c[k]) for k in ('n','flagged_light','flagged_heavy',
                                                     'only_light','only_heavy')]])
    return rows


def gate_deep_rows(deep):
    groups = defaultdict(Counter)
    keys=('passed_clean_truth','passed_bad_size_truth','passed_missing_truth','passed_wrong_identity')
    for r in deep['fusion_joint']:
        groups[r['kalman'],r['size_check']].update({k:r[k] for k in keys})
    return [['Cấu hình','Đúng tàu + khai đúng','Đúng tàu + khai lệch','Thiếu chiều dài','Sai danh tính¹']]+[
        [label(k,t),*[count(groups[k,t][x]) for x in keys]]
        for k,t in ((False,False),(False,True),(True,False),(True,True))
    ]


def behavior_deep_rows(deep):
    sets=defaultdict(list)
    for r in deep['behavior']:
        sets[r['model'],r['scenario']].append(r['macro_f1'])
    return [['Đầu vào · tập học · số mẫu',*TRACK_DEEP.values()]]+[
        [display,*[fst(mean(sets[model,key])) for key in TRACK_DEEP]]
        for model,display in MODEL_DEEP.items()
    ]


def measured_contrast(deep, scenario, contrast):
    return next(r for r in deep['behavior_contrasts'] if (r['scenario'],r['contrast'])==(scenario,contrast))


CHAIN_PRIMARY = (
    (False,True,'mixed_training'), (True,False,'mixed_training'),
    (True,True,'without_behavior'), (True,True,'clean_training'),
    (True,True,'mixed_training'),
)
CHAIN_BEHAVIOR = {'without_behavior':'Duyệt tất cả cặp đủ điều kiện',
                  'clean_training':'Hành vi · học sạch',
                  'mixed_training':'Hành vi · học hỗn hợp'}


def chain_lookup(chain):
    return {(r['kalman'],r['size_check'],r['behavior']):r
            for r in chain['aggregate'] if r['scenario']=='all'}


def chain_rows(chain, keys=None):
    lookup=chain_lookup(chain)
    return [['Ước lượng / kích thước / hành vi','Ca đưa vào rà','Đúng mục tiêu',
             'Cờ không đúng','Bỏ sót','Recall (%)']]+[
        [f"{label(k,z)} · {CHAIN_BEHAVIOR[m]}", *[count(r[v]) for v in
         ('reviewed','hits','false_priorities','misses')],pp(r['recall'])]
        for k,z,m in (keys or tuple(lookup)) for r in [lookup[k,z,m]]
    ]


def chain_miss_rows(chain):
    data=[row for row in chain['aggregate'] if row['kalman'] and row['size_check']
          and row['behavior']=='mixed_training']
    return [['Kịch bản','Chưa ghép','Ghép sai','Chặn do chiều dài','Hành vi chưa ưu tiên']]+[
        [FUSION_DEEP.get(r['scenario'],'Tất cả'),r['miss_unmatched'],r['miss_wrong_id'],
         r['miss_size_gate'],r['miss_behavior']] for r in data
    ]


def proxy_comparison(proxy):
    pairs=[row for policy in proxy['policies'] for row in policy['per_case']]
    a=lambda row: row['control']=='priority'
    b=lambda row: row['ai']=='priority'
    return {
        'rescued':sum(row['priority'] and not a(row) and b(row) for row in pairs),
        'new_misses':sum(row['priority'] and a(row) and not b(row) for row in pairs),
        'resolved_flags':sum(not row['priority'] and a(row) and not b(row) for row in pairs),
        'new_flags':sum(not row['priority'] and not a(row) and b(row) for row in pairs),
        'missed':[sum(p[k]['missed'] for p in proxy['policies']) for k in ('control','ai')],
        'flags':[sum(p[k]['false_flags'] for p in proxy['policies']) for k in ('control','ai')],
        'positive_pairs':sum(row['priority'] for row in pairs),
        'negative_pairs':sum(not row['priority'] for row in pairs),
        'example_rescues':sum(row['id']=='Q16' and not a(row) and b(row) for row in pairs),
    }


def proxy_time_rows(proxy):
    data=proxy['browser_click_time_ms']
    return [['Thao tác tự động','Không gợi ý','Có gợi ý'],
            ['Trung vị',*[f"{data[k]['median_ms']:g} ms" for k in ('control','ai')]],
            ['Khoảng quan sát',*[f"{data[k]['min_ms']}–{data[k]['max_ms']} ms" for k in ('control','ai')]]]


def pdf_report(external, proxy, robust, transfer, sar, deep, chain):
    base=Path('/System/Library/Fonts/Supplemental')
    pdfmetrics.registerFont(TTFont('ArabicFreeNormal',str(base/'Arial.ttf')))
    pdfmetrics.registerFont(TTFont('ArabicFreeBold',str(base/'Arial Bold.ttf')))
    pdfmetrics.registerFontFamily('ArabicFreeNormal',normal='ArabicFreeNormal',bold='ArabicFreeBold')
    navy=colors.HexColor('#102e3e')
    teal=colors.HexColor('#00675c')
    line=colors.HexColor('#d5e5e5')
    body=ParagraphStyle('body',fontName='ArabicFreeNormal',fontSize=11,leading=16,textColor=navy,spaceAfter=9)
    heading=ParagraphStyle('heading',parent=body,fontName='ArabicFreeBold',fontSize=17,leading=22,spaceBefore=10,spaceAfter=9)
    title=ParagraphStyle('title',parent=heading,fontSize=29,leading=34,spaceBefore=7,spaceAfter=13)
    caption=ParagraphStyle('caption',parent=body,fontSize=9.3,leading=13,textColor=colors.HexColor('#425e68'))
    cell=ParagraphStyle('cell',parent=body,fontSize=9.3,leading=12,spaceAfter=0)
    cell_bold=ParagraphStyle('cell_bold',parent=cell,fontName='ArabicFreeBold',textColor=teal)
    story=[]
    def p(text, style=body):
        story.append(Paragraph(text,style))
    def h(text):
        p(text,heading)
    def page(name, subtitle):
        p(name,title)
        p(subtitle,caption)
    def table(rows,widths):
        converted=[[Paragraph(markup_escape(str(x)),cell_bold if idx==0 else cell)
                    for x in row] for idx,row in enumerate(rows)]
        tbl=Table(converted,colWidths=widths,hAlign='LEFT',repeatRows=1)
        tbl.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e5f3ef')),
          ('LINEBELOW',(0,0),(-1,-1),.35,line),('VALIGN',(0,0),(-1,-1),'TOP'),
          ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),
          ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f5f9f9')])]))
        story.extend([tbl,Spacer(1,8)])
    total=deep['fusion_paired'][0]
    headline=measured_contrast(deep,'overlap','mix_given_history_400')
    coverage=external['coverage']
    page('Kiểm chứng mô-đun hành vi','SONARNET VIỆT NAM  ·  CHUNG KẾT AI 2026  ·  CHẶNG 2  ·  ĐỀ PHIÊN BẢN 1')
    p('Một nhận định hành vi đi qua ba bước có thể mắc lỗi riêng. SonarNet phải ghép đúng tàu, nhìn được kích thước đủ tin cậy và đọc được tín hiệu từ chuỗi AIS. Báo cáo kiểm tra từng bước trên cùng ca và kiểm tra mô hình hành vi trên hai nguồn AIS công khai.')
    table([['Yêu cầu của BTC','Thiết kế đối chứng','Minh chứng'],
           ['Tách Kalman',f"Bật/tắt trên {count(total['scenes'])} cảnh mô phỏng, cùng dữ liệu và luật ghép.",
            f"{count(total['correct_0'])} → {count(total['correct_1'])} cặp đúng. Bật Kalman giúp đúng ở {count(total['only_kalman'])} ca và làm mất {count(total['only_linear'])} ca đúng."],
           ['Tách kích thước','Bật/tắt sau khi đã ghép. Chấm theo mức lệch khai báo và nhiễu đo.',
            'Bảng độ nhạy và số cặp được qua bước kiểm tra kích thước.'],
           ['Tách dữ liệu hành vi','Đổi đầu vào, chất lượng và lượng dữ liệu trên cùng mẫu chấm.',
            f"Kiểm thử 10 seed. Khi tín hiệu chồng lấn và đủ 400 mẫu học, macro-F1 tăng {fst(headline['mean'])} khi đưa chuỗi nhiễu vào tập học."],
           ['Khảo sát chuyên viên','Đối chiếu giao diện trên cùng ca. Chấm bỏ sót và cờ nhầm theo quy tắc mô phỏng.',
            f"{proxy['sessions']} phiên trình duyệt tự động. Chưa đo thời gian quyết định của chuyên viên."],
          ],[110,196,195])
    h('Kiểm tra tác động đến quyết định ưu tiên')
    p(f"Trên {count(chain['scenes_per_scenario_seed']*len(chain['scenarios'])*len(chain['seeds']))} cảnh kiểm tra bổ sung, 12 tổ hợp ghép, kích thước và hành vi cho thấy đánh đổi giữa lượng hồ sơ cần rà và ca bị bỏ sót. Xem trang 5.")
    h('Đối chứng bằng dữ liệu AIS có nhãn')
    p(f"Chấm nhị phân trên {count(coverage['scored_windows'])} cửa sổ AIS Đan Mạch và {count(transfer['suites']['9']['windows'])} cửa sổ của Global Fishing Watch. Đối chứng này giúp đo khả năng chuyển nguồn. SonarNet còn thiếu nhãn bốn lớp xác minh ở Việt Nam. Phần thao tác dựa trên đối chiếu giao diện và chạy tự động.")
    p(f'<link href="{PAGE}evidence.html#ablation" color="#00675c">Mở bảng đối chứng đầy đủ</link>  ·  <link href="{PAGE}compare.html" color="#00675c">So sánh hai giao diện</link>  ·  <link href="{SOURCE}" color="#00675c">Mã nguồn</link>')
    story.append(PageBreak())

    page('Kalman có cải thiện ghép tàu?', 'THỬ GHÉP CẶP  ·  8 KỊCH BẢN  ·  10 SEED')
    p(f"Mỗi seed sinh 90 cảnh mỗi kịch bản. Hai cấu hình dùng đúng cùng bản tin AIS, phát hiện SAR, luật từ chối và ngưỡng. Mỗi dòng chấm 3.600 mục tiêu, có thêm điểm nhiễu trong kịch bản riêng. Kích thước chỉ xem sau bước ghép.")
    table(fusion_deep_rows(deep),[153,73,61,75,70,69])
    p('¹ Ghép sai gồm nhầm tàu và gán AIS vào điểm nhiễu. Các cột chỉ tuyến tính đúng hoặc chỉ Kalman đúng lấy từ cùng từng mục tiêu. Ca được cả hai ghép đúng chỉ tính một lần trong cột của từng cấu hình.',caption)
    ci=total['delta_correct_rate']['ci_95']
    p(f"Trên {count(total['targets'])} mục tiêu, chênh lệch tỷ lệ ghép đúng là {pp(total['delta_correct_rate']['mean'])} điểm phần trăm. Khoảng bootstrap 95% theo seed là [{pp(ci[0])}, {pp(ci[1])}]. Khoảng này mô tả độ ổn định trên trình sinh ca thử.")
    sparse=next(r for r in deep['fusion_paired'] if r['scenario']=='sparse_one_sided')
    crossing=next(r for r in deep['fusion_paired'] if r['scenario']=='keep_two_crossing_tracks_when_separated')
    p(f"<b>Kết quả phụ thuộc kịch bản.</b> Bản tin một phía có {count(sparse['correct_0'])} → {count(sparse['correct_1'])} cặp đúng. Khi tàu cắt hướng nhưng còn tách vị trí, số cặp đúng giảm {count(crossing['correct_0'])} → {count(crossing['correct_1'])}. Ngưỡng bất định và lý do từ chối cần được kiểm tra riêng theo tình huống.")
    p(f'<link href="{PAGE}fusion-paired-scenes.csv" color="#00675c">Tải kết quả theo từng cảnh</link>',caption)
    story.append(PageBreak())

    page('Kích thước phát hiện được mức lệch nào?', 'CÙNG CẶP GHÉP  ·  7 MỨC KHAI BÁO  ·  HAI MỨC NHIỄU ĐO')
    p('Kiểm kích thước sau khi đã khóa cặp SAR–AIS. Hệ thống đánh cờ khi sai lệch tuyệt đối chia cho chiều dài lớn hơn đạt ít nhất 0,42. Thử sáu mức khai báo có số đo và một tình huống thiếu số đo, với nhiễu độ dài mô phỏng 9% và 33% trên cùng cặp, dùng cùng độ lệch chuẩn hóa cho mỗi phép đo.')
    table(size_deep_rows(deep),[118,79,80,80,72,72])
    p('Tính trên cặp Kalman ghép đúng. Dòng khai báo đúng là số cờ nhầm. Dòng thiếu khai báo ghi số ca được đánh dấu thiếu dữ liệu. Các mức lệch nhẹ có thể nằm dưới ngưỡng dù cặp đã ghép đúng.',caption)
    paired_valid=[r for r in deep['paired_size_noise'] if r['category']=='valid']
    valid_n=sum(r['n'] for r in paired_valid)
    heavy_fp=sum(r['flagged_heavy'] for r in paired_valid)
    light_fp=sum(r['flagged_light'] for r in paired_valid)
    p(f"Trên cùng {count(valid_n)} cặp khai báo đúng, nhiễu đo mạnh làm số cờ nhầm tăng "
      f"{count(light_fp)} → {count(heavy_fp)} ({fst(100*heavy_fp/valid_n,1)}%). "
      "Độ dài radar cần đủ tin cậy để dùng cờ này khi rà.")
    h('Ảnh hưởng lên bước rà tiếp')
    table(gate_deep_rows(deep),[139,94,94,83,91])
    p('Các cột đếm cặp qua bước kiểm theo trạng thái AIS_OK. ¹ Có cả cặp ghép nhầm tàu và cặp gán vào điểm nhiễu. Bật kích thước không thay đổi MMSI đã ghép. Dòng kích thước không xác nhận chiều dài vật lý ngoài hiện trường.',caption)
    p(f'<link href="{PAGE}paired-size-noise.csv" color="#00675c">Đối chứng hai mức nhiễu trên cùng cặp</link>  ·  <link href="{PAGE}size-by-factor.csv" color="#00675c">Chi tiết bật/tắt theo kịch bản</link>',caption)
    story.append(PageBreak())

    page('Dữ liệu nào giúp đọc hành vi?', 'SO SÁNH ĐẦU VÀO, CHẤT LƯỢNG VÀ LƯỢNG DỮ LIỆU HỌC')
    p('Ở mỗi seed có 800 quỹ đạo học độc lập. Dùng các tập con lồng nhau 48, 400 và 800. Phương án hỗn hợp giữ nguyên danh sách quỹ đạo, với 25% sạch và 25% ở mỗi mức nhiễu học. Chấm cùng 240 quỹ đạo riêng mỗi seed ở năm điều kiện.')
    table(behavior_deep_rows(deep),[149,70,67,78,69,68])
    p('Các ô là macro-F1 trung bình qua 10 seed. “Mất liên tục” loại một đoạn 55 mốc trước khi làm thưa phần còn lại. Kiểu nhiễu này không được dùng để huấn luyện.',caption)
    for scenario,text in (('overlap','Tín hiệu chồng lấn'),('block_gap','Mất liên tục')):
        item=measured_contrast(deep,scenario,'mix_given_history_400')
        lo,hi=item['ci_95']
        p(f"<b>{text}.</b> Giữ nguyên 400 quỹ đạo và thêm nhiễu vào tập học cho chênh macro-F1 {fst(item['mean'])}, khoảng bootstrap theo seed [{fst(lo)}, {fst(hi)}]. Bỏ sót {item['miss_before']} → {item['miss_after']} trên 1.200 ca khai thác. Cờ nhầm {item['fp_before']} → {item['fp_after']}.")
    vol_clean=measured_contrast(deep,'overlap','volume_clean_48_400')
    vol_mixed=measured_contrast(deep,'overlap','volume_mixed_48_400')
    p(f"<b>Tăng số mẫu phụ thuộc chất lượng tập học.</b> Trong kịch bản chồng lấn, tăng 48 → 400 quỹ đạo làm macro-F1 đổi {fst(vol_clean['mean'])} nếu học sạch và +{fst(vol_mixed['mean'])} nếu học hỗn hợp. Tệp JSON lưu ma trận nhầm lẫn và F1 từng lớp.")
    p(f'<link href="{PAGE}deep-ablation.json" color="#00675c">Mở các chênh lệch theo cặp và khoảng bất định</link>',caption)
    story.append(PageBreak())

    page('Từ ghép tàu đến quyết định rà','12 TỔ HỢP  ·  10 SEED  ·  CÙNG CẢNH VÀ NHÃN')
    lookup=chain_lookup(chain)
    simulated_scenes=chain['scenes_per_scenario_seed']*len(chain['scenarios'])*len(chain['seeds'])
    chosen=lookup[True,True,'mixed_training']
    p(f"Trong {count(simulated_scenes)} cảnh mới, cùng một quỹ đạo tiềm ẩn tạo bản tin AIS gần giờ chụp và lịch sử hành vi. Chấm {count(chosen['positives'])} mục tiêu cần ưu tiên. Một ca chỉ tính đúng khi được ưu tiên và gắn đúng tàu. Bảng trình bày năm đối chiếu chính cùng số lượng ca phải rà.")
    table(chain_rows(chain,CHAIN_PRIMARY),[171,61,66,69,60,74])
    before=lookup[True,True,'without_behavior']
    clean=lookup[True,True,'clean_training']
    p(f"<b>Khối lượng rà.</b> Khi đã dùng Kalman và kiểm kích thước, thêm hành vi học hỗn hợp đổi số ca đưa vào rà {count(before['reviewed'])} → {count(chosen['reviewed'])}, số cờ không đúng {count(before['false_priorities'])} → {count(chosen['false_priorities'])} và số ca đúng {count(before['hits'])} → {count(chosen['hits'])}. Học hỗn hợp lấy lại {count(chosen['hits']-clean['hits'])} ca đúng so với học sạch.")
    ungated=lookup[True,False,'mixed_training']
    p(f"<b>Đánh đổi của điều kiện kích thước.</b> Dùng kích thước để loại ca ở đầu ra làm số ca đúng giảm từ {count(ungated['hits'])} xuống {count(chosen['hits'])}. Giữ ca thiếu bằng chứng ở một hàng rà riêng là phương án cần thử trước vận hành.")
    h('Ca dương bị bỏ qua ở bước nào?')
    table(chain_miss_rows(chain)[:5],[155,72,72,101,101])
    p('Bảng hiển thị tổng và ba kịch bản đầu. Mỗi ca chỉ thuộc nguyên nhân đầu tiên xảy ra. Phần còn lại, đủ 12 tổ hợp và khoảng bootstrap theo seed có trong dữ liệu. Thử nghiệm bắt đầu từ các phát hiện SAR mô phỏng có sẵn và đo hàng rà giả định, chưa đo người rà hoặc radar ngoài thực địa.',caption)
    p(f'<link href="{PAGE}chain-ablation.json" color="#00675c">Đầy đủ 12 tổ hợp, nguyên nhân bỏ sót và khoảng bootstrap</link>',caption)
    story.append(PageBreak())

    page('Đối chứng bằng AIS thật','ĐAN MẠCH  ·  PHÂN LOẠI NHỊ PHÂN  ·  TÁCH THEO TÀU')
    p(f"Tệp của Song Wu chứa {count(coverage['messages'])} bản ghi AIS có nhãn gán thủ công và {coverage['trips']} mã chuyến phân biệt. Sau lọc và lấy mẫu, chấm {count(coverage['scored_windows'])} cửa sổ dài hai giờ thuộc {coverage['scored_vessels']} tàu, gồm {count(coverage['fishing_windows'])} cửa sổ khai thác và {count(coverage['sailing_windows'])} cửa sổ di chuyển.")
    p('Mô hình bốn lớp đã học mô phỏng được giữ nguyên, gộp câu và kéo lưới thành khai thác. Ba biến thể nhị phân học AIS thật dùng cùng năm lượt chia theo tàu và cùng bộ chấm. Mỗi tàu chỉ xuất hiện trong tập chấm một lần, ngoài tập huấn luyện của lượt đó.')
    table(external_rows(external),[168,68,56,60,76,73])
    p('Dòng đầu báo trung bình chỉ số và khoảng nhỏ nhất–lớn nhất của số lỗi trên 5 seed mô phỏng, cùng tập AIS chấm. Ba dòng sau gộp dự đoán ngoài tập huấn luyện của 5 lượt.',caption)
    held=external['vessel_held_out']
    delta=held['history']['macro_f1']-held['speed_history']['macro_f1']
    ci=held['paired_vessel_bootstrap']['macro_f1_delta_ci']
    h('Giá trị của thông tin quỹ đạo')
    p(f"Thêm đặc trưng hướng và hình học so với chuỗi tốc độ làm macro-F1 đổi {fst(delta)}. Khoảng 95% bootstrap theo tàu [{fst(ci[0])}, {fst(ci[1])}] dùng các dự đoán ngoài tập học. Chênh recall khoảng {fst(held['history']['recall']-held['speed_history']['recall'])}, với khoảng 95% [{fst(held['paired_vessel_bootstrap']['recall_delta_ci'][0])}, {fst(held['paired_vessel_bootstrap']['recall_delta_ci'][1])}].")
    p(f"Khi nhãn trong cửa sổ đồng thuận ít nhất 80%, F1 của toàn quỹ đạo là {fst(held['history_on_stable']['macro_f1'])} (n={count(coverage['stable_windows'])}). Ở các cửa sổ hỗn hợp, F1 là {fst(held['history_on_mixed']['macro_f1'])} (n={count(coverage['mixed_windows'])}). Nhãn do tác giả đọc từ dữ liệu AIS. Nhật ký hoạt động hoặc quan sát trực tiếp sẽ bổ sung một nguồn đối chiếu độc lập.")
    p('Đối chứng này có phạm vi hai trạng thái trên AIS Đan Mạch. Cần nhãn bốn lớp ở Việt Nam và dữ liệu SAR–AIS ghép có đối chứng để xác nhận khả năng chuyển sang sử dụng ngoài thực địa.')
    p(f'<link href="{external["dataset"]}" color="#00675c">Dữ liệu gốc · DOI 10.5281/zenodo.7283281 · CC BY 4.0</link>  ·  <link href="{PAGE}real-ais.json" color="#00675c">Số liệu theo lượt chia</link>',caption)
    story.append(PageBreak())

    comparison=proxy_comparison(proxy)
    page('Cùng một ca AIS, hai cách rà','ĐỐI CHIẾU GIAO DIỆN  ·  QUỸ ĐẠO MÔ PHỎNG')
    p('Hai chế độ giữ cùng dữ liệu AIS, câu hỏi và ba nút lựa chọn. Bên có AI thêm một dòng đề xuất mức ưu tiên và lớp hành vi. Người rà vẫn chọn quyết định.')
    story.append(Image(str(WEB/'review-comparison.png'),width=499,height=250,kind='proportional'))
    p('Ảnh chụp ca Q16 từ trang so sánh. Hai bên giữ nguyên quỹ đạo, tốc độ, thời gian và lựa chọn.',caption)
    table([['Bước rà','Không có gợi ý AI','Có gợi ý AI'],
           ['Bắt đầu','Đọc hai đồ thị rồi tự hình thành giả thuyết.','Đọc đề xuất và lớp dự đoán để có giả thuyết ban đầu.'],
           ['Kiểm tra','Đối chiếu tốc độ, đổi hướng và số bản tin.','Đối chiếu gợi ý với cùng dữ liệu, nhất là khi có mâu thuẫn.'],
           ['Quyết định','Chọn ưu tiên, chưa ưu tiên hoặc chưa đủ dữ liệu.','Giữ ba lựa chọn và quyền quyết định của người rà.']],[102,200,199])
    p(f"Ở Q16, gợi ý câu phù hợp nhãn và giúp {comparison['example_rescues']} trong 8 quy tắc tự động đổi sang đúng ưu tiên. Q02 minh họa nguy cơ bỏ sót khi gợi ý chưa ưu tiên một ca dương. Q08 minh họa nguy cơ cờ nhầm khi gợi ý ưu tiên một ca âm.")
    p(f'<link href="{PAGE}compare.html" color="#00675c">Thử ba tình huống trên hai giao diện</link>',caption)

    story.append(PageBreak())
    page('Ảnh hưởng đến bỏ sót và thao tác','32 PHIÊN TRÌNH DUYỆT TỰ ĐỘNG  ·  8 QUY TẮC GIẢ LẬP')
    p(f"Phát lại {proxy['sessions']} phiên trên giao diện bài thử, ghi {proxy['browser_decisions']} quyết định. Mỗi quy tắc chạy đủ bốn bố trí A/B. Cùng quy tắc và cùng ca chỉ được tính một lần trong mỗi điều kiện.")
    table(proxy_rows(proxy),[151,108,108,134])
    p(f"Bỏ sót giảm {comparison['missed'][0]} → {comparison['missed'][1]} trên {comparison['positive_pairs']} cặp ca dương × quy tắc, gồm {comparison['rescued']} quyết định được sửa và {comparison['new_misses']} bỏ sót mới. Cờ nhầm giảm {comparison['flags'][0]} → {comparison['flags'][1]} trên {comparison['negative_pairs']} cặp ca âm × quy tắc, gồm {comparison['resolved_flags']} cờ được bỏ và {comparison['new_flags']} cờ mới. Các ca được dùng lại giữa các quy tắc.")
    table(proxy_time_rows(proxy),[183,159,159])
    p('<b>Kết luận.</b> Gợi ý cung cấp giả thuyết ngay khi vào ca, có thể giúp người rà bắt đầu từ bước kiểm chứng. Gợi ý sai có thể kéo quyết định sai. Thời gian bảng trên đo từ lúc giao diện mở ca đến khi trình duyệt bấm nút tự động. Thời gian tư duy và tốc độ của chuyên viên chưa được đo.')
    p(f'<link href="{PAGE}proxy-study.json" color="#00675c">Tải dữ liệu chạy tự động theo ca và quy tắc</link>',caption)

    story.append(PageBreak())
    page('Khi bản tin AIS bị thiếu','ĐAN MẠCH  ·  5 LẦN CHIA NHÓM  ·  25 LƯỢT GIỮ RIÊNG TÀU')
    p('Mỗi lần chia đánh giá trên cùng 1.155 cửa sổ khai thác. Hai phép thử giữ nhãn tham chiếu, rồi xóa ba mốc 10 phút liên tiếp hoặc xóa ngẫu nhiên khoảng một nửa các mốc. XGBoost tăng cường chỉ học thêm bản sao làm thưa từ các tàu thuộc tập huấn luyện.')
    story.append(Image(str(WEB/'robustness.png'),width=499,height=182))
    p('Các cột cho biết số bỏ sót trung bình và độ lệch chuẩn trên năm lần chia. Quy tắc chọn chất lượng dùng mô hình học chuỗi thiếu khi có dưới 9 mốc hoặc khoảng trống bên trong dài hơn 30 phút.',caption)
    table(robustness_rows(robust),[175,103,110,113])
    rows=robustness_summary(robust)
    base, quality=rows['xgboost','half'], rows['quality_routed','half']
    missed_before, missed_after=(mean(row['fn'] for row in x) for x in (base,quality))
    flags_extra=mean(row['fp'] for row in quality)-mean(row['fp'] for row in base)
    p(f"Ở nhóm mất khoảng nửa số mốc, chọn theo chất lượng giảm bỏ sót {fst(missed_before,1)} → {fst(missed_after,1)} trên 1.155 ca dương và tăng trung bình {fst(flags_extra,1)} cờ nhầm.")
    p('Mỗi ô là số ca bỏ sót / số cờ nhầm trung bình. Hai cách chọn mô hình cuối dùng Logistic, Extra Trees hoặc HistGradientBoosting, chọn mô hình và ngưỡng trên 3 fold bên trong. Quy tắc ưu tiên recall nhắm precision ít nhất 0,95 trong vòng chọn.')
    h('Độ dài cửa sổ')
    p('Macro-F1 trên cửa sổ 60, 120 và 240 phút lần lượt là '
      + ' · '.join(fst(row['macro_f1']) for row in robust['duration'])
      + '. Các độ dài tạo tập cửa sổ riêng. So sánh này mô tả độ nhạy theo cách lấy mẫu.')
    p(f'<link href="{PAGE}ais-robustness.json" color="#00675c">Số liệu năm lần chia, từng ngưỡng và từng lượt giữ riêng tàu</link>',caption)
    story.append(PageBreak())

    page('Thử chuyển giữa hai nguồn AIS','GLOBAL FISHING WATCH  ·  TÀU LƯỚI VÂY, CÂU DÂY VÀ LƯỚI KÉO')
    gfw=transfer['suites']['9']
    p(f"Đối chứng ngoài nguồn Đan Mạch dùng {count(gfw['windows'])} cửa sổ từ {gfw['vessels']} tàu trong tập có nhãn của Global Fishing Watch. Tất cả cấu hình được chấm trên cùng {count(gfw['positive'])} cửa sổ dương và {count(gfw['windows']-gfw['positive'])} cửa sổ âm. Hai dòng cuối cho phép học từ một phần dữ liệu GFW theo giới hạn đã nêu.")
    table(transfer_rows(transfer),[186,62,54,61,68,70])
    p('Nhóm học thuần Đan Mạch, bản tăng cường và các bản chuẩn hóa đều giữ toàn bộ GFW ngoài tập học. Tính lại tốc độ và hướng từ tọa độ làm macro-F1 giảm nhẹ so với kênh gốc. Đối chứng học đa nguồn giữ riêng cả nhóm nghề và tất cả mã tàu trong nhóm chấm.')
    lower=transfer['suites']['5']
    p(f"Khi yêu cầu tối thiểu 5 mốc thay cho 9, có {count(lower['windows'])} cửa sổ trên {lower['vessels']} tàu. Nhóm câu dây tại ngưỡng 9 không có cửa sổ dương đủ dày. Tại ngưỡng 5 có {lower['cohorts']['longlines']['positive']} cửa sổ dương. Chi tiết theo nhóm nghề có trong JSON.")
    p('Kết quả học và chấm trong cùng nguồn cho thấy khả năng phân biệt hai trạng thái khi có dữ liệu cùng miền. Khi chuyển nguồn, khác biệt về hoạt động, thiết bị và cách gán nhãn có thể làm số cờ nhầm tăng mạnh. Cần dữ liệu cùng vùng cùng quy trình trước khi dùng cho Việt Nam.')
    p(f'<link href="{transfer["source"]}" color="#00675c">Global Fishing Watch Training Data · CC BY 4.0</link>  ·  <link href="{PAGE}gfw-transfer.json" color="#00675c">Kết quả chi tiết</link>',caption)

    story.append(PageBreak())
    page('Vì sao có khung chồng mà vẫn trượt?','OPEN SAR INSIGHT  ·  Ô 4048  ·  11/05/2020 UTC')
    p('IoU là diện tích giao chia cho diện tích hợp của hai khung. Chấm ở IoU từ 0,50, sau khi lọc theo điểm dự đoán. Mỗi nhãn chỉ được ghép một lần. Trường hợp ô 4048, LS-SSDD có hộp phủ vào tàu phía dưới nhưng đạt IoU 0,309. SLC VV ghép đủ hai nhãn và còn hai hộp trùng, một hộp ngoài nhãn.')
    table(tile_rows(sar),[104,105,83,209])
    p('Ngưỡng IoU 0,30 cho LS-SSDD một hộp khớp ở ô này. Kết quả chính vẫn dùng ngưỡng 0,50 đã khóa. Bảng dưới báo toàn bộ tập ảnh, tránh suy rộng từ một ví dụ.',caption)
    table(sar_rows(sar),[92,139,60,48,85,77])
    p(f'<link href="https://huggingface.co/datasets/opensar-insight/vessel-detection-dataset" color="#00675c">Nguồn OpenSAR Insight</link>  ·  <link href="{PAGE}sar-tile-4048.json" color="#00675c">Tọa độ hộp, điểm dự đoán và phép chấm tái lập</link>',caption)
    story.append(PageBreak())

    page('Giới hạn và cách kiểm chứng tiếp','TỪ KẾT QUẢ ĐỐI CHỨNG ĐẾN PHÉP THỬ NGOÀI HIỆN TRƯỜNG')
    table([['Phần cần kiểm chứng','Giới hạn đã quan sát','Thí nghiệm hoặc dữ liệu cần có'],*FUTURE],
          [100,153,248])
    p('Ưu tiên xác nhận độ bền và độ chuyển vùng trên dữ liệu giữ riêng trước khi thay mô hình vận hành. Báo riêng kết quả kỹ thuật, đánh giá chuyên viên và bằng chứng trực tiếp từ thực địa.')
    p(f'<link href="{PAGE}evidence.html#gioi-han" color="#00675c">Bảng đối chiếu và dữ liệu tải về</link>',caption)

    def footer(c,doc):
        c.setFillColor(teal)
        c.rect(0,A4[1]-8,A4[0],8,fill=1,stroke=0)
        c.setStrokeColor(line)
        c.line(47,40,A4[0]-47,40)
        c.setFillColor(navy)
        c.setFont('ArabicFreeNormal',8)
        c.drawString(47,24,'SONARNET VIỆT NAM  /  28.11.2026')
        c.drawRightString(A4[0]-47,24,str(doc.page))
    doc=SimpleDocTemplate(str(WEB/REPORT),pagesize=A4,leftMargin=47,rightMargin=47,
                          topMargin=35,bottomMargin=54,title='SonarNet • Báo cáo Chặng 2')
    doc.build(story,onFirstPage=footer,onLaterPages=footer)


def html_table(rows):
    rendered=[]
    for i,row in enumerate(rows):
        tag='th' if i==0 else 'td'
        rendered.append('<tr>'+''.join(f'<{tag}>{escape(str(v))}</{tag}>' for v in row)+'</tr>')
    return '<div class="table-wrap"><table>'+''.join(rendered)+'</table></div>'


def web_report(behavior,fusion,external,proxy,robust,transfer,sar,deep,chain):
    behavior_table=html_table([['Dữ liệu học','Đủ bản tin','Mất bản tin','Cửa sổ ngắn','Chồng lấn']]
        +[[name,*[fst(behavior[s,m]['mean'])+' ± '+fst(behavior[s,m]['sd']) for s in SCENARIOS]]
          for m,name in MODELS.items()])
    fusion_table=html_table([['Cấu hình','Cặp đúng','Cặp sai','Từ chối','Mâu thuẫn đúng / tổng¹','Cờ nhầm¹']]
       +[[label(k,s),count(v['id_correct']),v['id_wrong'],count(v['id_abstained']),
          f"{v['mod_mismatch_true']}/{v['mismatches_on_valid_pairs']}",v['mod_mismatch_false']] for (k,s),v in fusion['all'].items()])
    comparison=proxy_comparison(proxy)
    coverage=external['coverage']
    held=external['vessel_held_out']
    ci=held['paired_vessel_bootstrap']['macro_f1_delta_ci']
    gfw=transfer['suites']['9']
    relaxed=transfer['suites']['5']
    total=deep['fusion_paired'][0]
    highlight=measured_contrast(deep,'overlap','mix_given_history_400')
    durations=html_table([['Độ dài','Cửa sổ','Recall','Macro-F1']]+[
        [f"{row['duration_minutes']} phút",count(row['windows']),fst(row['recall']),fst(row['macro_f1'])]
        for row in robust['duration']
    ])
    html=f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Minh chứng Chặng 2 · SonarNet Việt Nam</title><link rel="stylesheet" href="style.css"></head>
<body><header><div><a href="./">SonarNet Việt Nam</a><span>Chung kết AI 2026 · Bảng C</span></div><a href="study.html">Thử rà quỹ đạo</a></header>
<main><section><h1>Kiểm chứng mô-đun hành vi</h1><p>Đề Chặng 2 yêu cầu tách đóng góp của bộ ước lượng Kalman, đối chiếu kích thước và dữ liệu hành vi, rồi kiểm tra ảnh hưởng của gợi ý AI lên thao tác rà.</p>
<div class="stats"><div class="stat"><strong>10 seed</strong>8 kịch bản ghép, 5 điều kiện hành vi</div><div class="stat"><strong>{count(total['correct_0'])} → {count(total['correct_1'])}</strong>cặp đúng trên cùng {count(total['targets'])} mục tiêu mô phỏng</div><div class="stat"><strong>+{fst(highlight['mean'])}</strong>macro-F1 khi tín hiệu chồng lấn, cùng 400 mẫu học</div></div>
<div class="links"><a href="#ablation">Đối chứng chính</a><a href="#chuoi-ra">Kiểm tra đầu ra</a><a href="{REPORT}">Đọc báo cáo PDF</a><a href="{ZIP}">Tải bộ minh chứng ZIP</a><a href="{SOURCE}">Mã nguồn Chặng 2</a><a href="#kiem-thu-bo-sung">Xem kiểm thử bổ sung</a><a href="#sar-4048">Giải thích ô SAR 4048</a><a href="#gioi-han">Giới hạn và hướng tiếp theo</a></div></section>
<section id="ablation"><h2>Đối chứng Kalman trên cùng từng ca</h2>
<p>10 seed, 8 kịch bản và 90 cảnh mỗi kịch bản ở mỗi seed. Cùng bản tin, cùng điểm SAR và cùng luật ghép, thay cách ước lượng vị trí. Hai cột “chỉ đúng” cho biết từng phương pháp cứu hay làm mất bao nhiêu ca.</p>
{html_table(fusion_deep_rows(deep))}
<p class="muted">Ghép sai gồm nhầm tàu và gán AIS vào điểm nhiễu. Kích thước được chấm sau ghép.</p>
<p><a href="fusion-paired-scenes.csv" download>Tải đối chứng theo từng cảnh</a></p></section>
<section><h2>Đối chứng kích thước sau khi ghép</h2>
{html_table(size_deep_rows(deep))}
<p class="muted">Dòng khai báo đúng đếm cờ nhầm. Dòng thiếu khai báo đếm số cặp bị đánh dấu thiếu dữ liệu. Cả hai mức nhiễu đo 9% và 33% dùng đúng cùng cặp ghép, cùng chiều dài và cùng độ lệch chuẩn hóa.</p>
<h3>Cặp qua kiểm tra kích thước</h3>{html_table(gate_deep_rows(deep))}
<p><a href="paired-size-noise.csv" download>Tải so sánh hai mức nhiễu theo cặp</a> · <a href="size-by-factor.csv" download>Tải kết quả bật/tắt theo kịch bản</a></p></section>
<section><h2>Đối chứng đầu vào, chất lượng và lượng dữ liệu hành vi</h2>
<p>Chấm cùng 240 quỹ đạo mỗi seed ở năm điều kiện. Nhóm hỗn hợp giữ nguyên tập quỹ đạo, thay chất lượng quan sát. Nhóm 48, 400 và 800 có số quỹ đạo học độc lập khác nhau.</p>
{html_table(behavior_deep_rows(deep))}
<p class="muted">Chỉ số là macro-F1 trung bình qua 10 seed trên bốn lớp mô phỏng. Đối chứng ngoài mô phỏng được báo riêng trên AIS có nhãn nhị phân.</p>
<p><a href="behavior-factorial.csv" download>Tải kết quả theo seed</a> · <a href="deep-ablation.json" download>Tải ma trận nhầm lẫn và khoảng bootstrap</a></p></section>
<section id="chuoi-ra"><h2>Từ ghép tàu đến danh sách ưu tiên</h2>
<p>Giữ cùng cảnh và nhãn qua 12 tổ hợp. Ca đúng là ca dương được ưu tiên và ghép đúng tàu. Khi tắt mô-đun hành vi, mọi cặp qua các bước kiểm còn lại đều đưa vào hàng rà.</p>
{html_table(chain_rows(chain))}
<h3>Nguyên nhân bỏ sót khi bật Kalman, kích thước và học hỗn hợp</h3>
{html_table(chain_miss_rows(chain))}
<p class="muted">Đo trên danh sách phát hiện SAR mô phỏng có sẵn và hàng rà giả định. Mỗi ca dương bỏ sót chỉ được gán cho nguyên nhân đầu tiên.</p>
<p><a href="chain-ablation.csv" download>Tải kết quả theo kịch bản và seed</a> · <a href="chain-ablation.json" download>Tải số liệu tổng hợp và khoảng bootstrap</a></p></section>
<section><h2>Kalman và kích thước · đợt kiểm tra ban đầu</h2>{fusion_table}
<p class="muted">¹ Trên cặp ghép đúng. Kịch bản hộp radar nhiễu mạnh có 85/110 mâu thuẫn được phát hiện, 25 bỏ sót và 23 cờ nhầm với Kalman và kiểm kích thước. Dữ liệu mô phỏng.</p>
<p><a href="fusion.csv" download>Tải CSV ghép và kích thước theo từng seed</a></p></section>
<section><h2>Dữ liệu huấn luyện hành vi</h2><img class="chart" src="behavior.png" width="1305" height="530" alt="Biểu đồ F1 qua bốn mức chất lượng, so quỹ đạo sạch, quỹ đạo thêm nhiễu và chỉ tốc độ cuối">
{behavior_table}<p class="muted">Trung bình ± độ lệch chuẩn trên 5 seed. Bảng này dùng nhãn từ trình sinh quỹ đạo.</p>
<p><a href="behavior.csv" download>Tải CSV hành vi theo từng seed</a></p></section>
<section id="ais-that"><h2>Đối chứng bằng AIS thật</h2>
<p>{count(coverage['messages'])} bản ghi với {coverage['trips']} mã chuyến phân biệt trong tệp AIS Đan Mạch, được tác giả bộ dữ liệu gán nhãn thủ công. Chấm {count(coverage['scored_windows'])} cửa sổ hai giờ của {coverage['scored_vessels']} tàu, gồm {count(coverage['fishing_windows'])} cửa sổ khai thác.</p>
{html_table(external_rows(external))}
<p>Mô hình học mô phỏng được giữ nguyên. Các biến thể học AIS thật chấm theo 5 lượt tách tàu, dùng cùng bộ lọc và cửa sổ chấm. Khoảng 95% bootstrap theo tàu của chênh macro-F1 giữa toàn quỹ đạo và chuỗi tốc độ là [{fst(ci[0])}, {fst(ci[1])}].</p>
<p class="muted">Phạm vi gồm hai trạng thái khai thác và di chuyển tại Đan Mạch. Cần thêm nhãn bốn lớp ở Việt Nam, dữ liệu SAR–AIS đối chứng và đánh giá với chuyên viên thật.</p>
<p><a href="{external['dataset']}">Dữ liệu gốc và giấy phép CC BY 4.0</a> · <a href="real-ais.json" download>Tải kết quả theo seed và tàu giữ riêng</a></p></section>
<section id="do-goi-y"><h2>So sánh có và không có gợi ý AI</h2>
<p>Hai bên cùng dữ liệu AIS và ba lựa chọn. Người rà tự dựng giả thuyết ở bên không AI. Ở bên có AI, đề xuất tạo một điểm bắt đầu để đối chiếu lại với hai đồ thị.</p>
<p><a href="compare.html"><strong>Mở hai giao diện cạnh nhau và thử ba tình huống</strong></a></p>
<h3>Bỏ sót và cờ nhầm trong mô phỏng</h3>
<p>{proxy['sessions']} phiên trình duyệt tự động, {proxy['browser_decisions']} lượt chọn, {len(proxy['policies'])} quy tắc và {proxy['unique_cases']} ca mô phỏng. Bảng gộp các lần lặp của cùng một ca và quy tắc.</p>
{html_table(proxy_rows(proxy))}
<p>Bỏ sót {comparison['missed'][0]} → {comparison['missed'][1]} trên {comparison['positive_pairs']} cặp ca dương × quy tắc. Có {comparison['rescued']} quyết định được sửa và {comparison['new_misses']} bỏ sót mới. Cờ nhầm {comparison['flags'][0]} → {comparison['flags'][1]} trên {comparison['negative_pairs']} cặp ca âm × quy tắc. Có {comparison['resolved_flags']} cờ được bỏ và {comparison['new_flags']} cờ mới.</p>
<h3>Thời gian thao tác tự động</h3>{html_table(proxy_time_rows(proxy))}
<p class="muted">Thời gian tính từ khi giao diện mở ca đến khi trình duyệt tự động bấm nút. Chưa đo thời gian tư duy hay tốc độ của chuyên viên. Các kết quả lỗi áp dụng cho bộ ca và quy tắc mô phỏng này.</p>
<p><a href="proxy-study.json" download>Tải kết quả theo ca và quy tắc</a></p></section>
<section id="kiem-thu-bo-sung"><h2>Độ bền khi mất bản tin</h2>
<p>Năm lần chia theo tàu, tổng 25 lượt giữ riêng tàu. Mỗi lần chấm cùng 1.155 cửa sổ khai thác qua dữ liệu gốc và hai kịch bản thiếu bản tin.</p>
<img class="chart" src="robustness.png" alt="Số cửa sổ khai thác bị bỏ sót với ba phương án XGBoost khi làm thiếu dữ liệu">
{html_table(robustness_rows(robust))}
<p class="muted">Mỗi ô là số ca bỏ sót / số cờ nhầm trung bình. Quy tắc chọn chất lượng dùng mô hình học chuỗi thiếu khi có dưới 9 mốc hoặc khoảng trống bên trong dài hơn 30 phút.</p>
<h3>Độ dài cửa sổ</h3>{durations}
<p><a href="ais-robustness.json" download>Tải số liệu theo lần chia và cấu hình</a></p></section>
<section id="gfw"><h2>Kiểm tra trên Global Fishing Watch</h2>
<p>{count(gfw['windows'])} cửa sổ từ {gfw['vessels']} tàu, bao gồm {count(gfw['positive'])} cửa sổ khai thác. Cùng điều kiện 9 mốc tối thiểu trong mỗi cửa sổ 2 giờ.</p>
{html_table(transfer_rows(transfer))}
<p>Hai dòng cuối dùng một phần GFW để học. Phương án đa nguồn giữ riêng toàn bộ nhóm nghề đang chấm và từng tàu trong nhóm đó. Phương án cùng nguồn giữ riêng tàu, các nhóm nghề vẫn có thể xuất hiện trong tập học.</p>
<p class="muted">Ngưỡng 5 mốc cho {count(relaxed['windows'])} cửa sổ từ {relaxed['vessels']} tàu. Nhánh câu dây chỉ có đủ ví dụ dương ở điều kiện này. Khác biệt giữa nguồn có thể làm cờ nhầm tăng.</p>
<p><a href="{transfer['source']}">Nguồn dữ liệu Global Fishing Watch · CC BY 4.0</a> · <a href="gfw-transfer.json" download>Tải kết quả theo nguồn và nhóm nghề</a></p></section>
<section id="sar-4048"><h2>Vì sao hai hộp chồng mà vẫn trượt?</h2>
<p>Ở ô OpenSAR Insight 4048, khung dự đoán LS-SSDD trên tàu phía dưới chồng lên nhãn với IoU 0,309. Ngưỡng chấm chính là 0,50. Bên SLC VV, hai dự đoán đã được ghép vào hai nhãn, hai hộp khác trùng lên chính các nhãn đã ghép và một hộp nằm ngoài cả hai nhãn.</p>
{html_table(tile_rows(sar))}
<p class="muted">IoU là phần diện tích giao chia cho diện tích hợp. Mỗi nhãn được ghép một lần theo thứ tự điểm dự đoán. Chấm mô tả ở IoU 0,30 cho LS-SSDD khớp 1/2 nhãn ở ô này.</p>
<h3>So sánh toàn bộ tập ảnh</h3>{html_table(sar_rows(sar))}
<p><a href="sar-tile-4048.json" download>Tải tọa độ và IoU của từng hộp</a></p></section>
<section id="gioi-han"><h2>Giới hạn và phép thử tiếp theo</h2>
{html_table([['Phần cần kiểm chứng','Giới hạn đã quan sát','Thí nghiệm hoặc dữ liệu cần có'],*FUTURE])}</section></main>
<footer>SonarNet Việt Nam · Chặng 2 · 28/11/2026</footer></body></html>"""
    (WEB/'evidence.html').write_text(html)


def main():
    raw=json.loads((OUT/'results.json').read_text())
    study=json.loads((OUT/'study-summary.json').read_text())
    assert not study['qa_fixture_only']
    behavior,fusion,_=metrics(raw,study)
    figure(behavior)
    external=json.loads((OUT/'real-ais.json').read_text())
    proxy=json.loads((OUT/'proxy-study.json').read_text())
    robust=json.loads((OUT/'ais-robustness.json').read_text())
    transfer=json.loads((OUT/'gfw-transfer.json').read_text())
    robustness_plot(robust)
    sar=json.loads((OUT/'sar-tile-4048.json').read_text())
    deep=json.loads((OUT/'deep-ablation.json').read_text())
    chain=json.loads((OUT/'chain-ablation.json').read_text())
    pdf_report(external,proxy,robust,transfer,sar,deep,chain)
    web_report(behavior,fusion,external,proxy,robust,transfer,sar,deep,chain)
    import shutil
    for name in ('behavior.csv','fusion.csv','study-summary.json','real-ais.json','proxy-study.json',
                 'ais-robustness.json','gfw-transfer.json','sar-tile-4048.json','deep-ablation.json','fusion-paired-scenes.csv',
                 'size-by-factor.csv','paired-size-noise.csv','behavior-factorial.csv','chain-ablation.csv','chain-ablation.json'):
        shutil.copyfile(OUT/name,WEB/name)
    files=[(OUT/file,file) for file in ('behavior.csv','fusion.csv','results.json','study-cases.json','study-summary.json','PROTOCOL.md','real-ais.json','proxy-study.json','ais-robustness.json','gfw-transfer.json','sar-tile-4048.json','deep-ablation.json','fusion-paired-scenes.csv',
                                       'size-by-factor.csv','paired-size-noise.csv','behavior-factorial.csv','chain-ablation.csv','chain-ablation.json')]
    files += [(ROOT/'scripts'/f,'scripts/'+f) for f in ('evaluate_chang2.py','score_chang2_study.py','evaluate_chang2_real_ais.py','replay_chang2_proxy.cjs','stress_chang2_real_ais.py','transfer_chang2_gfw.py','audit_chang2_sar_tile.py','deep_ablation_chang2.py','chain_ablation_chang2.py','capture_chang2_comparison.cjs')]
    files += [(WEB/file,file) for file in (REPORT,'behavior.png','robustness.png','review-comparison.png')]
    with ZipFile(WEB/ZIP,'w',compression=ZIP_DEFLATED) as archive:
        for source,name in files:
            archive.write(source,name)
        archive.writestr('SHA256SUMS',''.join(f'{checksum(file)}  {name}\n' for file,name in files))
    print(WEB/REPORT,WEB/ZIP)


if __name__=='__main__':
    main()
