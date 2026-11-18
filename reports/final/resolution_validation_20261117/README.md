# Kiểm tra độ phân giải đầu vào — validation chỉ dùng tập validation

Thử nghiệm tiếp nối ngày 17/11/2026 sau khi đã xem kết quả holdout ban đầu. Không thay đổi checkpoint, không đọc ảnh test và không thay báo cáo test đã công bố.

Có 594 ảnh validation, 425 nhãn; CPU 4 luồng. Quy tắc chọn được ghi trước khi chạy trong protocol.json: F1 validation lớn nhất, hòa thì ưu tiên ảnh nhỏ hơn.

| Cỡ đầu vào | Confidence | Precision | Recall | F1 | Trung vị (ms) |
|---|---|---|---|---|---|
| 640 | 0.1 | 0.4343 | 0.4588 | 0.4462 | 67.31 |
| 640 | 0.25 | 0.6641 | 0.4094 | 0.5066 | 67.31 |
| 640 | 0.4 | 0.8202 | 0.3435 | 0.4842 | 67.31 |
| 640 | 0.6 | 0.8889 | 0.1318 | 0.2295 | 67.31 |
| 800 | 0.1 | 0.3814 | 0.4353 | 0.4066 | 90.47 |
| 800 | 0.25 | 0.5861 | 0.3765 | 0.4585 | 90.47 |
| 800 | 0.4 | 0.7166 | 0.3153 | 0.4379 | 90.47 |
| 800 | 0.6 | 0.8636 | 0.1341 | 0.2322 | 90.47 |
| 1024 | 0.1 | 0.3705 | 0.3835 | 0.3769 | 154.47 |
| 1024 | 0.25 | 0.5116 | 0.3106 | 0.3865 | 154.47 |
| 1024 | 0.4 | 0.6185 | 0.2518 | 0.3579 | 154.47 |
| 1024 | 0.6 | 0.8600 | 0.1012 | 0.1811 | 154.47 |

Kết quả: giữ 640 pixel / confidence 0,25. 800 và 1024 không cải thiện F1; không có lý do đổi cấu hình chỉ vì ảnh lớn hơn.

Tập validation hiện không có nhãn nhóm ven bờ, nên `nearshore_recall` là null. Không dùng phép thử này để tuyên bố đã giải quyết bỏ sót ven bờ.

Cần đánh giá ngoài bộ dữ liệu và dữ liệu có metadata hình học trước khi nâng cấp mô hình công khai. Những thay đổi phát sinh sau khi xem lỗi test phải được công bố là thử nghiệm tiếp nối; không gọi tập test đã xem là xác nhận mới.

Lệnh tái chạy (thư mục đầu ra phải chưa tồn tại):
```sh
python scripts/evaluate_sar_resolution.py --manifest /PATH/independent_ls_ssdd/manifest.json --weights assets/models/sonarnet_ls_ssdd_20261117.pt --output /PATH/new-resolution-run
```
