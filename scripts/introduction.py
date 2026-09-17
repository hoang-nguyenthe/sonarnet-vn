"""Compact product introduction with progressive motion."""
import streamlit as st


def render_introduction():
    st.markdown('''<style>
.sn-intro{overflow:hidden;border-radius:30px;background:#050f1d;color:#fff;position:relative;padding:clamp(50px,9vw,130px) 7%;isolation:isolate;min-height:540px;display:flex;align-items:center}
.sn-intro:before{content:"";position:absolute;inset:-30%;z-index:-1;background:radial-gradient(ellipse at 65% 45%,#07559599,transparent 45%),radial-gradient(ellipse at 25% 65%,#12657766,transparent 40%);animation:sn-aurora 12s ease-in-out infinite alternate}
.sn-intro h2{color:#fff!important;font-size:clamp(42px,7.8vw,108px)!important;line-height:1.04;letter-spacing:-.06em!important;max-width:1000px;margin:24px 0!important;font-weight:650;animation:sn-rise .85s ease both}
.sn-intro h2 span{color:#79caff}.sn-intro p{color:#b6c9dc;font-size:clamp(16px,2vw,22px);animation:sn-rise 1.1s ease both}
.sn-eyebrow{letter-spacing:.22em;font:600 11px system-ui;color:#86bce8}
.sn-orbit{position:absolute;width:440px;height:440px;border:1px solid #80caff22;border-radius:50%;right:-130px;bottom:-150px;pointer-events:none}
.sn-orbit:before,.sn-orbit:after{content:"";position:absolute;inset:45px;border:1px solid #80caff22;border-radius:50%}.sn-orbit:after{inset:100px}
.sn-sweep{position:absolute;inset:0;border-radius:50%;background:conic-gradient(from 0deg,transparent 75%,#55baff25,transparent);animation:sn-turn 16s linear infinite}
.sn-story{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin:24px 0}.sn-panel{padding:clamp(28px,4vw,64px);border-radius:28px;background:#fff;border:1px solid #e5eaf0;overflow:hidden;transition:box-shadow .3s ease}
.sn-panel h3{font-size:clamp(28px,3.6vw,48px)!important;line-height:1.13;letter-spacing:-.045em!important;margin:18px 0}.sn-panel p{font-size:17px;line-height:1.5;color:#68798a;max-width:440px}.sn-panel small{font:600 11px system-ui;letter-spacing:.15em;color:#1676c8}.sn-panel:hover{box-shadow:0 20px 50px #123b5914}
.sn-status{display:flex;gap:10px;flex-wrap:wrap;margin-top:32px}.sn-status span{padding:9px 13px;border-radius:100px;font:500 12px system-ui;background:#f0f5fa;color:#33475c}.sn-status i{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:7px}
.sn-strip{padding:32px 6%;border-radius:24px;background:#e9f1f8;display:flex;gap:20px;justify-content:space-between;flex-wrap:wrap;margin:24px 0}.sn-strip span{font:600 14px system-ui;color:#355675}
@keyframes sn-aurora{to{transform:translate3d(5%,-3%,0) scale(1.12)}}
@keyframes sn-turn{to{transform:rotate(360deg)}}
@keyframes sn-rise{from{opacity:0;transform:translateY(35px)}to{opacity:1;transform:translateY(0)}}
@keyframes sn-reveal{from{opacity:.25;translate:0 55px;scale:.97}to{opacity:1;translate:0 0;scale:1}}
@supports(animation-timeline:view()){.sn-panel,.sn-strip{animation:sn-reveal linear both;animation-timeline:view();animation-range:entry 0% entry 100%}}
@media(max-width:720px){.sn-intro{min-height:420px;border-radius:22px}.sn-story{grid-template-columns:1fr;gap:16px}.sn-panel{border-radius:22px}.sn-orbit{opacity:.6;width:300px;height:300px}}
@media(prefers-reduced-motion:reduce){.sn-intro:before,.sn-intro h2,.sn-intro p,.sn-sweep,.sn-panel,.sn-strip{animation:none!important;transition:none!important;opacity:1!important;transform:none!important;translate:none!important;scale:1!important}}
</style>
<section class="sn-intro"><div><div class="sn-eyebrow">SONARNET / VIỆT NAM</div><h2>Rõ vùng biển.<br><span>Hiện dấu tàu.</span></h2><p>Quan sát bằng radar.<br>Đối chiếu từng dấu vết.</p></div><div class="sn-orbit" aria-hidden="true"><div class="sn-sweep"></div></div></section>
<div class="sn-story"><section class="sn-panel"><small>01 / QUAN SÁT</small><h3>Từ toàn cảnh.<br>Đến chi tiết.</h3><p>Ảnh Sentinel-1, thời gian chụp và bằng chứng tại từng vị trí.</p></section><section class="sn-panel"><small>02 / ĐỐI CHIẾU</small><h3>Ba trạng thái.<br>Một góc nhìn.</h3><p>Hồ sơ phương tiện và vị trí quan sát, trong cùng một không gian.</p><div class="sn-status"><span><i style="background:#0a84ff"></i>AIS khớp</span><span><i style="background:#ffd60a"></i>AIS lệch</span><span><i style="background:#ff453a"></i>Chưa có AIS</span></div></section></div>
<div class="sn-strip"><span>Sentinel-1 · Ảnh radar</span><span>YOLO · Nhận diện</span><span>SAR × AIS · Đối chiếu</span><span>MPS · Xử lý cục bộ</span></div>
''', unsafe_allow_html=True)
    st.caption('Ảnh radar thật · Hồ sơ tàu & AIS: dữ liệu mẫu')
    st.markdown('''<div class="sn-story">
<section class="sn-panel"><small>BÀI TOÁN</small><h3>Ảnh có mục tiêu.<br>Tín hiệu có khớp?</h3><p>Một dấu sáng trên radar chưa cho biết đó là tàu nào. Một bản tin vị trí cũng chưa đủ để xác nhận mục tiêu trên ảnh.</p><p>SonarNet hướng tới đặt hai nguồn cạnh nhau — giúp người kiểm tra biết vị trí nào cần được xem xét trước.</p></section>
<section class="sn-panel"><small>GIÁ TRỊ SỬ DỤNG</small><h3>Bớt tìm kiếm.<br>Thêm bằng chứng.</h3><p>Thay vì rà từng ảnh rời, người xem có một bản đồ quan sát, danh sách điểm cần kiểm tra và hồ sơ ảnh tại từng vị trí.</p><p>Dành cho nhóm nghiên cứu và người phân tích giám sát biển; hỗ trợ rà soát, không tự đưa ra kết luận vi phạm.</p></section>
</div>
<section class="sn-panel"><small>LUỒNG XỬ LÝ</small><h3>Từ ảnh vệ tinh đến hồ sơ quan sát.</h3><div class="sn-story">
<div><h4>01 — Thu nhận ảnh</h4><p>Lấy ảnh Sentinel-1 theo khu vực và ngày quan sát. Lưu nguồn gốc cùng ảnh; mỗi vùng có thể được chụp ở thời điểm khác nhau.</p></div>
<div><h4>02 — Tìm mục tiêu</h4><p>Chia ảnh chi tiết thành các ô để nhận diện. Loại đất liền và dải sát bờ 500 m; giữ tọa độ cho từng vùng nghi là tàu.</p></div>
<div><h4>03 — Đối chiếu vị trí</h4><p>Khi có AIS: đưa vị trí tàu về cùng thời điểm quan sát để kiểm tra mức phù hợp. Hiện giao diện sử dụng dữ liệu mẫu cho bước này.</p></div>
<div><h4>04 — Lưu hồ sơ</h4><p>Giữ ảnh gốc, ngày chụp, vị trí, kết quả nhận diện và đánh giá của người kiểm tra trong hồ sơ tải xuống.</p></div>
</div></section>
<div class="sn-story">
<section class="sn-panel"><small>NHẬN DIỆN / YOLO</small><h3>Tìm dấu vết.<br>Không đoán danh tính.</h3><p>YOLO tìm vùng có đặc trưng giống tàu trên ảnh radar. Tên tàu, chủ phương tiện và số đăng ký phải đến từ nguồn hồ sơ riêng, không được suy ra chỉ từ ảnh.</p><p>Việc huấn luyện trên dữ liệu radar thật và kiểm chứng tại Việt Nam là hai bước khác nhau.</p></section>
<section class="sn-panel"><small>ĐỒNG BỘ / KALMAN–RTS</small><h3>Khác thời điểm.<br>Cần cùng vị trí.</h3><p>Bộ làm trơn dùng chuỗi bản tin AIS để ước lượng vị trí tại thời điểm radar quan sát, thay vì ghép với bản tin gần nhất một cách máy móc.</p><p>Mô-đun đã có trong mã nghiên cứu; chưa được nối vào luồng web vì chưa có AIS thật phù hợp.</p></section>
</div>
<section class="sn-panel"><small>BƯỚC TIẾP THEO / KẾT NỐI DỮ LIỆU</small><h3>Từ trải nghiệm mẫu<br>đến đối chiếu thực tế.</h3><p>Cần bản tin AIS có mã phương tiện, tọa độ, thời gian, tốc độ và hướng đi; hồ sơ đăng ký từ nguồn được phép sử dụng. Sau tích hợp, phải kiểm chứng sai số ghép vị trí và đánh giá các trường hợp lệch hoặc thiếu tín hiệu trước khi triển khai nghiệp vụ.</p><div class="sn-status"><span>Ảnh Sentinel-1: có thật</span><span>Nhận diện: đang kiểm chứng</span><span>Hồ sơ & AIS: dữ liệu mẫu</span></div></section>
''', unsafe_allow_html=True)
    with st.expander('Công nghệ & trạng thái triển khai'):
        st.markdown('''**Sentinel-1:** ảnh ghép nhiều lượt chụp, không phải luồng trực tiếp.

**YOLO:** nhận diện ứng viên trên ảnh chi tiết; bỏ qua đất liền và 500 m sát bờ. Cần kiểm chứng trước khi dùng cho quyết định nghiệp vụ.

**Kalman/RTS:** có trong mã nghiên cứu, chưa chạy trong luồng web; cần chuỗi AIS và thời điểm quan sát phù hợp.

**Global Fishing Watch:** thống kê tham khảo theo vùng, không phải danh tính từng tàu.

**Tự động hoá:** xử lý nền và giữ kết quả theo từng ô. Độ phủ thực tế được ghi trong tab Quan sát.''')
