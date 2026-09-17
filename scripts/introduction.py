"""Public-facing purpose and honest technology overview."""
import streamlit as st


def render_introduction():
    st.markdown('''<style>
.intro-lead{padding:clamp(24px,5vw,68px) 0 28px;max-width:900px}
.intro-kicker{color:#0876db;font:600 12px system-ui;letter-spacing:.16em;text-transform:uppercase}
.intro-lead h2{font-size:clamp(32px,5vw,64px)!important;line-height:1.06;letter-spacing:-.05em!important;margin:14px 0 20px}
.intro-lead p{font-size:18px;line-height:1.65;color:#526679;max-width:760px}
.intro-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px;margin:16px 0 36px}
.intro-card{background:linear-gradient(145deg,#fff,#edf5ff);border:1px solid #dae6f2;border-radius:24px;padding:28px;transition:transform .25s ease,box-shadow .25s ease}
.intro-card:hover{transform:translateY(-3px);box-shadow:0 14px 34px #12385612}
.intro-card small{color:#0876db;font-weight:650}.intro-card h3{font-size:22px!important;margin:12px 0}.intro-card p{color:#53687b;line-height:1.6}
@keyframes intro-arrive{from{opacity:.35;translate:0 18px}to{opacity:1;translate:0 0}}
.intro-lead{animation:intro-arrive .65s cubic-bezier(.2,.65,.3,1) both}
@supports(animation-timeline:view()){
  .intro-card{animation:intro-arrive linear both;animation-timeline:view();animation-range:entry 0% entry 85%}
}
@media(max-width:720px){.intro-grid{grid-template-columns:1fr}.intro-card{padding:22px}.intro-lead p{font-size:16px}}
@media(prefers-reduced-motion:reduce){.intro-card,.intro-lead{animation:none!important;translate:none!important;opacity:1!important;transition:none}.intro-card:hover{transform:none}}
</style>
<section class="intro-lead"><div class="intro-kicker">SonarNet · Từ dữ liệu đến bằng chứng</div>
<h2>Biển rộng lớn.<br>Mỗi quan sát cần rõ ràng.</h2>
<p>SonarNet giúp người xem khám phá ảnh radar vùng biển Việt Nam, rà soát những vị trí nghi là tàu và lưu lại bằng chứng để đối chiếu. Một không gian quan sát — từ toàn cảnh đến từng dấu vết.</p></section>
<div class="intro-grid">
<article class="intro-card"><small>01 · QUAN SÁT</small><h3>Biết đang nhìn gì.</h3><p>Di chuyển trên ảnh vệ tinh, xem khu vực, ngày quan sát và nguồn ảnh. Phóng gần để tải ảnh radar chi tiết.</p></article>
<article class="intro-card"><small>02 · KIỂM TRA</small><h3>Đi thẳng vào điểm cần xem.</h3><p>Mở một vòng khoanh để xem ảnh gốc tại vị trí đó. Trong chế độ trình diễn, khám phá hồ sơ tàu và ba tình huống đối chiếu AIS.</p></article>
<article class="intro-card"><small>03 · LƯU BẰNG CHỨNG</small><h3>Không dừng ở một dấu chấm.</h3><p>Ghi chú, đánh giá từng điểm và tải hồ sơ kèm ảnh, tọa độ, thời gian. Người có chuyên môn có thể tiếp tục xác minh từ bằng chứng này.</p></article>
</div>''', unsafe_allow_html=True)
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
