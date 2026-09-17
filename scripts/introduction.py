"""Public-facing purpose and honest technology overview."""
import streamlit as st
from pathlib import Path


def render_introduction():
    st.markdown('''<style>
.intro-lead{padding:clamp(44px,7vw,110px) 20px 48px;max-width:1100px;margin:auto;text-align:center}
.intro-kicker{color:#0876db;font:600 12px system-ui;letter-spacing:.16em;text-transform:uppercase}
.intro-lead h2{font-size:clamp(38px,6.5vw,88px)!important;line-height:1.04;letter-spacing:-.055em!important;margin:20px 0 28px;font-weight:650}
.intro-lead p{font-size:clamp(17px,1.8vw,22px);line-height:1.55;color:#627081;max-width:760px;margin:0 auto}
.intro-lead h2 span{background:linear-gradient(100deg,#064fa7,#087edc,#189aaa);background-clip:text;-webkit-background-clip:text;color:transparent}
.intro-scroll{display:block;margin-top:34px;color:#647580;font-size:12px;letter-spacing:.06em}
.intro-chapter{padding:clamp(24px,4vw,56px) 12px 18px;max-width:1000px;margin:auto;text-align:center}
.intro-chapter h2{font-size:clamp(28px,4vw,52px)!important;line-height:1.12;letter-spacing:-.045em!important}
.intro-chapter p{color:#637488;font-size:18px;line-height:1.5}
.intro-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px;margin:16px 0 36px}
.intro-card{background:linear-gradient(145deg,#fff,#edf5ff);border:1px solid #dae6f2;border-radius:24px;padding:28px;transition:transform .25s ease,box-shadow .25s ease}
.intro-card:hover{transform:translateY(-3px);box-shadow:0 14px 34px #12385612}
.intro-card small{color:#0876db;font-weight:650}.intro-card h3{font-size:22px!important;margin:12px 0}.intro-card p{color:#53687b;line-height:1.6}
@keyframes intro-arrive{from{opacity:.35;translate:0 18px}to{opacity:1;translate:0 0}}
.intro-lead{animation:intro-arrive .65s cubic-bezier(.2,.65,.3,1) both}
@supports(animation-timeline:view()){
  .intro-card,.intro-chapter{animation:intro-arrive linear both;animation-timeline:view();animation-range:entry 0% entry 85%}
}
@media(max-width:720px){.intro-grid{grid-template-columns:1fr}.intro-card{padding:22px}.intro-lead p{font-size:16px}}
@media(prefers-reduced-motion:reduce){.intro-card,.intro-lead{animation:none!important;translate:none!important;opacity:1!important;transition:none}.intro-card:hover{transform:none}}
</style>
<section class="intro-lead"><div class="intro-kicker">SonarNet · Từ dữ liệu đến bằng chứng</div>
<h2>Biển rộng lớn.<br><span>Nhìn rõ từng dấu vết.</span></h2>
<p>Khám phá ảnh radar vùng biển Việt Nam.<br>Kiểm tra điểm nghi vấn. Lưu lại bằng chứng.<br>Một không gian, từ toàn cảnh đến từng chi tiết.</p><small class="intro-scroll">CUỘN ĐỂ KHÁM PHÁ ↓</small></section>
<div class="intro-grid">
<article class="intro-card"><small>01 · QUAN SÁT</small><h3>Biết đang nhìn gì.</h3><p>Di chuyển trên ảnh vệ tinh, xem khu vực, ngày quan sát và nguồn ảnh. Phóng gần để tải ảnh radar chi tiết.</p></article>
<article class="intro-card"><small>02 · KIỂM TRA</small><h3>Đi thẳng vào điểm cần xem.</h3><p>Mở một vòng khoanh để xem ảnh gốc tại vị trí đó. Trong chế độ trình diễn, khám phá hồ sơ tàu và ba tình huống đối chiếu AIS.</p></article>
<article class="intro-card"><small>03 · LƯU BẰNG CHỨNG</small><h3>Không dừng ở một dấu chấm.</h3><p>Ghi chú, đánh giá từng điểm và tải hồ sơ kèm ảnh, tọa độ, thời gian. Người có chuyên môn có thể tiếp tục xác minh từ bằng chứng này.</p></article>
</div>''', unsafe_allow_html=True)
    st.markdown('''<section class="intro-chapter"><h2>Không chỉ nhìn thấy.<br>Còn biết mình đang nhìn gì.</h2><p>Ảnh thật. Nguồn rõ ràng. Thời gian quan sát đi cùng bằng chứng.</p></section>''', unsafe_allow_html=True)
    panorama = Path(__file__).resolve().parents[1] / 'assets/sentinel1_vietnam_latest.png'
    if panorama.exists():
        with st.expander('Khám phá ảnh radar Việt Nam đang lưu sẵn', expanded=False):
            st.image(str(panorama), width='stretch', caption='Ảnh ghép Sentinel-1 lưu sẵn · xem ngày từng vùng và tiến độ nhận diện trong tab Quan sát. Không phải ảnh trực tiếp.')
    st.subheader('Bắt đầu trong một phút')
    st.write('Mở tab **Quan sát** → phóng gần khu vực cần xem → chọn một tàu hoặc điểm quan sát. Dùng bộ lọc màu để trình bày từng tình huống; vào **Kiểm tra chi tiết** để đánh giá và lưu hồ sơ.')
    st.caption('🔵 AIS khớp · 🟡 AIS lệch · 🔴 Chưa có AIS — các trạng thái AIS và hồ sơ tàu hiện là dữ liệu trình diễn, không phải kết quả đối chiếu với AIS thật.')
    st.subheader('Công nghệ phía sau trải nghiệm')
    with st.expander('Ảnh radar Sentinel-1 · nguồn quan sát thật', expanded=True):
        st.write('Ảnh radar từ Copernicus được chia thành các ô chi tiết để xử lý. Ảnh toàn cảnh là ảnh ghép nhiều lượt chụp, có thể khác ngày giữa các vùng; giờ hiện tại không phải giờ chụp. Chỉ những ô xử lý thành công mới có kết quả nhận diện.')
    with st.expander('Nhận diện tự động · tìm ứng viên tàu'):
        st.write('Mô hình YOLO đánh dấu những vùng ảnh có đặc trưng giống tàu. Pipeline loại đất liền và dải 500 m sát bờ trước nhận diện. Kết quả là ứng viên cần kiểm tra, không tự xác nhận loại tàu hoặc hành vi vi phạm. Mô hình đang được đánh giá trên dữ liệu radar thật; chưa đủ kiểm chứng để dùng độc lập cho quyết định nghiệp vụ.')
    with st.expander('Kalman / RTS và SAR–AIS · bước đối chiếu khi có dữ liệu'):
        st.write('Mã nghiên cứu có bộ làm trơn Kalman/RTS để ước lượng vị trí từ chuỗi AIS về thời điểm quan sát radar, phục vụ ghép vị trí. Phần này chưa được nối vào luồng web đang hiển thị: cần AIS có dấu thời gian và thời điểm quan sát đủ chính xác. Ba màu trong chế độ trình diễn hiện do kịch bản tạo, không phải đầu ra Kalman.')
    with st.expander('Global Fishing Watch · nguồn tham khảo độc lập'):
        st.write('Lớp tham khảo cung cấp thống kê phát hiện theo vùng và thời gian. Nó không thay thế AIS trực tiếp, không tự cung cấp danh tính từng mục tiêu và không chứng minh một điểm nhận diện là tàu.')
    with st.expander('Tự động hoá · xử lý nền, xem kết quả lưu sẵn'):
        st.write('Tác vụ nền kiểm tra nguồn ảnh và lưu kết quả theo từng ô; có checkpoint để tiếp tục phần còn thiếu. GPU MPS trên MacBook hỗ trợ các lượt xử lý cục bộ. Web đọc kết quả đã công bố, không yêu cầu người xem tự tải ảnh hay chạy mô hình. Tiến độ thực tế nằm tại mục nguồn, thời gian và độ phủ.')
    st.info('Mục đích hiện tại: trình bày quy trình giám sát và hỗ trợ rà soát ảnh. Ảnh radar là dữ liệu thật; hồ sơ tàu trình diễn không phải danh tính được suy ra từ ảnh. Phạm vi đã xử lý chưa đồng nghĩa phủ kín Việt Nam.')
