# Mở minh chứng SonarNet trong khoảng 2 phút

Mở [demo công khai](https://sonarnet.streamlit.app/?trang=minh-chung). Nút tải PDF và hồ sơ mẫu nằm ngay dưới phần giới thiệu. Có thể [mở trực tiếp hồ sơ mẫu](https://sonarnet.streamlit.app/?trang=quan-sat&che-do=ho-so-mau) để bỏ qua bước mở bản đồ. Bật **Rà soát và lưu ghi chú trên hồ sơ mẫu** để thử lưu từng đánh giá và tải hồ sơ có mã băm. Dùng [hướng dẫn nộp và chạy ngoại tuyến](../NOP_CHANG_1.md) để kiểm tra bản ZIP hoặc tải báo cáo.

[Trang minh chứng công khai](https://hoang-nguyenthe.github.io/sonarnet-vn/) mở không cần đăng nhập. Chọn tập chấm, số ứng viên cần rà và bán kính để đối chiếu kết quả. Trong [Thử ghép AIS](https://hoang-nguyenthe.github.io/sonarnet-vn/#thu-ghep), chọn **Dữ liệu đủ điều kiện ghép** và đổi tuổi bản tin từ 180 lên 181 giây, hoặc đổi độ bất định từ 150 lên 151 m với AIS 10 giây. Tải JSON để xem tham số, lý do và commit. Mở **Hồ sơ mẫu** để tải ảnh nguồn, ZIP và ghi chú có mã băm. Streamlit phục vụ bản đồ và luồng xử lý của ứng dụng.

| Thời gian dự kiến | Thao tác | Điểm cần quan sát |
| --- | --- | --- |
| 0:00–0:25 | Bật **Mở hồ sơ ảnh SAR thật thiếu AIS** | Ảnh, ngày chụp và trạng thái thiếu AIS. Hồ sơ ảnh ở trạng thái chờ xác minh. |
| 0:25–0:50 | Thử **Kích thước mâu thuẫn** và **AIS gần nhất đã cũ, có tín hiệu khác gần đó** | Đây là vị trí mô phỏng chạy qua bộ ghép thật. Khi đề xuất thiếu chất lượng, hệ thống giữ ca để rà và tránh chuyển sang mã kế cận. |
| 0:50–1:20 | Xem **Recall trên 12 lượt chụp mới**, bật **Đúng số lượt rà của bản đồ** | Hai thẻ cho biết số nhãn khớp và số điểm cần rà. Cả hai ngưỡng khớp 80/152 ở 116 lượt rà. Mục **Phát hiện thêm với cùng số lượt rà** cho thấy lọc 35 m đạt 82/152. Trong thử nghiệm 191 lượt rà, chia ô ảnh chồng lấn đạt 102/152 so với 96/152. |
| 1:20–1:45 | Mở **Xem ảnh radar thật và các điểm được tìm thêm** | Hình cho thấy điểm khớp và chưa khớp trên cùng một ô Sentinel-1. Trong **Thử xoay, lật và chia ô ảnh cho mô hình bản đồ**, có ảnh trước và sau của ba nhãn tìm thêm ở cùng số lượt rà. |
| 1:45–2:00 | Mở **Tải báo cáo cải tiến Chặng 1** | Báo cáo có phương pháp, phép đối chứng và giới hạn của từng chỉ số. |

## Thao tác và câu trả lời khi xem kỹ hơn

- **Kiểm tra chi tiết** trong **Quan sát** có thể lưu ghi chú, lấy ảnh nguồn và xuất ZIP gồm `review.html`, `evidence.json` và `checksums.json`. Bản đọc và in hồ sơ ghi từng đánh giá đã lưu. Tệp phiên giữ cả ghi chú của ảnh cũ. Ứng dụng hiển thị mỗi ghi chú khi có đúng ảnh và kết quả của lượt rà. Khi chưa có kho ảnh đầy đủ, dùng hồ sơ mẫu thật.
- **Không ghép AIS** có nhiều nguyên nhân như không có dữ liệu phù hợp, lệch thời gian, độ bất định hoặc ứng viên cạnh tranh. Chỉ người có chuyên môn xác nhận kết luận nghiệp vụ và căn cứ.
- **Có dữ liệu AIS thật** trong phép phát lại NOAA và phép thử cùng cảnh ở New York Harbor. Ca New York ban đầu có bốn mốc vị trí. Mục **Đối chiếu SAR và AIS trên sáu lượt chụp** có 17 mốc gần giờ và 8 mốc ít dịch chuyển từ ba cảng. So sánh danh tính thật ở Việt Nam cần nguồn độc lập.
- **Có dữ liệu SAR có vị trí** trong đối chứng OpenSAR và ảnh Sentinel-1 RTC có nhãn điểm Ai2 ở Việt Nam. Điểm khớp trong 100 m đo độ phủ theo nhãn điểm. Khớp hộp theo IoU là phép chấm khác.
- **Bản đồ** hiển thị ứng viên cần rà theo từng ô và ngày chụp. Khung bản đồ co theo kích thước màn hình. Cấu hình hạ ngưỡng, đa tỷ lệ và huấn luyện 640 px có kết quả riêng trong Minh chứng.
