# Khai báo hỗ trợ AI trong lượt cải tiến SonarNet

Phạm vi: công việc được thực hiện trong cuộc trò chuyện Codex này cho chặng cải tiến, ngày 16-17/11/2026. Đây là phụ lục để tác giả đối chiếu và điền vào mẫu BTC, không phải một biểu mẫu BTC tự thiết kế lại.

| Công đoạn | Vai trò của AI | Căn cứ kiểm tra |
|---|---|---|
| Đọc và phân tích yêu cầu | Đọc đề cải tiến trên cổng BTC, lập danh sách đầu việc và giới hạn | docs/FINAL_STATUS.md; báo cáo cải tiến |
| Chỉnh mã nguồn | Hỗ trợ trạng thái thiếu dữ liệu, cổng ghép AIS, quy trình rà soát và bản xuất | Git diff; src/ và scripts/ |
| Dữ liệu | Tìm nguồn LS-SSDD, tải ảnh và nhãn công khai, chia tập, kiểm tra checksum và ảnh tương tự | configs/ls_ssdd_scenes.json; reports/final/dataset_audit/ |
| Mô hình | Chuẩn bị và chạy huấn luyện lại YOLO11n từ trọng số nền, sau khi tác giả xác nhận checkpoint cũ đã xóa | training_provenance.json; model card |
| Đánh giá | Viết/chạy công cụ, lưu dự đoán và lỗi; tạo mô phỏng AIS riêng | results.json; summary.csv; kiểm thử |
| Tài liệu | Soạn báo cáo, vẽ biểu đồ Python, dựng slide và lời thoại | Mã dựng, PDF, PPTX và kịch bản |

Các con số công bố lấy từ đầu ra thực nghiệm. Codex hỗ trợ chuẩn bị và chạy đối chứng đa tỷ lệ, đối chiếu nhãn điểm Ai2 với lịch chụp Sentinel-1 RTC ở ven biển Việt Nam và trình bày bảng kết quả. Các nguồn nhãn SAR gồm LS-SSDD, OSSDD, OpenSAR Insight và Ai2. Nhãn thuộc các bộ nguồn đã công bố. AIS gồm các ca mô phỏng, phát lại bản tin NOAA thật và một cảnh SAR–AIS cùng thời điểm. Từng phép thử có ghi nguồn và phạm vi trong báo cáo.

Tác giả cần tự kiểm tra tính đúng của mã, nguồn dữ liệu, nội dung hồ sơ, quyền sử dụng và các cam kết trước khi nộp. AI không thay tác giả ký hoặc xác nhận, không xác nhận thay chuyên gia và không đưa ra kết luận vi phạm.

## Nhật ký công việc có thể xác minh

1. Khôi phục 9.000 ảnh/nhãn LS-SSDD từ nguồn tác giả, lưu checksum từng tệp.
2. Định trước nhóm cảnh/vùng/ngày, cách ly 115 ảnh tương tự; audit cohort 7.085 ảnh đạt.
3. Huấn luyện lại, dừng sớm ở epoch 24; lưu best.pt và bản sao SSD.
4. Chạy kiểm thử 3.000 ảnh độc lập cùng baseline trên CPU; giữ cả ảnh nhiều lỗi.
5. Chạy 600 kịch bản AIS, báo số ghép đúng, ghép sai, từ chối và cặp ghép thiếu điều kiện.
6. Sửa giao diện, bản xuất, trạng thái và cơ chế xác nhận; kiểm tra trang Minh chứng bằng Chrome.
7. Khôi phục 22.064 tệp ảnh công bố theo mã Git; chuyển vùng làm việc sang SSD khi ổ trong hết chỗ.
8. Chuẩn bị báo cáo, slide, kịch bản và gói bằng chứng để tác giả rà soát.

Danh sách này là bản tóm tắt thao tác, **không phải prompt log nguyên văn**. Không dùng lịch sử commit để giả thành lịch sử prompt. Nếu BTC yêu cầu hội thoại gốc, tác giả xuất đúng cuộc trò chuyện đang có hoặc dùng liên kết chia sẻ do mình kiểm tra quyền truy cập.

Người xác nhận: [TÁC GIẢ ĐIỀN]. Ngày xác nhận: [TÁC GIẢ ĐIỀN].
