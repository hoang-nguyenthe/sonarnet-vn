"""Build the 20-page judge edition and draw the SAR/AIS comparison charts."""

import argparse
from io import BytesIO
import json
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.graphics.shapes import Circle, Drawing, Line, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

INK = colors.HexColor('#102b40')
TEAL = colors.HexColor('#007f86')
MUTED = colors.HexColor('#526579')
GRID = colors.HexColor('#d8e5eb')
BG = colors.HexColor('#eaf4f5')
ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'reports/final/vietnam_rtc_transfer_20261119/ais-box-dimensions/results.json'
PAGES = (*range(14), 18, 19, 22, 24)
WIDTH = 477


def fmt(value):
    return f'{value:,.1f}'.translate(str.maketrans(',.', '.,'))


def plot(results):
    """Use the same units on both axes within each panel."""
    pairs = [p for scene in results['scenes'] for p in scene['modes']['0.35']['pairs']
             if p['noaa_dimensions_m'] is not None]
    figure = Drawing(WIDTH, 181)
    for panel, title in enumerate(('Chiều dài', 'Chiều rộng')):
        origin_x, origin_y, side = 42 + panel * 240, 35, 113
        upper = max(max(p['box_axes_m'][panel], p['noaa_dimensions_m'][panel]) for p in pairs)
        limit = 100 * (int(upper / 100) + 1)
        figure.add(String(origin_x, 166, title, fontName='SonarBold', fontSize=10, fillColor=INK))
        for offset in range(5):
            value = limit * offset / 4
            tick = side * offset / 4
            figure.add(Line(origin_x, origin_y + tick, origin_x + side, origin_y + tick, strokeColor=GRID))
            figure.add(Line(origin_x + tick, origin_y, origin_x + tick, origin_y + side, strokeColor=GRID))
            figure.add(String(origin_x + tick, origin_y - 14, f'{value:g}', textAnchor='middle',
                              fontName='Sonar', fontSize=7.5, fillColor=MUTED))
            figure.add(String(origin_x - 7, origin_y + tick - 3, f'{value:g}', textAnchor='end',
                              fontName='Sonar', fontSize=7.5, fillColor=MUTED))
        figure.add(Line(origin_x, origin_y, origin_x + side, origin_y + side, strokeColor=MUTED,
                        strokeDashArray=[2, 3]))
        for p in pairs:
            x = origin_x + side * p['noaa_dimensions_m'][panel] / limit
            y = origin_y + side * p['box_axes_m'][panel] / limit
            figure.add(Circle(x, y, 3.1, fillColor=TEAL, strokeColor=colors.white, strokeWidth=.55))
        figure.add(String(origin_x + side / 2, 3, 'Metadata AIS (m)', textAnchor='middle',
                          fontName='Sonar', fontSize=8, fillColor=INK))
        figure.add(String(origin_x, 153, 'Hộp SAR (m)', fontName='Sonar', fontSize=8, fillColor=INK))
    return figure


def build(base, regular, bold, output):
    for name, source in (('Sonar', regular), ('SonarBold', bold)):
        pdfmetrics.registerFont(TTFont(name, str(source)))
    pdfmetrics.registerFontFamily('Sonar', normal='Sonar', bold='SonarBold')
    normal = ParagraphStyle('body', fontName='Sonar', fontSize=10.5, leading=15.2, textColor=INK, spaceAfter=9)
    small = ParagraphStyle('caption', parent=normal, fontSize=8.5, leading=12, textColor=MUTED)
    label = ParagraphStyle('label', parent=normal, fontName='SonarBold', fontSize=9, textColor=TEAL)
    title = ParagraphStyle('title', parent=normal, fontName='SonarBold', fontSize=24, leading=29, spaceAfter=13)
    heading = ParagraphStyle('heading', parent=normal, fontName='SonarBold', fontSize=13, leading=17, spaceBefore=8)
    story = []

    def add(text, style=normal):
        story.append(Paragraph(text, style))

    def table(rows, widths):
        cells = [[Paragraph(str(cell), small) for cell in row] for row in rows]
        grid = Table(cells, colWidths=widths, hAlign='LEFT')
        grid.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), BG), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ('LINEBELOW', (0, 0), (-1, -1), .5, GRID),
        ]))
        story.extend((grid, Spacer(1, 12)))

    add('CHẶNG 1 / BẢNG C / 20.11.2026', label)
    add('Đối chiếu ba yêu cầu cải tiến', title)
    add('Đề Phiên bản 1 trong tài khoản của đội yêu cầu kiểm soát suy diễn khi thiếu dữ liệu, dùng độ tin cậy trong ghép AIS và kiểm định SAR độc lập. Bảng này trỏ tới bằng chứng chính trong bản nộp.')
    table([
        ['Yêu cầu trong đề', 'Bằng chứng có thể kiểm tra'],
        ['Tách trạng thái và yêu cầu người rà xác nhận', 'Trang 1 và 7. Mở hồ sơ SAR thật thiếu AIS. Thử ca không ghép được và ca kích thước mâu thuẫn. Ghi quyết định, căn cứ và người rà gắn với mã ảnh. Bản demo ghi tên tự khai.'],
        ['Dùng tuổi bản tin và độ bất định để ghép AIS', 'Trang 3, 5-7 và 13. Có ca hai tàu cắt nhau, thiếu/nhiễu AIS, bản tin cũ và sai số vị trí lớn. Đọc bảng số cặp đồng ý, sai và bị từ chối.'],
        ['Detector SAR độc lập và cùng phần cứng', 'Trang 2, 4 và 15-18. Cảnh, vùng và ngày dùng để học/chọn cấu hình được giữ riêng với tập chấm. Có mốc cơ sở chạy cùng CPU, mật độ không khớp theo diện tích, recall gần bờ, ảnh lỗi và độ trễ.'],
        ['Sai lệch vị trí và kích thước', 'Trang 17 so với nhãn tọa độ OpenSAR. Trang 20 đối chiếu tâm hộp và hai cạnh hộp với AIS lịch sử có điều kiện. Nhóm mốc ít dịch chuyển có kích thước trong metadata NOAA.'],
    ], [164, 313])
    add('Hồ sơ chạy thử và tái lập', heading)
    add('Ba trường bắt buộc trên cổng gồm mã nguồn HTTPS, sản phẩm chạy thử HTTPS và báo cáo cải tiến HTTPS. Mẫu kiểm tra ảnh cho phép tải PNG nguồn, các ảnh đánh dấu, JSON và bảng SHA-256. Các lệnh tái lập cùng dữ liệu chấm nằm trong thư mục <b>reports/final</b>.')
    add('Qua sáu lượt chụp cảng Mỹ giữ riêng, gộp thứ hạng YOLO và xView3 khớp 14/15 mốc so với 12/15 ở cùng 409 lượt rà. Cảnh ven biển Việt Nam dùng bộ nhãn điểm khác và cần kiểm tra thêm ở mức lượt rà nhỏ.')
    add('Mở <link href="https://hoang-nguyenthe.github.io/sonarnet-vn/#thu-hang" color="#007f86">bảng số liệu và hồ sơ mẫu</link> hoặc <link href="https://sonarnet.streamlit.app/?trang=minh-chung" color="#007f86">demo Streamlit</link>.', small)
    story.append(PageBreak())

    results = json.loads(RESULTS.read_text())
    add('ĐỐI CHIẾU SAR VÀ AIS NOAA / 20.11.2026', label)
    add('Hộp radar sai lệch bao nhiêu so với metadata tàu?', title)
    add('Chọn 15 mốc AIS ít dịch chuyển ở sáu lượt chụp Sentinel-1 RTC giữ riêng tại ba vùng cảng Mỹ. Chốt mốc trước khi suy luận. Chấm tâm hộp theo phép ghép một-một trong 100 m; báo số đo kích thước khi metadata có hai bản tin cùng báo cặp chiều dài và chiều rộng hợp lệ.')
    rows = [['Ngưỡng YOLO và lượt rà', 'Mốc khớp', 'Lệch tâm p50 / p90', 'Cặp có kích thước', 'MAE dài / rộng']]
    for threshold, values in results['totals'].items():
        distance, length, width = (values[k] for k in ('anchor_distance', 'length_error', 'width_error'))
        rows.append([
            threshold.replace('.', ',') + ' · ' + f'{values["candidates"]:,}'.replace(',', '.'),
            f'{values["matched"]}/{values["anchors"]}',
            f'{fmt(distance["median_absolute_m"])} / {fmt(distance["p90_absolute_m"])} m',
            values['size_pairs'], f'{fmt(length["mae_m"])} / {fmt(width["mae_m"])} m',
        ])
    table(rows, [104, 55, 110, 79, 129])
    story.append(plot(results))
    add('Mỗi điểm là một cặp ghép ở ngưỡng 0,35. Đường chấm biểu diễn hai số đo bằng nhau. MAE là sai số tuyệt đối trung bình.', small)
    add('Dùng kết quả để rà soát', heading)
    add('Đo hai cạnh hộp chữ nhật theo WGS84 và đối chiếu với chiều dài, chiều rộng trong metadata NOAA. Cạnh hộp phụ thuộc hướng tàu, vệt phản xạ và các vật thể xung quanh. Độ lệch tâm chịu ảnh hưởng của vị trí anten và thời điểm AIS. Với các sai lệch đo được, cạnh hộp phù hợp để hỗ trợ rà ảnh. Kích thước thân tàu cần nguồn xác nhận độc lập.')
    add('<link href="https://www.fisheries.noaa.gov/inport/item/73064" color="#007f86">NOAA 2024</link> và Sentinel-1 RTC. Tệp kết quả theo cảnh, ngưỡng và từng cặp nằm tại <b>reports/final/vietnam_rtc_transfer_20261119/ais-box-dimensions</b>.', small)

    def footer(canvas, document):
        canvas.setFillColor(TEAL)
        canvas.setFont('Sonar', 8)
        canvas.drawString(55, 27, 'SONARNET-VN  /  BÁO CÁO CẢI TIẾN CHẶNG 1')
        canvas.drawRightString(540, 27, str(len(PAGES) + document.page))

    buffer = BytesIO()
    SimpleDocTemplate(buffer, pagesize=A4, leftMargin=53, rightMargin=53, topMargin=43, bottomMargin=39
                      ).build(story, onFirstPage=footer, onLaterPages=footer)
    buffer.seek(0)
    appendix = PdfReader(buffer)
    if len(appendix.pages) != 2:
        raise ValueError('Expected exactly two pages for the closing evidence')
    source = PdfReader(base)
    writer = PdfWriter()
    for ordinal, index in enumerate(PAGES, start=1):
        page = source.pages[index]
        if index >= 14:
            overlay = BytesIO()
            stamp = Canvas(overlay, pagesize=(float(page.mediabox.width), float(page.mediabox.height)))
            stamp.setFillColor(colors.white)
            stamp.rect(500, 16, 53, 29, fill=1, stroke=0)
            stamp.setFillColor(TEAL)
            stamp.setFont('Sonar', 8)
            stamp.drawRightString(540, 27, str(ordinal))
            stamp.save()
            overlay.seek(0)
            page.merge_page(PdfReader(overlay).pages[0])
        writer.add_page(page)
    writer.append(appendix, outline_item='Đối chiếu yêu cầu và đo kích thước')
    writer.add_metadata({'/Title': 'SonarNet Việt Nam - Báo cáo cải tiến Chặng 1'})
    writer.write(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('base', 'regular', 'bold', 'output'):
        parser.add_argument('--'+flag, type=Path, required=True)
    options = parser.parse_args()
    build(options.base, options.regular, options.bold, options.output)
