# Kiểm tra lại recall SAR đa tỷ lệ

Cùng checkpoint YOLO SLC VV, cùng vùng biển hợp lệ, cùng nhãn HIGH/MEDIUM và ngưỡng IoU 0,50. So 7 cách đọc ảnh ở 5 ngưỡng trên 48 ô phát triển, 29 nhãn. Chọn số nhãn khớp cao nhất ở cùng giới hạn 1 lượt rà / 20 km² biển hợp lệ. Khi hòa, chọn ít điểm không khớp hơn trước khi xét kết quả không giới hạn. Cấu hình khóa trước khi chấm lại bốn cảnh đã báo cáo. Ba cảnh đối chiếu và cảnh Biển Bắc không tham gia chọn cấu hình. Đây là đánh giá lại, chưa phải một tập xác nhận mới hoặc nhãn tại Việt Nam.

| Nhóm cảnh | Phương án | Tất cả điểm qua ngưỡng | Điểm không khớp | Cùng giới hạn rà | Điểm không khớp |
| --- | --- | ---: | ---: | ---: | ---: |
| Ba cảnh, 218 ô | 512 px, ngưỡng 0,025 | 51/147 | 211 | 36/147 | 93 |
| Ba cảnh, 218 ô | Đa tỷ lệ, ngưỡng 0,005 | 60/147 | 837 | 38/147 | 91 |
| Ba cảnh, 218 ô | Chỉ hạ ngưỡng 512 px xuống 0,005 | 65/147 | 1.011 | 36/147 | 93 |
| Biển Bắc, 196 ô | 512 px, ngưỡng 0,025 | 69/146 | 943 | 20/146 | 108 |
| Biển Bắc, 196 ô | Đa tỷ lệ, ngưỡng 0,005 | 87/146 | 1.453 | 22/146 | 106 |
| Biển Bắc, 196 ô | Chỉ hạ ngưỡng 512 px xuống 0,005 | 88/146 | 2.175 | 20/146 | 108 |

Đọc ở 512 px, 768 px và 768 px sau lật ngang. Đưa hộp về hệ tọa độ ảnh gốc, gộp trùng ở IoU 0,45, rồi lọc theo vùng biển chấm. Trung vị thời gian CPU 4 luồng tăng từ 52–57 lên 218–243 ms/ô, chưa tính đọc ảnh. Điểm không khớp nhãn cần xem lại trên ảnh.

Phép phát lại dành tối đa 20% lượt rà cho dải 500 m từ bờ giữ 7/35 nhãn ven bờ ở ba cảnh và tăng từ 2/14 lên 3/14 ở Biển Bắc. Kết quả tách khỏi cấu hình đã khóa, chưa dùng để thay mô hình trên bản đồ.

## Tái lập

Chuẩn bị dữ liệu và checkpoint theo thư mục opensar_adaptation_20261118 liền kề, dùng cùng manifest và cấu trúc thư mục. Chạy evaluate_sar_multiscale.py với --data, --adaptation, --diagnostic, --previous, --weights và --out. Sau đó chạy replay_sar_multiscale.py với --data, --adaptation, --diagnostic, --evaluation và --out. Script đối chiếu checksum đầu vào và từ chối chấm nếu manifest hoặc checkpoint thay đổi.

Ba tệp protocol.json, operating_point.json và results.json lần lượt lưu giao thức, lựa chọn khóa và số đo. Dự đoán theo ô nằm trong các tệp *_predictions.json.gz. threshold-and-coast.json ghi phép phát lại kiểm tra riêng ngưỡng và ven bờ.
