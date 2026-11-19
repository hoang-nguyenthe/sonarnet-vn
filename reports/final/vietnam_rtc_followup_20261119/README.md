# Đối chứng thêm các cách tăng recall RTC

Mỗi phương án trong bảng được chọn trên nhóm phát triển. Chấm lại trên
86 ô thuộc 12 lượt Sentinel-1 lịch sử có 152 nhãn điểm Ai2 và trên hai lượt
giữ riêng ở Bắc Trung Bộ có 8 nhãn. 12 lượt đã được dùng trong các phép đối
chứng SonarNet trước đây. Ghép một–một trong 100 m trên cùng vùng nước hợp
lệ. Điểm không khớp có thể gồm mục tiêu chưa được nguồn gắn nhãn.

| Phương án | 116 lượt rà | 191 lượt rà |
| --- | ---: | ---: |
| Bản đồ ở ngưỡng tương ứng | 80/152 | 96/152 |
| Phương án đã đối chứng trước, lọc 35 m hoặc chia ô | 82/152 | 102/152 |
| Heatmap học từ nhãn tâm | 45/152 | 63/152 |
| Tinh chỉnh YOLO từ LS-SSDD với hộp quy ước | 64/152 | 90/152 |
| Đổi dải cường độ đầu vào | 78/152 | 97/152 |
| Hiệu chỉnh tâm theo heatmap | 80/152 | 100/152 |
| Phân bổ lại lượt rà giữa các cảnh | 65/152 | 93/152 |

Heatmap đề xuất 4.676 điểm, khớp 120/152 nhãn khi rà toàn bộ. Số
đếm này đo độ phủ của danh sách thô. Hai ngân sách rà nhỏ hơn cho thấy
việc xếp hạng các điểm còn khó. Phép hiệu chỉnh tâm lấy danh sách trước
đã lọc 35 m hoặc chia ô làm đối chứng chặt hơn, khớp 82/152 và 102/152.
Phân bổ lại giữ tổng lượt rà và mức trần theo diện tích. Số lượt của từng
cảnh có thể khác. Hai cảnh Bắc Trung Bộ có số liệu tách riêng trong
`summary.json` và các tệp theo lượt chụp.

## Cách chạy lại

Chuẩn bị các bộ RTC theo [đối chứng xếp hạng](../vietnam_rtc_ranking_20261118/README.md),
[tập chia ô và xác nhận](../vietnam_rtc_tta_20261119/README.md). Mỗi
`protocol.json` ghi mã băm của manifest, cache, mã và trọng số. Hai mô
hình dùng trọn ngày 29/06/2022 và 16/08/2022 để phát triển, ba lượt phát
triển còn lại để học. Hộp 7×7 px chỉ là đích huấn luyện cho YOLO. Phép
kiểm chấm tọa độ tâm cùng bán kính như các phương án khác.

| Thư mục kết quả | Lệnh chính |
| --- | --- |
| `point/` | `python scripts/evaluate_rtc_point_detector.py --help` |
| `weak_boxes/` | `python scripts/train_rtc_weak_boxes.py --help` |
| `radiometry/` | `python scripts/evaluate_rtc_radiometry.py --help` |
| `centers/` | `python scripts/evaluate_rtc_center_refinement.py --help` |
| `allocation/` | `python scripts/evaluate_rtc_queue_allocation.py --help` |

Chạy từ thư mục dự án với `PYTHONPATH=src`. Hai tệp trọng số đã khóa, danh
sách ảnh huấn luyện theo mã băm và log số đếm của YOLO được kèm theo. Môi
trường gồm PyTorch 2.8.0, Ultralytics 8.3.253, NumPy, SciPy, PyProj, Shapely
và các thư viện ở đối chứng trước. Lệnh `python scripts/summarize_rtc_followup.py`
tạo lại bảng tóm tắt từ các kết quả lưu sẵn và kiểm tra mã của phép thử,
lựa chọn khóa và trọng số. Nguồn ảnh Sentinel-1 RTC qua Microsoft Planetary
Computer. Nhãn điểm từ Ai2 Vessel Detection with Sentinels.
