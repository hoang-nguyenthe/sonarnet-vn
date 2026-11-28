#!/usr/bin/env python
"""Public observation workspace; historical research code remains in git."""
from importlib import import_module
from pathlib import Path
import sys
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'src'))

st.set_page_config(page_title='SonarNet · Quan sát biển', page_icon='◉', layout='wide', initial_sidebar_state='collapsed')
st.markdown('''<style>
html,body,.stApp{font-family:-apple-system,BlinkMacSystemFont,"Helvetica Neue",sans-serif;-webkit-font-smoothing:antialiased}
.stApp{background:#f5f6f8;color:#172b3d}
[data-testid="stMainBlockContainer"]{max-width:none;padding:4rem clamp(12px,2vw,32px) 2rem}
/* Both the Streamlit wrapper and iframe have an explicit component size. */
.st-key-national_map{--national-map-height:clamp(520px,78vh,960px)}
.st-key-national_map [data-testid="stElementContainer"]{
  flex:0 0 var(--national-map-height)!important;
  height:var(--national-map-height)!important;
  min-height:0!important;
  max-height:var(--national-map-height)!important;
}
.st-key-national_map iframe[data-testid="stIFrame"]{height:var(--national-map-height)!important}
@media(max-width:720px), (max-height:650px){
  .st-key-national_map{--national-map-height:clamp(320px,68svh,760px)}
}
.sonar-hero{position:relative;overflow:hidden;border-radius:24px;padding:30px 34px;margin:0 0 8px;color:#fff;background:linear-gradient(125deg,#07192d,#103c5b 62%,#146466);box-shadow:0 16px 50px #132f4220}
.sonar-hero:after{content:"";position:absolute;width:450px;height:450px;border-radius:50%;background:radial-gradient(circle,#50c4d025,transparent 65%);right:-100px;top:-180px;animation:drift 14s ease-in-out infinite alternate;pointer-events:none}
.sonar-eyebrow{color:#9fd5d9;font-size:11px;letter-spacing:.17em;font-weight:650;margin-bottom:12px}
.sonar-title{font-size:clamp(28px,3.6vw,46px);font-weight:650;letter-spacing:-.045em;line-height:1.12}
.sonar-copy{margin-top:12px;color:#d0e0e9;font-size:15px;max-width:650px;line-height:1.5}
.observation-meta{display:flex;flex-wrap:wrap;gap:18px 32px;background:#fff;border:1px solid #e1e7ed;border-radius:16px;padding:15px 19px;margin:10px 0 18px}
.observation-meta span{color:#637488;font-size:12px}.observation-meta strong{display:block;color:#18334c;font-size:15px;font-weight:600;margin-top:5px}
h1,h2,h3{letter-spacing:-.025em!important}
[data-testid="stExpander"]{background:white;border:1px solid #e1e7ed;border-radius:15px}
[data-testid="stButton"] button,[data-testid="stDownloadButton"] button{border-radius:12px;min-height:44px;transition:box-shadow .2s,background .2s}
[data-testid="stButton"] button:hover{box-shadow:0 5px 18px #18334c15}
[data-testid="stMetric"]{background:white;border:1px solid #e1e7ed;border-radius:16px;padding:16px}
.stApp iframe{border-radius:18px;overflow:hidden}.stApp img{border-radius:12px}
[role="tablist"]{background:#e9edf2;border-radius:14px;padding:4px;gap:5px}
[role="tab"]{border-radius:11px;min-height:44px;padding:10px 24px!important}
[role="tab"][aria-selected="true"]{background:white;box-shadow:0 2px 8px #17304910}
[role="tab"]{transition:background .2s ease,box-shadow .2s ease,color .2s ease}
@keyframes section-arrive{from{opacity:.55;translate:0 12px}to{opacity:1;translate:0 0}}
@supports(animation-timeline:view()){
  [data-testid="stExpander"],.observation-meta{animation:section-arrive linear both;animation-timeline:view();animation-range:entry 0% entry 70%}
}
[data-baseweb="tab-highlight"],[data-baseweb="tab-border"]{display:none}
[data-testid="stSidebar"]{background:#fff}
:focus-visible{outline:3px solid #168cff!important;outline-offset:3px}
@keyframes drift{from{transform:translateX(-15px)}to{transform:translateX(45px)}}
@media(max-width:720px){[data-testid="stMainBlockContainer"]{padding:3.7rem .9rem 1.5rem}.sonar-hero{padding:20px 21px;border-radius:20px}.sonar-copy{display:none}.sonar-title{font-size:26px}.observation-meta{padding:12px 14px;gap:12px 22px}.observation-meta strong{font-size:13px}[role="tab"]{padding:10px 16px!important}}
@media(max-width:640px){
  .st-key-main_section [role="radiogroup"]{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}
  .st-key-main_section [role="radiogroup"] label{width:100%;padding:0 8px;min-height:44px;margin:0}
  .st-key-fresh_rtc_review_mode [role="radiogroup"] label{min-height:44px;margin:0}
}
@media(prefers-reduced-motion:reduce){*,*:before,*:after{animation:none!important;transition:none!important}}
</style>
<div style="font:650 20px -apple-system,sans-serif;letter-spacing:-.04em">SonarNet<span style="font-size:11px;letter-spacing:.12em;color:#66798c;margin-left:16px">VIỆT NAM</span></div>''', unsafe_allow_html=True)

st.components.v1.html('''<div id="time" style="font:12px -apple-system,sans-serif;color:#64748b;text-align:right;padding:5px 4px"></div>
<script>function tick(){document.getElementById('time').textContent='Giờ Việt Nam · '+new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',dateStyle:'short',timeStyle:'medium'}).format(new Date())}tick();setInterval(tick,1000);</script>''', height=32)

with st.sidebar:
    st.title('SonarNet')
    st.write('Xem ảnh → kiểm tra điểm nghi vấn → lưu bằng chứng.')
    st.caption('Ngày chụp ảnh khác với giờ hiện tại. Ảnh nền toàn cảnh không đồng nghĩa đã kiểm tra toàn bộ; xem tiến độ xử lý của khu vực.')
    st.info('Chưa có dữ liệu định danh tàu. Kết quả cần người có chuyên môn xác minh.')

SECTIONS = {'gioi-thieu': 'Nghiên cứu', 'quan-sat': 'Quan sát',
            'minh-chung': 'Minh chứng cải tiến', 'quan-ly': 'Quản lý quyết định', 'huong-dan': 'Hướng dẫn'}


def update_section_url():
    slug = next(slug for slug, label in SECTIONS.items() if label == st.session_state.main_section)
    st.query_params['trang'] = slug
    if slug != 'quan-sat' and 'che-do' in st.query_params:
        del st.query_params['che-do']
    if slug != 'minh-chung':
        for param in ('muc', 'chang'):
            if param in st.query_params:
                del st.query_params[param]


def open_evidence():
    st.session_state.main_section = SECTIONS['minh-chung']
    update_section_url()


def open_manager(region, point_id):
    st.session_state.main_section = SECTIONS['quan-ly']
    st.session_state.manager_region = region
    st.session_state.manager_point = point_id
    st.session_state.manager_filter = 'Tất cả'
    update_section_url()


def open_decided_observation(label, point_id):
    st.session_state.main_section = SECTIONS['quan-sat']
    st.session_state.observation_region = label
    st.session_state.observation_workflow = 'Xem toàn cảnh'
    st.session_state.panorama_yolo_enabled = True
    st.session_state.panorama_illustrative = False
    st.session_state.panorama_decided_only = False
    st.session_state.panorama_candidate = point_id
    st.session_state.observation_focus = point_id
    update_section_url()
    st.query_params['che-do'] = 'xem-toan-canh'


def load_view(module_name):
    try:
        return import_module(module_name)
    except KeyError as error:
        if error.args != (module_name,):
            raise
        # A hot reload may remove this page from sys.modules during import.
        return import_module(module_name)


if 'main_section' not in st.session_state:
    st.session_state.main_section = SECTIONS.get(st.query_params.get('trang'), SECTIONS['gioi-thieu'])
section = st.radio('Điều hướng', list(SECTIONS.values()), horizontal=True, index=None,
                   label_visibility='collapsed', key='main_section', on_change=update_section_url)
# Build only the selected workspace, including the active evidence tab.
if section == 'Nghiên cứu':
    load_view('introduction').render_introduction(ROOT, open_evidence=open_evidence)
elif section == 'Quan sát':
    load_view('observation_view').render(ROOT, open_manager=open_manager)
elif section == 'Minh chứng cải tiến':
    default_stage = 'Chặng 2' if st.query_params.get('chang') == '2' else 'Chặng 1'
    stage_one, stage_two = st.tabs(
        ('Chặng 1', 'Chặng 2'), default=default_stage, key='evidence_stage', on_change='rerun',
    )
    if stage_one.open:
        with stage_one:
            if st.query_params.get('muc') == 'recall':
                st.subheader('Đối chứng recall trên ảnh Sentinel-1')
                st.markdown('[Mở toàn bộ minh chứng và báo cáo](?trang=minh-chung) · '
                            '[Xem bảng gộp thứ hạng và dữ liệu chấm lại]'
                            '(https://hoang-nguyenthe.github.io/sonarnet-vn/#thu-hang)')
                load_view('vn_recall_view').render_transfer_rtc(ROOT, expanded=True)
            else:
                load_view('improvement_view').render_improvements(ROOT)
    if stage_two.open:
        with stage_two:
            load_view('chang2_view').render(ROOT)
elif section == 'Quản lý quyết định':
    load_view('decision_manager_view').render(ROOT, open_decided_observation)
else:
    st.subheader('Từ xem ảnh đến kiểm tra bằng chứng.')
    st.markdown('''1. **Chọn khu vực:** xem ảnh vệ tinh và thời gian quan sát. Ảnh màu bên dưới chỉ là nền tham chiếu.
2. **Xem tiến độ kiểm tra:** xem số ô đã xử lý và còn chờ của khu vực; phóng to để ảnh chi tiết tự tải. Không có điểm đánh dấu không có nghĩa là không có tàu.
3. **Mở điểm nghi vấn:** xem ảnh gốc, tọa độ và ngày quan sát. Một điểm sáng chưa chắc là tàu.
4. **Lưu bằng chứng:** chuyển sang “Kiểm tra chi tiết”, ghi nhận đánh giá và tải hồ sơ.''')
    st.subheader('Giới hạn cần biết')
    st.write('Chưa thể xác nhận tàu cá, tên tàu, chủ sở hữu hoặc hành vi vi phạm. Chưa có dữ liệu phát vị trí từ tàu cùng thời điểm để đối chiếu.')
    st.write('Hệ thống bỏ qua đất liền và dải 500 m từ bờ ra biển. Tàu trong cảng hoặc sát bờ cũng bị bỏ qua. Không thấy điểm nghi vấn không có nghĩa là không có tàu.')
    st.write('Nhận diện tự động hiện chưa đạt chất lượng cho quyết định nghiệp vụ. Ảnh và hồ sơ hỗ trợ rà soát, không thay thế xác minh của chuyên gia.')
