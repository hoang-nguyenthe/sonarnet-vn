"""Show the paired behavior evaluation and its scope in the public app."""
import json
from pathlib import Path

import streamlit as st

from evaluation_summary import format_number, render_comparison_cards

SITE = 'https://hoang-nguyenthe.github.io/sonarnet-vn/'


def local_decimal(value, precision):
    return f'{value:.{precision}f}'.replace('.', ',')


def render(root: Path):
    st.subheader('Kiểm chứng mô-đun hành vi')
    st.write('Theo dõi từ ghép SAR–AIS đến gợi ý rà và kết quả đối chứng từng ca.')
    with st.container(horizontal=True, gap='small'):
        st.link_button('Rà 200 ca và xem lý do AI gợi ý', SITE+'chang2/compare.html', type='primary')
        st.link_button('Xem toàn bộ minh chứng', SITE+'chang2/evidence.html')
        st.link_button('Xem hoặc tải báo cáo PDF', SITE+'tai-lieu/')
    metrics = json.loads((root/'reports/final/chang2/streamlit-summary.json').read_text())
    kalman, ais, review, clicks = (metrics[key] for key in ('kalman','ais','review','clicks'))
    before, after = review['missed']
    false_before, false_after = review['false_flags']
    render_comparison_cards((
        ('Ghép đúng nhiều cặp SAR–AIS hơn',
         f"{format_number(kalman['scenes'])} cảnh mô phỏng · {metrics['seeds']} seed",
         format_number(kalman['correct_0']), format_number(kalman['correct_1']),
         f"Kalman so với nội suy tuyến tính trên cùng {format_number(kalman['targets'])} mục tiêu.",
         f"Kalman tìm thêm {format_number(kalman['only_kalman'])} cặp đúng và mất "
         f"{format_number(kalman['only_linear'])} cặp mà nội suy tuyến tính đã ghép đúng."),
        ('Phân biệt khai thác và di chuyển',
         'AIS có nhãn tại Đan Mạch · tách tàu giữa tập học và tập kiểm tra',
         local_decimal(ais['speed_snapshot'],3), local_decimal(ais['history'],3),
         'Macro-F1 khi dùng tốc độ gần nhất so với toàn quỹ đạo. '
         f"Chỉ dùng chuỗi tốc độ đạt {local_decimal(ais['speed_history'],3)}.",
         'Phép đo gồm hai trạng thái. Việt Nam còn thiếu nhãn thực địa cho đủ bốn lớp.'),
        ('Bỏ sót trong quy trình rà mô phỏng',
         f"{review['cases']} ca · {review['rules']} quy tắc tự động",
         before, after,
         f"Bỏ sót trên {format_number(review['positive_pairs'])} cặp ca dương × quy tắc, "
         'so sánh hai giao diện trên cùng dữ liệu.',
         f"Cờ nhầm giảm từ {false_before} xuống {false_after}. Kết quả tính theo quy tắc mô phỏng."),
        ('Thời gian bấm tự động',
         f"{format_number(clicks['pairs'])} cặp thao tác trình duyệt · trung vị",
         f"{clicks['medians'][0]:g} ms", f"{clicks['medians'][1]:g} ms",
         f"Trung vị chênh lệch từng cặp là {clicks['paired_delta']:g} ms.",
         'Phép đo tính từ lúc mở ca đến khi trình duyệt tự động bấm. Chưa đo thời gian ra quyết định của người rà.'),
    ))
    st.markdown(
        f"[Đối chứng riêng Kalman, kích thước và hành vi]({SITE}chang2/evidence.html#ablation) · "
        f"[Dữ liệu và cấu hình thí nghiệm]({metrics['source']})"
    )
