# Demo SonarNet - Chặng cải tiến 1

Kịch bản 12 slide và lời thoại khoảng 5 phút: `output/slides/SonarNet_Kich_ban_5_phut.md`. Thời lượng là dự kiến, cần bấm giờ tập trước.

## Bản đang kiểm chứng

Bản làm việc hiện tại: /Volumes/SonarNetWork/sonarnet-final. Giữ SSD kết nối. Chạy `python -m streamlit run scripts/demo_app.py`.

## Phần demo trong bài nói

1. Mở sẵn **Minh chứng cải tiến**.
2. Chọn **Thiếu AIS**: bảng ghi “Thiếu dữ liệu”, chưa có định danh đã ghép, kết luận nghiệp vụ chờ xác minh.
3. Chọn **Kích thước mâu thuẫn**: bảng ghi “Đang xác minh: kích thước lệch”. Nói rõ đây là mô phỏng chạy qua thuật toán thật.
4. Nếu còn thời gian, chọn **Hai quỹ đạo giao nhau** và tải JSON để xem nguyên nhân từ chối.
5. Nếu ứng dụng lỗi quá 5 giây, quay lại slide 10 và tiếp tục.

## Demo mở rộng khi hội đồng hỏi

- **Quan sát**: bản đồ Sentinel-1, ngày ảnh, độ đậm radar và cụm ứng viên. Các mảnh xám là ảnh radar. Ảnh nền toàn cảnh không chứng minh vùng đó đã được mô hình kiểm tra.
- **Kiểm tra chi tiết**: chọn ô có ảnh hợp lệ, xem ảnh gốc và ứng viên. Ô thiếu hoặc sai checksum không được coi là vùng không có tàu.
- Ghi chú và xuất bằng chứng. Người rà soát phải tự khai tên, căn cứ, quyết định và xác nhận. Không dùng danh tính chuyên viên hư cấu.
- Mở ZIP, đối chiếu review.html, evidence.json và checksums.json. Các trạng thái phải thống nhất.
- Mục SAR mới có 3.000 ảnh test LS-SSDD, precision 69,25%, recall 63,54%, AP50 0,6618 theo VOC. Nhấn mạnh recall nhóm ảnh có đất liền chỉ 27,86%.
- Không gán chỉ số của checkpoint mới cho mô hình lịch sử trong bản đồ Việt Nam.

## Các câu trả lời cần nhất quán

**Có AIS thật chưa?** Chưa có nguồn cùng thời điểm đủ để đánh giá thực địa. Phần ghép được kiểm tra bằng mô phỏng, tách riêng khỏi SAR thật.

**Không ghép được có phải tắt AIS không?** Không. Có thể do thiếu nguồn, lệch thời gian, độ bất định hoặc ứng viên cạnh tranh.

**Số điểm trên bản đồ là số tàu?** Đây là ứng viên cần kiểm tra, có thể có nhiễu hoặc trùng giữa các thời điểm.

**Đã chứng minh tốt hơn mô hình cũ?** Checkpoint cũ đã mất. Mô hình mới có đánh giá riêng và baseline đơn giản cùng điều kiện, chưa có so sánh trực tiếp hai checkpoint.

**Đủ mọi chỉ tiêu BTC chưa?** Còn thiếu quy đổi mét/diện tích có metadata kiểm chứng và xác nhận bản công khai đã cập nhật. Báo cáo giữ rõ những mục còn mở.
