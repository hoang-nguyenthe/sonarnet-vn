# Đối chứng chuyển nguồn ảnh SAR

Ngày chạy: 18/11/2026. Mục tiêu: kiểm tra checkpoint đã huấn luyện bằng LS-SSDD khi chuyển sang OSSDD, **không dùng OSSDD để huấn luyện**. Do bộ ảnh, số nhãn, phân bố nhóm và cách chuẩn hóa khác nhau, không dùng chênh lệch chỉ số giữa hai bộ để suy ra mức giảm chính xác ngoài thực địa.

## Thiết kế và kết quả

- Chọn 200 ảnh validation / 400 ảnh test từ phân tập công bố, chia đều nhóm có đất và mặt nước. Loại bốn mẫu trong phân tập công bố dùng chung tiền tố cảnh với train. Có 3/16 tiền tố cảnh trong validation/test, không giao nhau; 1.200 thành viên archive đã xác minh CRC và SHA-256 từng tệp. Không kiểm tra được mã băm toàn bộ ZIP vì chỉ tải theo khoảng byte.
- Khóa mô hình, ảnh 640, NMS 0,7 và lưới tham số trước chạy. Chọn theo F1 validation: YOLO log1p/p1–p99,9, confidence 0,40; ngưỡng sáng 0,85; tương phản cục bộ 3,0. `frozen_operating_points.json` được ghi trước khi đọc pixel test. Không chọn lại ngưỡng trên test.
- Test chứa 2.384 nhãn. AP tích phân VOC; TP/FP/FN tại IoU ≥ 0,50. Độ trễ đo batch 1 trên cùng CPU bốn luồng, gồm chuẩn hóa và xử lý dự đoán, không gồm đọc tệp.

| Phương án | Precision | Recall | F1 | AP50 | Báo nhầm | ms/ảnh trung vị |
|---|---:|---:|---:|---:|---:|---:|
| YOLO11n LS-SSDD | 33,86% | 27,89% | 0,3059 | 0,1562 | 1.299 | 66,34 |
| Ngưỡng sáng | 3,03% | 50,67% | 0,0572 | 0,0914 | 38.632 | 9,24 |
| Tương phản cục bộ | 4,29% | 16,69% | 0,0682 | 0,0079 | 8.882 | 14,20 |

YOLO giảm mạnh số điểm cần rà soát so với hai đối chứng cơ sở, nhưng bỏ sót nhiều. Recall của YOLO là **16,33%** trên ảnh gốc phân loại có đất (1.280 nhãn) và **41,30%** trên nhóm mặt nước (1.104 nhãn). Đây là phân nhóm theo diện tích đất của ảnh mẹ, không phải khoảng cách từ tàu đến bờ. Vì tập được cân bằng khi chọn, các số liệu không thể diễn giải như tần suất vận hành tự nhiên.

## Kiểm tra địa vật lặp và đơn vị vật lý

- Không có ảnh trùng pixel. Một cặp dHash khoảng cách 3 (`e01e_1733_452` / `2948_1733_327`) có bố cục địa vật tương đồng rõ trên ảnh rà soát. Khi bỏ ảnh test đã đánh dấu, giữ nguyên cấu hình khóa, kết quả 399 ảnh: YOLO F1 0,3060, recall 27,91%, AP50 0,1562. Đây là phân tích độ nhạy sau kiểm tra, không sửa tập test chính. dHash không loại trừ các ảnh chụp cùng vùng với dịch vị trí, thời gian hoặc góc chụp khác; không khẳng định đã tách địa lý/ngày giữa hai bộ dữ liệu.
- Không ảnh nào trong 400 TIFF test có tag địa tham chiếu đã tìm. Bài báo mô tả pixel spacing danh định 10 m ở nguồn GRD; quy đổi tham khảo của YOLO là 0,1239 báo nhầm/km² **toàn raster danh định** (gồm đất và có thể đếm lặp footprint), sai số tâm trung vị 18,25 m danh định (1,83 px) **trong ảnh** trên 665 hộp khớp. Sai số chiều hộp danh định 31,33 m và 45,94 m theo hai trục ảnh, không phải kích thước thân tàu. Các trường báo nhầm/km² biển hữu hiệu và sai số vị trí tuyệt đối còn `null`. Không đánh dấu đạt yêu cầu vật lý từ phép quy đổi này.
- Mô hình chỉ phát hiện ứng viên, không xác nhận danh tính. Các báo nhầm/bỏ sót được xác định theo nhãn công bố, có thể chịu ảnh hưởng bởi sai số hoặc thiếu nhãn.

## Tái lập và ghi công

Chạy `scripts/prepare_ossdd_followup.py` với metadata gốc đã lưu trong `../ossdd_source_audit/`, rồi `scripts/evaluate_ossdd_followup.py --cohort PATH --weights assets/models/sonarnet_ls_ssdd_20261117.pt --output PATH_MOI`. Dùng môi trường trong `../independent_sar/requirements-training-lock.txt`. `cohort_inputs.json` chứa danh sách tệp, nhãn, checksum và thông tin phục vụ tái lập; `*_test_predictions.json` và `*_test_errors.json` chứa kết quả thô. Ảnh gallery có nhãn cyan và dự đoán cam; chỉ là ca lỗi điển hình, không phải mẫu ngẫu nhiên.

Nguồn: Hammer và cộng sự, *OpenSARShip Ship Detection Dataset*, arXiv:2608.01963v1; kho `sylviaHoch/OpenSARShip-Ship-Detection-Dataset`, revision `46cee3d9e4ff8b4716e2ea5bbe2934e13cb36460`. Contains modified Copernicus Sentinel data, processed and annotated by the dataset authors. Annotations and adapted figures in this folder: CC BY-NC-SA 4.0. Modifications: quantile normalization to grayscale with diagnostic overlays, cohort sampling and derived metrics. Không kèm TIFF gốc trong ZIP.
