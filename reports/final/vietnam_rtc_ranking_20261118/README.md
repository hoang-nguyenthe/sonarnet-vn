# Xếp hạng và hạ ngưỡng trên các lượt chụp mới

Phát triển trên 5 lượt chụp của đối chứng Việt Nam trước. Ở mỗi vòng phát triển, giữ toàn bộ một lượt chụp làm đối chứng và học trên bốn lượt còn lại. Dùng điểm hai detector, đỉnh và độ tương phản radar cục bộ, độ phân tán nền, khoảng bờ và phần pixel hợp lệ để thử hồi quy logistic và boosting. Khóa phương án giữ ứng viên bản đồ rồi bổ sung theo hồi quy logistic dựa trên số nhãn khớp dưới mức trần 1 ứng viên/20 km². Các phương án chỉ xếp hạng lại và các điểm học từ mô hình là nghiên cứu.

Tập mới gồm 12 lượt chụp không cùng ngày UTC với tập phát triển, 86 ô có ảnh và 152 điểm nhãn tại các vùng khảo sát ven bờ phía Bắc, duyên hải Nam Trung Bộ và phía Nam. Mỗi nhãn khớp nhiều nhất một ứng viên trong 100 m WGS84. Cùng vùng nước hợp lệ và cùng quy tắc cho mọi phương án. Trong 13 cảnh lấy được từ nguồn, một cảnh cùng ngày phát triển bị loại. Kiểm lại bằng manifest và mã định danh ảnh. Mục ghi nhận Quảng Ninh trong tệp số liệu là tên khu vực khảo sát; hộp khu vực không xác định ranh giới hành chính hay vùng tài phán.

| Phương án | Nhãn khớp, trần 1/20 km² | Ứng viên phải rà | Điểm không khớp nhãn |
| --- | ---: | ---: | ---: |
| Bản đồ 0,35 | 80/152 | 116 | 36 |
| Bản đồ 0,05 | 96/152 | 191 | 95 |
| Giữ bản đồ, bổ sung theo hồi quy logistic | 95/152 | 287 | 192 |
| Chỉ xếp hạng lại theo hồi quy logistic | 95/152 | 287 | 192 |
| Giữ bản đồ, bổ sung theo boosting | 92/152 | 287 | 195 |
| Chỉ xếp hạng theo boosting | 86/152 | 287 | 201 |

Đối chứng giữ đúng số điểm của bản đồ trên mỗi cảnh cho 116 lượt rà. Bản đồ và hạ ngưỡng đều khớp 80/152. Chỉ xếp hạng hồi quy khớp 66/152, boosting khớp 64/152. Giữ ứng viên gốc cũng khớp 80/152 vì ở mức này không có suất bổ sung. Không suy rộng vượt phạm vi các ô đã có nhãn. Một phần điểm không khớp có thể là mục tiêu chưa được gắn nhãn.

## Tái lập

Chuẩn bị tập phát triển như đối chứng Việt Nam trước. Dùng thêm scikit-learn 1.9.1. Kho ảnh lịch sử là Sentinel-1 RTC từ Microsoft Planetary Computer, nhãn điểm xuất phát từ tệp Ai2 đã ghim phiên bản.

```bash
export PYTHONPATH=src
python scripts/prepare_fresh_vn_references.py --development DEV_DIR --output FRESH_DIR
python scripts/fetch_vn_reference_rtc.py FRESH_DIR
OMP_NUM_THREADS=2 python scripts/evaluate_review_ranking.py --development DEV_DIR --fresh FRESH_DIR --out OUT_DIR
```

Tệp results.json lưu số đếm theo từng lượt chụp ở cả hai điều kiện rà. Tệp equal_count_selection.json lưu kiểm tra khóa riêng trên tập phát triển khi tiêu chí là đúng số lượt rà của bản đồ.

## Hình minh họa từ ảnh SAR thật

Ô ảnh được chọn tự động theo số nhãn tăng thêm khi hạ ngưỡng, với ít nhất ba nhãn trong mô-đun chấm. Hình có hai lớp so sánh trên cùng ảnh Sentinel-1. Nhãn nguồn được giữ riêng với ứng viên của mô hình. Đây là ca minh họa có mức cải thiện lớn trong một ô. Số đo tổng hợp vẫn tính trên mọi ô và các lượt chụp trong bảng. Xem example.json để đối chiếu số đếm và định danh ảnh.

Tạo lại hình bằng scripts/export_vn_recall_example.py với --source là FRESH_DIR, --cache là fresh_features.json.gz từ phép xếp hạng, --font là tệp DejaVu Sans TTF và --output là thư mục đích.
