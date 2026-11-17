"""Executable evidence for the final-round requirements, with explicit provenance."""
from __future__ import annotations

import json
import math
from pathlib import Path
import pandas as pd
import streamlit as st
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
    'Hai quỹ đạo giao nhau': 'crossing',
    'Dữ liệu đủ điều kiện ghép': 'clean',
}
REASONS = {
    'no_ais': 'Không có AIS để đối chiếu',
    'out_of_range': 'Không có AIS trong ngưỡng ghép',
    'stale_ais': 'AIS cách thời điểm chụp quá xa',
    'uncertain_position': 'Độ bất định vị trí vượt ngưỡng',
    'invalid_ais': 'AIS thiếu hoặc có giá trị không hợp lệ',
    'ambiguous': 'Nhiều ứng viên cạnh tranh; chưa thể chọn',
    'assigned_elsewhere': 'Ứng viên đã ghép với điểm khác',
    'matched': 'Đạt điều kiện ghép vị trí',
}


def run_scenario(kind, age_s=None, sigma_m=20.):
    """Illustrative inputs go through the production association/classification code."""
    cfg = RunConfig()
    fusion = SARAISFusion(cfg)
    positions = [-5., 5.] if kind == 'crossing' else [0.]
    detections = [Detection(i, 0., x / 111195., 80., 20., (0, 0, 8, 2))
                  for i, x in enumerate(positions)]
    estimates = {}
    if kind != 'missing':
        for i, x in enumerate(positions):
            offset = 700. if kind == 'distant' else 3.
            age = age_s if age_s is not None else (600. if kind == 'stale' else 10.)
            estimate = KalmanEstimate(0., (x + offset) / 111195., 0., 0., sigma_m, age, 5)
            estimate.declared_length_m = float('nan') if kind == 'missing_size' else (200. if kind == 'conflict' else 80.)
            estimates[100 + i] = estimate
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
        operational_assessment=pending_review())


def render_improvements(root: Path):
    st.markdown('''<div class="sonar-hero"><div class="sonar-eyebrow">KIỂM TRA BẰNG CHỨNG</div>
    <div class="sonar-title">Biết khi nào chưa thể kết luận.</div>
    <div class="sonar-copy">Tự kiểm tra cách SonarNet xử lý thiếu dữ liệu, thông tin mâu thuẫn và những cặp ghép không chắc chắn.</div></div>''', unsafe_allow_html=True)
    st.caption('Ảnh SAR thật, thử nghiệm ghép AIS mô phỏng và chỉ số đánh giá được trình bày riêng. Ghép được vị trí không xác nhận danh tính hoặc tính hợp pháp.')
    st.subheader('1. Thử các tình huống khó')
    st.info('DỮ LIỆU MÔ PHỎNG: các điểm, mã AIS và kích thước dưới đây do kịch bản tạo ra. Thuật toán ghép và phân loại là mã đang dùng trong dự án.')
    label = st.selectbox('Tình huống kiểm tra', list(SCENARIOS), key='evidence_case')
    kind = SCENARIOS[label]
    a, b = st.columns(2)
    age = a.slider('Độ lệch thời gian AIS (giây)', 0, 900, 600 if kind == 'stale' else 10,
                   key='evidence_age_' + kind, disabled=kind == 'missing')
    sigma = b.slider('Độ bất định vị trí AIS (m)', 1, 400, 20,
                     key='evidence_sigma_' + kind, disabled=kind == 'missing')
    rows, payload = run_scenario(kind, age, float(sigma))
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    if kind == 'missing_size':
        st.warning('Vị trí có thể ghép được nhưng thiếu kích thước khai báo để đối chiếu. Không suy ra “trung thực” từ dữ liệu bị thiếu.')
    elif kind == 'conflict':
        st.warning('Kích thước từ ảnh và khai báo khác nhau. Đây là dấu hiệu cần xác minh, chưa chứng minh khai báo sai hay hành vi vi phạm.')
    elif not payload['matches']:
        st.warning('Hệ thống chưa xác nhận cặp ghép. Không có cặp ghép không chứng minh tàu tắt AIS.')
    else:
        st.success('Đạt điều kiện ghép vị trí trong kịch bản. Kết luận nghiệp vụ vẫn đang chờ xác minh.')
    st.download_button('Tải kết quả tình huống', json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
                       'sonarnet-tinh-huong.json', 'application/json')
    with st.expander('Vì sao một cặp ghép bị từ chối?'):
        st.markdown('''- AIS phải cách thời điểm chụp **không quá 180 giây**, độ bất định vị trí **không quá 150 m**.
- Khoảng cách ghép tối đa là giá trị nhỏ hơn giữa **500 m** và **3 × độ bất định kết hợp của SAR/AIS**.
- Khi các ứng viên có khoảng cách gần như nhau, hệ thống giữ trạng thái chưa ghép để chuyên viên kiểm tra.

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

    st.subheader('3. Đánh giá trên ảnh SAR thật')
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
    st.info('Chưa xác minh đầy đủ quy đổi pixel sau resampling sang mét/diện tích. Chỉ số báo nhầm/km² và sai số mét chưa được công bố; sai số tâm 1,82 pixel là sai lệch so với nhãn trên các cặp đã ghép đúng, không phải độ chính xác định vị tuyệt đối. Nhóm ven bờ ở đây nghĩa là ảnh có đất liền.')
    st.download_button('Tải kết quả SAR và giới hạn đánh giá', (sar / 'results.json').read_bytes(),
                       'sonarnet-sar-doc-lap.json', 'application/json')
