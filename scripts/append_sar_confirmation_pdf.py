"""Append a single verified replication page without altering the previous PDF."""
import argparse
from io import BytesIO
import json
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.enums import TA_JUSTIFY
from document_format import register_document_fonts, page_number
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT=Path(__file__).resolve().parents[1]
BENCH=ROOT/'reports/final/opensar_confirmation_20261118'
BG='#eaf4f5'; INK='#102b40'; NAVY='#102b40'; TEAL='#007f86'


def vietnamese(n,digits=2):
    return f'{n:,.{digits}f}'.translate(str.maketrans(',.','.,'))


def build(font, base, output):
    r=json.loads((BENCH/'results.json').read_text()); bm=r['models']['yolo']; basic=bm['metrics']; coast=basic['by_distance_to_mapped_shore_m']['500']
    follow=json.loads((BENCH/'followup/frozen_operating_points.json').read_text())
    first=json.loads((BENCH/'followup/results.json').read_text())['models']['reference']['metrics']
    diag=json.loads((BENCH/'posthoc_diagnostics.json').read_text())['box_iou_sensitivity']
    register_document_fonts('DV','DV-Bold')
    normal=ParagraphStyle('p',fontName='DV',fontSize=10.3,leading=15.7,textColor=colors.black,spaceAfter=8)
    label=ParagraphStyle('k',parent=normal,fontName='DV-Bold',fontSize=9,textColor=colors.black)
    title=ParagraphStyle('h',parent=normal,fontName='DV-Bold',fontSize=15,leading=19,spaceAfter=11)
    head=ParagraphStyle('h2',parent=normal,fontName='DV-Bold',fontSize=12,leading=17,spaceBefore=6)
    small=ParagraphStyle('s',parent=normal,fontSize=8.8,leading=13)
    story=[]
    def add(t,style=normal):story.append(Paragraph(t,style))
    def table(rows,widths):
        t=Table([[Paragraph(str(c),small) for c in row] for row in rows],colWidths=widths,hAlign='LEFT')
        t.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.45,colors.black),('VALIGN',(0,0),(-1,-1),'TOP'),
            ('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),
            ('TEXTCOLOR',(0,0),(-1,-1),colors.black)]))
        story.extend([t,Spacer(1,10)])
    add('CHẶNG 1 / PHỤ LỤC / 18.11.2026',label)
    add('Khả năng lặp lại trên ba cảnh SAR mới',title)
    add(f'<b>Không thay checkpoint bản đồ.</b> Ở cấu hình đã khóa, YOLO khớp {first["true_positive"]}/{first["n_ground_truth"]} nhãn '
        f'trên 503 ô từng đánh giá, nhưng chỉ khớp {basic["true_positive"]}/{basic["n_ground_truth"]} trên {r["test_chips"]} ô ở ba cảnh mới. '
        'Không gộp hai tập: khác cảnh và phân bố mục tiêu. Kết quả tốt ở tập trước không lặp lại ở tập mới.')
    rows=[['Ngày chụp UTC','Nhãn khớp / tổng','Điểm không khớp','Biển ước tính']]
    for k,m in sorted(bm['per_scene'].items(),key=lambda row:row[0].split('__',1)[1].split('_')[1]):
        d=k.split('__',1)[1].split('_')[1][:8]
        rows.append([f'{d[6:]}/{d[4:6]}/{d[:4]}',f'{m["true_positive"]}/{m["n_ground_truth"]}',m['false_positive'],
                     vietnamese(m['evaluated_water_scene_km2'],2)+' km²'])
    rows.append(['<b>Tổng YOLO</b>',f'<b>{basic["true_positive"]}/{basic["n_ground_truth"]}</b>',basic['false_positive'],vietnamese(basic['evaluated_water_scene_km2'])+' km²'])
    table(rows,[109,118,130,118])
    add(f'Trong dải 500 m từ bờ, chỉ <b>{coast["matched"]}/{coast["labels"]}</b> nhãn khớp. Mật độ không khớp {vietnamese(basic["benchmark_unmatched_per_km2"],4)}/km² '
        'đi cùng tỷ lệ bỏ sót cao, không phải dấu hiệu cải thiện. Sai lệch tâm 24,69 m chỉ tính trên 3 hộp khớp; chưa có GPS hoặc kích thước thân tàu độc lập.')
    add('Những thay đổi đã thử trước khi đọc kết quả mới',head)
    add(f'Tăng tương phản, chia ô chồng lấn và ghép nhiều lượt suy luận không vượt ảnh nguyên trên validation dưới giới hạn {follow["fp_budget"]} điểm không khớp. '
        'Đối chứng CFAR dùng vòng nền có vùng bảo vệ không tìm được nhãn nào trên ba cảnh mới. Đây là bản đối chứng thực nghiệm, không phải CFAR đã hiệu chuẩn cho ảnh vệ tinh.')
    add('Sai hộp và ngưỡng không giải thích hết bỏ sót',head)
    add(f'Nới IoU tới 0,25 ở confidence 0,10 tăng số nhãn khớp lên {diag["conf_0.10_iou_0.25"]["true_positive"]}. '
        f'Hạ confidence về 0,01 và giữ IoU 0,50 cho {diag["conf_0.01_iou_0.50"]["true_positive"]} nhãn khớp, '
        f'nhưng có {diag["conf_0.01_iou_0.50"]["false_positive"]} điểm không khớp. Đây là chẩn đoán sau đo, không dùng chọn lại ngưỡng.')
    add('Phạm vi sử dụng',head)
    add('Chỉ dùng ứng dụng để mở và rà ảnh nguồn. Bản đồ hiện còn loại dải 500 m; đừng đọc vùng không có điểm như vùng biển không có tàu. '
        'Bước tiếp theo là dùng ảnh ven bờ ở nhiều vùng có nhãn kiểm chứng để huấn luyện, rồi kiểm lại trên các cảnh chưa từng xem.')
    add('Nguồn: OpenSAR Insight (ESA Φ-lab) và GSHHG 2.3.7. Ba cảnh được giữ riêng theo footprint/ngày và kiểm trùng ảnh trước chấm. '
        'Chi tiết, giới hạn nhãn nguồn và kết quả từng phương án nằm trong reports/final/opensar_confirmation_20261118.',small)
    pages=BytesIO(); prev=PdfReader(base); n=len(prev.pages)
    def footer(c,d):
        page_number(c,d.page+n,'DV')
    SimpleDocTemplate(pages,pagesize=A4,leftMargin=55,rightMargin=55,topMargin=42,bottomMargin=43).build(story,onFirstPage=footer,onLaterPages=footer)
    pages.seek(0)
    if len(PdfReader(pages).pages)!=1:raise ValueError('Unexpected appendix pagination')
    pages.seek(0)
    writer=PdfWriter();writer.append(prev);writer.append(pages,outline_item='Kiểm tra lại trên ba cảnh SAR mới')
    writer.add_metadata({'/Title':'SonarNet-VN - Báo cáo cải tiến và kiểm tra lặp lại SAR'})
    writer.write(output)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for opt in ('font','base','output'):p.add_argument('--'+opt,type=Path,required=True)
    a=p.parse_args();build(a.font,a.base,a.output)
