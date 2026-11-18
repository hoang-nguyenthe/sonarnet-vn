"""Display published benchmark counts without loading the inference stack."""
from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

SAR_RESULTS = 'reports/final/opensar_adaptation_20261118/results.json'
AIS_RESULTS = 'reports/final/ais_preserve_proposal_20261118/held_out.json'
MULTISCALE_RESULTS = 'reports/final/sar_multiscale_20261118/results.json'


def format_number(value: int) -> str:
    return f'{value:,}'.replace(',', '.')


def rate(count: int, total: int) -> str:
    return f'{100 * count / total:.1f}'.replace('.', ',') + '%'


def render_evaluation_summary(root: Path, *, detailed=False) -> bool:
    sar_path, ais_path = root / SAR_RESULTS, root / AIS_RESULTS
    if not (sar_path.is_file() and ais_path.is_file()):
        return False
    scenes = json.loads(sar_path.read_text())['evaluation']
    diagnostic = scenes['diagnostic']['models']
    old_sar = diagnostic['reference_ls_ssdd']['metrics']
    new_sar = diagnostic['adapted_slc_vv']['metrics']
    old_coast = old_sar['by_distance_to_mapped_shore_m']['500']
    new_coast = new_sar['by_distance_to_mapped_shore_m']['500']
    days = json.loads(ais_path.read_text())['days']
    routes = days['2024-12-13']['results']
    old_ais = routes['gate_first_100m']['overall']
    new_ais = routes['assign_then_veto_200m']['overall']
    targets = new_sar['n_ground_truth']
    old_hits, new_hits = old_sar['true_positive'], new_sar['true_positive']
    before_correct, after_correct = old_ais['correct'], new_ais['correct']
    old_errors, new_errors = old_ais['wrong'], new_ais['wrong']
    ais_count = format_number(new_ais['targets'])

    st.subheader('Kết quả trước và sau cải tiến')
    st.markdown(
        f'''<style>
.chang1-results {{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}}
.chang1-result {{border:1px solid #7995aa44;border-radius:23px;padding:clamp(18px,2.7vw,33px);
    background:linear-gradient(155deg,#fff,#edf6f9);color:#122b41;min-width:0}}
.chang1-result h3 {{margin:0;color:#183751!important;font-size:clamp(17px,2.3vw,22px)!important}}
.chang1-result-value {{display:flex;flex-wrap:wrap;gap:.24em;align-items:baseline;
    margin:.38em 0;font-size:clamp(29px,5.1vw,58px);font-weight:720;letter-spacing:-.075em;
    line-height:1.12;font-variant-numeric:tabular-nums}}
.chang1-result-value strong {{color:#006457}}
.chang1-result-arrow {{color:#3f6478;font-size:.57em;letter-spacing:0}}
.chang1-result p {{font-size:14px;color:#304f62;margin:9px 0 0;line-height:1.55}}
.chang1-result .chang1-scope {{margin:0;color:#3b5a71;font-size:12px}}
.chang1-result .chang1-review {{padding-top:10px;border-top:1px solid #a4bfc977}}
@media(max-width:680px) {{.chang1-results {{grid-template-columns:1fr;gap:11px}}}}
.st-key-recall_retest_metrics [data-testid="stMetricValue"] {{
    font-size:clamp(22px,3.5vw,40px);white-space:normal;line-height:1.14}}
</style>
<div class="chang1-results">
<article class="chang1-result">
<h3>Tìm được nhiều mục tiêu SAR hơn</h3>
<p class="chang1-scope">Sentinel-1 SLC VV · {scenes['diagnostic']['scenes']} cảnh đối chiếu</p>
<div class="chang1-result-value"><span>{old_hits}/{targets}</span> <span class="chang1-result-arrow">→</span> <strong>{new_hits}/{targets}</strong></div>
<p>Recall {rate(old_hits, targets)} → {rate(new_hits, targets)}.
Nhãn khớp trong 500 m từ bờ tăng từ {old_coast['matched']}/{old_coast['labels']} lên {new_coast['matched']}/{new_coast['labels']}.</p>
<p class="chang1-review">Điểm không khớp nhãn tăng từ {old_sar['false_positive']} lên {new_sar['false_positive']}.</p>
</article>
<article class="chang1-result">
<h3>Giảm ghép sai mã AIS</h3>
<p class="chang1-scope">Phát lại {ais_count} bản tin NOAA giữ riêng · 13/12/2024</p>
<div class="chang1-result-value"><span>{old_errors}</span> <span class="chang1-result-arrow">→</span> <strong>{new_errors}</strong></div>
<p>Số cặp ghép sai mã khi giữ nguyên đối tác đề xuất rồi kiểm tra chất lượng.</p>
<p class="chang1-review">Số cặp ghép đúng giảm từ {before_correct} xuống {after_correct}.</p>
</article>
</div>''',
        unsafe_allow_html=True,
    )
    st.caption(
        'SAR được chấm theo nhãn ảnh (IoU ≥ 0,50). Phép thử AIS dùng bản tin cùng nguồn bị giữ lại làm mốc. '
        'Hai phép đo chưa xác nhận hiệu quả nghiệp vụ tại vùng biển Việt Nam.'
    )

    multiscale_path = root / MULTISCALE_RESULTS
    if multiscale_path.is_file():
        render_recall_retest(multiscale_path, detailed=detailed)
    elif detailed:
        north = scenes['north_sea']['models']['adapted_slc_vv']['metrics']
        st.caption(
            f"Cảnh Biển Bắc giữ riêng có {north['true_positive']}/{north['n_ground_truth']} nhãn khớp "
            f"và {format_number(north['false_positive'])} điểm không khớp nhãn. "
            "Xem thêm bảng chi tiết về số điểm phải rà và ví dụ ảnh."
        )
    return True



def render_recall_retest(path: Path, *, detailed: bool) -> None:
    report = json.loads(path.read_text())
    cohorts = report['evaluation']
    cases = (
        ('diagnostic', 'Ba cảnh đối chiếu'),
        ('north_sea', 'Cảnh Biển Bắc'),
    )
    budget_label = 'Cùng giới hạn 1 ứng viên / 20 km²'
    scopes = {'full': 'Mọi ứng viên qua ngưỡng', 'fixed_budget': budget_label}
    if detailed:
        st.markdown('#### Kiểm tra thêm cách đọc SAR ở hai tỷ lệ')
        st.caption(
            'Cùng checkpoint SLC VV. Bản gốc đọc ở 512 px. Bản thử đọc ở 512 px và 768 px, '
            'thêm một lượt lật ngang rồi loại hộp trùng. Ngưỡng và cách đọc được chọn trên cảnh phát triển.'
        )
        mode = st.radio('Phạm vi so sánh', list(scopes), format_func=scopes.__getitem__,
                        horizontal=True, key='recall_retest_mode')
    else:
        mode = 'full'
        st.markdown('#### Thử thêm hai tỷ lệ ảnh SAR')
    with st.container(key='recall_retest_metrics'):
        columns = st.columns(2)
        for column, (key, heading) in zip(columns, cases):
            test = cohorts[key]
            before = test['methods']['baseline'][mode]
            after = test['methods']['candidate'][mode]
            n = before['n_ground_truth']
            old = before['true_positive']
            new = after['true_positive']
            column.metric(
                heading, f'{old}/{n} → {new}/{n}',
                f'{(new - old) * 100 / n:+.1f}'.replace('.', ',') + ' điểm % recall',
            )
            column.caption(
                f"{test['chips']} ô ảnh · Điểm không khớp nhãn "
                f"{format_number(before['false_positive'])} → {format_number(after['false_positive'])}."
            )
    if detailed:
        explain_recall_tradeoff(path, cohorts)
    else:
        gains = [group['methods']['candidate']['fixed_budget']['true_positive']
                 - group['methods']['baseline']['fixed_budget']['true_positive']
                 for group in cohorts.values()]
        st.caption(f'Cùng giới hạn rà soát, số nhãn khớp thay đổi {gains[0]:+d} ở ba cảnh '
                   f'và {gains[1]:+d} ở Biển Bắc. Đây là phép thử lại trên bốn cảnh đã báo cáo.')


def explain_recall_tradeoff(path: Path, cohorts: dict) -> None:
    def latency_range(method):
        times = [round(group['methods'][method]['latency_ms']['p50']) for group in cohorts.values()]
        return f'{min(times)}–{max(times)}'

    latency_before, latency_after = latency_range('baseline'), latency_range('candidate')
    st.caption(
        f'CPU 4 luồng, trung vị ở hai nhóm: từ khoảng {latency_before} ms/ô ở bản gốc '
        f'đến {latency_after} ms/ô ở bản thử. Bốn cảnh trên đã được báo cáo ở lượt trước, '
        'được giữ ngoài tập chọn cấu hình lần này.'
    )
    replay = path.with_name('threshold-and-coast.json')
    if replay.is_file():
        render_recall_controls(replay)
    st.download_button('Tải số liệu so sánh recall', path.read_bytes(),
                       'sonarnet-sar-recall.json', 'application/json', key='download_sar_recall')



def render_recall_controls(path: Path) -> None:
    results = json.loads(path.read_text())['evaluation']
    with st.expander('Xem tác động của ngưỡng điểm và ưu tiên ven bờ'):
        st.caption(
            'Phát lại dự đoán đã lưu để kiểm tra riêng ảnh hưởng của ngưỡng điểm. '
            'Cũng thử dành tối đa 20% suất rà soát cho ứng viên cách bờ không quá 500 m.'
        )
        rows = []
        for key, group in results.items():
            view = 'Ba cảnh đối chiếu' if key == 'diagnostic' else 'Cảnh Biển Bắc'
            native = group['native_at_candidate_threshold']['full']
            old = group['baseline']['coastal_budget']
            new = group['candidate']['coastal_budget']
            old_coast = old['by_distance_to_mapped_shore_m']['500']
            new_coast = new['by_distance_to_mapped_shore_m']['500']
            rows.append({
                'Nhóm cảnh': view,
                'Chỉ hạ ngưỡng ở 512 px · nhãn khớp': f"{native['true_positive']}/{native['n_ground_truth']}",
                'Điểm không khớp nhãn khi chỉ hạ ngưỡng': native['false_positive'],
                'Có ưu tiên bờ · tất cả nhãn': f"{old['true_positive']} → {new['true_positive']} / {new['n_ground_truth']}",
                'Có ưu tiên bờ · nhãn ≤500 m': f"{old_coast['matched']} → {new_coast['matched']} / {new_coast['labels']}",
            })
        st.dataframe(rows, hide_index=True, width='stretch')
        st.caption('Chỉ hạ ngưỡng tìm được nhiều nhãn hơn khi rà toàn bộ, nhưng cũng tạo nhiều điểm '
                   'không khớp hơn. Với cùng giới hạn rà soát, chỉ hạ ngưỡng giữ nguyên số nhãn khớp '
                   'của bản gốc ở cả hai nhóm.')
        st.download_button('Tải phép phát lại theo ngưỡng và ven bờ', path.read_bytes(),
                           'sonarnet-sar-nguong-va-ven-bo.json', 'application/json')
