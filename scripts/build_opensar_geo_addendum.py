"""Append audited OpenSAR geometry results to the Chặng 1 report."""
import argparse
from io import BytesIO
import json
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'reports/final/opensar_geo_20261118'
NAVY, TEAL, MIST = '#102B40', '#007F86', '#EAF4F6'


def vn(n, digit=2):
    return f'{n:,.{digit}f}'.translate(str.maketrans(',.', '.,'))


def build(fonts, base, output):
    result = json.loads((REPORT/'results.json').read_text())
    gallery = json.loads((REPORT/'gallery.json').read_text())
    m = result['models']['yolo']['metrics']
    for name,file in [('DV','DejaVuSans.ttf'),('DV-Bold','DejaVuSans-Bold.ttf')]:
        pdfmetrics.registerFont(TTFont(name,str(fonts/file)))
    pdfmetrics.registerFontFamily('DV',normal='DV',bold='DV-Bold')
    body=ParagraphStyle('body',fontName='DV',fontSize=10.3,leading=15.7,textColor=colors.HexColor(NAVY),spaceAfter=8)
    small=ParagraphStyle('small',parent=body,fontSize=8.7,leading=12.5)
    label=ParagraphStyle('label',parent=body,textColor=colors.HexColor(TEAL),fontName='DV-Bold',fontSize=9,spaceAfter=8)
    title=ParagraphStyle('title',parent=body,fontName='DV-Bold',fontSize=22,leading=28,spaceAfter=13)
    sub=ParagraphStyle('sub',parent=body,fontName='DV-Bold',fontSize=12,leading=16,spaceBefore=8)
    story=[]
    def add(s,style=body):
        story.append(Paragraph(s,style))
    def table(vals,widths):
        tab=Table([[Paragraph(str(v),small) for v in row] for row in vals],colWidths=widths,hAlign='LEFT')
        tab.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor(MIST)),
            ('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),
            ('LINEBELOW',(0,0),(-1,-1),.4,colors.HexColor('#D6E3E8'))]))
        story.extend([tab,Spacer(1,10)])

    add('CHẶNG 1 / PHỤ LỤC / 18.11.2026',label)
    add('Đánh giá SAR có tọa độ',title)
    add('Đối chứng OpenSAR Insight SLC VV bổ sung phép đo theo mét và diện tích biển. '
        f'Giữ nguyên checkpoint LS-SSDD, chọn ngưỡng từ {result["val_chips"]} ô validation, '
        f'đo trên {result["test_chips"]} ô từ {result["test_scene_count"]} lượt chụp test tại Tây Phi. '
        'Không dùng dữ liệu OpenSAR để huấn luyện.')
    table([['Nhãn trong vùng biển','Điểm không khớp nhãn','Trong 500 m từ bờ'],
           [f'<b>{m["true_positive"]}/{m["n_ground_truth"]} khớp</b><br/>Recall {vn(100*m["recall"])}% tại IoU ≥ 0,50',
            f'<b>{vn(m["benchmark_unmatched_per_km2"],4)}/km²</b><br/>{m["false_positive"]} điểm trên {vn(m["evaluated_water_scene_km2"])} km² biển ước tính',
            f'<b>{m["by_distance_to_mapped_shore_m"]["500"]["matched"]}/{m["by_distance_to_mapped_shore_m"]["500"]["labels"]} khớp</b><br/>Mẫu nhỏ, không suy rộng']],[156,168,151])
    add('Đối chứng cùng CPU bốn luồng',sub)
    vals=[['Phương án','Precision','Recall','AP50','Không khớp/km²','ms/ảnh p50']]
    for k,n in [('yolo','YOLO11n LS-SSDD'),('global_threshold','Ngưỡng sáng'),('local_contrast','Tương phản cục bộ')]:
        q=result['models'][k]['metrics']
        vals.append([n,vn(100*q['precision'])+'%',vn(100*q['recall'])+'%',vn(q['mAP@0.5'],4),
                     vn(q['benchmark_unmatched_per_km2'],4),vn(q['latency_ms_p50'])])
    table(vals,[111,66,57,59,93,89])
    add('Ngưỡng sáng tạo 354.714 điểm không khớp nhãn; tương phản cục bộ ở ngưỡng đã khóa không tìm được tàu. '
        'Đây là hai mốc cơ sở đơn giản. Độ trễ tính tiền xử lý và lọc, không tính đọc ảnh. AP tích phân VOC.',small)
    add('Các phép đo mét trả lời những câu hỏi khác nhau',sub)
    vals=[['So với tham chiếu nào?', 'Trung vị', 'p95']]
    for k,n in [('projected_box_center_error_m','Tâm hộp dự đoán so với tâm hộp nhãn'),
                ('projected_box_width_error_m','Sai lệch chiều ngang hộp ảnh'),
                ('projected_box_height_error_m','Sai lệch chiều dọc hộp ảnh'),
                ('error_to_source_wgs84_centroid_m','Tâm dự đoán so với tọa độ WGS84 trong nhãn')]:
        vals.append([n,vn(m[k]['median'])+' m',vn(m[k]['p95'])+' m'])
    table(vals,[303,85,87])
    add(f'Số đo chỉ trên {m["projected_box_center_error_m"]["n"]} hộp khớp. Nội suy bốn góc ảnh có sai lệch trung vị '
        f'{vn(m["transform_residual_at_source_centroid_m"]["median"])} m so với tâm WGS84 của chính nhãn. '
        'Không coi sai số hộp là độ chính xác GPS, chiều dài thân tàu hay giá trị kiểm định độc lập.',small)
    story.append(PageBreak())

    add('CHẶNG 1 / PHỤ LỤC / 18.11.2026',label)
    add('Các ca lỗi và cách kiểm tra lại',title)
    pics=[]
    captions=[]
    for r in gallery[:2]:
        pics.append(Image(str(REPORT/r['file']),width=225,height=225*604/512))
        captions.append(Paragraph(f'<b>Ô {r["id"]}</b> · {r["fp"]} điểm không khớp, {r["fn"]} nhãn bỏ sót.'+
                                  (f' {r["nearshore_missed"]} nhãn bỏ sót cách bờ không quá 500 m.' if r['nearshore_missed'] else ''),small))
    story.append(Table([pics,captions],colWidths=[237.5]*len(pics),hAlign='LEFT',style=[('VALIGN',(0,0),(-1,-1),'TOP')]))
    add('Lam: nhãn nguồn. Cam: dự đoán khớp. Đỏ: dự đoán không khớp nhãn. Các ảnh trên được chọn theo số lỗi, không phải mẫu điển hình của toàn bộ vùng.',small)
    add('Giữ riêng cảnh, ngày chụp và vùng dùng để chọn ngưỡng',sub)
    add('Đối chiếu footprint gốc của bảy sản phẩm LS-SSDD đã dùng với danh mục ASF. Loại một cảnh Biển Bắc có vùng cách chưa tới 10 km; '
        'cách ly các ô validation trong 20 km quanh hai cảnh test. Sau sàng lọc, kiểm tra SHA-256 pixel và dHash không thấy cặp qua hai tập.')
    add('Mẫu số là phần biển của ô SLC sau khi trừ đất và pixel rỗng, không đếm lại vùng chồng trong cùng lượt chụp. '
        'Đường bờ từ GSHHG 2.3.7. “Không khớp” nghĩa là không khớp nhãn công bố, không phải xác minh từng tàu ngoài thực địa. '
        'Bản đồ demo hiện vẫn loại dải 500 m; phép thử đánh giá ứng viên YOLO không loại dải đó.')
    add('Còn cần kiểm chứng',sub)
    add('Xác nhận ca thật với người có chuyên môn và nguồn định vị độc lập. Ưu tiên thêm cảnh ven bờ, nhãn hộp được kiểm thủ công, '
        'đối chứng SAR mạnh hơn; chưa thay checkpoint của bản đồ công khai.')
    add('Nguồn: OpenSAR Insight (Indra Space, INTA, Universidad de Alcalá; ESA Φ-lab, kho dữ liệu MIT); '
        'contains modified Copernicus Sentinel data. Footprint ASF và đường bờ GSHHG. Protocol, checksum, dự đoán và mã tái lập nằm trong ZIP.',small)
    base_pages=len(PdfReader(base).pages)
    def footer(c,doc):
        c.setFillColor(colors.HexColor(TEAL)); c.setFont('DV',8)
        c.drawString(56,26,'SONARNET-VN  /  BẰNG CHỨNG KỸ THUẬT')
        c.drawRightString(540,26,str(base_pages+doc.page))
    pages=BytesIO()
    SimpleDocTemplate(pages,pagesize=A4,leftMargin=55,rightMargin=55,topMargin=42,bottomMargin=43).build(story,onFirstPage=footer,onLaterPages=footer)
    pages.seek(0)
    if len(PdfReader(pages).pages)!=2:
        raise ValueError('Unexpected appendix pagination')
    pages.seek(0)
    writer=PdfWriter()
    writer.append(base)
    writer.append(pages,outline_item='Phụ lục OpenSAR Insight - Đối chứng có tọa độ')
    writer.add_metadata({'/Title':'SonarNet-VN - Báo cáo cải tiến Chặng 1 và phụ lục SAR có tọa độ'})
    writer.write(output)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for opt in ('font-dir','base','output'):
        p.add_argument('--'+opt,type=Path,required=True)
    args=p.parse_args()
    build(args.font_dir,args.base,args.output)
