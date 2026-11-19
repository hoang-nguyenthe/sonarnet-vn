"""Executable evidence for the final-round requirements, with explicit provenance."""
from __future__ import annotations

import json
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from demo_snapshot import render_snapshot
from evaluation_summary import render_evaluation_summary
from vn_recall_view import render_contrast_recall, render_fresh_recall, render_vn_recall
from sonarnet.config import RunConfig
from sonarnet.fusion.kalman import KalmanEstimate
from sonarnet.fusion.matching import Detection, SARAISFusion
from sonarnet.fusion.status import STATE_LABELS, pending_review

SCENARIOS = {
    'Thiếu AIS': 'missing',
    'AIS ở ngoài vùng ghép': 'distant',
    'Kích thước mâu thuẫn': 'conflict',
    'Thiếu kích thước khai báo': 'missing_size',
    'AIS quá cũ': 'stale',
    'AIS gần nhất đã cũ, có tín hiệu khác gần đó': 'stale_nearby',
    'Hai quỹ đạo giao nhau': 'crossing',
    'Chuỗi AIS lệch vị trí': 'bias',
    'Dữ liệu đủ điều kiện ghép': 'clean',
}
REASONS = {
    'no_ais': 'Không có AIS để đối chiếu',
    'out_of_range': 'Không có AIS trong ngưỡng ghép',
    'stale_ais': 'AIS cách thời điểm chụp quá xa',
    'uncertain_position': 'Độ bất định vị trí vượt ngưỡng',
    'invalid_ais': 'AIS thiếu hoặc có giá trị không hợp lệ',
    'ambiguous': 'Nhiều ứng viên cạnh tranh; chưa thể chọn',
    'assigned_elsewhere': 'Không có cặp duy nhất trong phép gán',
    'matched': 'Đạt điều kiện ghép vị trí',
    'invalid_detection': 'Tọa độ SAR không hợp lệ',
}


def run_scenario(kind, age_s=None, sigma_m=20.):
    """Illustrative inputs go through the production association/classification code."""
    cfg = RunConfig()
    fusion = SARAISFusion(cfg)
    positions = {'crossing': [-5., 5.], 'bias': [-70., 70.]}.get(kind, [0.])
    detections = [Detection(i, 0., x / 111195., 80., 20., (0, 0, 8, 2))
                  for i, x in enumerate(positions)]
    estimates = {}
    positions_ais = {}
    if kind != 'missing':
        for i, x in enumerate(positions):
            offset = 700. if kind == 'distant' else 3.
            if kind == 'bias':
                offset = (160., -160.)[i]
            age = age_s if age_s is not None else (600. if kind in {'stale','stale_nearby'} else 10.)
            estimate = KalmanEstimate(0., (x + offset) / 111195., 0., 0., sigma_m, age, 5)
            estimate.declared_length_m = float('nan') if kind == 'missing_size' else (200. if kind == 'conflict' else 80.)
            estimates[100 + i] = estimate
            positions_ais[100 + i] = x + offset
    if kind == 'stale_nearby':
        estimates[101] = KalmanEstimate(0.,80/111195.,0.,0.,20.,10.,5)
        positions_ais[101] = 80.
    matches, distances, reasons = fusion.match_with_reasons(detections, estimates)
    states = fusion.classify_states(detections, matches, estimates, reasons)
    rows = []
    for i, state in enumerate(states):
        rows.append({
            'Điểm SAR': f'Điểm {i + 1}',
            'Trạng thái': STATE_LABELS[state],
            'Mã AIS mẫu': str(matches[i]) if i in matches else 'Chưa ghép',
            'Khoảng cách (m)': round(distances[i], 1) if i in distances else None,
            'Lý do': REASONS[reasons[i]],
            'Xác minh nghiệp vụ': 'Chờ người có chuyên môn',
        })
    return rows, dict(dataset_type='synthetic_demo', scenario=kind,
        age_s=age_s, sigma_m=sigma_m, thresholds=vars(cfg.fusion),
        states=states, reasons=reasons, matches=matches,
        sar_east_m=positions, ais_east_m=positions_ais,
        operational_assessment=pending_review())


def draw_scenario(payload):
    """Show the same positions and accepted edges as the tabular evidence."""
    sar = payload['sar_east_m']
    ais = payload['ais_east_m']
    matches = payload['matches']
    fig = go.Figure()
    if matches:
        x, y = [], []
        for i, target in matches.items():
            x.extend((sar[i], ais[target], None))
            y.extend((1, 0, None))
        fig.add_scatter(x=x, y=y, mode='lines', name='Cặp ghép vị trí',
                        line=dict(color='#16826f', width=3), hoverinfo='skip')
    fig.add_scatter(
        x=sar, y=[1]*len(sar), mode='markers+text', name='SAR',
        marker=dict(size=14, color='#12598e'), text=[f'SAR {i+1}' for i in range(len(sar))],
        textposition='top center', hovertemplate='%{text}<br>%{x:.0f} m<extra></extra>',
    )
    if ais:
        fig.add_scatter(
            x=list(ais.values()), y=[0]*len(ais), mode='markers+text', name='AIS',
            marker=dict(size=12, color='#aa5a18', symbol='diamond'),
            text=[f'AIS {key}' for key in ais], textposition='bottom center',
            hovertemplate='%{text}<br>%{x:.0f} m<extra></extra>',
        )
    else:
        fig.add_annotation(x=0, y=0, text='Thiếu bản tin AIS', showarrow=False, font=dict(color='#5a6c7c'))
    left, right = min([*sar, *ais.values()]), max([*sar, *ais.values()])
    margin = max(9, (right-left) * .13)
    fig.update_layout(
        height=232, margin=dict(l=8, r=10, t=14, b=10), showlegend=False,
        xaxis=dict(range=[left-margin, right+margin], title='Độ lệch về phía đông (m)', fixedrange=True),
        yaxis=dict(tickvals=[0, 1], ticktext=['AIS', 'SAR'], range=[-.32, 1.32], fixedrange=True),
    )
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False}, key='evidence_positions')
    st.caption('Hai hàng biểu diễn cùng một trục vị trí. Đường nối biểu thị cặp được thuật toán chấp nhận về vị trí.')


def render_improvements(root: Path):
    st.markdown('''<div class="sonar-hero"><div class="sonar-eyebrow">KIỂM TRA BẰNG CHỨNG</div>
    <div class="sonar-title">Biết khi nào chưa thể kết luận.</div>
    <div class="sonar-copy">Tự kiểm tra cách SonarNet xử lý thiếu dữ liệu, thông tin mâu thuẫn và những cặp ghép không chắc chắn.</div></div>''', unsafe_allow_html=True)
    final_report = root/'output/pdf/SonarNet_Bao_cao_Chang1_Giu_cap_AIS_20261118.pdf'
    if final_report.is_file():
        st.download_button('Tải báo cáo cải tiến Chặng 1', final_report.read_bytes(),
                           final_report.name, 'application/pdf', key='download_chang1_report')
    if st.toggle('Mở hồ sơ ảnh SAR thật thiếu AIS', key='evidence_open_snapshot'):
        render_snapshot(root)
    render_contrast_recall(root)
    render_evaluation_summary(root, detailed=True)
    render_vn_recall(root)
    render_fresh_recall(root)
    st.subheader('1. Thử các tình huống khó')
    st.info('DỮ LIỆU MÔ PHỎNG: các điểm, mã AIS và kích thước dưới đây do kịch bản tạo ra. Thuật toán ghép và phân loại là mã đang dùng trong dự án.')
    label = st.selectbox('Tình huống kiểm tra', list(SCENARIOS), key='evidence_case')
    kind = SCENARIOS[label]
    a, b = st.columns(2)
    age = a.slider('Độ lệch thời gian AIS (giây)', 0, 900, 600 if kind in {'stale','stale_nearby'} else 10,
                   key='evidence_age_' + kind, disabled=kind == 'missing')
    sigma = b.slider('Độ bất định vị trí AIS (m)', 1, 400, 20,
                     key='evidence_sigma_' + kind, disabled=kind == 'missing')
    rows, payload = run_scenario(kind, age, float(sigma))
    draw_scenario(payload)
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    if kind == 'missing_size':
        st.warning('Vị trí có thể ghép được nhưng thiếu kích thước khai báo để đối chiếu. Không suy ra “trung thực” từ dữ liệu bị thiếu.')
    elif kind == 'conflict':
        st.warning('Kích thước từ ảnh và khai báo khác nhau. Đây là dấu hiệu cần xác minh, chưa chứng minh khai báo sai hay hành vi vi phạm.')
    elif kind == 'bias':
        st.warning('Mỗi chuỗi AIS bị dịch 160 m theo hai hướng ngược nhau. Hai cặp gần nhất nhìn có vẻ hợp lý. Hệ thống giữ ca này để rà soát nếu ứng viên cạnh tranh có thể làm đổi thứ tự ghép.')
    elif kind == 'stale_nearby':
        st.warning('Cặp đề xuất ban đầu dùng AIS 100. Nếu cặp này không qua kiểm tra, hệ thống giữ ca để rà soát. AIS 101 ở gần có thể là một tàu khác.')
    elif not payload['matches']:
        st.warning('Hệ thống chưa xác nhận cặp ghép. Không có cặp ghép không chứng minh tàu tắt AIS.')
    else:
        st.success('Đạt điều kiện ghép vị trí trong kịch bản. Kết luận nghiệp vụ vẫn đang chờ xác minh.')
    st.download_button('Tải kết quả tình huống', json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
                       'sonarnet-tinh-huong.json', 'application/json')
    with st.expander('Vì sao một cặp ghép bị từ chối?'):
        st.markdown('''- AIS phải cách thời điểm chụp **không quá 180 giây**, độ bất định vị trí **không quá 150 m**.
- Khoảng cách ghép tối đa là giá trị nhỏ hơn giữa **500 m** và **3 × độ bất định kết hợp của SAR/AIS**.
- Cố định đề xuất theo khoảng cách trước khi kiểm tra chất lượng. Nếu từ chối đề xuất, hệ thống không ghép sang ứng viên khác.
- Kiểm tra ở cả hai đầu. Nếu khoảng cách với ứng viên tiếp theo chưa đủ tách biệt khi xét dịch chuyển vị trí, cặp được giữ lại để rà soát.

Đây là ngưỡng nghiên cứu mặc định, chưa hiệu chỉnh bằng AIS thực địa. Trong mục **Quan sát → Kiểm tra chi tiết**, đánh giá nghiệp vụ yêu cầu người rà soát, căn cứ và xác nhận; bản xuất giữ lại các thông tin này. Tên người rà soát là thông tin tự khai, chưa có đăng nhập xác thực.''')

    st.subheader('2. Ghép đúng, ghép sai và từ chối ghép')
    directory = root / 'reports/final/ais_matching'
    if (directory / 'summary.csv').exists():
        frame = pd.read_csv(directory / 'summary.csv')
        scenarios = dict(fresh_separated='AIS mới, tàu cách xa', crossing_ambiguous='Quỹ đạo giao nhau',
            noisy_ais='AIS nhiễu', stale_ais='AIS quá cũ', missing_ais='Thiếu AIS', unknown_sigma='Chưa biết độ bất định')
        shown = frame.copy()
        shown['scenario'] = shown.scenario.map(scenarios)
        shown['method'] = shown.method.map({'distance_only':'Chỉ khoảng cách', 'quality_gated':'Có kiểm tra chất lượng'})
        shown = shown.rename(columns={'scenario':'Tình huống','method':'Phương pháp','detections':'Số điểm',
            'accepted':'Đã ghép','correct_identity':'Đúng nhãn mô phỏng','wrong_identity':'Sai nhãn mô phỏng',
            'abstained':'Từ chối ghép','unsafe_accepted':'Ghép khi điều kiện chưa đủ'})
        st.dataframe(shown, hide_index=True, use_container_width=True)
        st.caption('600 kịch bản / 1.200 điểm SAR mô phỏng; 100 lần mỗi tình huống, seed 20261116. Hai phương pháp nhận cùng đầu vào. Từ chối ghép làm giảm độ phủ; bảng này không đo độ chính xác ngoài thực địa.')
        st.download_button('Tải bảng đối chứng AIS', (directory/'summary.csv').read_bytes(), 'doi-chung-ais.csv', 'text/csv')
    else:
        st.info('Chưa có báo cáo stress test tại bản triển khai này.')
    render_trajectory_evidence(root)
    render_noaa_replay(root)
    render_frozen_assignment(root)
    render_coincident_replay(root)

    st.subheader('3. Đánh giá trên ảnh SAR thật')
    render_slc_adaptation(root)
    sar = root / 'reports/final/independent_sar'
    if not (sar / 'results.json').exists():
        st.info('Chưa có kết quả kiểm thử độc lập tại bản triển khai này.')
        return
    report = json.loads((sar / 'results.json').read_text())
    model = report['models']['yolo_rebuilt']
    metrics = model['metrics']
    a, b, c = st.columns(3)
    a.metric('Ảnh kiểm thử độc lập', f"{report['counts']['test']:,}")
    b.metric('Precision / Recall', f"{metrics['precision']:.1%} / {metrics['recall']:.1%}")
    c.metric('AP50 / AP50-95', f"{metrics['mAP@0.5']:.3f} / {metrics['mAP@0.5:0.95']:.3f}")
    st.caption('LS-SSDD thật; YOLO11n huấn luyện lại. Tách cảnh, nhóm vùng và ngày UTC trước huấn luyện; ngưỡng chọn trên validation. Đây là bộ chia riêng, không phải điểm benchmark chính thức hoặc kết quả lịch sử của mô hình cũ.')
    scores = []
    names = {'global_threshold': 'Ngưỡng sáng toàn cục (đối chứng đơn giản)', 'yolo_rebuilt': 'YOLO11n huấn luyện lại'}
    for name, result in report['models'].items():
        m = result['metrics']
        scores.append({'Phương pháp': names.get(name, name), 'AP50': m['mAP@0.5'],
            'AP50-95': m['mAP@0.5:0.95'], 'Precision': m['precision'], 'Recall': m['recall'],
            'Báo nhầm': m['false_positive'], 'Bỏ sót': m['false_negative'],
            'Báo nhầm / triệu pixel': round(m['false_alarms_per_megapixel'], 3),
            'Độ trễ CPU trung vị (ms)': round(m['latency_ms_median'], 2)})
    st.dataframe(pd.DataFrame(scores), hide_index=True, use_container_width=True)
    st.warning(f"Điểm yếu cần nhìn thẳng: recall trên nhóm ảnh có đất liền chỉ {metrics['nearshore_recall']:.2%}; bỏ sót {metrics['false_negative']:,} / {metrics['n_ground_truth']:,} nhãn tàu trên toàn tập. Không dùng kết quả này để kết luận một vùng biển không có tàu.")
    st.caption('Cả hai chạy cùng CPU, 4 luồng; độ trễ gồm tiền xử lý, suy luận và NMS, không gồm đọc tệp. AP tích phân VOC, không đồng nhất COCO/Ultralytics. Đối chứng ngưỡng sáng không đại diện cho các mô hình SAR mạnh khác.')
    with st.expander('Cách chia tập và truy vết dữ liệu'):
        st.markdown("""**3.491 train / 594 validation / 3.000 test.** Cách ly 115 ảnh train/validation có chữ ký ảnh gần giống qua các tập; giữ nguyên toàn bộ test. Không còn trùng pixel hoặc cặp dHash ≤ 3 đi qua các tập được giữ lại.

- Train: cảnh 01/02/03/04/05/08. Validation: cảnh 10. Test: cảnh 11-15.
- Loại cảnh 06/09 gần vùng test và cảnh 07 gần vùng validation.
- Nhãn do tác giả LS-SSDD cung cấp; chưa phải nhãn được chuyên gia SonarNet kiểm định lại.
- [Dữ liệu và tài liệu gốc LS-SSDD](https://github.com/TianwenZhang0825/LS-SSDD-v1.0-OPEN) · [Bài báo nguồn](https://doi.org/10.3390/rs12182997).""")
        st.code('SHA256 checkpoint: ' + report['weights_sha256'] + '\nSHA256 manifest: ' + report['manifest_sha256'])
    with st.expander('Kết quả từng cảnh và các lỗi khó nhất'):
        st.dataframe(pd.DataFrame(model['per_scene'])[['scene_id', 'images', 'precision', 'recall', 'false_positive', 'false_negative', 'nearshore_recall']], hide_index=True, use_container_width=True)
        st.caption('Lam: nhãn gốc; cam: dự đoán. Chọn tự động 3 ảnh nhiều báo nhầm nhất và 3 ảnh nhiều bỏ sót nhất; không chọn ảnh đẹp để che lỗi.')
        cols = st.columns(2)
        for i, entry in enumerate(model['error_gallery']):
            cols[i % 2].image(str(sar / entry['file']), caption=f"{entry['id']}: {entry['false_positives']} báo nhầm, {entry['missed_ships']} bỏ sót", use_container_width=True)
    st.info('Riêng LS-SSDD: chưa xác minh quy đổi pixel sau resampling. Sai số tâm 1,82 pixel chỉ là sai lệch so với nhãn trên các cặp đã ghép đúng. Nhóm ven bờ ở đây nghĩa là ảnh có đất liền.')
    st.download_button('Tải kết quả SAR và giới hạn đánh giá', (sar / 'results.json').read_bytes(),
                       'sonarnet-sar-doc-lap.json', 'application/json')
    render_georeferenced_benchmark(root)


def render_trajectory_evidence(root: Path):
    path = root/'reports/final/ais_trajectories_guard_20261118/summary.csv'
    if not path.is_file():
        return
    frame = pd.read_csv(path)
    gated = frame[frame['method'].str.startswith('quality_gated')]
    previous = gated[gated['method'] == 'quality_gated_previous'].set_index('scenario')
    current = gated[gated['method'] == 'quality_gated'].set_index('scenario')
    with st.expander('Đối chứng từ chuỗi bản tin AIS có nhiễu và lệch vị trí'):
        st.caption('840 kịch bản mô phỏng. Cùng bản tin đầu vào đi qua bộ làm trơn Kalman của SonarNet, sau đó so sánh ba cách ghép.')
        metrics = st.columns(3)
        for column, scenario, title in zip(
                metrics, ('position_bias', 'position_bias_beyond_guard', None),
                ('Ghép sai · lệch 128–185 m', 'Ghép sai · lệch 208–242 m', 'Ghép đúng · toàn phép thử')):
            if scenario:
                before = previous.at[scenario, 'links_wrong']
                after = current.at[scenario, 'links_wrong']
            else:
                before, after = previous['links_correct'].sum(), current['links_correct'].sum()
            column.metric(title, f'{before} → {after}')
        st.caption('So với cổng tin cậy cũ. Ghép được vẫn cần xác minh. Sai lệch lớn hoặc thiếu ứng viên đối chiếu vẫn có thể dẫn đến ghép sai.')
        labels = {
            'mixed_quality': 'Tín hiệu tốt, cũ, nhiễu và thiếu xen kẽ',
            'near_crossing': 'Hai tàu sát nhau ở điểm giao',
            'keep_two_crossing_tracks_when_separated': 'Tại lúc chụp hai tàu đã tách',
            'unlabeled_clutter_near_track': 'Nhiễu SAR gần vị trí tàu',
            'sparse_one_sided': 'Chỉ có bản tin trước giờ chụp',
            'position_bias': 'Lệch vị trí 128–185 m',
            'position_bias_beyond_guard': 'Lệch vị trí 208–242 m',
        }
        methods = {'distance_only':'Khoảng cách', 'quality_gated_previous':'Cổng cũ', 'quality_gated':'Cổng có kiểm tra độ nhạy'}
        shown = frame.assign(scenario=frame['scenario'].map(labels), method=frame['method'].map(methods))
        st.dataframe(shown.rename(columns=dict(scenario='Tình huống', method='Cách ghép', points='Điểm SAR',
            links_correct='Ghép đúng', links_wrong='Ghép nhầm tàu', links_to_clutter='Ghép nhầm nhiễu',
            abstained_on_target='Mục tiêu còn lại', clutter_unmatched='Nhiễu không ghép')),
            hide_index=True, use_container_width=True)
        st.download_button('Tải đối chứng chuỗi bản tin AIS', path.read_bytes(), 'doi-chung-chuoi-ais.csv', 'text/csv')


def render_noaa_replay(root: Path):
    evidence = root / 'reports/final/noaa_ais_replay_20261118'
    choices = {
        'Hai ngày khảo sát': evidence / 'development/results.json',
        'Ngày giữ riêng': evidence / 'confirmation/results.json',
    }
    available = {label:path for label,path in choices.items() if path.is_file()}
    if not available:
        return
    with st.expander('Đối chứng trên bản tin AIS thật của NOAA'):
        scope = st.radio('Ngày đối chứng AIS', list(available), horizontal=True, key='noaa_replay_day')
        path = available[scope]
        report = json.loads(path.read_text())
        group = st.selectbox('Mật độ tàu trong cửa sổ kiểm tra',
            ['Tất cả', 'Có tàu khác trong 250 m', 'Cách tàu gần nhất hơn 250 m'], key='noaa_replay_density')
        key = {'Tất cả':'overall','Có tàu khác trong 250 m':'neighbor_250m',
               'Cách tàu gần nhất hơn 250 m':'separated'}[group]
        methods = {'distance_only':'Khoảng cách gần nhất', 'guard_0m':'Cổng gốc',
                   'guard_25m':'Biên 25 m', 'guard_50m':'Biên 50 m',
                   'guard_75m':'Biên 75 m', 'guard_100m':'Biên 100 m'}
        rows = []
        for method, group_counts in report['results'].items():
            m = group_counts[key]
            rows.append({'Cách ghép':methods[method], 'Điểm kiểm tra':m['targets'],
                         'Ghép đúng mã':m['correct'],'Ghép sai mã':m['wrong'],'Từ chối':m['unassigned']})
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        selected = report['selection']['selected_guard_m']
        if selected is None:
            st.warning('Không biên nào giảm số ghép sai trên cả hai ngày khảo sát mà vẫn giữ mức giảm ghép đúng trong 5 điểm phần trăm.')
        st.caption('Đầu vào và mốc đối chiếu là bản tin NOAA ở ba khu vực cảng. Bản tin giữ lại thay cho vị trí SAR trong phép thử này. Kết quả đo khả năng nối lại mã bản tin trong cùng nguồn, chưa đo độ chính xác ghép trực tiếp SAR–AIS.')
        st.download_button('Tải số đếm và giao thức NOAA', path.read_bytes(), 'sonarnet-noaa-ais.json',
                           'application/json', key='noaa_replay_download')


def render_frozen_assignment(root: Path):
    directory = root/'reports/final/ais_preserve_proposal_20261118'
    path = directory/'held_out.json'
    if not path.is_file():
        return
    day = json.loads(path.read_text())['days']['2024-12-13']
    with st.expander('Kiểm tra lỗi đổi đối tác sau khi lọc AIS'):
        st.caption('Ngày 13/12/2024 được giữ riêng để phát lại bản tin NOAA theo giờ. Mốc đối chiếu là bản tin cùng nguồn được giấu khỏi đầu vào.')
        names = {'gate_first':'Lọc trước, ghép sau · cổng gốc',
                 'gate_first_100m':'Lọc trước, ghép sau · biên 100 m',
                 'assign_then_veto_200m':'Giữ cặp ban đầu, sau đó kiểm tra'}
        rows = []
        for key,label in names.items():
            m = day['results'][key]['overall']
            rows.append({'Phương án':label,'Ghép đúng mã':m['correct'],'Ghép sai mã':m['wrong'],
                         'Từ chối':m['unassigned'],'Đổi sang mã khác':day['reroutes'][key]['altered']})
        st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
        st.caption('Bảng đo khả năng nối lại mã AIS ở các cửa sổ lịch sử. Kết quả trên ảnh SAR thật nằm ở phép thử cùng lượt chụp bên dưới.')
        st.download_button('Tải số đếm ngày giữ riêng',path.read_bytes(),'sonarnet-giu-cap-ais.json','application/json')


def render_coincident_replay(root: Path):
    directory = root/'reports/final/coincident_sar_ais_20261118'
    path = directory/'results.json'
    if not path.is_file():
        return
    report = json.loads(path.read_text())
    with st.expander('Xem cảnh Sentinel-1 và AIS cùng lượt chụp'):
        acquisition = report['raster_source']['source_acquired_at']
        st.write(f"**New York Harbor · {acquisition[:10]} · {acquisition[11:19]} UTC**")
        st.caption('Giờ giữa cảnh Sentinel-1 RTC. AIS NOAA được lấy trong ±10 phút. Mốc đối chiếu trong ±20 giây được giữ ngoài đầu vào ghép.')
        a,b,c = st.columns(3)
        a.metric('Ứng viên radar',report['radar_candidates'])
        b.metric('Quỹ đạo AIS ước lượng',report['estimated_ais_tracks'])
        c.metric('Đối chiếu vị trí đủ điều kiện',report['spatial_references'])
        names = {'distance_only':'Khoảng cách','previous_gates':'Cổng gốc','100m_guard':'Biên cạnh tranh 100 m',
                 'propose_then_veto':'Giữ nguyên đối tác đề xuất'}
        rows = [{'Cách ghép':names[k], 'Cặp đề xuất':m['proposed'],
                 'Đồng thuận vị trí':m['agree'], 'Đề xuất chưa có mốc đối chiếu':m['proposed_without_reference'],
                 'Giữ lại để rà soát':m['withheld']} for k,m in report['matching'].items()]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        st.warning('Phép thử đo mức đồng thuận với mốc AIS giữ lại. Các khung và cặp ghép cần người có chuyên môn xác minh trước khi đưa ra kết luận về tàu.')
        tiles = [r for r in report['tiles'] if r['usable']]
        tile = st.selectbox('Ô ảnh radar',tiles,format_func=lambda r:f"Ô {r['tile']+1} · {r['detected_candidates']} ứng viên",
                            key='coincident_tile')
        marked = st.toggle('Hiện khung radar',value=True,key='coincident_marked')
        name = tile['marked'] if marked else f"tile_{tile['tile']}.png"
        path_image = directory/name
        if path_image.is_file():
            st.image(str(path_image),width=680,caption='Lam: có mốc AIS gần và tách biệt. Vàng: ứng viên còn thiếu mốc đối chiếu.')
        st.download_button('Tải kết quả đồng thời SAR–AIS',path.read_bytes(),'sonarnet-sar-ais-cung-canh.json','application/json')


def render_slc_adaptation(root: Path):
    directory = root/'reports/final/opensar_adaptation_20261118'
    path = directory/'results.json'
    budget_path = directory/'review-budget/results.json'
    if not (path.is_file() and budget_path.is_file()):
        return
    runs = json.loads(path.read_text())['evaluation']
    budget = json.loads(budget_path.read_text())
    st.markdown('#### Kiểm tra mô hình huấn luyện trên SLC VV')
    st.caption('Huấn luyện từ COCO trên 1.669 ô OpenSAR ở 7 cảnh. Chọn checkpoint và ngưỡng trên một cảnh riêng. Chọn nhóm để so sánh các cách ưu tiên ứng viên.')
    names = {'diagnostic': 'Ba cảnh đối chiếu lại', 'north_sea': 'Cảnh Biển Bắc giữ riêng'}
    cohort = st.radio('Nhóm ảnh kiểm tra', list(names), format_func=names.__getitem__,
                      horizontal=True, key='slc_adaptation_cohort')
    run = runs[cohort]
    methods = {
        'reference_ls_ssdd': 'YOLO học trên LS-SSDD',
        'guard_ring_cfar': 'CFAR vòng nền',
        'adapted_slc_vv': 'YOLO học trên SLC VV',
    }
    all_scores = [(methods[name], item['metrics']) for name, item in run['models'].items()]
    short = budget['evaluation'][cohort]['metrics']
    all_scores.append(('Danh sách ưu tiên · tối đa 1 điểm/20 km²', short))
    coastal_path = directory/'coastal-budget/results.json'
    if coastal_path.is_file():
        coastal = json.loads(coastal_path.read_text())['evaluation'][cohort]['metrics']
        all_scores.append(('Cùng giới hạn · dành 20% lượt cho ven bờ', coastal))
    rows = []
    for name, m in all_scores:
        coast = m['by_distance_to_mapped_shore_m']['500']
        rows.append({'Phương án': name, 'Nhãn khớp': f"{m['true_positive']}/{m['n_ground_truth']}",
                     'Không khớp nhãn': m['false_positive'],
                     'Không khớp/km²': f"{m['benchmark_unmatched_per_km2']:.4f}",
                     'Nhãn ven bờ ≤500 m': f"{coast['matched']}/{coast['labels']}"})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    selected = run['models']['adapted_slc_vv']
    m = selected['metrics']
    st.caption(f"{run['chips']} ô · {run['scenes']} cảnh · {m['evaluated_water_scene_km2']:,.0f} km² biển ước tính. "
               f"CPU 4 luồng: {selected['latency_ms']['p50']:.1f} ms trung vị/ô. Sai lệch tâm trung vị trên "
               f"{m['projected_box_center_error_m']['n']} hộp khớp là {m['projected_box_center_error_m']['median']:.1f} m so với hộp nhãn.")
    st.warning('Giới hạn danh sách giảm số điểm phải rà và giảm cả số nhãn tìm được. Đây là phép phát lại sau kiểm thử. '
               'Các phép đo so với nhãn nguồn; chưa có xác minh thực địa để đưa mô hình này lên bản đồ.')
    gallery = directory/'gallery.json'
    if gallery.is_file():
        for image in json.loads(gallery.read_text()):
            if image['cohort'] == cohort:
                with st.expander('Mở ảnh kiểm tra và hộp dự đoán'):
                    st.image(str(directory/image['file']), use_container_width=True,
                             caption=image['selection'] + ' · Lam: nhãn · Cam: dự đoán khớp · Đỏ: dự đoán không khớp.')
    a, b = st.columns(2)
    a.download_button('Tải kết quả kiểm thử SLC', path.read_bytes(), 'sonarnet-slc-vv.json', 'application/json')
    b.download_button('Tải kết quả giới hạn rà soát', budget_path.read_bytes(),
                      'sonarnet-slc-review-budget.json', 'application/json')
    if coastal_path.is_file():
        b.download_button('Tải đối chứng có ưu tiên ven bờ', coastal_path.read_bytes(),
                          'sonarnet-slc-coastal-budget.json', 'application/json')


def render_georeferenced_benchmark(root: Path):
    directory = root / 'reports/final/opensar_geo_20261118'
    path = directory / 'results.json'
    if not path.is_file():
        return
    report = json.loads(path.read_text())
    models = report['models']
    yolo = models['yolo']['metrics']
    close = yolo['by_distance_to_mapped_shore_m']['500']
    st.subheader('4. Đối chứng SAR có tọa độ')
    st.caption(f"OpenSAR Insight SLC VV: {report['test_chips']} ô từ {report['test_scene_count']} lượt chụp ngoài tập dùng để huấn luyện/chọn ngưỡng. Giữ riêng kết quả này với LS-SSDD.")
    a, b, c = st.columns(3)
    a.metric('Biển hợp lệ ước tính', f"{yolo['evaluated_water_scene_km2']:,.0f} km²")
    b.metric('Điểm không khớp nhãn/km²', f"{yolo['benchmark_unmatched_per_km2']:.3f}")
    c.metric('Tìm thấy trong 500 m từ bờ', f"{close['matched']}/{close['labels']}")
    names = {'yolo': 'YOLO11n huấn luyện lại', 'global_threshold': 'Ngưỡng sáng', 'local_contrast': 'Tương phản cục bộ'}
    st.dataframe(pd.DataFrame([{'Phương pháp': names[k], 'Precision': v['metrics']['precision'],
        'Recall': v['metrics']['recall'], 'Điểm không khớp': v['metrics']['false_positive'],
        'Điểm không khớp/km²': round(v['metrics']['benchmark_unmatched_per_km2'], 3),
        'CPU trung vị (ms)': round(v['metrics']['latency_ms_p50'], 2)} for k,v in models.items()]),
        hide_index=True, use_container_width=True)
    st.write(f"Trên {yolo['projected_box_center_error_m']['n']} cặp khớp: sai lệch tâm hộp trung vị "
             f"{yolo['projected_box_center_error_m']['median']:.1f} m; sai lệch hai chiều hộp "
             f"{yolo['projected_box_width_error_m']['median']:.1f} m và {yolo['projected_box_height_error_m']['median']:.1f} m. "
             f"So với tâm WGS84 trong nhãn nguồn: {yolo['error_to_source_wgs84_centroid_m']['median']:.1f} m trung vị.")
    st.warning('Hộp bao ảnh không phải kích thước thân tàu. Tọa độ nguồn và bốn góc nội suy không phải GPS độc lập; “không khớp” không khẳng định là báo nhầm ngoài thực địa. Số nhãn gần bờ ít, không dùng để suy rộng. Chế độ bản đồ vẫn loại dải 500 m; phép thử mô hình ở đây thì không.')
    with st.expander('Kiểm tra cách đo và xem ca lỗi'):
        st.write('Đo trên nhãn tàu HIGH/MEDIUM trong phần biển của ảnh. Loại đất, pixel rỗng và phần trùng lặp giữa các ô cùng lượt chụp. Mặt nạ địa lý GSHHG L1; nội suy theo bốn góc ảnh từ XML. Hai đối chứng đều đơn giản: một cho quá nhiều điểm, một không tìm được tàu ở điểm vận hành đã khóa.')
        st.markdown('[Dữ liệu và nhãn OpenSAR Insight](https://huggingface.co/datasets/opensar-insight/vessel-detection-dataset) · [Đường bờ GSHHG](https://www.soest.hawaii.edu/pwessel/gshhg/)')
        gallery = directory / 'gallery.json'
        if gallery.is_file():
            cols = st.columns(2)
            for i, item in enumerate(json.loads(gallery.read_text())):
                cols[i % 2].image(str(directory / item['file']), caption=f"Ô {item['id']} · {item['fp']} không khớp · {item['fn']} bỏ sót", use_container_width=True)
    st.download_button('Tải kết quả đối chứng có tọa độ', path.read_bytes(), 'sonarnet-opensar-geo.json', 'application/json')
    render_repeatability_check(root)


def render_repeatability_check(root: Path):
    path = root / 'reports/final/opensar_confirmation_20261118/results.json'
    if not path.is_file():
        return
    report = json.loads(path.read_text())
    model = report['models']['yolo']
    m = model['metrics']
    coast = m['by_distance_to_mapped_shore_m']['500']
    st.subheader('5. Kiểm tra lại trên các cảnh mới')
    st.warning(f"Với cùng checkpoint và ngưỡng đã khóa, trên {report['test_chips']} ô từ "
               f"{report['test_scene_count']} cảnh mới, YOLO chỉ khớp {m['true_positive']}/{m['n_ground_truth']} nhãn; "
               f"trong dải 500 m từ bờ chỉ {coast['matched']}/{coast['labels']}. "
               'Kết quả trước đó không lặp lại trên những cảnh này. Không dùng bản đồ để quyết định một vùng biển không có tàu.')
    shots=[]
    for scene, outcome in sorted(model['per_scene'].items(), key=lambda row:row[0].split('__',1)[1].split('_')[1]):
        day=scene.split('__',1)[1].split('_')[1][:8]
        shots.append({'Ngày chụp UTC': f'{day[6:]}/{day[4:6]}/{day[:4]}',
            'Khớp nhãn': outcome['true_positive'], 'Số nhãn': outcome['n_ground_truth'],
            'Điểm không khớp nhãn': outcome['false_positive']})
    st.dataframe(pd.DataFrame(shots), hide_index=True, use_container_width=True)
    st.caption('Các cảnh mới khác vùng/ngày với dữ liệu đã dùng; nhãn thuộc cùng kho OpenSAR Insight, không phải xác nhận GPS độc lập. Không thay checkpoint của bản đồ dựa trên các thử nghiệm này.')
    st.download_button('Tải đối chứng trên ba cảnh mới', path.read_bytes(), 'sonarnet-opensar-canh-moi.json', 'application/json')
