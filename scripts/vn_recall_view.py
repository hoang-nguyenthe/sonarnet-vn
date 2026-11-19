"""Show local historical point-label checks alongside the SLC box benchmark."""
from pathlib import Path
import json

import streamlit as st

RESULTS = 'reports/final/vietnam_rtc_recall_20261118/results.json'
RANKING_RESULTS = 'reports/final/vietnam_rtc_ranking_20261118/results.json'
POLARIMETRIC_RESULTS = 'reports/final/vietnam_rtc_vv_vh_20261118/results.json'
CONTRAST_RESULTS = 'reports/final/vietnam_rtc_contrast_20261119/results.json'
TTA_RESULTS = 'reports/final/vietnam_rtc_tta_20261119/results.json'
RECALL_NAMES = {
    'map_default': 'Bản đồ · ngưỡng 0,35',
    'map_lower_threshold': 'Bản đồ · ngưỡng 0,05',
    'distinct_35m': 'Lọc điểm nằm trong 35 m',
    'distinct_65m': 'Lọc điểm nằm trong 65 m',
    'contrast_only': 'Đỉnh tương phản radar',
    'learned_union': 'Xếp hạng theo điểm radar và YOLO',
    'map_prior_union': 'Ưu tiên điểm YOLO, bổ sung tương phản',
    'map_prior_distinct_65m': 'Ưu tiên điểm YOLO, lọc trong 65 m',
    'flip_rotation_max': 'Xoay và lật ảnh · lấy điểm cao nhất',
    'overlap_only_max': 'Các ô chồng lấn · lấy điểm cao nhất',
}
REVIEW_MODES = {
    'equal_incumbent': 'Cùng số lượt rà với ngưỡng 0,35',
    'equal_relaxed': 'Cùng số lượt rà với ngưỡng 0,05',
}
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
    baseline, expanded = rows[:2]
    for column, result in zip(st.columns(2), (baseline, expanded)):
        with column.container(border=True):
            st.markdown(f"**{result['Phương án']}**")
            st.markdown(f"**{result['Nhãn khớp']}** nhãn khớp · **{result['Ứng viên phải rà']}** điểm cần rà")
    with st.expander('Bảng đầy đủ và các bộ xếp hạng'):
        st.dataframe(rows, hide_index=True, width='stretch')
    st.caption('Thử nghiệm phát lại trên ảnh lịch sử. Điểm không khớp nhãn cần được kiểm tra trên ảnh nguồn.')
    st.download_button('Tải kết quả 12 lượt chụp mới', path.read_bytes(),
                       'sonarnet-recall-tap-viet-nam-moi.json', 'application/json')
    image_path = path.with_name('example.png')
    example_path = path.with_name('example.json')
    if image_path.is_file() and example_path.is_file():
        with st.expander('Xem ảnh radar thật và các điểm được tìm thêm'):
            example = json.loads(example_path.read_text())
            acquired = example['source']['source_acquired_at'][:10]
            panels = [path.with_name(f'example-{side}.png') for side in ('before','after')]
            if all(panel.is_file() for panel in panels):
                for column, panel, summary in zip(st.columns(2), panels, example['summaries']):
                    column.markdown(
                        f"**{summary['threshold']}** · **{summary['matched']}/{example['label_count']}** "
                        f"nhãn khớp · {summary['proposal_count']} điểm cần rà"
                    )
                    column.image(str(panel), width='stretch')
                st.caption('Hình thoi lam là nhãn Ai2. Vòng vàng là điểm khớp trong 100 m. '
                           'Vòng hồng là điểm chưa khớp nhãn.')
            else:
                st.image(str(image_path), width='stretch')
            st.caption(f"Sentinel-1 RTC VV · {acquired} · ô {example['window_id']}. "
                       "Chọn ô tìm thêm nhiều nhãn nhất để minh họa. "
                       "Chỉ đánh dấu điểm thuộc vùng nước dùng chấm.")
            st.download_button('Tải nguồn và số đếm của ảnh minh họa',example_path.read_bytes(),
                               'sonarnet-nguon-anh-minh-hoa.json','application/json')
    render_polarimetric_recall(root)


def review_totals(cases, mode, method, radius=100):
    cells = [c[mode][method][str(radius)] for c in cases]
    return {k: sum(c[k] for c in cells) for k in ('matched', 'labels', 'predictions', 'unmatched')}


def render_contrast_recall(root: Path) -> None:
    path = root / CONTRAST_RESULTS
    if not path.is_file():
        return
    result = json.loads(path.read_text())
    cases = result['cases']
    st.subheader('Phát hiện thêm với cùng số lượt rà', anchor='recall-cung-luot-ra')
    st.caption('Cùng 12 lượt chụp lịch sử, 86 ô có ảnh. Chọn bán kính lọc trên năm lượt phát triển '
               'rồi chấm lại trên các lượt giữ riêng. Một ứng viên khớp tối đa một nhãn trong 100 m.')
    mode = st.radio('Số lượt rà trong phép lọc điểm gần nhau', list(REVIEW_MODES),
                    format_func=REVIEW_MODES.__getitem__, horizontal=True, key='close_point_review_mode')
    baseline = 'map_default' if mode == 'equal_incumbent' else 'map_lower_threshold'
    selected = result['selected'][mode]
    for column, method in zip(st.columns(2), (baseline, selected)):
        scores = review_totals(cases, mode, method)
        with column.container(border=True):
            column.markdown(f"**{RECALL_NAMES[method]}**")
            column.markdown(f"**{scores['matched']}/{scores['labels']}** nhãn khớp · "
                            f"**{scores['predictions']}** điểm cần rà")
    st.caption('Ưu tiên ứng viên có điểm YOLO cao hơn khi các tâm cách nhau trong 35 m. '
               'Hai nhãn tăng thêm ở mức rà 0,35 đến từ hai lượt chụp tại vùng khảo sát Quảng Ninh.')
    with st.expander('Xem kết quả theo bán kính khớp và cách xếp hạng'):
        radius = st.select_slider('Bán kính khớp nhãn (m)', options=[50, 100, 150], value=100,
                                  key='close_point_match_radius')
        data = []
        for method in cases[0][mode]:
            scores = review_totals(cases, mode, method, radius)
            data.append({'Phương án': RECALL_NAMES[method],
                         'Nhãn khớp': f"{scores['matched']}/{scores['labels']}",
                         'Điểm cần rà': scores['predictions'], 'Không khớp nhãn': scores['unmatched']})
        st.dataframe(data, hide_index=True, width='stretch')
        st.caption('Phép phát lại dùng nhãn điểm có sẵn. Điểm không khớp cần xem trên ảnh nguồn. '
                   'Kết quả đã đo trên các ô có nhãn; bản đồ công khai vẫn dùng cấu hình đã công bố.')
        st.download_button('Tải số liệu lọc điểm gần nhau', path.read_bytes(),
                           'sonarnet-recall-loc-diem-gan.json', 'application/json')
    render_map_tta_recall(root)
    confirmation = (root / TTA_RESULTS).parent / 'confirmation/results.json'
    if confirmation.is_file():
        new_cases = json.loads(confirmation.read_text())['cases']
        base_tight = review_totals(new_cases,'equal_incumbent','baseline')
        base_wide = review_totals(new_cases,'equal_relaxed','baseline')
        tight = review_totals(new_cases,'equal_incumbent','distinct_35m')
        wide = review_totals(new_cases,'equal_relaxed','overlap_only_max')
        st.caption(f"Hai lượt chụp bổ sung ở Bắc Trung Bộ. Ở {base_tight['predictions']} lượt rà, "
                   f"bản đồ và lọc 35 m lần lượt khớp {base_tight['matched']}/{base_tight['labels']} và "
                   f"{tight['matched']}/{tight['labels']}. Ở {base_wide['predictions']} lượt rà, "
                   f"bản đồ và chia ô lần lượt khớp {base_wide['matched']}/{base_wide['labels']} và "
                   f"{wide['matched']}/{wide['labels']}.")


def render_map_tta_recall(root: Path) -> None:
    path = root / TTA_RESULTS
    if not path.is_file():
        return
    result = json.loads(path.read_text())
    with st.expander('Thử xoay, lật và chia ô ảnh cho mô hình bản đồ'):
        chart = path.with_name('equal-review.png')
        if chart.is_file():
            st.image(str(chart), width='stretch')
        rows = []
        for mode, baseline in (('equal_incumbent', 'map_default'), ('equal_relaxed', 'map_lower_threshold')):
            method = result['selected'][mode]
            before = review_totals(result['cases'], mode, baseline)
            after = review_totals(result['cases'], mode, method)
            rows.append({'Số lượt rà': after['predictions'], 'Cấu hình gốc': f"{before['matched']}/{before['labels']}",
                         'Phương án thử': RECALL_NAMES[method], 'Nhãn khớp': f"{after['matched']}/{after['labels']}"})
        st.dataframe(rows, hide_index=True, width='stretch')
        st.caption('Dùng trọng số YOLO đang phục vụ bản đồ. Chọn cách kết hợp trên năm lượt phát triển, '
                   'sau đó chấm riêng trên 12 lượt chụp đã có nhãn Ai2.')
        st.download_button('Tải kết quả biến đổi ảnh trước suy luận', path.read_bytes(),
                           'sonarnet-recall-bien-doi-anh.json', 'application/json')


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
