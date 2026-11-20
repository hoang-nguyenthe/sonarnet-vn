"""Show local historical point-label checks alongside the SLC box benchmark."""
from pathlib import Path
import json

import streamlit as st

RESULTS = 'reports/final/vietnam_rtc_recall_20261118/results.json'
RANKING_RESULTS = 'reports/final/vietnam_rtc_ranking_20261118/results.json'
POLARIMETRIC_RESULTS = 'reports/final/vietnam_rtc_vv_vh_20261118/results.json'
CONTRAST_RESULTS = 'reports/final/vietnam_rtc_contrast_20261119/results.json'
TTA_RESULTS = 'reports/final/vietnam_rtc_tta_20261119/results.json'
FOLLOWUP_RESULTS = 'reports/final/vietnam_rtc_followup_20261119/summary.json'
TRANSFER_RESULTS = 'reports/final/vietnam_rtc_transfer_20261119/summary.json'
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
    st.caption('12 lượt chụp Sentinel-1 · 152 nhãn điểm Ai2 · khớp một–một trong 100 m.')
    mode = st.radio('Mức rà để so sánh', list(REVIEW_MODES),
                    format_func=REVIEW_MODES.__getitem__, horizontal=True, key='close_point_review_mode')
    baseline = 'map_default' if mode == 'equal_incumbent' else 'map_lower_threshold'
    winner = result
    overlap_path = root / TTA_RESULTS
    if mode == 'equal_relaxed' and overlap_path.is_file():
        winner = json.loads(overlap_path.read_text())
    winning_method = winner['selected'][mode]
    with st.container(border=True):
        for source, method in ((result,baseline),(winner,winning_method)):
            scores = review_totals(source['cases'], mode, method)
            st.markdown(f"**{RECALL_NAMES[method]}** · **{scores['matched']}/{scores['labels']}** nhãn khớp · "
                        f"**{scores['predictions']}** điểm cần rà")
    if winning_method == 'overlap_only_max':
        st.caption('Chia ô chồng lấn tìm thêm sáu nhãn trong một lượt chụp tại vùng khảo sát Quảng Ninh. '
                   'So sánh giữ đúng số lượt rà của mỗi cảnh.')
    else:
        st.caption('Chọn bán kính trên năm lượt phát triển rồi chấm lại trên 86 ô ảnh giữ riêng. '
                   'Khi hai tâm cách nhau trong 35 m, ưu tiên điểm YOLO cao hơn. '
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
    render_followup_rtc(root)
    render_transfer_rtc(root)
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


def render_followup_rtc(root: Path) -> None:
    path = root / FOLLOWUP_RESULTS
    if not path.is_file():
        return
    result = json.loads(path.read_text())
    with st.expander('Kết quả năm hướng tăng recall đã thử'):
        modes = result['review_modes']
        headers = [f"{result['map_baselines'][mode]['predictions']} lượt rà" for mode in modes]

        def as_row(name, values):
            return {'Hướng đã thử':name,
                    **{header:f"{row['matched']}/{row['labels']}" for header,row in zip(headers,values)}}

        rows = [
            as_row('Bản đồ theo ngưỡng đang so sánh', [result['map_baselines'][mode] for mode in modes]),
            as_row('Lọc 35 m / chia ô chồng lấn', result['prior_best']),
        ]
        for trial in result['trials']:
            rows.append(as_row(trial['name'],[trial['results']['held_out'][mode] for mode in modes]))
        st.dataframe(rows, hide_index=True, width='stretch')
        pool = result['point_pool']
        st.caption(f"{pool['labels']} nhãn Ai2 trên {result['held_out_scenes']} lượt chụp đã dùng để đối chứng. "
                   'Khớp trong 100 m. Chọn phương án trên các ngày phát triển. Cách phân bổ lại '
                   'giữ nguyên tổng số lượt rà và có thể chuyển lượt giữa các cảnh.')
        amount = f"{pool['predictions']:,}".replace(',', '.')
        st.caption(f"Heatmap khớp {pool['matched']}/{pool['labels']} nhãn nếu rà cả {amount} ứng viên. "
                   f"Số liệu tải về gồm phép kiểm bổ sung trên {result['confirmation_scenes']} "
                   'lượt chụp Bắc Trung Bộ.')
        st.download_button('Tải bảng đối chứng năm hướng thử',path.read_bytes(),
                           'sonarnet-doi-chung-nam-huong-recall.json','application/json')


def render_transfer_rtc(root: Path, *, expanded=False) -> None:
    path = root / TRANSFER_RESULTS
    if not path.is_file():
        return
    results = json.loads(path.read_text())['datasets']
    selections = {
        'held_out': '12 lượt đối chứng',
        'confirmation': '2 lượt Bắc Trung Bộ',
    }
    with st.expander('Mô hình SAR hai kênh và quét tín hiệu yếu', expanded=expanded):
        group = st.radio('Nhóm ảnh kiểm tra', list(selections),
                         format_func=selections.__getitem__, horizontal=True, key='rtc_transfer_group')
        dataset = results[group]
        modes = dataset['modes']
        headers = [f"{mode['map']['predictions']} lượt rà" for mode in modes.values()]
        names = {
            'map': 'Bản đồ theo ngưỡng tương ứng',
            'previous_best': 'Lọc 35 m hoặc chia ô chồng lấn',
            'weak_echoes': 'Quét tín hiệu yếu theo mức rà',
            'xview3': 'xView3 dùng VV và VH theo mức rà',
        }
        table = []
        for key, label in names.items():
            row = {'Cách phát hiện radar': label}
            for header, mode in zip(headers, modes.values(), strict=True):
                count = mode[key]
                row[header] = f"{count['matched']}/{count['labels']}"
            table.append(row)
        st.table(table, hide_index=True, border='horizontal')
        prior, transfer = (modes['equal_relaxed'][name] for name in ('previous_best', 'xview3'))
        st.markdown(f"**{prior['matched']}/{prior['labels']} → {transfer['matched']}/{transfer['labels']}** nhãn khớp "
                    f"với cùng **{transfer['predictions']} lượt rà** khi phối hợp xView3 với YOLO.")
        st.caption(f"{dataset['scenes']} lượt chụp · {dataset['windows']} ô ảnh · ghép một–một trong 100 m. "
                   'Năm lượt phát triển khác ngày dùng để chọn cấu hình. Ở mức rà nhỏ, hàng quét tín hiệu yếu '
                   'dùng phương án lọc 35 m và hàng xView3 ưu tiên điểm tâm của mô hình.')
        coverage = dataset['coverage']
        baseline, expanded = (coverage[key] for key in ('previous', 'weak_echoes'))
        expanded_count = f"{expanded['predictions']:,}".replace(',', '.')
        baseline_count = f"{baseline['predictions']:,}".replace(',', '.')
        st.markdown(f"Rà toàn bộ danh sách quét tín hiệu yếu khớp **{expanded['matched']}/{expanded['labels']}** "
                    f"nhãn qua **{expanded_count}** ứng viên. Danh sách trước đó khớp "
                    f"**{baseline['matched']}/{baseline['labels']}** nhãn qua **{baseline_count}** ứng viên.")
        missing = dataset['missing_vh_windows']
        if missing:
            st.caption(f"Thiếu kênh VH ở {missing} ô. Phép chấm giữ nguyên các nhãn và danh sách đối chứng ở những ô đó.")
        st.caption('Đối chứng trên ảnh lịch sử. Điểm không khớp nhãn vẫn cần xem trên ảnh nguồn.')
        st.download_button('Tải kết quả thử radar hai kênh',
                           path.read_bytes(), 'sonarnet-thu-radar-hai-kenh.json', 'application/json')
        sample = path.parent / 'xview3'
        coords = sample / 'review-queues.json'
        st.download_button('Tải tọa độ đối chiếu xView3', coords.read_bytes(),
                           'sonarnet-toa-do-xview3.json', 'application/json')
        if group == 'held_out' and st.toggle('Xem nhãn tìm thêm trên ảnh radar', key='rtc_xview_example'):
            render_recovered_example(sample,
                                     after='Sau khi phối hợp xView3 với YOLO',
                                     download_label='Tải thông tin ô ảnh xView3',
                                     show_queue_download=False)
    render_recall_followup(root, path.parent)
    render_rank_fusion(path.parent / 'rank_fusion')


def render_rank_fusion(folder: Path) -> None:
    path = folder / 'results.json'
    if not path.is_file():
        return
    data = json.loads(path.read_text())['test']
    cohorts = [('12 lượt ven biển', data['held_out']['totals']),
               ('2 lượt Bắc Trung Bộ', data['confirmation']['totals'])]
    holdout = folder / 'ais-holdout' / 'results.json'
    if holdout.is_file():
        cohorts.append(('Mốc AIS · 6 cảnh cảng Mỹ', json.loads(holdout.read_text())['totals']))
    with st.expander('Xếp hạng theo đồng thuận YOLO và xView3'):
        st.caption('Giữ đúng số lượt rà từng cảnh, ghép trong 100 m.')
        rows = []
        for label, totals in cohorts:
            for mode in totals.values():
                baseline, rank, guarded = (mode[name]['100'] for name in ('published', 'rank_60', 'rank_60_keep_75'))
                rows.append({
                    'Tập ảnh': label,
                    'Lượt rà': baseline['predictions'],
                    'Đã công bố': f"{baseline['matched']}/{baseline['labels']}",
                    'Gộp thứ hạng': f"{rank['matched']}/{rank['labels']}",
                    'Giữ đầu danh sách': f"{guarded['matched']}/{guarded['labels']}",
                })
        st.table(rows, hide_index=True, border='horizontal')
        st.caption('Cấu hình giữ đầu danh sách được thiết kế sau khi xem kết quả trên nhóm ảnh Việt Nam.')
        st.download_button('Tải số liệu thử gộp thứ hạng', path.read_bytes(),
                           'sonarnet-thu-gop-thu-hang.json', 'application/json')
        if holdout.is_file():
            st.caption('Sáu cảnh cảng Mỹ dùng mốc AIS ít dịch chuyển, chọn trước khi chạy mô hình. '
                       'Các mốc này được chấm riêng với nhãn Ai2 ven biển Việt Nam.')
            st.download_button('Tải đối chứng gộp hạng trên sáu cảnh AIS', holdout.read_bytes(),
                               'sonarnet-gop-thu-hang-doi-chung-ais.json', 'application/json')


def render_recall_followup(root: Path, folder: Path) -> None:
    ais_path = root/'reports/final/stationary_ais_detection_20261120/results.json'
    extension_path = folder/'extension/results.json'
    if not ais_path.is_file() or not extension_path.is_file():
        return
    ais = json.loads(ais_path.read_text())
    extension = json.loads(extension_path.read_text())
    with st.expander('Đối chứng với mốc AIS và chi phí rà bổ sung'):
        st.markdown('**13 mốc AIS ít dịch chuyển trên sáu lượt chụp**')
        outcomes = ais['totals']
        rows = []
        for label, base, test in (
                ('Mức rà hẹp', 'base_at_035', 'same_count_overlap'),
                ('Mức rà rộng', 'base_at_005', 'same_wide_count_overlap')):
            a, b = (outcomes[name]['100'] for name in (base,test))
            rows.append({'Mức rà': label, 'Lượt rà': a['predictions'],
                         'Ảnh nguyên': f"{a['matched']}/{a['labels']}",
                         'Thêm ô chồng lấn': f"{b['matched']}/{b['labels']}"})
        st.table(rows, hide_index=True, border='horizontal')
        st.caption('Mốc được chọn từ bản tin AIS và vùng ảnh hợp lệ trước khi chạy YOLO. '
                   'Ghép một–một trong 100 m. Các mốc chỉ đại diện vị trí của nhóm phát AIS ít dịch chuyển.')
        trials = extension['test']['held_out']['totals']
        prior, expanded = (trials[name]['100'] for name in ('initial', extension['selected']))
        st.markdown(f"**{prior['predictions']} → {expanded['predictions']} lượt rà**, "
                    f"vẫn khớp **{expanded['matched']}/{expanded['labels']}** nhãn Ai2 "
                    'khi bổ sung ứng viên sau danh sách xView3 phối hợp YOLO.')
        st.download_button('Tải số liệu đối chứng với mốc AIS', ais_path.read_bytes(),
                           'sonarnet-doi-chung-phat-hien-bang-ais.json', 'application/json')
        st.download_button('Tải số liệu rà bổ sung', extension_path.read_bytes(),
                           'sonarnet-doi-chung-ra-bo-sung.json', 'application/json')
        render_dual_band_ais(ais_path.parent/'dual-band')


def render_dual_band_ais(folder: Path) -> None:
    report = folder/'results.json'
    if not report.is_file():
        return
    cases = json.loads(report.read_text())['totals']
    st.markdown('**Kiểm tra xView3 trên cùng các mốc AIS**')
    for mode in ('narrow','wide'):
        reference, fused = (cases[mode][key]['100'] for key in ('prior','fused_xview3'))
        reviews = f"{reference['predictions']:,}".replace(',', '.')
        st.markdown(f"Ở **{reviews} lượt rà**, phối hợp VV/VH với YOLO cho "
                    f"**{reference['matched']}/{reference['labels']} → {fused['matched']}/{fused['labels']}** mốc khớp.")
    st.caption('Dùng cùng trọng số xView3 đã thử trên ảnh Việt Nam. Mỗi ô có hai kênh radar cùng lượt chụp. '
               'Số điểm cần rà được giữ theo từng cảnh.')
    st.download_button('Tải kết quả xView3 đối chiếu AIS',report.read_bytes(),
                       'sonarnet-xview3-doi-chung-ais.json','application/json')
    if st.toggle('Xem ô ảnh xView3 khớp thêm mốc AIS',key='rtc_xview3_ais_example'):
        example=json.loads((folder/'example.json').read_text())
        st.caption(f"{example['area']} · {example['utc'][:10]} · "
                   f"{example['before']} → {example['after']} mốc khớp với {example['reviewed']} lượt rà.")
        for column, side, label in zip(st.columns(2),('before','after'),('Danh sách trước','Phối hợp xView3')):
            column.markdown(f'**{label}**')
            column.image(str(folder/example['images'][side]['name']),width='stretch')
        distance=f"{example['distance_m']:.1f}".replace('.', ',')
        st.caption(f"Hình thoi lam là mốc AIS. Vòng vàng là tâm radar ghép cách mốc {distance} m.")


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
        render_recovered_example(path.parent)


def render_recovered_example(folder: Path, *, after='Sau khi chia ô ảnh chồng lấn',
                             download_label='Tải nguồn và vị trí ba nhãn minh họa',
                             show_queue_download=True) -> None:
    details = folder/'recovered-example.json'
    packet = folder/'review-queues.json'
    panels = [folder/f'recovered-{side}.png' for side in ('before','after')]
    if not all(path.is_file() for path in (details, packet, *panels)):
        return
    evidence = json.loads(details.read_text())
    n = len(evidence['recovered'])
    st.markdown(f'**{n} nhãn khớp thêm trên một ô ảnh radar**')
    day = evidence['source']['source_acquired_at'][:10]
    st.caption(f"Sentinel-1 RTC VV · {day} · ô {evidence['window_id']}. Trên cả lượt chụp, "
               f"{evidence['before_matches']} → {evidence['after_matches']} nhãn khớp "
               f"với cùng {evidence['scene_reviews']} lượt rà. "
               'Hai ảnh chỉ đánh dấu các nhãn tìm thêm trong ô minh họa.')
    for column, image, heading in zip(st.columns(2),panels,('Ảnh gốc và nhãn Ai2', after)):
        column.markdown(f'**{heading}**')
        column.image(str(image), width='stretch')
    offsets = ' · '.join(f"Nhãn {row['marker']} cách {row['distance_m']:.1f} m".replace('.', ',')
                         for row in evidence['recovered'])
    st.caption('Hình thoi lam là nhãn Ai2. Vòng vàng là tâm ứng viên được ghép. '
               f'{offsets}.')
    if show_queue_download:
        st.download_button('Tải tọa độ để tính lại recall', packet.read_bytes(),
                           'sonarnet-recall-toa-do-da-cham.json', 'application/json')
    st.download_button(download_label, details.read_bytes(),
                       'sonarnet-recall-nguon-o-anh.json', 'application/json')


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
