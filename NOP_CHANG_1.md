# SonarNet Việt Nam | Chặng 1 Vòng Chung kết

Đối chiếu với đề riêng **Phiên bản 1** trong tài khoản tại [Cổng Chặng 1](https://ai.tainangviet.vn/dashboard/final). Hạn hiển thị **23:59 ngày 26/11/2026**, giờ Việt Nam.

## Ba ô bắt buộc trên cổng

| Ô trên cổng | Giá trị để điền |
| --- | --- |
| Liên kết mã nguồn | https://github.com/hoang-nguyenthe/sonarnet-vn. Ghi thêm mã commit đã thử vào ô phiên bản nếu dùng. |
| Liên kết sản phẩm chạy thử | https://sonarnet.streamlit.app/?trang=minh-chung mở thẳng phần minh chứng. Thử mở bằng cửa sổ chưa đăng nhập. |
| Liên kết báo cáo cải tiến PDF/Word | https://raw.githubusercontent.com/hoang-nguyenthe/sonarnet-vn/main/output/pdf/SonarNet_Bao_cao_Chang1_Giu_cap_AIS_20261118.pdf. Dùng URL ghim theo commit khi chốt bản nộp. |

Cổng Chặng 1 không có ô nộp video hoặc biểu mẫu đăng ký Bảng C. ZIP là bản bàn giao mã nguồn và bằng chứng để rà soát. Chủ dự án kiểm tra quyền mở cả ba liên kết rồi tự xác nhận cam kết và nộp chính thức.

## Hướng dẫn dùng thử

> Trong **Recall trên 12 lượt chụp mới**, chuyển giữa cùng mức trần theo diện tích và đúng số lượt rà của bản đồ để so sánh ngưỡng 0,35 với 0,05 và các bộ xếp hạng thử nghiệm. Dữ liệu là nhãn điểm lịch sử, khớp trong 100 m.

> Ở mục **Kiểm tra trên ảnh ven biển Việt Nam**, xem mẫu Sentinel-1 có nhãn điểm Ai2 ở Đà Nẵng và Vũng Tàu. Có thể đổi bán kính 50, 100, 150 m và xem số ứng viên cần rà. Đây là phép so sánh với nhãn điểm, khác với IoU 0,50 dùng để chấm hộp trên SLC.

> Ở đầu trang Minh chứng, chuyển **Phạm vi so sánh** giữa mọi ứng viên qua ngưỡng và cùng giới hạn rà soát để xem recall SAR trước–sau. Mở **Xem tác động của ngưỡng điểm và ưu tiên ven bờ** để xem kết quả riêng khi chỉ hạ ngưỡng. Bảng giữ cả số điểm không khớp nhãn và độ trễ.

> Mở **Minh chứng cải tiến** và bật **Mở hồ sơ ảnh SAR thật thiếu AIS** để xem và tải bằng chứng. Thử **Kích thước mâu thuẫn**, **Hai quỹ đạo giao nhau** và **AIS gần nhất đã cũ, có tín hiệu khác gần đó**. Mở **Xem cảnh Sentinel-1 và AIS cùng lượt chụp** để xem ảnh, mức đồng thuận với bản tin giữ lại và ca cần rà. Trong phần kiểm thử SLC VV, có hai nhóm ảnh độc lập và ảnh lỗi. Hồ sơ mẫu mở được khi thiếu nguồn bản đồ.

Chạy bản bàn giao bằng Python 3.12 từ thư mục `SonarNet` trong ZIP.

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run scripts/demo_app.py
```

Mở `http://localhost:8501/?trang=minh-chung` sau khi chạy. Ảnh bản đồ công bố được phục hồi theo README. Hồ sơ mẫu và trang minh chứng dùng các tệp gọn trong ZIP. SHA-256 từng tệp nằm trong `PACKAGE_MANIFEST.json`.

Trong bản chạy từ ZIP, **Quan sát → Kiểm tra chi tiết** mở hồ sơ ảnh thật đã xác minh khi kho ảnh chưa sẵn sàng. Có thể giữ ghi chú của phiên và xuất ZIP kèm ảnh, mã băm và trạng thái thiếu AIS. Chạy `python scripts/verify_chang1_runtime.py` để kiểm tra luồng này trong thư mục vừa giải nén.

## Nội dung khai báo AI và nguồn để đối chiếu trước khi điền

> Trong lượt cải tiến Chặng 1, OpenAI Codex hỗ trợ đối chiếu yêu cầu, sửa mã, viết kiểm thử, chuẩn bị và kiểm tra dữ liệu, chạy huấn luyện và đối chứng, trình bày báo cáo. Số liệu lấy từ đầu ra chạy thực nghiệm trong reports/final. Dữ liệu SAR sử dụng Copernicus Sentinel-1, LS-SSDD, OSSDD và OpenSAR Insight. GSHHG dùng để xác định đường bờ. YOLO11n khởi tạo từ trọng số COCO của Ultralytics. AIS có bài thử mô phỏng và đối chứng giữ lại bản tin lịch sử NOAA Marine Cadastre. Phép kiểm tra ven biển Việt Nam dùng nhãn điểm công khai Ai2 và ảnh Sentinel-1 RTC từ Microsoft Planetary Computer. Nguồn, phiên bản, mã băm và phạm vi đánh giá nằm trong báo cáo và tài liệu tái lập.

Chủ dự án bổ sung các công cụ hoặc nguồn đã sử dụng trong các giai đoạn trước nếu có. Các ca ảnh thật đang chờ người có chuyên môn xác nhận. Tên người rà soát trong demo là thông tin tự khai.
