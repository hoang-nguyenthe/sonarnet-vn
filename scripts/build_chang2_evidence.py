"""Build the Vietnamese report, web evidence and reproducibility bundle."""
from collections import defaultdict
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
    ('Thời gian người rà',
     '32 phiên chỉ đo thao tác của trình duyệt tự động. Cần phiếu chuyên viên để đo tác động ở người.',
     'Dùng bài thử chéo với các mã luân phiên A/B. Đo thời gian trong từng người, bỏ sót và cờ nhầm. Báo số phiếu và độ bất định của chênh lệch.'),
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


def pdf_report(raw, behavior, fusion, study, external, proxy, robust, transfer, sar):
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
    page('Kiểm chứng mô-đun hành vi','SONARNET VIỆT NAM  ·  CHUNG KẾT AI 2026  ·  CHẶNG 2, PHIÊN BẢN 1')
    p('Một gợi ý hành vi chỉ có ích khi quỹ đạo đủ chất lượng, cặp SAR–AIS đủ căn cứ và người rà có thể kiểm tra lại. Đội chạy các cấu hình bật/tắt trên cùng ca, rồi dùng một bài thử đối chứng để đo thao tác của người rà.')
    h('Kết quả chính')
    table([['Đối chứng','Kết quả','Điều cần giữ khi đọc'],
           ['Ghép bằng Kalman','1.229 → 1.239 cặp đúng, 3 → 0 cặp sai','4.800 mục tiêu mô phỏng cho mỗi cấu hình. Cùng quy tắc ghép và từ chối.'],
           ['Đối chiếu kích thước','393/418 trường hợp mâu thuẫn được phát hiện, 23 cờ nhầm','Tính ở những cặp Kalman đã ghép đúng. Khi kích thước radar nhiễu mạnh, còn 25/110 trường hợp bị bỏ sót.'],
           ['Huấn luyện với chuỗi nhiễu','Macro-F1 0,236 → 0,883 trong kịch bản chồng lấn','Giữ 400 mẫu huấn luyện, cùng 5 seed và cùng tập chấm. Mô phỏng.'],
          ],[142,152,207])
    h('Phạm vi xác nhận')
    specialist=study['specialists_self_reported']
    pilot=study['other_pilot']
    p(f"<b>Đối chứng mô hình.</b> Năm seed, bốn kịch bản ghép, bốn kịch bản hành vi. Có số đếm theo seed, ma trận nhầm lẫn, mã chạy và dữ liệu ca thử.")
    if specialist['n']:
        p(f"<b>Khảo sát.</b> Có {specialist['n']} phiếu của người tự khai chuyên môn liên quan và {pilot['n']} phiếu nhóm thử nghiệm khác. Kết quả theo cặp ở trang 5.")
    else:
        p(f"<b>Khảo sát.</b> Có {specialist['n']} phiếu chuyên viên hoàn chỉnh và {pilot['n']} phiếu nhóm thử nghiệm khác. Bài thử đã chạy qua kiểm tra trình duyệt. Kết quả kiểm tra tự động được loại khỏi số liệu người tham gia.")
    coverage=external['coverage']
    p(f"<b>Đối chứng AIS thật.</b> {count(coverage['scored_windows'])} cửa sổ từ {coverage['scored_vessels']} tàu. Mô hình chỉ học mô phỏng đạt macro-F1 trung bình {fst(mean(row['macro_f1'] for row in external['synthetic_only']))}. Mô hình học AIS thật với toàn quỹ đạo đạt {fst(external['vessel_held_out']['history']['macro_f1'])} khi tách tàu để chấm. Kết quả và giới hạn ở trang 4.")
    p(f"<b>Thử tự động.</b> {proxy['sessions']} phiên trình duyệt kiểm tra {proxy['browser_decisions']} thao tác với các quy tắc giả lập. Số liệu người tham gia được tính từ phiếu thật.",caption)
    gfw=transfer['suites']['9']['models']
    p(f"<b>Kiểm tra chuyển nguồn.</b> Macro-F1 của mô hình học Đan Mạch khi chấm trên Global Fishing Watch là {fst(gfw['denmark_to_gfw']['macro_f1'])}. Khi học cùng nguồn và tách tàu để chấm, kết quả là {fst(gfw['gfw_held_vessel']['macro_f1'])}. Xem phần kiểm tra mở rộng ở trang 7–8.",caption)
    h('Mở kết quả và thử trực tiếp')
    p(f'<link href="{PAGE}" color="#00675c">Ứng dụng Chặng 2</link>  ·  <link href="{PAGE}evidence.html" color="#00675c">Minh chứng và tệp tải</link>  ·  <link href="{SOURCE}" color="#00675c">Mã nguồn</link>')
    story.append(PageBreak())

    page('Kalman và kích thước','ĐỐI CHỨNG 2 × 2  ·  CÙNG DỮ LIỆU THEO TỪNG SEED')
    p('Dùng 5 seed (101, 203, 307, 409, 503), mỗi seed có 60 lượt cho mỗi kịch bản. Mỗi lượt có bốn mục tiêu. Cấu hình tuyến tính và Kalman dùng cùng điểm radar, bản tin AIS, ngưỡng tuổi, bất định và cạnh tranh. Kiểm kích thước diễn ra sau khi ghép. Bật/tắt bước này chỉ tác động tới trạng thái dùng khi rà.')
    table([['Cấu hình','Đúng','Sai','Từ chối','Phát hiện mâu thuẫn¹','Cờ nhầm¹']]
          +[[label(k,s), count(v['id_correct']),v['id_wrong'],count(v['id_abstained']),
             f"{v['mod_mismatch_true']}/{v['mismatches_on_valid_pairs']}",v['mod_mismatch_false']]
            for (k,s),v in fusion['all'].items()],[144,52,42,63,116,84])
    p('¹ Chấm mâu thuẫn kích thước trên các cặp ghép đúng. Mâu thuẫn là kích thước khai báo bị nhân 2,25 trong mô phỏng. Cờ nhầm là cặp không bị đổi kích thước nhưng thuật toán báo mâu thuẫn. Ngưỡng chênh lệch tương đối 0,42 được giữ từ hệ thống gốc.',caption)
    h('Cặp ghép qua từng tình huống')
    rows=[['Kịch bản','Tuyến tính đúng/sai','Kalman đúng/sai','Từ chối tuyến tính → Kalman']]
    for scenario, wording in FUSION.items():
        before,after=fusion[scenario][False,True],fusion[scenario][True,True]
        rows.append([wording,f"{before['id_correct']} / {before['id_wrong']}",
                     f"{after['id_correct']} / {after['id_wrong']}",
                     f"{before['id_abstained']} → {after['id_abstained']}"])
    table(rows,[146,107,104,144])
    p('Mức tăng Kalman tập trung ở AIS hỗn hợp và nhiễu kích thước. Ở nhóm tàu cắt nhau và lệch vị trí, hai bộ ước lượng cùng giữ 300 cặp đúng và từ chối 900 trường hợp mỗi nhóm. Bộ ghép ưu tiên giữ ca bất định để rà tiếp.')
    p('Ở kịch bản hộp radar nhiễu mạnh, kiểm kích thước trên cặp Kalman ghép đúng phát hiện 85/110 mâu thuẫn, bỏ sót 25 và tạo 23 cờ nhầm. Kích thước vì vậy phù hợp để yêu cầu rà thêm.')
    story.append(PageBreak())

    page('Dữ liệu huấn luyện hành vi','XGBOOST  ·  BỐN LỚP HÀNH VI  ·  5 SEED ĐỘC LẬP')
    p('Mỗi seed sinh riêng 400 quỹ đạo học và 240 quỹ đạo chấm (60 mỗi lớp). Các phương án dùng cùng quỹ đạo chấm. So tốc độ mới nhất với đặc trưng toàn chuỗi, giảm số mẫu học xuống 48 và đối chiếu tăng cường nhiễu ở cùng 400 mẫu. Biến thể 800 gồm các bản gốc và biến thể nhiễu của 400 quỹ đạo học.')
    story.append(Image(str(WEB/'behavior.png'),width=499,height=202))
    p('Đường và thanh dọc lần lượt là trung bình và độ lệch chuẩn giữa 5 seed. Kịch bản làm mất 60% bản tin là kỳ vọng của cơ chế lấy mẫu, có ràng buộc giữ tối thiểu 5 mốc. Nhóm cửa sổ ngắn và tín hiệu chồng lấn gồm 9–19 mốc trước khi loại ngẫu nhiên. Kịch bản chồng lấn thêm nhiễu vị trí, hướng, hệ số và độ lệch tốc độ báo.',caption)
    table([['Dữ liệu học · số hàng','Đủ bản tin','Mất bản tin','Cửa sổ ngắn','Chồng lấn']]
         +[[label,*[fst(behavior[s,m]['mean']) for s in SCENARIOS]] for m,label in MODELS.items()],
          [168,75,83,87,88])
    p('Ở kịch bản chồng lấn, bản có nhiễu 400 mẫu đạt 0,883 (độ lệch chuẩn 0,021), so với 0,236 (0,033) khi học trên quỹ đạo sạch. Theo quy tắc giản lược ưu tiên rà hai lớp khai thác, số mẫu dương bị mô hình bỏ sót giảm từ 38 xuống 8 trên 600 mẫu, và số gợi ý ưu tiên nhầm giảm từ 503 xuống 2.')
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
    p('Đối chứng này có phạm vi hai trạng thái trên AIS Đan Mạch. SonarNet vẫn cần nhãn bốn lớp ở Việt Nam, dữ liệu SAR–AIS ghép có đối chứng và phiếu chuyên viên thật để xác nhận các phần còn lại.')
    p(f'<link href="{external["dataset"]}" color="#00675c">Dữ liệu gốc · DOI 10.5281/zenodo.7283281 · CC BY 4.0</link>  ·  <link href="{PAGE}real-ais.json" color="#00675c">Số liệu theo lượt chia</link>',caption)
    story.append(PageBreak())

    page('Đo thao tác của người rà','THỬ CHÉO HAI ĐIỀU KIỆN  ·  GIỮ CÙNG LOẠI BẰNG CHỨNG')
    p('Mỗi người làm hai lượt, mỗi lượt 8 ca khác nhau. Hai tập A và B đều có bốn ca cần ưu tiên theo nhãn mô phỏng, đủ bốn lớp hành vi. Mã được phân theo bốn bố trí để cân bằng thứ tự và tập ca. Cả hai chế độ có cùng biểu đồ; chế độ AI thêm gợi ý từ mô hình XGBoost đã chạy trên chính ca đó.')
    table([['Mã','Lượt 1','Lượt 2'],['R01','A · không gợi ý','B · có gợi ý'],
           ['R02','B · có gợi ý','A · không gợi ý'],['R03','A · có gợi ý','B · không gợi ý'],
           ['R04','B · không gợi ý','A · có gợi ý']],[100,200,201])
    p('<b>Chỉ số.</b> Tính trung vị thời gian mỗi điều kiện và chênh lệch có gợi ý trừ không gợi ý trong từng người. Bỏ thời gian của ca đổi tab, giữ đáp án để tính lỗi. Bỏ sót là ca dương được chọn chưa ưu tiên hoặc chưa đủ dữ liệu. Ghi riêng cờ ưu tiên nhầm.')
    counts=[['Nhóm','Người rà','Bỏ sót không / có AI','Chênh thời gian²']]
    for key, wording in (('specialists_self_reported','Chuyên viên tự khai'),('other_pilot','Thử nghiệm sơ bộ')):
        item=study[key]
        c,a=item['control'],item['ai']
        delta=item['median_paired_delta_seconds']
        counts.append([wording,item['n'],f"{c['missed']}/{c['positive']} · {a['missed']}/{a['positive']}" if item['n'] else 'Chưa có phiếu',
                       fst(delta,2)+' giây' if delta is not None else 'Chưa ước tính'])
    table(counts,[151,61,150,139])
    p('² Chênh lệch tính theo từng người, rồi lấy trung vị giữa những người có hai điều kiện hợp lệ. Bài thử tăng cường ca khó và có ba gợi ý sai về mức ưu tiên trên 16 ca. Kết quả, khi có, phản ánh thao tác với bộ ca này. Nghề và kinh nghiệm do người tham gia tự khai.',caption)
    h('Giới hạn khi dùng ngoài hiện trường')
    p('Chuỗi AIS ngoài thực địa có mất tín hiệu, sai số và hành vi hỗn hợp. Kết quả trên AIS thật ở trang 4 chỉ có nhãn nhị phân từ tập Đan Mạch. Tiếp theo cần bộ ca có nhãn đối chiếu độc lập ở Việt Nam và đánh giá thao tác với chuyên viên thật.')
    p(f'<link href="{PAGE}study.html" color="#00675c">Mở bài thử</link>  ·  <link href="{PAGE}{ZIP}" color="#00675c">Tải dữ liệu, giao thức và mã tái lập</link>',caption)

    story.append(PageBreak())
    page('Đối chứng thao tác tự động','32 PHIÊN TRÌNH DUYỆT  ·  8 QUY TẮC GIẢ LẬP')
    p(f"Phát lại {proxy['sessions']} phiên trên đúng giao diện bài thử, ghi {proxy['browser_decisions']} quyết định. Mỗi quy tắc chạy đủ bốn bố trí A/B. Quy tắc dùng tốc độ và độ thẳng của đường đi. Chế độ có AI còn đọc gợi ý đang hiển thị.")
    p('Bảng gộp các lần lặp cùng quy tắc, điều kiện và ca. Mỗi dòng so cùng 16 ca trong mỗi điều kiện, gồm 8 ca dương. Các ngưỡng và trọng số cố định được ghi trong mã chạy. Chúng thể hiện nhiều cách dùng gợi ý giả định.')
    table(proxy_rows(proxy),[151,108,108,134])
    less=sum(row['ai']['missed']<row['control']['missed'] for row in proxy['policies'])
    more_flags=sum(row['ai']['false_flags']>row['control']['false_flags'] for row in proxy['policies'])
    p(f"Gợi ý giảm bỏ sót ở {less}/{len(proxy['policies'])} quy tắc và tăng cờ nhầm ở {more_flags}/{len(proxy['policies'])} quy tắc.")
    p('Số ca bỏ sót gồm cả lựa chọn chưa ưu tiên và chưa đủ dữ liệu ở ca dương. Cờ nhầm là ưu tiên ở ca âm. Số liệu thời gian trong JSON đo thao tác tự động của trình duyệt. Ước tính thời gian chuyên viên cần phiếu do người thật thực hiện.')
    p(f'<link href="{PAGE}proxy-study.json" color="#00675c">Tải kết quả kiểm tra tự động</link>  ·  <link href="{PAGE}study.html" color="#00675c">Mở khảo sát người tham gia</link>',caption)

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


def web_report(behavior,fusion,study,external,proxy,robust,transfer,sar):
    behavior_table=html_table([['Dữ liệu học','Đủ bản tin','Mất bản tin','Cửa sổ ngắn','Chồng lấn']]
        +[[name,*[fst(behavior[s,m]['mean'])+' ± '+fst(behavior[s,m]['sd']) for s in SCENARIOS]]
          for m,name in MODELS.items()])
    fusion_table=html_table([['Cấu hình','Cặp đúng','Cặp sai','Từ chối','Mâu thuẫn đúng / tổng¹','Cờ nhầm¹']]
       +[[label(k,s),count(v['id_correct']),v['id_wrong'],count(v['id_abstained']),
          f"{v['mod_mismatch_true']}/{v['mismatches_on_valid_pairs']}",v['mod_mismatch_false']] for (k,s),v in fusion['all'].items()])
    study_rows=[['Nhóm','Số phiếu','Bỏ sót không / có AI','Chênh giây có − không AI']]
    for key,name in (('specialists_self_reported','Chuyên viên tự khai'),('other_pilot','Thử nghiệm sơ bộ')):
        row=study[key]
        before,after=row['control'],row['ai']
        misses=f"{before['missed']}/{before['positive']} · {after['missed']}/{after['positive']}" if row['n'] else 'Chưa có phiếu'
        delta=row['median_paired_delta_seconds']
        study_rows.append([name,row['n'],misses,fst(delta,2) if delta is not None else 'Chưa ước tính'])
    coverage=external['coverage']
    held=external['vessel_held_out']
    ci=held['paired_vessel_bootstrap']['macro_f1_delta_ci']
    gfw=transfer['suites']['9']
    relaxed=transfer['suites']['5']
    durations=html_table([['Độ dài','Cửa sổ','Recall','Macro-F1']]+[
        [f"{row['duration_minutes']} phút",count(row['windows']),fst(row['recall']),fst(row['macro_f1'])]
        for row in robust['duration']
    ])
    html=f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Minh chứng Chặng 2 · SonarNet Việt Nam</title><link rel="stylesheet" href="style.css"></head>
<body><header><div><a href="./">SonarNet Việt Nam</a><span>Chung kết AI 2026 · Bảng C</span></div><a href="study.html">Thử rà quỹ đạo</a></header>
<main><section><h1>Kiểm chứng mô-đun hành vi</h1><p>Đề Chặng 2 yêu cầu tách đóng góp của bộ ước lượng Kalman, đối chiếu kích thước và dữ liệu hành vi, rồi kiểm tra ảnh hưởng của gợi ý AI lên thao tác rà.</p>
<div class="stats"><div class="stat"><strong>5 seed</strong>4 kịch bản ghép và 4 mức chất lượng quỹ đạo</div><div class="stat"><strong>3 → 0</strong>cặp ghép sai trên 4.800 mục tiêu mô phỏng</div><div class="stat"><strong>0,236 → 0,883</strong>macro-F1 khi tín hiệu chồng lấn, cùng 400 mẫu học</div></div>
<div class="links"><a href="{REPORT}">Đọc báo cáo PDF</a><a href="{ZIP}">Tải bộ minh chứng ZIP</a><a href="{SOURCE}">Mã nguồn Chặng 2</a><a href="#kiem-thu-bo-sung">Xem kiểm thử bổ sung</a><a href="#sar-4048">Giải thích ô SAR 4048</a><a href="#gioi-han">Giới hạn và hướng tiếp theo</a></div></section>
<section><h2>Kalman và kiểm tra kích thước</h2>{fusion_table}
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
<section><h2>Rà với và không có gợi ý AI</h2><p>Hai lượt, mỗi lượt 8 ca mô phỏng, đổi thứ tự và điều kiện theo mã người rà. Thời lượng, ca bỏ sót và cờ nhầm được tính từ phiếu thực tế.</p>{html_table(study_rows)}
<p><a href="study.html">Mở bài thử và tải phiếu sau hai lượt</a> · <a href="study-summary.json" download>Tải số liệu khảo sát</a></p></section>
<section id="mo-phong"><h2>Đối chứng thao tác tự động</h2>
<p>{proxy['sessions']} phiên trình duyệt, {proxy['browser_decisions']} quyết định, {len(proxy['policies'])} quy tắc giả lập. Mỗi dòng gộp lặp và so cùng {proxy['unique_cases']} ca mô phỏng ở từng điều kiện.</p>
{html_table(proxy_rows(proxy))}
<p class="muted">Thời gian trong tệp JSON là thời gian thao tác của trình duyệt tự động. Kết quả khảo sát người tham gia chỉ nhận phiếu thật.</p>
<p><a href="proxy-study.json" download>Tải kết quả kiểm tra tự động</a></p></section>
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
    behavior,fusion,groups=metrics(raw,study)
    figure(behavior)
    external=json.loads((OUT/'real-ais.json').read_text())
    proxy=json.loads((OUT/'proxy-study.json').read_text())
    robust=json.loads((OUT/'ais-robustness.json').read_text())
    transfer=json.loads((OUT/'gfw-transfer.json').read_text())
    robustness_plot(robust)
    sar=json.loads((OUT/'sar-tile-4048.json').read_text())
    pdf_report(raw,behavior,fusion,groups,external,proxy,robust,transfer,sar)
    web_report(behavior,fusion,groups,external,proxy,robust,transfer,sar)
    import shutil
    for name in ('behavior.csv','fusion.csv','study-summary.json','real-ais.json','proxy-study.json',
                 'ais-robustness.json','gfw-transfer.json','sar-tile-4048.json'):
        shutil.copyfile(OUT/name,WEB/name)
    files=[(OUT/file,file) for file in ('behavior.csv','fusion.csv','results.json','study-cases.json','study-summary.json','PROTOCOL.md','real-ais.json','proxy-study.json','ais-robustness.json','gfw-transfer.json','sar-tile-4048.json')]
    files += [(ROOT/'scripts'/f,'scripts/'+f) for f in ('evaluate_chang2.py','score_chang2_study.py','evaluate_chang2_real_ais.py','replay_chang2_proxy.cjs','stress_chang2_real_ais.py','transfer_chang2_gfw.py','audit_chang2_sar_tile.py')]
    files += [(WEB/file,file) for file in (REPORT,'behavior.png','robustness.png')]
    with ZipFile(WEB/ZIP,'w',compression=ZIP_DEFLATED) as archive:
        for source,name in files:
            archive.write(source,name)
        archive.writestr('SHA256SUMS',''.join(f'{checksum(file)}  {name}\n' for file,name in files))
    print(WEB/REPORT,WEB/ZIP)


if __name__=='__main__':
    main()
