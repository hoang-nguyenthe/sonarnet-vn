#!/usr/bin/env python
"""Public observation workspace; historical research code remains in git."""
from pathlib import Path
import sys
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'src'))
from observation_view import render

st.set_page_config(page_title='SonarNet · Quan sát biển', page_icon='◉', layout='wide', initial_sidebar_state='collapsed')
st.markdown('''<style>
html,body,.stApp{font-family:-apple-system,BlinkMacSystemFont,"Helvetica Neue",sans-serif;-webkit-font-smoothing:antialiased}
.stApp{background:#f5f6f8;color:#172b3d}
[data-testid="stMainBlockContainer"]{max-width:none;padding:4rem clamp(12px,2vw,32px) 2rem}
iframe[height="820"]{height:82vh!important;min-height:580px;max-height:1100px}
@media(max-width:720px){iframe[height="820"]{height:72svh!important;min-height:420px;max-height:760px}}
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

section = st.radio('Điều hướng', ['Giới thiệu', 'Quan sát', 'Hướng dẫn'], horizontal=True,
                   label_visibility='collapsed', key='main_section')
# st.tabs evaluates every tab on every rerun.  Do not construct the national
# raster workspace while a visitor is reading the lightweight introduction.
if section == 'Giới thiệu':
    from introduction import render_introduction
    render_introduction()
elif section == 'Quan sát':
    render(ROOT)
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
