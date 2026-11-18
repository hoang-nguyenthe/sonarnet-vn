"""Show local historical point-label checks alongside the SLC box benchmark."""
from pathlib import Path
import json

import streamlit as st

RESULTS = 'reports/final/vietnam_rtc_recall_20261118/results.json'
RANKING_RESULTS = 'reports/final/vietnam_rtc_ranking_20261118/results.json'
POLARIMETRIC_RESULTS = 'reports/final/vietnam_rtc_vv_vh_20261118/results.json'
NAMES = {
    'map_default': 'Cấu hình bản đồ hiện tại',
    'map_lower_threshold': 'Bản đồ, hạ ngưỡng điểm',
    'map_land_only': 'Bản đồ, giữ vùng nước sát bờ',
    'map_land_only_sensitive': 'Giữ vùng sát bờ và hạ ngưỡng',
    'slc_512': 'YOLO SLC VV, 512 px',
    'slc_multiscale': 'YOLO SLC VV, đa tỷ lệ',
    'slc_multiscale_log_stretch': 'Đa tỷ lệ, chuẩn hóa lại độ sáng',
    'fill_with_coastal_map': 'Giữ bản đồ, bổ sung ứng viên ven bờ',
    'fill_with_slc': 'Giữ bản đồ, bổ sung từ đa tỷ lệ',
    'fill_with_agreement': 'Giữ bản đồ, bổ sung điểm hai mô hình cùng gợi ý',
}


def total(cohorts, method, scope, distance):
    cells = [c['results'][method][scope][str(distance)] for c in cohorts]
    return {key: sum(c[key] for c in cells) for key in ('labels', 'matched', 'unmatched', 'predictions')}


def render_vn_recall(root: Path) -> None:
    path = root / RESULTS
    if not path.is_file():
        return
    report = json.loads(path.read_text())
    dev_day = report['development_day']
    cohorts = [row for scene, row in report['per_acquisition'].items() if dev_day not in scene]
    selected = report['selected']
    before = total(cohorts, 'map_default', 'fixed_budget', 100)
    after = total(cohorts, selected, 'fixed_budget', 100)
    st.subheader('Kiểm tra trên ảnh ven biển Việt Nam')
    st.caption(
        f"{len(cohorts)} lượt chụp giữ riêng ở Đà Nẵng và Vũng Tàu, "
        f"{sum(c['windows'] for c in cohorts)} ô Sentinel-1 GRD/RTC. "
        'Nhãn điểm công khai từ Ai2. Khớp một–một trong 100 m trên vùng nước có ảnh và nhãn.'
    )
    a, b, c = st.columns(3)
    a.metric('Nhãn điểm khớp · cùng giới hạn rà', f"{before['matched']} → {after['matched']}")
    b.metric('Điểm không khớp · cùng giới hạn rà', f"{before['unmatched']} → {after['unmatched']}")
    c.metric('Nhãn điểm trong vùng chấm', before['labels'])
    st.caption(f"Phương án được chọn trên cảnh phát triển: {NAMES[selected]}. "
               f"Số ứng viên cần rà là {before['predictions']} → {after['predictions']}. "
               'Giới hạn mỗi cảnh là tối đa 1 ứng viên/20 km² biển hợp lệ. '
               'Nhóm phối hợp được thử lại trên các cảnh đã chấm.')
    full_before = total(cohorts, 'map_default', 'all', 100)
    full_slc = total(cohorts, 'slc_multiscale', 'all', 100)
    st.caption(f"Khi rà mọi điểm, YOLO đa tỷ lệ tăng số nhãn khớp từ {full_before['matched']} lên "
               f"{full_slc['matched']}/{full_slc['labels']}. Điểm không khớp nhãn tăng từ "
               f"{full_before['unmatched']:,} lên {full_slc['unmatched']:,}.".replace(',', '.'))
    with st.expander('So sánh từng phương án và bán kính khớp'):
        scope = st.radio('Phạm vi rà soát', ('fixed_budget', 'all'), horizontal=True,
                         format_func={'fixed_budget':'Cùng giới hạn', 'all':'Mọi điểm qua ngưỡng'}.__getitem__,
                         key='vn_rtc_scope')
        distance = st.select_slider('Bán kính khớp (m)', options=[50, 100, 150], value=100, key='vn_rtc_distance')
        data = []
        for method in cohorts[0]['results']:
            name = NAMES[method]
            count = total(cohorts, method, scope, distance)
            data.append({
                'Phương án': name, 'Nhãn khớp': f"{count['matched']}/{count['labels']}",
                'Điểm không khớp nhãn': count['unmatched'], 'Ứng viên phải rà': count['predictions'],
            })
        st.dataframe(data, hide_index=True, width='stretch')
        st.caption('Các phương án bổ sung ứng viên tự dừng ở giới hạn rà của từng cảnh.')
        baseline = []
        for row in cohorts:
            a = total([row], 'map_default', scope, distance)
            z = total([row], selected, scope, distance)
            baseline.append({
                'Khu vực': 'Đà Nẵng' if row['region'].startswith('da_nang') else 'Vũng Tàu',
                'Nhãn điểm': a['labels'], 'Bản đồ khớp': a['matched'], 'Phương án đã chọn khớp': z['matched'],
                'Bản đồ phải rà': a['predictions'], 'Phương án đã chọn phải rà': z['predictions'],
            })
        st.dataframe(baseline, hide_index=True, width='stretch')
        st.caption('Bảng chỉ dùng các điểm có nhãn trong những ô đã lấy. Nhãn ngoài nguồn có thể còn thiếu. '
                   'Kết quả giúp đánh giá độ phủ theo điểm, chưa xác nhận kích thước hoặc danh tính tàu.')
        st.download_button('Tải đối chứng SAR ven biển Việt Nam', path.read_bytes(),
                           'sonarnet-recall-viet-nam.json', 'application/json')



def render_fresh_recall(root: Path) -> None:
    path = root / RANKING_RESULTS
    if not path.is_file():
        return
    result = json.loads(path.read_text())
    cases = result['test']
    st.subheader('Recall trên 12 lượt chụp mới')
    st.caption('86 ô ảnh có nhãn điểm Ai2 từ các lượt chụp không cùng ngày với tập phát triển. '
               'Khớp một–một trong 100 m. So sánh hạ ngưỡng bản đồ và bộ xếp hạng học máy.')
    modes = {'methods':'Cùng mức trần 1 ứng viên / 20 km²',
             'matched_review_count':'Đúng số lượt rà của bản đồ'}
    mode = st.radio('Giới hạn rà soát trên tập mới', list(modes), format_func=modes.__getitem__,
                    horizontal=True, key='fresh_rtc_review_mode')
    names = {'map_default':'Bản đồ · ngưỡng 0,35', 'map_lower_threshold':'Bản đồ · ngưỡng 0,05',
             'linear_preserve_map':'Giữ bản đồ, bổ sung theo hồi quy logistic',
             'linear_rank_only':'Chỉ xếp hạng hồi quy logistic',
             'boosting_preserve_map':'Giữ bản đồ, bổ sung theo boosting',
             'boosting_rank_only':'Chỉ xếp hạng boosting'}
    rows = []
    for key in names:
        counts = [row[mode][key] for row in cases]
        n, matched, reviewed, unmatched = (
            sum(c[k] for c in counts) for k in ('labels','matched','predictions','unmatched')
        )
        rows.append({'Phương án':names[key], 'Nhãn khớp':f'{matched}/{n}',
                     'Ứng viên phải rà':reviewed,'Không khớp nhãn':unmatched})
    st.dataframe(rows, hide_index=True, width='stretch')
    st.caption('Ở mức trần theo diện tích, hạ ngưỡng tăng từ 80 lên 96 nhãn khớp. '
               'Khi cố định ở 116 lượt rà, vẫn khớp 80 nhãn. Cấu hình hạ ngưỡng đang được đánh giá bằng phép phát lại.')
    st.download_button('Tải kết quả 12 lượt chụp mới', path.read_bytes(),
                       'sonarnet-recall-tap-viet-nam-moi.json', 'application/json')
    image_path = path.with_name('example.png')
    example_path = path.with_name('example.json')
    if image_path.is_file() and example_path.is_file():
        with st.expander('Xem ảnh radar thật và các điểm được tìm thêm'):
            example = json.loads(example_path.read_text())
            acquired = example['source']['source_acquired_at'][:10]
            st.image(str(image_path), width='stretch',
                     caption=f"Sentinel-1 RTC VV · {acquired} · ô {example['window_id']}. "
                             "Chọn ô tìm thêm nhiều nhãn nhất để minh họa. "
                             "Chỉ đánh dấu điểm thuộc vùng nước dùng chấm.")
            st.download_button('Tải nguồn và số đếm của ảnh minh họa',example_path.read_bytes(),
                               'sonarnet-nguon-anh-minh-hoa.json','application/json')
    render_polarimetric_recall(root)



def render_polarimetric_recall(root: Path) -> None:
    path = root / POLARIMETRIC_RESULTS
    if not path.is_file():
        return
    report = json.loads(path.read_text())
    cases = report['outside_development']
    with st.expander('Thử xếp hạng bằng hai kênh radar VV và VH'):
        windows = sum(case['paired_windows'] for case in cases)
        missing = sum(case['missing_vh_windows'] for case in cases)
        st.caption(f'VV và VH cùng lưới ở {windows} ô thuộc {len(cases)} lượt chụp đã chấm lại. '
                   f'Bỏ {missing} ô thiếu VH khỏi cả ba cách đo. '
                   'Khóa cấu hình trên năm lượt phát triển rồi chấm ở đúng số lượt rà của bản đồ.')
        method = [('map_default','Xếp theo bản đồ'),
                  (report['selected']['vv'],'Xếp lại với đặc trưng VV'),
                  (report['selected']['vv_vh'],'Xếp lại với đặc trưng VV và VH')]
        rows = []
        for key,name in method:
            data = [case['results'][key] for case in cases]
            matches, labels, n = (sum(d[field] for d in data) for field in ('matched','labels','predictions'))
            rows.append({'Cách xếp hạng':name,'Nhãn điểm khớp':f'{matches}/{labels}','Điểm cần rà':n})
        st.dataframe(rows, hide_index=True, width='stretch')
        st.download_button('Tải kết quả VV và VH', path.read_bytes(),
                           'sonarnet-recall-vv-vh.json','application/json')
