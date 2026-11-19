# Lọc điểm gần nhau trên ảnh Sentinel-1 RTC VV

Hai ứng viên nằm gần nhau có thể lấy hai lượt rà cho cùng một phản xạ. Phép thử
dùng danh sách YOLO ở ngưỡng 0,05, duyệt theo điểm giảm dần và lọc các tâm gần
nhau trong 35 m. Khi cần, dùng phần dự phòng để giữ đúng số lượt rà theo từng
cảnh. So sánh thêm bán kính 65 m, đỉnh tương phản cục bộ ở ba tỷ lệ và mô hình
xếp hạng kết hợp điểm YOLO với tương phản. Lựa chọn khóa dùng năm ngày phát triển.
Mỗi vòng đánh giá mô hình học xếp hạng giữ riêng trọn một lượt chụp.

Trên 12 lượt chụp giữ riêng, phép lọc 35 m tăng từ 80/152 lên 82/152 với 116 lượt
rà. Mức 191 lượt rà tăng từ 96/152 lên 97/152. Đo khớp một–một trong 100 m trên
cùng vùng nước. Hai nhãn tăng thêm ở mức 116 lượt rà đến từ hai cảnh ở vùng khảo
sát Quảng Ninh. Các lượt chụp này đã được dùng để đánh giá các phương án trước.
Đối chứng bổ sung trên hai lượt chụp khác cùng mã nguồn nằm trong thư mục
[vietnam_rtc_tta_20261119/confirmation](../vietnam_rtc_tta_20261119/confirmation).

Hợp tất cả đề xuất theo tương phản và hai mô hình cho 126/152 nhãn với 4.364
điểm trước lọc, so với 100/152 và 240 điểm ở ngưỡng 0,05 khi bỏ mức trần rà.
Ở đúng số lượt rà, các cách xếp hạng dựa vào tương phản chưa cải thiện số nhãn.
Nguồn nhãn điểm có thể thiếu mục tiêu thực. Phạm vi là các ô ảnh có nhãn Ai2.

Tạo hai tệp cache bằng lệnh trong [đối chứng trước](../vietnam_rtc_ranking_20261118/README.md).
Chạy lại cùng môi trường khoa học có PyTorch, Ultralytics, scikit-learn, Shapely,
PyProj và các phụ thuộc của các bộ đánh giá OpenSAR.

```sh
PYTHONPATH=src python scripts/evaluate_rtc_contrast_recall.py \
  --development DEV_DIR --held-out FRESH_DIR --cached-neural RANKER_DIR --output OUT_DIR
```

Protocol ghi mã băm ảnh theo manifest, cache, mô hình và mã đánh giá. Tệp kết
quả có số đếm riêng ở bán kính khớp 50, 100 và 150 m. Bán kính khớp nhãn khác
bán kính 35 m dùng để lọc các đề xuất sát nhau.
