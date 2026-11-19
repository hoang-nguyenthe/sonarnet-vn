"""Build the Chặng 1 report update from saved evaluation outputs."""
import argparse
import csv
from io import BytesIO
import json
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT/'reports/final/opensar_adaptation_20261118'
INK, TEAL, DIM, PALE = map(HexColor, ('#102e40', '#087772', '#41606b', '#eaf5f3'))
WHITE = HexColor('#ffffff')


def fmt(x, places=0):
    return f'{x:,.{places}f}'.translate(str.maketrans(',.', '.,'))


def fraction(m):
    return f"{m['true_positive']}/{m['n_ground_truth']}"


def coast(m):
    c = m['by_distance_to_mapped_shore_m']['500']
    return f"{c['matched']}/{c['labels']}"


def build(args):
    for font, file in [('Body', 'DejaVuSans.ttf'), ('Heavy', 'DejaVuSans-Bold.ttf')]:
        pdfmetrics.registerFont(TTFont(font, str(args.font/file)))
    pdfmetrics.registerFontFamily('Body', normal='Body', bold='Heavy')
    normal = ParagraphStyle('body', fontName='Body', fontSize=10, leading=15, textColor=INK)
    muted = ParagraphStyle('muted', parent=normal, fontSize=9, leading=13, textColor=DIM)
    sub = ParagraphStyle('subtitle', parent=normal, fontName='Heavy', fontSize=12.7, leading=17, textColor=TEAL)
    title = ParagraphStyle('title', parent=sub, fontSize=23, leading=29, textColor=INK)
    cell = ParagraphStyle('cell', parent=normal, fontSize=8.2, leading=11)
    text_source = EVIDENCE/'results.json'
    test = json.loads(text_source.read_text())['evaluation']
    budgets = json.loads((EVIDENCE/'coastal-budget/results.json').read_text())['evaluation']
    with (ROOT/'reports/final/ais_trajectories_guard_20261118/summary.csv').open() as file:
        ais = list(csv.DictReader(file))
    noaa = ROOT/'reports/final/noaa_ais_replay_20261118'
    development = json.loads((noaa/'development/results.json').read_text())
    confirmation = json.loads((noaa/'confirmation/results.json').read_text())
    coincident_dir = ROOT/'reports/final/coincident_sar_ais_20261118'
    coincident = json.loads((coincident_dir/'results.json').read_text())
    assignment_dir = ROOT/'reports/final/ais_preserve_proposal_20261118'
    assignment_dev = json.loads((assignment_dir/'development.json').read_text())
    assignment_test = json.loads((assignment_dir/'held_out.json').read_text())['days']['2024-12-13']
    old = test['diagnostic']['models']['reference_ls_ssdd']['metrics']
    new = test['diagnostic']['models']['adapted_slc_vv']['metrics']
    north = test['north_sea']['models']['adapted_slc_vv']['metrics']
    north_short = budgets['north_sea']['metrics']
    multiscale = ROOT/'reports/final/sar_multiscale_20261118'
    retest_path = multiscale/'results.json'
    retest = json.loads(retest_path.read_text())['evaluation'] if retest_path.is_file() else None
    extra_controls = json.loads((multiscale/'threshold-and-coast.json').read_text())['evaluation'] if retest else None
    local_path = ROOT/'reports/final/vietnam_rtc_recall_20261118/results.json'
    local = json.loads(local_path.read_text()) if local_path.is_file() else None
    fresh_path = ROOT/'reports/final/vietnam_rtc_ranking_20261118/results.json'
    fresh = json.loads(fresh_path.read_text()) if fresh_path.is_file() else None
    polar_path = ROOT/'reports/final/vietnam_rtc_vv_vh_20261118/results.json'
    polar = json.loads(polar_path.read_text()) if polar_path.is_file() else None
    example_path = fresh_path.with_name('example.png')
    contrast_path = ROOT/'reports/final/vietnam_rtc_contrast_20261119/results.json'
    tta_path = ROOT/'reports/final/vietnam_rtc_tta_20261119/results.json'
    equal_review_plot = tta_path.with_name('equal-review.png')
    equal_review = contrast_path.is_file() and tta_path.is_file() and equal_review_plot.is_file()
    total_update_pages = 7 + bool(retest) + bool(local) + bool(fresh) + bool(polar) + equal_review
    b = BytesIO()
    c = Canvas(b, pagesize=A4)

    def text(value, y, style=normal, x=47, width=501):
        p = Paragraph(value, style)
        _, height = p.wrap(width, 700)
        p.drawOn(c, x, y-height)
        return y-height

    def table(values, widths, y):
        t = Table([[Paragraph(str(v), cell) for v in row] for row in values], colWidths=widths)
        t.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), PALE),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [WHITE, HexColor('#f5f8f8')]),
            ('TOPPADDING', (0,0), (-1,-1), 6), ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('VALIGN', (0,0), (-1,-1), 'TOP')]))
        _, h = t.wrap(501, 700)
        t.drawOn(c, 47, y-h)
        return y-h

    def header(label, heading):
        c.setFillColor(TEAL)
        c.setFont('Heavy', 9)
        c.drawString(47, 798, label)
        return text(heading, 772, title)-10

    def footer(number):
        c.setStrokeColor(HexColor('#c5dbdf'))
        c.line(47, 48, 548, 48)
        c.setFillColor(DIM)
        c.setFont('Body', 8)
        c.drawString(47, 32, 'SONARNET VIỆT NAM  /  CHẶNG 1  /  19.11.2026')
        c.drawRightString(548, 32, f'Bản cập nhật {number}/{total_update_pages}')
        c.showPage()

    c.setFillColor(INK)
    c.rect(0, 651, A4[0], A4[1]-651, stroke=0, fill=1)
    c.setFillColor(HexColor('#a6e5dd'))
    c.setFont('Heavy', 9.4)
    c.drawString(47, 800, 'SONARNET VIỆT NAM  /  VÒNG CHUNG KẾT  /  BẢNG C')
    c.setFillColor(WHITE)
    c.setFont('Heavy', 26)
    c.drawString(47, 752, 'Báo cáo cải tiến Chặng 1')
    c.setFont('Body', 12)
    c.drawString(47, 716, 'Ảnh SAR thật, ghép AIS có điều kiện, kết quả đo được')
    c.setFillColor(HexColor('#a6e5dd'))
    c.setFont('Body', 9)
    c.drawString(47, 684, 'Đề riêng phiên bản 1  ·  Hạn 23:59 ngày 26/11/2026 (giờ Việt Nam)')
    y = text('Một điểm trên bản đồ chỉ hữu ích khi người xem mở được ảnh nguồn, biết phần nào đã được kiểm tra và biết vì sao hệ thống giữ lại hay từ chối cặp ghép.', 628)
    for i,(label, value) in enumerate([
            ('Nhãn SAR khớp · ba cảnh', f"{fraction(old)} → {fraction(new)}"),
            ('Nhãn khớp trong 500 m từ bờ', f"{coast(old)} → {coast(new)}"),
            ('Ghép AIS sai · ngày giữ riêng', '32 → 0')]):
        x = 47+169*i
        c.setFillColor(PALE)
        c.roundRect(x, 513, 163, 62, 8, stroke=0, fill=1)
        text(label, 562, muted, x+10, 148)
        text(value, 542, sub, x+10, 148)
    y = 493
    items = [
        ('Trạng thái khi dữ liệu thiếu hoặc mâu thuẫn',
         'Hồ sơ ảnh thật cell_0_1 giữ ảnh nguồn, ngày chụp, SHA-256, trạng thái thiếu AIS và chờ xác minh. Mở trực tiếp từ Minh chứng cải tiến. Mô phỏng riêng trường hợp mất AIS, kích thước mâu thuẫn và quỹ đạo giao nhau.'),
        ('Ghép AIS có cơ chế giữ lại hồ sơ cần rà soát',
         'Giữ nguyên đề xuất ban đầu khi bản tin quá cũ, quá nhiễu hoặc có cạnh tranh. So sánh trên mô phỏng, bản tin AIS giữ lại và một cảnh Sentinel-1 có AIS cùng giờ. Kết quả 32 → 0 là số ca sai trong phép phát lại AIS của ngày giữ riêng.'),
        ('Đánh giá độc lập và tải rà soát theo diện tích',
         'Huấn luyện mới trên 1.669 ô SLC VV. So sánh trên ba cảnh đối chiếu và một cảnh Biển Bắc giữ riêng. Đo điểm không khớp/km², recall ven bờ, độ trễ và sai lệch hộp theo mét. Phép phát lại dành một phần lượt cho vùng sát bờ.')
    ]
    if retest:
        diagnostic_methods = retest['diagnostic']['methods']
        north_sea_methods = retest['north_sea']['methods']
        items.append(('Tăng recall bằng cách đọc SAR ở hai tỷ lệ',
            f"Trên bốn cảnh chấm lại, số nhãn khớp tăng từ {fraction(diagnostic_methods['baseline']['full'])} lên "
            f"{fraction(diagnostic_methods['candidate']['full'])} và từ {fraction(north_sea_methods['baseline']['full'])} lên "
            f"{fraction(north_sea_methods['candidate']['full'])}. Trang 8 trình bày thêm tải rà soát và tác động khi chỉ hạ ngưỡng."))
    for heading, description in items:
        y = text(heading, y, sub)-5
        y = text(description, y)-17
    if local:
        y = text('Đã đối chiếu điểm trên ảnh ven biển Việt Nam. Kết quả cho biết độ phủ trên ô có nhãn, '
                 'chưa xác nhận danh tính hay hỗ trợ suy rộng ra toàn bản đồ. '
                 'Xem số liệu tại trang 9' + (' và đối chứng cùng số lượt rà tại trang 12.' if equal_review else '.'), y, muted)
    else:
        y = text('Kết quả trên nhãn ảnh nguồn phục vụ rà soát. Cần đối chứng tại Việt Nam và xác nhận '
                 'của người có chuyên môn trước khi dùng mô hình mới cho nghiệp vụ.', y, muted)
    y = text('Các phép đo trước nằm ở phụ lục và giữ số trang ban đầu. Trang Minh chứng cải tiến có bản so sánh, ca lỗi và tệp tải xuống.', y-12, muted)
    assert y > 77
    c.setFillColor(TEAL)
    c.setFont('Heavy', 8)
    for x, label, url in [(47,'MÃ NGUỒN','https://github.com/hoang-nguyenthe/sonarnet-vn'),
                          (151,'DEMO','https://sonarnet.streamlit.app/?trang=minh-chung'),
                          (227,'CỔNG CHẶNG 1','https://ai.tainangviet.vn/dashboard/final')]:
        c.drawString(x, 66, label)
        c.linkURL(url,(x,63,x+pdfmetrics.stringWidth(label,'Heavy',8),74),relative=0)
    footer(1)

    y = header('KIỂM ĐỊNH ẢNH THẬT', 'Giảm bỏ sót và giới hạn tải rà soát')
    y = text('Tập học 1.669 ô thuộc 7 cảnh, gồm 1.086 ô nền. Tập chọn 48 ô thuộc một cảnh riêng. Khởi tạo YOLO11n COCO, dừng sớm ở epoch 9, chọn ngưỡng 0,025 trước khi chấm. Tách ngày, kiểm khoảng cách 20 km và kiểm SHA-256 pixel/dHash trước huấn luyện.', y)-10
    rows = [['Nhóm và phương pháp', 'Nhãn khớp', 'Không khớp', '≤500 m', 'Không khớp/km²']]
    for name, m in [
            ('3 cảnh · YOLO LS-SSDD',old),('3 cảnh · YOLO SLC VV',new),
            ('3 cảnh · Giới hạn, ưu tiên bờ',budgets['diagnostic']['metrics']),
            ('Biển Bắc · CFAR',test['north_sea']['models']['guard_ring_cfar']['metrics']),
            ('Biển Bắc · YOLO SLC VV',north),('Biển Bắc · Giới hạn, ưu tiên bờ',north_short)]:
        rows.append([name,fraction(m),m['false_positive'],coast(m),fmt(m['benchmark_unmatched_per_km2'],4)])
    y = table(rows, [195,66,69,57,114], y)-11
    y = text(f"Ba cảnh có {fmt(new['evaluated_water_scene_km2'],2)} km² biển theo lượt chụp. Biển Bắc là một cảnh chưa từng chấm, có {fmt(north['evaluated_water_scene_km2'],2)} km². Danh sách tối đa 1 ứng viên/20 km² dành trước 20% lượt cho dải 500 m. Phép phát lại giữ {coast(north_short)} nhãn ven bờ ở Biển Bắc và giảm tổng nhãn khớp còn {fraction(north_short)}.", y, muted)-9
    y = text('Trên 51 hộp khớp của ba cảnh, sai lệch trung vị là 18,54 m ở tâm, 18,27 m theo chiều ngang và 28,02 m theo chiều dọc. CPU 4 luồng đạt 43,02/45,04 ms trung vị/p95, so với 59,35/62,36 ms của YOLO LS-SSDD. Diện tích và hộp tính từ hình học ảnh, chưa đối chiếu GPS hoặc thân tàu độc lập.', y, muted)-10
    img_width = 440
    img_height = img_width*626/1032
    c.drawImage(str(EVIDENCE/'comparison_diagnostic.png'), 47, y-img_height, img_width, img_height)
    y = text('Hình chọn theo mức tăng số nhãn khớp. Lam là nhãn gốc, cam là hộp khớp, đỏ là hộp không khớp. Ca lỗi Biển Bắc có trong thư mục kết quả.', y-img_height-6, muted)
    assert y > 57, y
    footer(2)

    y = header('ĐỐI CHỨNG MÔ PHỎNG · CỔNG LỌC TRƯỚC', 'Một cặp gần nhất vẫn có thể là cặp sai')
    y = text('Chuỗi bản tin bị lệch đều có thể cho độ bất định thấp khi nội suy Kalman. Đối chứng dùng cùng 840 kịch bản, gồm bản tin xen kẽ tốt/cũ/nhiễu, nhiễu SAR gần mục tiêu và hai mức lệch vị trí thiết kế. Ghi riêng số ghép đúng, ghép nhầm mục tiêu và ghép nhầm nhiễu.', y)-11
    agg = {}
    for method in ('distance_only','quality_gated_previous','quality_gated'):
        pick = [r for r in ais if r['method']==method]
        agg[method] = [fmt(sum(int(r[key]) for r in pick)) for key in
                       ('links_correct','links_wrong','links_to_clutter')]
    rows = [['Phương pháp', 'Ghép đúng', 'Ghép nhầm mục tiêu', 'Ghép nhầm nhiễu']]
    for label, name in [('Khoảng cách gần nhất', 'distance_only'), ('Cổng tin cậy trước cải tiến','quality_gated_previous'),
                        ('Cổng có kiểm tra độ nhạy','quality_gated')]:
        rows.append([label, *agg[name]])
    y = table(rows, [219,75,105,102], y)-14
    y = text('Tình huống có thể tự kiểm tra', y, sub)-6
    y = text('Hai điểm SAR ở −70 m và +70 m. Hai chuỗi AIS tương ứng lệch 160 m trái chiều. Khoảng cách tới tàu sai chỉ 20 m, tới tàu đúng 160 m. Với sigma AIS 20 m, ngưỡng gốc xấp xỉ 108 m. Phép thử độ nhạy xem thêm ứng viên trong 100 m kế tiếp. Khi thứ tự có thể đảo, SonarNet giữ ca ở trạng thái chưa ghép.', y)-12
    y = text('Lệch 128–185 m: giảm 240 → 0 ghép sai. Lệch 208–242 m: còn 130 ghép sai. Toàn bộ phép thử giữ ít hơn 51 cặp đúng. Đây là dữ liệu mô phỏng, chưa dùng biên 100 m để xác nhận danh tính thực.', y)-15
    y = text('Tái lập từ gói mã nguồn', y, sub)-6
    y = text('<b>AIS.</b> Chạy scripts/evaluate_ais_trajectories.py với thư mục đầu ra mới. Tệp cases.json.gz có thời gian AIS, vị trí, trạng thái và kết quả từng phép thử.', y)-7
    y = text('<b>SAR.</b> Dùng README trong reports/final/opensar_adaptation_20261118 để tái lập chuẩn bị ảnh, huấn luyện, đối chứng, giới hạn rà soát và hình minh họa. Tệp protocol.json và operating_point.json giữ checksum và cấu hình khóa.', y)-7
    y = text('<b>Khai báo.</b> OpenAI Codex hỗ trợ sửa mã, thử nghiệm, tạo hình và chuẩn bị báo cáo. Các số lấy từ tệp thực nghiệm. Nguồn ảnh Copernicus Sentinel-1, nhãn OpenSAR Insight và đường bờ GSHHG 2.3.7. Nhóm nộp xác minh quyền mở ba liên kết HTTPS và chịu trách nhiệm về cam kết trên cổng.', y)-9
    y = text('Để kiểm tra bản triển khai, mở Minh chứng cải tiến và tìm ca giữ nguyên cặp AIS đề xuất cùng phép thử ảnh Sentinel-1 có AIS đúng lượt chụp. Mục đầu của hồ sơ cung cấp liên kết demo và mã nguồn.', y, muted)
    assert y > 67, y
    footer(3)

    y = header('THIẾT KẾ KIỂM ĐỊNH', 'Cảnh nào dùng để học và cảnh nào được giữ riêng')
    y = text('Các vùng màu biểu diễn footprint của từng lượt chụp trong dữ liệu nguồn. Những lần chụp lặp ở Tây Phi có thể phủ gần cùng khu vực. Hai cảnh Tây Phi từng được dùng để kiểm mô hình cũ được loại khỏi phép chấm mới do gần dữ liệu học SLC VV.', y)-11
    c.drawImage(str(EVIDENCE/'scene_split.png'), 47, y-235, 501, 235)
    y -= 249
    y = table([
        ['Vai trò', 'Ngày chụp UTC', 'Ô hợp lệ'],
        ['Huấn luyện', '07/04, 14/05, 30/06, 19/07, 24/07, 24/08 và 10/09/2020', '1.669'],
        ['Chọn checkpoint và ngưỡng', '03/05/2020', '48'],
        ['Đối chiếu lại ba cảnh', '21/04, 11/05 và 06/07/2020', '218'],
        ['Kiểm tra giữ riêng Biển Bắc', '28/09/2020', '196'],
    ], [184,239,78], y)-13
    y = text('Sáu ô học trong vòng 20 km của footprint chọn ngưỡng đã được cách ly. Kiểm SHA-256 pixel và dấu vân tay dHash ở ngưỡng Hamming 3 giữa các nhóm không tìm thấy cặp trùng. Manifest còn giữ phần biển hợp lệ của từng ô để có thể tính lại diện tích và sai lệch.', y)-15
    y = text('Ba cảnh đối chiếu đã từng làm lộ nhược điểm của mô hình LS-SSDD. Cảnh Biển Bắc được giữ riêng từ đầu lượt huấn luyện này. Ở Biển Bắc, CFAR vòng nền chạy cùng CPU là đối chứng tách vùng. Dòng LS-SSDD được dùng ở ba cảnh đối chiếu do lịch sử huấn luyện của nó gần vùng Biển Bắc.', y, muted)
    assert y > 67, y
    footer(4)

    y = header('KIỂM TRA BẰNG BẢN TIN LỊCH SỬ', 'Cổng AIS giữ lại nhiều ca tại khu vực đông tàu')
    y = text('Dữ liệu NOAA Marine Cadastre gồm ba khu vực cảng: Los Angeles/Long Beach, Galveston/Houston và New York. Trong mỗi cửa sổ UTC, lấy một bản tin trong ±20 giây làm điểm đối chiếu cho mỗi mã. Tách toàn bộ bản tin trong ±20 giây trước khi ước lượng quỹ đạo trong ±10 phút. Ghép đúng được tính theo mã ghi trong bản tin giữ lại.', y)-12
    def add_counts_table(result, title_text, y):
        targets = result['results']['guard_0m']['overall']['targets']
        y = text(f'{title_text} · {fmt(targets)} điểm',y,sub)-6
        rows = [['Phương pháp', 'Đúng mã', 'Sai mã', 'Từ chối']]
        for method, name in [
                ('distance_only', 'Khoảng cách'), ('guard_0m','Cổng gốc'),
                ('guard_25m','Biên 25 m'), ('guard_50m','Biên 50 m'),
                ('guard_75m','Biên 75 m'), ('guard_100m','Biên 100 m')]:
            m = result['results'][method]['overall']
            rows.append([name] + [fmt(m[key]) for key in ('correct','wrong','unassigned')])
        return table(rows, [221,93,93,94], y)-11
    y = add_counts_table(development,'14/07 và 01/10/2024',y)
    y = add_counts_table(confirmation,'15/12/2024 giữ riêng',y)
    m = development['results']['guard_100m']['neighbor_250m']
    y = text(f"Trong {fmt(m['targets'])} điểm có tàu khác trong vòng 250 m ở hai ngày khảo sát, biên 100 m chỉ giữ {m['correct']} cặp đúng. Không cấu hình mở rộng nào vừa giảm số sai ở cả hai ngày vừa giới hạn mất cặp đúng trong 5 điểm phần trăm. Ngày 15/12 được tách để kiểm tra xu hướng, không chọn lại cấu hình.", y, muted)-8
    y = text('Điểm đối chiếu đến từ bản tin cùng nguồn với quỹ đạo. Đây là kết quả phát lại AIS, chưa đo ghép với vị trí radar, chưa đủ căn cứ dùng cho nhận dạng thực địa.', y, muted)
    c.setFillColor(TEAL)
    c.setFont('Heavy',8)
    c.drawString(47, 64, 'NGUỒN AIS NOAA VÀ TỆP THEO NGÀY')
    c.linkURL('https://coast.noaa.gov/htdata/CMSP/AISDataHandler/2024/',(47,61,238,73),relative=0)
    assert y > 79, y
    footer(5)

    y = header('SAR VÀ AIS CÙNG THỜI ĐIỂM', 'Từ ảnh radar đến cặp đề xuất có thể đối chiếu')
    y = text('New York Harbor, Sentinel-1 RTC VV, 22:51:42 UTC ngày 13/12/2024. Chọn cảnh theo lịch chụp, cố định bốn ô trước khi đọc dữ liệu. Ảnh được so với AIS NOAA trong ±10 phút. Giữ riêng AIS trong ±20 giây ở giữa cảnh để đối chiếu.', y)-11
    y = text(f"YOLO đưa ra <b>{coincident['radar_candidates']} ứng viên</b>, chuỗi AIS cung cấp <b>{coincident['estimated_ais_tracks']} ước lượng</b> và có {coincident['held_ais_positions']} vị trí giữ lại. Có <b>{coincident['spatial_references']} mốc vị trí</b> trong 100 m, với ứng viên cạnh tranh ở ngoài 250 m. Mốc này chưa xác nhận danh tính.", y)-11
    rows = [['Cách ghép', 'Cặp đề xuất', 'Đồng thuận vị trí', 'Đề xuất thiếu mốc', 'Giữ lại']]
    for key, title_text in [('distance_only','Khoảng cách'),('previous_gates','Cổng gốc'),
                            ('100m_guard','Lọc trước · biên 100 m'),('propose_then_veto','Giữ cặp đề xuất')]:
        data = coincident['matching'][key]
        rows.append([title_text, data['proposed'], f"{data['agree']}/{coincident['spatial_references']}",
                     data['proposed_without_reference'], data['withheld']])
    y = table(rows,[150,81,94,111,65],y)-11
    tile = max(coincident['tiles'],key=lambda r:r['spatial_references'])
    size = 290
    c.drawImage(str(coincident_dir/tile['marked']),47,y-size,size,size)
    text(f"Ô {tile['tile']+1} trên bốn ô khóa trước. Khung lam có mốc AIS gần và tách biệt. Khung vàng thiếu mốc đối chiếu.<br/><br/>"
         'Độ lệch thời gian theo từng pixel, chuyển động mục tiêu và sai số đăng ký ảnh chưa được đo độc lập. Bốn mốc vì vậy chỉ đủ để kiểm tra quy trình.', y-7, muted, 353, 192)
    y = text('Nguồn ảnh Copernicus Sentinel-1 qua Microsoft Planetary Computer, xử lý RTC bởi Catalyst. Nguồn bản tin NOAA Marine Cadastre. Gói bằng chứng có bốn ảnh radar, giao thức chọn cảnh, SHA-256 và bảng số đếm.',y-size-9,muted)
    assert y > 62, y
    footer(6)

    y = header('CHÍNH SÁCH GHÉP ĐANG DÙNG TRONG BẢN CẢI TIẾN', 'Một đề xuất AIS chỉ có thể được giữ hoặc từ chối')
    n = sum(d['reroutes']['gate_first']['altered'] for d in assignment_dev['days'].values())
    wrong = sum(d['reroutes']['gate_first']['wrong'] for d in assignment_dev['days'].values())
    y = text(f'Trên hai ngày khảo sát, cổng lọc trước đã đổi đối tác so với đề xuất khoảng cách ở {n} điểm. Trong đó <b>{wrong} cặp</b> cho mã khác bản tin giữ lại. Ví dụ trong demo có một AIS gần đã cũ và một AIS khác mới hơn ở cách 80 m. Ghép sang tín hiệu thứ hai có thể gán nhầm sang tàu khác.', y)-17
    y = text('Cách xử lý', y, sub)-6
    y = text('Tính đề xuất Hungarian một lần. Giữ nguyên giới hạn tuổi 180 giây, bất định 150 m và bán kính kết hợp. Kiểm khoảng cách với ứng viên cạnh tranh ở cả hai đầu. Nếu một cặp bị loại, nó không được chuyển sang đối tác khác.', y)-16
    y = text('Kết quả trên ngày 13/12/2024 giữ riêng', y, sub)-6
    rows = [['Cách ghép', 'Đúng mã', 'Sai mã', 'Từ chối']]
    for key, label in [('distance','Khoảng cách'),('gate_first','Cổng lọc trước'),
                       ('gate_first_100m','Cổng lọc trước có biên 100 m'),
                       ('assign_then_veto_200m','Giữ cặp đề xuất, kiểm tra sau')]:
        m=assignment_test['results'][key]['overall']
        rows.append([label,*[fmt(m[k]) for k in ('correct','wrong','unassigned')]])
    y=table(rows,[266,77,77,81],y)-12
    y = text('Phiên bản kiểm tra sau được khóa dựa trên hai ngày khảo sát và hai ca mô phỏng lệch vị trí đã có. Với 3.722 bản tin giữ lại, cổng mới không ghép sai mã trong mẫu này và giữ ít hơn 19 cặp đúng so với cổng lọc trước có biên 100 m.',y)-13
    y = text('Trên cảnh Sentinel-1 cùng giờ, cả hai cổng đều đồng thuận 1/4 mốc vị trí. Cổng giữ cặp đề xuất đưa ra 7 cặp, so với 9. Cần nhiều cảnh có bản tin cùng giờ và xác nhận độc lập trước khi suy rộng.',y)-15
    y = text('Tái lập',y,sub)-5
    y = text('Chạy scripts/evaluate_frozen_ais_assignment.py trên tệp NOAA theo ngày. Bản báo cáo theo ngày và theo mật độ, các lệnh và checksum nằm trong reports/final/ais_preserve_proposal_20261118/.',y,muted)
    assert y > 65, y
    footer(7)

    if retest:
        y = header('TĂNG RECALL TRÊN ẢNH SAR', 'Đọc ở hai tỷ lệ giúp giữ thêm mục tiêu')
        y = text('Giữ cùng checkpoint SLC VV. Thử ảnh 512, 768 và 1.024 px, lật ngang và chia cửa sổ chồng nhau. '
                 'So 35 cấu hình trên 48 ô phát triển. Chọn cách đọc 512 px + 768 px + một lượt lật ngang ở 768 px, '
                 'gộp hộp trùng và dùng ngưỡng 0,005. Tiêu chí chọn là số nhãn khớp khi có cùng giới hạn rà soát.', y)-12
        y = text('Khớp nhiều nhãn hơn ở cả hai nhóm cảnh', y, sub)-5
        rows = [['Nhóm cảnh', 'Cấu hình rà soát', 'Nhãn khớp<br/>Trước → Sau', 'Không khớp nhãn<br/>Trước → Sau']]
        for key, label in [('diagnostic', 'Ba cảnh · 218 ô'), ('north_sea', 'Biển Bắc · 196 ô')]:
            methods = retest[key]['methods']
            for mode, caption in [('full', 'Mọi điểm qua ngưỡng'), ('fixed_budget', 'Cùng giới hạn')]:
                a, z = (methods[k][mode] for k in ('baseline','candidate'))
                rows.append([label, caption,
                             f'{fraction(a)} → {fraction(z)}',
                             f"{fmt(a['false_positive'])} → {fmt(z['false_positive'])}"])
        y = table(rows, [121,128,126,126], y)-12
        y = text('Giới hạn tính theo cảnh, tối đa một ứng viên trên 20 km² biển hợp lệ. IoU 0,50 trên nhãn HIGH/MEDIUM. '
                 'Cả bốn cảnh đã được chấm ở bản trước. Chúng được giữ ngoài tập chọn cấu hình lần này.', y, muted)-15
        y = text('Tách riêng ảnh hưởng của ngưỡng và ưu tiên ven bờ', y, sub)-5
        diag = extra_controls['diagnostic']['native_at_candidate_threshold']['full']
        sea = extra_controls['north_sea']['native_at_candidate_threshold']['full']
        y = text(f"Chỉ hạ ngưỡng với ảnh 512 px cho {fraction(diag)} và {fraction(sea)}, nhưng tạo lần lượt "
                 f"{fmt(diag['false_positive'])} và {fmt(sea['false_positive'])} điểm không khớp. "
                 'Khi giữ cùng giới hạn rà soát, chỉ hạ ngưỡng vẫn cho số nhãn khớp như bản gốc.', y)-10
        y = text('Khi dành tối đa 20% suất rà soát cho dải 500 m từ bờ, bản đa tỷ lệ giữ 7/35 nhãn ven bờ '
                 'ở ba cảnh và tăng từ 2/14 lên 3/14 ở Biển Bắc. Phép phát lại này dùng dự đoán đã lưu.', y)-14
        y = text('Thời gian và phạm vi sử dụng', y, sub)-5
        y = text('Trung vị CPU 4 luồng tăng từ 52–57 lên 218–243 ms mỗi ô, chưa tính thời gian đọc ảnh. '
                 'Điểm không khớp nhãn cần được rà trên ảnh. Phép thử này dùng ảnh SLC ngoài Việt Nam. '
                 'Cấu hình đa tỷ lệ được đối chứng riêng với ảnh GRD/RTC và chưa chạy bản đồ.', y)-10
        y = text('Số liệu gốc, giao thức chọn cấu hình, dự đoán và tệp phục vụ tái lập nằm tại '
                 'reports/final/sar_multiscale_20261118/. Có thể xem trực tiếp ở mục Minh chứng cải tiến.', y, muted)
        fine_path = ROOT/'reports/final/sar_finetune_640_20261118/results.json'
        if fine_path.is_file():
            tuned = json.loads(fine_path.read_text())['evaluation']
            y = text('Huấn luyện tiếp ở 640 px',y-14,sub)-5
            a, z = tuned['diagnostic'], tuned['north_sea']
            y = text(f"Từ bản đa tỷ lệ đã khóa, sau sáu epoch, số nhãn khớp khi rà toàn bộ tăng "
                     f"{a['baseline']['full']['matched']} → {a['fine_tuned']['full']['matched']} ở ba cảnh và "
                     f"{z['baseline']['full']['matched']} → {z['fine_tuned']['full']['matched']} ở Biển Bắc. "
                     'Với cùng giới hạn rà, ba cảnh vẫn khớp 38/147 và Biển Bắc tăng 22/146 → 28/146. '
                     'Điểm không khớp khi rà toàn bộ tăng 837 → 1.307 và 1.453 → 1.866. '
                     'Checkpoint mới được chọn trên 48 ô phát triển và chấm lại cùng bốn cảnh.', y)-5
        assert y > 65, y
        footer(8)

    if local:
        y = header('ĐỐI CHỨNG VEN BIỂN VIỆT NAM', 'Mô hình cần bao nhiêu lượt rà để tìm thêm mục tiêu?')
        dev_day = local['development_day']
        hold = [row for key, row in local['per_acquisition'].items() if dev_day not in key]
        selected = local['selected']
        labels = sum(row['n_evaluated_labels'] for row in hold)
        n_windows = sum(row['windows'] for row in hold)
        y = text(f'Trên {n_windows} ô từ {len(hold)} lượt chụp Sentinel-1 GRD/RTC ở Đà Nẵng và Vũng Tàu, '
                 f'{labels} điểm nhãn Ai2 có ảnh hợp lệ và nằm trên vùng nước chấm. Điểm khớp một–một '
                 'nếu cách nhau không quá 100 m. Một lượt Đà Nẵng khác được dùng để chọn cấu hình.', y)-13
        y = text('Kết quả trên các lượt chụp ngoài tập chọn cấu hình', y, sub)-5
        names = {
            'map_default': 'Bản đồ hiện tại', 'map_land_only': 'Bản đồ, giữ nước sát bờ',
            'map_lower_threshold': 'Bản đồ, hạ ngưỡng',
            'slc_multiscale': 'YOLO SLC VV đa tỷ lệ',
            'fill_with_coastal_map': 'Giữ bản đồ + bổ sung vùng bờ',
            'fill_with_slc': 'Giữ bản đồ + bổ sung đa tỷ lệ',
            'fill_with_agreement': 'Giữ bản đồ + điểm hai mô hình cùng gợi ý',
        }
        rows = [['Phương án', 'Phạm vi rà', 'Nhãn khớp', 'Ứng viên rà', 'Không khớp nhãn']]
        for scope, scope_name, methods in (
                ('all', 'Mọi điểm', ['map_default', 'slc_multiscale']),
                ('fixed_budget', 'Cùng giới hạn', list(dict.fromkeys(['map_default','map_lower_threshold',
                                                                   'slc_multiscale',selected])))):
            for method in methods:
                counts = [row['results'][method][scope]['100'] for row in hold]
                match, points, unmatched = [sum(c[key] for c in counts) for key in ('matched','predictions','unmatched')]
                rows.append([names[method],scope_name,f'{match}/{labels}',fmt(points),fmt(unmatched)])
        y = table(rows,[174,78,69,81,99],y)-13
        y = text(f'Phương án chọn trước khi chấm lại là <b>{names[selected]}</b>. Giới hạn áp dụng theo từng '
                 'lượt chụp, tối đa một điểm trên 20 km² nước hợp lệ. Cấu hình bản đồ có thể dùng ít lượt hơn giới hạn. '
                 'Các phương án phối hợp được kiểm tra lại trên cùng bốn lượt chụp.', y)-13
        y = text('Ý nghĩa với vùng sát bờ',y,sub)-5
        coastal = [row['results']['slc_multiscale'] for row in hold]
        coastal_hit = sum(r['nearshore_label_matches_using_full_candidates'] for r in coastal)
        coastal_n = sum(r['nearshore_label_count'] for r in coastal)
        y = text(f'Ở dải 500 m từ bờ có {coastal_n} nhãn điểm. Khi rà toàn bộ, YOLO đa tỷ lệ tìm được '
                 f'{coastal_hit}/{coastal_n} điểm trong phép đo riêng cho dải này. Bản đồ hiện hành loại trừ '
                 'dải này trước khi suy luận. Các phương án mở dải cần kiểm thêm nhiễu ở cảng và công trình cố định.', y)-13
        y = text('Phạm vi kết luận',y,sub)-5
        y = text('Nhãn đối chiếu do Ai2 công bố. Kết quả lệ thuộc độ phủ nhãn, nơi chụp và số lượt chụp. '
                 'Chỉ đo khớp theo điểm, chưa xác nhận kích thước, danh tính tàu hay bao quát được mọi vùng biển Việt Nam. '
                 'Hiện trạng bản đồ và các mô hình thử tiếp tục được hiển thị riêng.', y)-13
        y = text('Mở Minh chứng cải tiến để thử các bán kính 50, 100 và 150 m. Đối chiếu nguồn theo vệ tinh, '
                 'quỹ đạo tuyệt đối và giây bắt đầu chụp trong reports/final/vietnam_rtc_recall_20261118/.',y,muted)
        assert y > 70, y
        footer(7 + bool(retest) + bool(local))

    if fresh:
        y = header('TẬP KIỂM TRA MỚI TẠI VIỆT NAM', 'Hạ ngưỡng tìm thêm mục tiêu khi có lượt rà')
        cases = fresh['test']
        sample = [case['methods']['map_default']['labels'] for case in cases]
        y = text(f'Tập kiểm tra mới gồm {len(cases)} lượt chụp không cùng ngày với tập phát triển, '
                 f'{sum(c["windows"] for c in cases)} ô và {sum(sample)} nhãn điểm. Giữ nguyên cách khớp một–một '
                 'trong 100 m. Trên năm lượt chụp phát triển, mỗi vòng bỏ riêng một cảnh để chọn bộ xếp hạng.', y)-13
        rows = [['Phương án', 'Nhãn khớp', 'Ứng viên rà', 'Không khớp nhãn']]
        for method, name in (
                ('map_default','Bản đồ, ngưỡng 0,35'), ('map_lower_threshold','Bản đồ, ngưỡng 0,05'),
                ('linear_preserve_map','Giữ bản đồ, bổ sung theo hồi quy logistic'),
                ('linear_rank_only','Chỉ xếp hạng hồi quy logistic'),
                ('boosting_preserve_map','Giữ bản đồ, bổ sung theo boosting'),
                ('boosting_rank_only','Chỉ xếp hạng boosting')):
            totals = [sum(c['methods'][method][k] for c in cases)
                      for k in ('matched','predictions','unmatched')]
            rows.append([name, f'{totals[0]}/{sum(sample)}', fmt(totals[1]), fmt(totals[2])])
        y = text('Cùng mức trần một ứng viên trên 20 km²',y,sub)-5
        y = table(rows,[224,82,88,107],y)-13
        y = text('Hạ ngưỡng cho thêm 16 nhãn khớp, đổi lại phải rà thêm 75 điểm. Bộ hồi quy giữ điểm '
                 'bản đồ và bổ sung 15 nhãn khớp, với thêm 171 điểm cần rà. Kết quả này giúp chọn cách '
                 'mở rộng danh sách khi có thêm thời gian rà.', y)-15
        y = text('Cố định đúng số lượt rà của bản đồ',y,sub)-5
        y = text('Khi cố định đúng 116 lượt rà, ngưỡng gốc và ngưỡng thấp đều khớp 80/152. Chỉ xếp hạng '
                 'lại theo hồi quy khớp 66/152. Chỉ xếp hạng theo boosting khớp 64/152. '
                 'Kết quả chưa xác nhận cách nào tăng recall với đúng số lượt rà của bản đồ.', y)-15
        y = text('Phạm vi kiểm chứng',y,sub)-5
        y = text('Đây là phép kiểm theo nhãn điểm lịch sử của Ai2. Mỗi cảnh dùng vùng nước và mức trần '
                 'riêng theo diện tích. Các điểm không khớp cần rà nguồn và bối cảnh. '
                 'Mục Minh chứng công bố số liệu và phương pháp để chấm lại.', y)-11
        y = text('Tệp kết quả, lựa chọn khóa và phép kiểm theo từng cảnh nằm tại '
                 'reports/final/vietnam_rtc_ranking_20261118/.',y,muted)
        assert y > 66,y
        footer(7 + bool(retest) + bool(local) + bool(fresh))

    if polar:
        y=header('ĐỐI CHỨNG VV VÀ VH', 'Hai kênh radar, cùng số lượt rà')
        cases = polar['outside_development']
        windows = sum(c['paired_windows'] for c in cases)
        missing = sum(c['missing_vh_windows'] for c in cases)
        labels = sum(c['results']['map_default']['labels'] for c in cases)
        y=text(f'Thử đặc trưng độ sáng, tương phản và độ phân tán nền cục bộ của hai kênh Sentinel-1 RTC. '
               f'Tập chấm lại có {len(cases)} lượt chụp, {windows} ô ghép đủ VV/VH và {labels} nhãn điểm '
               'trong vùng chấm. Các ô thiếu VH được loại khỏi mọi phương án. '
               'Chọn trọng số xếp hạng bằng năm lượt phát triển, tách toàn bộ từng lượt khi kiểm tra.',y)-12
        if missing:
            y=text(f'{missing} ô ở tập chấm lại thiếu VH từ nguồn tải. Các cách xếp hạng được đo trên cùng vùng nước có cặp ảnh.',y,muted)-8
        rows=[['Cách xếp hạng', 'Nhãn khớp', 'Điểm cần rà']]
        for method,name in (('map_default','Điểm gốc trên bản đồ'),
                            (polar['selected']['vv'],'Đặc trưng VV'),
                            (polar['selected']['vv_vh'],'Đặc trưng VV và VH')):
            records=[c['results'][method] for c in cases]
            rows.append([name,f"{sum(c['matched'] for c in records)}/{labels}",
                         sum(c['predictions'] for c in records)])
        y = table(rows,[270,115,116],y)-12
        y = text('Hai cách dùng đặc trưng radar xếp lại danh sách mở rộng ở ngưỡng 0,05. Với đúng số lượt rà '
                 'của bản đồ, cả hai đều khớp ít hơn một nhãn. Kết quả giữ nguyên lựa chọn xếp hạng gốc. '
                 'Xem lựa chọn khóa trong reports/final/vietnam_rtc_vv_vh_20261118/.',y,muted)-18
        if example_path.is_file():
            y = text('Hạ ngưỡng trên cùng một ô ảnh',y,sub)-8
            image_width=501
            image_height=299
            c.drawImage(str(example_path),47,y-image_height,image_width,image_height,mask='auto')
            y -= image_height+7
            y = text('Ví dụ được chọn theo số nhãn tìm thêm trong một ô. '
                     'Ảnh Sentinel-1 RTC VV ngày 23/08/2022, ô 44544. '
                     'Nguồn ảnh Copernicus/Catalyst qua Microsoft Planetary Computer, nhãn điểm Ai2.',y,muted)
        assert y > 66,y
        footer(total_update_pages - equal_review)
    if equal_review:
        contrast = json.loads(contrast_path.read_text())
        tta = json.loads(tta_path.read_text())
        y = header('SENTINEL-1 RTC VEN BIỂN VIỆT NAM', 'Phát hiện thêm với cùng số lượt rà')
        n = len(contrast['cases'])
        windows = sum(case['windows'] for case in contrast['cases'])
        y = text(f'Đối chiếu {windows} ô có ảnh trên {n} lượt chụp giữ riêng. '
                 'Chọn phương án trên năm lượt phát triển, giữ nguyên số ứng viên ở từng lượt chụp '
                 'khi chấm lại. Một ứng viên khớp tối đa một nhãn Ai2 trong 100 m.', y)-18
        fig_height = 180
        c.drawImage(str(equal_review_plot), 47, y-fig_height, 501, fig_height, mask='auto')
        y -= fig_height+17
        rows = [['Số lượt rà', 'Phương án', 'Nhãn khớp', 'Điểm không khớp']]
        for mode, baseline, name in (('equal_incumbent','map_default','Xoay và lật ảnh'),
                                     ('equal_relaxed','map_lower_threshold','Chia ô ảnh chồng lấn')):
            for source, method, label in ((contrast,baseline,'Bản đồ'),
                    (contrast,contrast['selected'][mode],'Lọc điểm trong 35 m'),
                    (tta,tta['selected'][mode],name)):
                counts = [case[mode][method]['100'] for case in source['cases']]
                total = {k:sum(row[k] for row in counts) for k in ('predictions','matched','labels','unmatched')}
                rows.append([total['predictions'],label,f"{total['matched']}/{total['labels']}",total['unmatched']])
        y = table(rows,[78,202,91,130],y)-14
        y = text('Lọc điểm gần nhau ưu tiên ứng viên có điểm YOLO cao hơn. Phần tăng thêm ở 116 lượt rà '
                 'tập trung ở hai lượt chụp tại vùng khảo sát Quảng Ninh. Sáu nhãn tăng thêm khi chia ô '
                 'ở 191 lượt rà đến từ một lượt chụp trong vùng này.', y)-10
        confirmation_path = tta_path.parent/'confirmation/results.json'
        if confirmation_path.is_file():
            extra = json.loads(confirmation_path.read_text())['cases']
            y = text(f'Phép xác nhận bổ sung trên {len(extra)} ngày chụp và '
                     f'{sum(row["windows"] for row in extra)} ô ở Bắc Trung Bộ. Cùng 6 lượt rà, '
                     'bản đồ và lọc 35 m đều khớp 5/8. Cùng 10 lượt rà, bản đồ '
                     'và chia ô đều khớp 6/8.',y)-10
        y = text('Các cảnh giữ riêng trong bảng đã được dùng trong những phép thử trước. Kết quả phản ánh '
                 'nhãn điểm trên các ô đã lấy. Dữ liệu theo cảnh, kết quả ở 50/100/150 m '
                 'và mã tái lập có trong mục Minh chứng. Nguồn nhãn Ai2 Vessel Detection with '
                 'Sentinels, ảnh Sentinel-1 RTC từ Microsoft Planetary Computer.',y,muted)
        assert y > 66,y
        footer(total_update_pages)
    c.save()
    b.seek(0)
    writer = PdfWriter()
    writer.append(b, outline_item='Kết quả cải tiến và thao tác kiểm tra')
    prior = PdfReader(args.base)
    if len(prior.pages) != 14:
        raise ValueError('Unexpected technical appendix version')
    writer.append(prior, pages=list(range(2, 9))+list(range(10, 14)),
                  outline_item='Phụ lục: các phép đo và nguồn kỹ thuật trước')
    writer.add_metadata({'/Title':'SonarNet Việt Nam - Báo cáo cải tiến Chặng 1', '/Subject':'SLC VV và độ tin cậy ghép AIS'})
    writer.write(args.output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('font','base','output'):
        parser.add_argument('--'+name, required=True, type=Path)
    build(parser.parse_args())
