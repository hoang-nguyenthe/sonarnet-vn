"""Research-led product introduction, designed for a public audience."""
from __future__ import annotations

import json
from pathlib import Path

import streamlit as st


def _research_snapshot(root: Path | None) -> tuple[str, str, str]:
    """Read lightweight published facts without starting the raster pipeline."""
    fallback = ("Ảnh radar thật", "Theo từng ô quan sát", "Có thể kiểm tra nguồn")
    if root is None:
        return fallback
    try:
        report = json.loads((root / "assets" / "real_scan" / "report.json").read_text())
        rows = report.get("tiles", [])
        tiles = int(report.get("processed_tiles", report.get("tiles_processed", 0)))
        candidates = int(report.get("candidate_count", report.get("detections", 0)))
        if isinstance(rows, list):
            processed = [row for row in rows if isinstance(row, dict) and row.get("status") == "processed"]
            tiles = tiles or len(processed)
            candidates = candidates or sum(len(row.get("detections", [])) for row in processed)
        dates = report.get("observation_dates", [])
        if not dates and isinstance(rows, list):
            dates = [row.get("observation_day_utc") for row in rows if isinstance(row, dict) and row.get("observation_day_utc")]
        newest = max(dates) if dates else ""
        return (
            f"{tiles:,} ô ảnh đã đọc" if tiles else fallback[0],
            f"{candidates:,} điểm cần xem" if candidates else fallback[1],
            f"Mốc mới nhất {newest}" if newest else fallback[2],
        )
    except (OSError, ValueError, TypeError):
        return fallback


def render_introduction(root: Path | None = None) -> None:
    first, second, third = _research_snapshot(root)
    hero = '''<style>
.research-hero{position:relative;overflow:hidden;isolation:isolate;min-height:560px;display:flex;align-items:flex-end;padding:clamp(34px,7vw,92px);border-radius:34px;color:#f8fbff;background:linear-gradient(135deg,#051326,#0a3250 52%,#14626a);box-shadow:0 30px 80px #071d3133}
.research-hero:before{content:"";position:absolute;inset:-36%;z-index:-2;background:radial-gradient(ellipse at 22% 32%,#1595d966,transparent 28%),radial-gradient(ellipse at 76% 57%,#57e0cf44,transparent 27%),radial-gradient(ellipse at 44% 92%,#1677cf55,transparent 32%);animation:research-aurora 16s ease-in-out infinite alternate}
.research-hero:after{content:"";position:absolute;width:560px;height:560px;right:-215px;top:-245px;z-index:-1;border-radius:50%;border:1px solid #b5eff22c;box-shadow:0 0 0 56px #b5eff209,0 0 0 128px #b5eff207,0 0 0 218px #b5eff205;animation:research-orbit 18s linear infinite}
.research-kicker{font:650 11px system-ui;letter-spacing:.21em;color:#9cd8e6}.research-hero h1{max-width:850px;margin:18px 0!important;color:#fff!important;font-size:clamp(44px,7vw,96px)!important;line-height:.99;letter-spacing:-.065em!important;font-weight:680}.research-hero h1 em{font-style:normal;color:#7ee5d7}.research-lede{max-width:610px;margin:0;color:#c0d4e3;font-size:clamp(16px,1.8vw,21px);line-height:1.48}.research-hero-copy{animation:research-rise .8s cubic-bezier(.2,.75,.3,1) both}
.research-facts{position:absolute;right:clamp(22px,5vw,64px);bottom:clamp(26px,5vw,58px);display:flex;gap:8px;max-width:460px;justify-content:flex-end;flex-wrap:wrap}.research-fact{padding:10px 13px;border:1px solid #d9f8ff33;border-radius:100px;background:#ffffff13;backdrop-filter:blur(18px) saturate(150%);-webkit-backdrop-filter:blur(18px) saturate(150%);font:500 11px system-ui;color:#e7f8ff;box-shadow:inset 0 1px #fff2}
.research-grid{display:grid;grid-template-columns:repeat(12,1fr);gap:18px;margin:22px 0}.glass-card{position:relative;overflow:hidden;padding:clamp(25px,3.5vw,48px);border:1px solid #ffffffa8;border-radius:28px;background:linear-gradient(135deg,#ffffffd9,#edf5fbab);box-shadow:0 18px 50px #153d5610;backdrop-filter:blur(20px) saturate(145%);-webkit-backdrop-filter:blur(20px) saturate(145%);transition:transform .45s cubic-bezier(.2,.75,.3,1),box-shadow .45s ease,border-color .45s ease}.glass-card:before{content:"";position:absolute;width:210px;height:130px;top:-85px;right:-40px;background:radial-gradient(ellipse,#fff9,transparent 68%);transform:rotate(-15deg);pointer-events:none}.glass-card:hover{transform:translateY(-6px);border-color:#b7ecf1;box-shadow:0 26px 60px #153d5620}.glass-card h2,.glass-card h3{position:relative;margin:13px 0!important;color:#102c43!important;letter-spacing:-.045em!important;line-height:1.08}.glass-card h2{font-size:clamp(31px,4vw,52px)!important}.glass-card h3{font-size:clamp(20px,2.3vw,28px)!important}.glass-card p{position:relative;margin:10px 0;color:#516879;font-size:15px;line-height:1.55}.section-tag{position:relative;font:650 10px system-ui;letter-spacing:.17em;color:#117484}.research-wide{grid-column:span 7}.research-side{grid-column:span 5}.research-third{grid-column:span 4}.research-half{grid-column:span 6}
.signal-row{display:flex;align-items:center;gap:13px;padding:14px 0;border-top:1px solid #7892a82b}.signal-row:first-of-type{margin-top:24px}.signal-dot{flex:0 0 11px;width:11px;height:11px;border-radius:50%;box-shadow:0 0 0 5px #0a84ff18}.signal-row b{font-size:14px;color:#17364d}.signal-row span{margin-left:auto;font-size:12px;color:#638095}
.journey{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:27px}.journey-step{position:relative;padding:17px 14px 14px;border-radius:19px;background:#ffffff73;border:1px solid #fff;font-size:13px;color:#456277}.journey-step:before{display:block;margin-bottom:12px;color:#0a7183;font:650 11px system-ui;letter-spacing:.12em}.journey-step:nth-child(1):before{content:"01 · ẢNH"}.journey-step:nth-child(2):before{content:"02 · LỌC"}.journey-step:nth-child(3):before{content:"03 · GỢI Ý"}.journey-step:nth-child(4):before{content:"04 · XÁC MINH"}.journey-step:not(:last-child):after{content:"";position:absolute;top:48%;right:-10px;width:8px;height:8px;border-top:1px solid #4893a5;border-right:1px solid #4893a5;transform:rotate(45deg);z-index:2}
.research-callout{padding:28px 30px;border-radius:25px;background:linear-gradient(115deg,#08233b,#104b5c);color:#e9fbff;box-shadow:0 20px 50px #09263c26}.research-callout h3{margin:0 0 9px;color:#fff!important;font-size:25px!important;letter-spacing:-.04em!important}.research-callout p{margin:0;color:#b9d9df;line-height:1.55}.research-rule{height:1px;margin:20px 0;background:#b5ebed36}.research-pill{display:inline-block;margin:9px 7px 0 0;padding:8px 11px;border:1px solid #cefcfa33;border-radius:99px;background:#ffffff10;font:500 11px system-ui;color:#e3faff}
.research-truth{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:22px}.truth{padding:19px;border-radius:20px;background:#f7fbfd;box-shadow:inset 0 0 0 1px #e0edf2}.truth b{display:block;color:#15354d;font-size:15px;margin-bottom:8px}.truth p{font-size:13px;margin:0}.research-foot{margin:17px 2px 0;color:#6f8190;font-size:12px}
@keyframes research-aurora{to{transform:translate3d(5%,-3%,0) scale(1.13)}}@keyframes research-orbit{to{transform:rotate(360deg)}}@keyframes research-rise{from{opacity:0;transform:translateY(34px)}to{opacity:1;transform:translateY(0)}}@keyframes research-reveal{from{opacity:.2;transform:translateY(38px) scale(.985)}to{opacity:1;transform:none}}
@supports(animation-timeline:view()){.research-grid,.research-callout{animation:research-reveal linear both;animation-timeline:view();animation-range:entry 4% entry 80%}}
@media(max-width:850px){.research-hero{min-height:500px;align-items:flex-start}.research-facts{left:clamp(20px,6vw,42px);right:20px;bottom:25px;justify-content:flex-start}.research-wide,.research-side,.research-third,.research-half{grid-column:span 12}.journey{grid-template-columns:1fr 1fr}.journey-step:nth-child(2):after{display:none}}
@media(max-width:560px){.research-hero{min-height:500px;padding:31px 25px;border-radius:23px}.research-hero h1{font-size:45px!important}.research-lede{font-size:16px}.research-grid{gap:12px;margin:12px 0}.glass-card{padding:26px 23px;border-radius:22px}.research-truth{grid-template-columns:1fr}.journey{grid-template-columns:1fr}.journey-step:after{display:none!important}.research-fact{font-size:10px;padding:8px 10px}}
@media(prefers-reduced-motion:reduce){.research-hero:before,.research-hero:after,.research-hero-copy,.research-grid,.research-callout{animation:none!important}.glass-card{transition:none!important}.glass-card:hover{transform:none}}
</style>
<section class="research-hero"><div class="research-hero-copy"><div class="research-kicker">SONARNET · KHÔNG GIAN NGHIÊN CỨU</div><h1>Đọc tín hiệu biển.<br><em>Rõ từng dấu vết.</em></h1><p class="research-lede">Một không gian để nhìn ảnh radar, phát hiện các điểm cần kiểm tra và giữ bằng chứng đúng nơi, đúng thời điểm.</p></div><div class="research-facts"><span class="research-fact">__FIRST__</span><span class="research-fact">__SECOND__</span><span class="research-fact">__THIRD__</span></div></section>
'''
    st.markdown(hero.replace("__FIRST__", first).replace("__SECOND__", second).replace("__THIRD__", third), unsafe_allow_html=True)
    st.markdown('''<div class="research-grid">
<section class="glass-card research-wide"><div class="section-tag">CÂU HỎI TRUNG TÂM</div><h2>Một điểm sáng<br>nói được gì?</h2><p>Trên ảnh radar, mục tiêu trên biển thường hiện thành điểm sáng. Nhưng ảnh đơn lẻ không tự nói đó là phương tiện nào, có di chuyển hay có liên quan tới một bản tin vị trí hay không.</p><p>SonarNet biến câu hỏi đó thành một quy trình có thể kiểm tra lại: giữ ảnh nguồn, thời gian, tọa độ và nhận xét cùng một điểm quan sát.</p><div class="journey"><div class="journey-step">Ảnh Sentinel-1 được lưu cùng thời điểm quan sát.</div><div class="journey-step">Đất liền và vùng sát bờ được loại khỏi phạm vi đọc ảnh.</div><div class="journey-step">Các điểm có tín hiệu giống mục tiêu được đưa lên bản đồ.</div><div class="journey-step">Người phân tích mở ảnh gốc và đối chiếu nguồn phù hợp.</div></div></section>
<section class="glass-card research-side"><div class="section-tag">MỘT BẢN ĐỒ, BA LỚP BẰNG CHỨNG</div><h3>Không chỉ là các chấm trên bản đồ.</h3><div class="signal-row"><i class="signal-dot" style="background:#0a84ff"></i><b>Ảnh tại điểm quan sát</b><span>có ngày chụp</span></div><div class="signal-row"><i class="signal-dot" style="background:#31c0b0"></i><b>Tọa độ & vùng ảnh</b><span>truy về nguồn</span></div><div class="signal-row"><i class="signal-dot" style="background:#ffb52a"></i><b>Nhận xét nghiệp vụ</b><span>có thể lưu lại</span></div></section>
</div><div class="research-grid">
<section class="glass-card research-half"><div class="section-tag">CÁCH ĐỌC KẾT QUẢ</div><h3>Thận trọng là một phần của thiết kế.</h3><div class="research-truth"><div class="truth"><b>Có điểm sáng ≠ đã xác nhận tàu</b><p>Điểm cần được người xem mở ảnh và kiểm tra bối cảnh trước khi ghi nhận.</p></div><div class="truth"><b>Không có điểm ≠ vùng biển trống</b><p>Chất lượng ảnh, thời điểm chụp, phạm vi đọc ảnh và điều kiện biển đều ảnh hưởng kết quả.</p></div></div></section>
<section class="glass-card research-half"><div class="section-tag">THỜI GIAN LÀ BẰNG CHỨNG</div><h3>Không ghép hai dữ liệu khác thời điểm.</h3><p>Mỗi ô ảnh có mốc quan sát riêng. Khi có dữ liệu hành trình được cấp phép, hệ thống sẽ đưa các mốc về cùng thời điểm trước khi đánh giá độ gần nhau.</p><p>Điều này giúp phân biệt giữa một sai lệch do thời gian và một điểm thực sự cần xem xét thêm.</p></section>
</div><div class="research-grid">
<section class="glass-card research-third"><div class="section-tag">01 / CHẤT LƯỢNG</div><h3>Đo độ tin cậy</h3><p>So sánh điểm gợi ý với nhãn kiểm chứng để biết loại ảnh, khu vực và điều kiện nào hệ thống đang làm tốt hoặc cần cải thiện.</p></section>
<section class="glass-card research-third"><div class="section-tag">02 / PHẠM VI</div><h3>Nhìn đúng khu vực</h3><p>Tiến độ được lưu theo từng ô ảnh. Người xem biết nơi nào đã đọc, nơi nào đang chờ dữ liệu phù hợp thay vì suy đoán từ nền bản đồ.</p></section>
<section class="glass-card research-third"><div class="section-tag">03 / CON NGƯỜI</div><h3>Giữ quyết định ở người dùng</h3><p>Hệ thống ưu tiên ảnh nguồn và quy trình rà soát. Kết luận nghiệp vụ luôn cần người có thẩm quyền xác minh.</p></section>
</div><section class="research-callout"><h3>Từ một quan sát đến một hồ sơ có thể giải thích.</h3><p>Giá trị của hệ thống không nằm ở việc tạo ra nhiều dấu chấm, mà ở khả năng trả lời: điểm này nằm ở đâu, ảnh chụp khi nào, tín hiệu đến từ ảnh nào và ai đã xem xét nó.</p><div class="research-rule"></div><span class="research-pill">Ảnh radar: nguồn Copernicus Sentinel-1</span><span class="research-pill">Điểm nghi vấn: cần xác minh</span><span class="research-pill">Hồ sơ hành trình: chỉ tích hợp từ nguồn được phép</span></section><p class="research-foot">Ảnh radar và thời điểm quan sát trong SonarNet là dữ liệu thật. Hồ sơ phương tiện trên giao diện là dữ liệu mẫu để minh hoạ cách đối chiếu khi có nguồn hành trình được cấp phép.</p>''', unsafe_allow_html=True)
    with st.expander("Nền tảng nghiên cứu & hướng phát triển"):
        st.markdown("""**Ảnh radar Sentinel-1.** Ảnh được chụp theo các lượt bay khác nhau; vì vậy một bản ghép không phải ảnh đồng thời cho mọi khu vực.

**Phát hiện mục tiêu.** Mô hình tìm các vùng có đặc trưng phù hợp trên ảnh chi tiết. Đất liền và dải sát bờ được loại trừ để giảm nhầm lẫn; kết quả vẫn cần kiểm chứng với ảnh nguồn.

**Đồng bộ thời gian.** Khi có chuỗi vị trí tàu hợp pháp, bộ lọc chuyển động có thể ước lượng vị trí tương ứng với thời điểm ảnh radar được chụp, thay vì so với một bản tin bất kỳ.

**Hướng kiểm chứng.** Mở rộng dữ liệu nhãn vùng biển Việt Nam, đánh giá theo khu vực, mùa và điều kiện sóng; kiểm tra sai số trước khi sử dụng trong quy trình nghiệp vụ.""")
