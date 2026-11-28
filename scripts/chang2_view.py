"""Show the paired behavior evaluation and its scope in the public app."""
import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
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
        '[Kalman và kích thước](#stage2-kalman) · [Hành vi](#stage2-behavior) · '
        '[AIS thật](#stage2-ais) · [Rà từng ca](#stage2-review) · [Ảnh SAR](#stage2-sar) · [Giới hạn](#stage2-limits)'
    )
    render_ablation(metrics)
    render_real_ais(metrics)
    render_review(metrics)
    render_sar(metrics)
    st.subheader('6. Giới hạn và phép thử tiếp theo', anchor='stage2-limits')
    show_table(metrics['tables']['limits'])
    with st.container(horizontal=True, gap='small'):
        st.link_button('Tải bộ minh chứng ZIP', SITE+'chang2/SonarNet_Minh_chung_Chang2.zip')
        st.link_button('Dữ liệu và cấu hình tái lập', metrics['source'])


def show_table(rows, **kwargs):
    return st.dataframe(pd.DataFrame(rows[1:], columns=rows[0]), hide_index=True, width='stretch', **kwargs)


def source_link(label, filename):
    st.markdown(f'[{label}]({SITE}chang2/{filename})')


def render_ablation(data):
    tables = data['tables']
    st.subheader('1. Kalman và kiểm tra kích thước', anchor='stage2-kalman')
    st.write('So sánh trên cùng bản tin, cùng điểm SAR và cùng luật ghép. Kalman thay cách ước lượng vị trí AIS. '
             'Kiểm tra kích thước được bật hoặc tắt sau khi đã chọn cặp ghép.')
    show_table(tables['kalman'])
    st.caption('Hai cột “chỉ đúng” đếm riêng cặp được cứu và cặp bị mất khi đổi phương pháp. Ghép sai gồm nhầm tàu hoặc gán AIS vào điểm nhiễu.')
    with st.expander('Đồ thị kết quả của từng seed'):
        scenario = st.selectbox('Kịch bản ghép', list(data['kalman_seeds']), key='stage2_kalman_scenario')
        seed_rows = data['kalman_seeds'][scenario]
        frame = pd.DataFrame(seed_rows, columns=['Seed','Tuyến tính','Kalman','Số mục tiêu'])
        chart = go.Figure()
        for label, color in (('Tuyến tính','#6e8590'),('Kalman','#007967')):
            chart.add_bar(x=frame['Seed'].astype(str), y=frame[label], name=label, marker_color=color)
        chart.update_layout(barmode='group', height=270, xaxis_title='Seed thí nghiệm',
                            yaxis_title='Cặp đúng', legend_orientation='h', margin=dict(t=22,b=44,l=44,r=12))
        st.plotly_chart(chart, width='stretch', config={'displayModeBar':False}, key='stage2_kalman_plot')
        st.dataframe(frame, hide_index=True, width='stretch')
        source_link('Tải các cặp đối chứng theo từng cảnh', 'fusion-paired-scenes.csv')

    st.markdown('#### Khi số đo kích thước bị nhiễu')
    st.write('Cùng các cặp ghép đúng được đo với nhiễu 9% và 33%. Trong nhóm khai báo đúng, '
             'số cờ nhầm tăng từ **0 lên 478** khi nhiễu tăng. Vì vậy cần xem độ tin cậy kích thước trước khi dùng cờ.')
    show_table(tables['size'])
    with st.expander('Bật/tắt cổng kích thước trên từng cách ghép'):
        show_table(tables['size_gate'])
        source_link('Tải bảng theo từng kịch bản và mức sai lệch khai báo', 'size-by-factor.csv')

    st.subheader('2. Dữ liệu hành vi và danh sách ưu tiên', anchor='stage2-behavior')
    st.write('Mỗi seed chấm 240 quỹ đạo trên cùng năm điều kiện. Bảng tách đầu vào tốc độ/quỹ đạo, '
             'chất lượng dữ liệu học và số quỹ đạo 48/400/800.')
    show_table(tables['behavior'])
    st.caption('Macro-F1 là trung bình F1 của bốn lớp. Các giá trị trong bảng là trung bình qua 10 seed.')
    st.write('Ở nhóm tín hiệu chồng lấn, cùng 400 quỹ đạo học, chuyển từ học sạch sang học hỗn hợp '
             f"giúp macro-F1 tăng **{local_decimal(data['behavior_highlight'],3)}**.")
    with st.expander('Xem chênh lệch, khoảng 95% và bốn lớp theo seed'):
        scenario = st.selectbox('Điều kiện AIS', list(data['behavior_contrasts']), key='stage2_behavior_scenario')
        show_table([
            ['Thay đổi duy nhất','Δ macro-F1','95% thấp','95% cao','Seed tăng','Seed giảm'],
            *[[label, local_decimal(gap,3), local_decimal(low,3), local_decimal(high,3), up, down]
              for label, gap, low, high, up, down in data['behavior_contrasts'][scenario]],
        ])
        labels = list(dict.fromkeys(row[2] for row in data['behavior_seeds']))
        model = st.selectbox('Cấu hình để kiểm tra từng seed', labels, key='stage2_behavior_model')
        subset = [[row[0],*row[3:]] for row in data['behavior_seeds'] if row[1:3]==[scenario,model]]
        show_table([['Seed','Macro-F1','Câu','Kéo lưới','Neo đậu/trôi','Quá cảnh','Bỏ sót','Cờ nhầm'],*subset])
        source_link('Tải kết quả đầy đủ theo seed', 'behavior-factorial.csv')
    st.markdown('#### Đầu ra thực tế của chuỗi xử lý mô phỏng')
    st.write('Giữ cùng 4.400 cảnh cho cả 12 tổ hợp. Một ca ưu tiên đúng cần đồng thời ghép đúng tàu '
             'và đưa ca dương vào danh sách rà. So sánh cột “Ca đưa vào rà” với “Bỏ sót” để thấy khối lượng và đánh đổi.')
    show_table(tables['chain'])
    with st.expander('Tìm bước đầu tiên gây bỏ sót'):
        show_table(tables['chain_misses'])
        source_link('Tải dữ liệu chuỗi theo kịch bản và seed', 'chain-ablation.csv')


def render_real_ais(data):
    tables = data['tables']
    st.subheader('3. AIS có nhãn và khả năng chuyển nguồn', anchor='stage2-ais')
    st.markdown('#### Đan Mạch · 1.399 cửa sổ từ 84 tàu')
    st.write('Cửa sổ dài hai giờ. Các cấu hình học AIS thật dùng năm lượt tách theo tàu. '
             'Cấu hình chỉ học mô phỏng được giữ nguyên để đo khả năng chuyển sang AIS thật.')
    show_table(tables['denmark'])
    low, high = data['ais_ci']
    st.caption(f"Khoảng 95% bootstrap theo tàu cho chênh macro-F1 giữa toàn quỹ đạo và chuỗi tốc độ là "
               f"[{local_decimal(low,3)} đến {local_decimal(high,3)}]. Hai nhãn là khai thác và di chuyển.")
    st.markdown('[Dữ liệu AIS Đan Mạch · CC BY 4.0](https://doi.org/10.5281/zenodo.7283281)')
    with st.expander('Độ bền khi mất bản tin và độ dài cửa sổ'):
        st.write('Tổng 25 lượt giữ riêng tàu. Mỗi ô báo số bỏ sót / số cờ nhầm trung bình. '
                 'So sánh đồng thời cả hai để tránh đánh giá dựa riêng vào recall.')
        show_table(tables['robustness'])
        show_table([['Độ dài','Số cửa sổ','Recall','Macro-F1'],*[
            [f"{row['duration_minutes']} phút",row['windows'],row['recall'],row['macro_f1']]
            for row in data['duration']
        ]])
        source_link('Tải số liệu theo từng lần tách tàu', 'ais-robustness.json')

    gfw = data['gfw_9']
    st.markdown('#### Global Fishing Watch · kiểm tra khác nguồn')
    st.write(f"{format_number(gfw['windows'])} cửa sổ hai giờ từ {gfw['vessels']} tàu, "
             f"gồm {gfw['positive']} cửa sổ khai thác, mỗi cửa sổ có ít nhất 9 mốc.")
    show_table(tables['gfw'])
    st.caption('Các hàng học ở Đan Mạch kiểm tra chuyển nguồn. Hai hàng cuối dùng một phần dữ liệu GFW '
               'để học và giữ riêng nhóm nghề hoặc giữ riêng tàu khi chấm.')
    source_link('Tải đối chứng theo nguồn, nhóm nghề và số bản tin tối thiểu', 'gfw-transfer.json')


def render_review(data):
    review, tables = data['review'], data['tables']
    st.subheader('4. So sánh hai cách rà ca AIS', anchor='stage2-review')
    st.write(f"**{review['sessions']} phiên trình duyệt**, {format_number(review['browser_decisions'])} lượt chọn, "
             f"{review['rules']} quy tắc trên {review['cases']} ca mô phỏng. Hai bên dùng cùng đồ thị và lựa chọn. "
             f"Gợi ý giúp sửa {review['rescued']} bỏ sót và tạo {review['new_misses']} bỏ sót mới.")
    st.caption(f"{review['human_responses']} phiếu người rà trong dữ liệu đã công bố. "
               "Các số đo dưới đây phản ánh quy tắc và thao tác trình duyệt tự động.")
    with st.expander('Bỏ sót, cờ nhầm và chưa đủ dữ liệu theo 8 quy tắc', expanded=True):
        show_table(tables['rules'])
    with st.expander('Thời gian ghép cặp và kết quả theo nhóm ca'):
        show_table(tables['timing'])
        st.caption('Ghép cùng ca, quy tắc và vị trí lượt để đo chênh lệch. '
                   'Kết quả gồm một lần bấm của trình duyệt; chưa đo công đọc đồ thị và ra quyết định.')
        show_table(tables['review_groups'])

    st.markdown('#### Kiểm tra từng ca và lời giải thích của AI')
    with st.expander('Tra cứu 200 ca và 16 ca thử thách', expanded=True):
        cases = review['case_details']
        group = st.radio('Bộ ca', ('200 ca cân bằng','16 ca thử thách'), horizontal=True, key='stage2_case_group')
        allowed = [key for key in cases if key.startswith('C' if group=='200 ca cân bằng' else 'Q')]
        errors = st.toggle('Chỉ xem ca AI gợi ý sai hướng ưu tiên', key='stage2_wrong_hint')
        if errors:
            allowed = [key for key in allowed if cases[key]['hint_priority'] != cases[key]['priority']]
        if allowed:
            selected = st.selectbox('Chọn ca AIS', allowed, key='stage2_case_id',
                                    format_func=lambda key: f"{key} · {cases[key]['scenario_label']}")
            case = cases[selected]
            st.write(f"**{case['messages']} bản tin** trong {case['duration_minutes']:g} phút · "
                     f"Nhãn mô phỏng **{case['reference']}** · AI dự đoán **{case['hint_class']}**.")
            st.write('Gợi ý ưu tiên: **'+('Ưu tiên rà' if case['hint_priority'] else 'Chưa ưu tiên')+
                     '**. '+('Khớp' if case['hint_priority']==case['priority'] else 'Mâu thuẫn')+
                     ' với nhãn ưu tiên mô phỏng.')
            show_table([
                ['Kết quả qua các quy tắc','Không AI','Có AI'],
                ['Chọn ưu tiên',*(case['counts'][mode].get('priority',0) for mode in ('control','ai'))],
                ['Chưa đủ dữ liệu',*(case['counts'][mode].get('insufficient',0) for mode in ('control','ai'))],
                ['Bỏ sót hoặc cờ nhầm',*(case['errors'][mode] for mode in ('control','ai'))],
            ])
            st.link_button(f'Mở quỹ đạo và lý do AI của {selected}', SITE+f'chang2/compare.html?ca={selected}#compare-panels')
        else:
            st.info('Không có ca sai trong nhóm này.')
        source_link('Tải kết quả đầy đủ theo ca và quy tắc', 'proxy-study.json')
    with st.container(horizontal=True, gap='small'):
        for identifier in review['examples'][1:]:
            st.link_button(f'Xem ca bỏ sót {identifier}', SITE+f'chang2/compare.html?ca={identifier}#compare-panels')
        st.link_button('Thử quy trình với 16 ca', SITE+'chang2/study.html')


def render_sar(data):
    st.subheader('5. Kiểm chứng đầu vào SAR', anchor='stage2-sar')
    st.write('Ở ô OpenSAR Insight 4048, hộp LS-SSDD chồng vào nhãn với IoU **0,309**. '
             'Chuẩn chấm chính là **0,50** và mỗi nhãn chỉ được ghép một lần. '
             'Điều này giải thích vì sao nhìn thấy hai khung chồng nhau vẫn có thể ghi “không khớp”.')
    with st.expander('Từng hộp trong ô 4048 và kết quả theo tập ảnh'):
        show_table(data['tables']['sar_tile'])
        show_table(data['tables']['sar_scenes'])
        source_link('Tải tọa độ và IoU từng hộp', 'sar-tile-4048.json')
