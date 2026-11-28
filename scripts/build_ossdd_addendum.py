"""Append the dated external SAR result to the existing competition report."""
from io import BytesIO
import argparse
import json
from pathlib import Path
import os

from pypdf import PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.enums import TA_JUSTIFY
from document_format import register_document_fonts, page_number
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'reports/final/ossdd_transfer_20261118'
PDF = Path(os.environ.get('SONARNET_CHANG1_PDF_DIR', str(ROOT / 'output/pdf')))
NAVY, TEAL, MIST = '#102B40', '#007F86', '#EAF4F6'


def main(fonts):
    data = json.loads((RESULTS / 'results.json').read_text())
    check = json.loads((RESULTS / 'sensitivity_exclude_flagged_chip.json').read_text())
    register_document_fonts('DV','DV-Bold')
    body = ParagraphStyle('BodyVI', fontName='DV', fontSize=10.2, leading=15.2,
                          textColor=colors.black, spaceAfter=9)
    note = ParagraphStyle('NoteVI', parent=body, fontSize=8.2, leading=11.5)
    label = ParagraphStyle('LabelVI', parent=body, fontName='DV-Bold', fontSize=9,
                           textColor=colors.black, spaceAfter=7)
    title = ParagraphStyle('TitleVI', parent=body, fontName='DV-Bold', fontSize=15, leading=19)
    story = [Paragraph('CHẶNG 1 / PHỤ LỤC / 18.11.2026', label),
             Paragraph('Khi đổi nguồn ảnh SAR', title)]

    def add(text, style=body):
        story.append(Paragraph(text, style))

    def num(value, digits=2):
        return f'{value:,.{digits}f}'.replace(',', '@').replace('.', ',').replace('@', '.')

    models = data['models']
    y = models['yolo']
    ym = y['overall']
    land = y['by_source_land_category']['land']
    water = y['by_source_land_category']['water']
    add('Cùng checkpoint YOLO, thử trên OSSDD với 200 ảnh để chọn ngưỡng và 400 ảnh để đo. '
        'Không huấn luyện trên OSSDD. Khóa cấu hình trước khi đọc ảnh test; so với hai phương án '
        'chọn ngưỡng trên cùng validation và chạy cùng CPU 4 luồng.')
    values = [['Phương án', 'Precision', 'Recall', 'AP50', 'Báo nhầm', 'ms/ảnh']]
    for ident, name in [('yolo', 'YOLO11n LS-SSDD'), ('global_threshold', 'Ngưỡng sáng'),
                        ('local_contrast', 'Tương phản cục bộ')]:
        m = models[ident]['overall']
        values.append([name, num(100*m['precision'])+'%', num(100*m['recall'])+'%',
                       num(m['mAP@0.5'], 4), num(m['false_positive'], 0), num(m['latency_ms_median'])])
    table = Table([[Paragraph(v, note) for v in row] for row in values],
                  colWidths=[128, 67, 62, 65, 75, 78], hAlign='LEFT')
    table.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.45,colors.black),
        ('TEXTCOLOR',(0,0),(-1,-1),colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
    story.extend([table, Spacer(1, 10)])
    add(f'<b>Giảm việc rà điểm, nhưng bỏ sót còn nhiều.</b> Trong {num(ym["n_ground_truth"],0)} nhãn, YOLO '
        f'tìm đúng {num(ym["true_positive"],0)}; recall nhóm ảnh có đất {num(land["recall"]*100)}%, '
        f'nhóm nước {num(water["recall"]*100)}%. Nhóm có đất là nhãn của ảnh mẹ, không phải khoảng cách từ tàu tới bờ.')
    story.append(Image(str(RESULTS / 'duplicate_triage_pair.png'), width=475, height=475*546/1024))
    add(f'Hai ảnh khác tiền tố cảnh nhưng có địa vật tương đồng. Không trùng pixel. '
        f'Bỏ ảnh test bị đánh dấu (còn {check["remaining_test_chips"]} ảnh), F1 YOLO '
        f'{num(ym["f1"],4)} → {num(check["models"]["yolo"]["f1"],4)}; chưa xác nhận độc lập theo vùng/ngày.', note)
    add('<b>Giới hạn vật lý.</b> TIFF không có địa tham chiếu. Spacing 10 m của nguồn chỉ dùng cho '
        'quy đổi danh định trong mặt phẳng ảnh; không dùng làm km² biển hữu hiệu, vị trí tuyệt đối '
        'hay kích thước thân tàu. Báo nhầm và bỏ sót đo theo nhãn công bố.')
    add('Nguồn: Hammer và cộng sự, arXiv:2608.01963v1, OSSDD. Contains modified Copernicus Sentinel data. '
        'Nhãn và ảnh điều chỉnh trong phụ lục: CC BY-NC-SA 4.0. Xem predictions, checksum và protocol trong ZIP.', note)
    add('Trạng thái 18/11: đã xác nhận trang Minh chứng cải tiến trên demo công khai. '
        'Phụ lục cập nhật trạng thái triển khai của báo cáo ngày 17/11; hồ sơ chưa nộp cổng BTC.', note)
    overlay = BytesIO()
    SimpleDocTemplate(overlay, pagesize=A4, leftMargin=55, rightMargin=55,
                      topMargin=42, bottomMargin=35).build(story)
    overlay.seek(0)
    writer = PdfWriter()
    writer.append(PDF / 'SonarNet_Bao_cao_cai_tien_Chang1.pdf')
    writer.append(overlay, outline_item='Phụ lục 18/11/2026 - Đối chứng chuyển nguồn SAR')
    writer.add_metadata({'/Title': 'SonarNet-VN - Báo cáo cải tiến Chặng 1 và phụ lục SAR',
                         '/Subject': 'Bảng C - Cập nhật ngày 18/11/2026'})
    writer.write(PDF / 'SonarNet_Bao_cao_Chang1_Cap_nhat_20261118.pdf')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--font-dir', required=True, type=Path,
                        help='Directory containing DejaVuSans.ttf and DejaVuSans-Bold.ttf')
    main(parser.parse_args().font_dir)
