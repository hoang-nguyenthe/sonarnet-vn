# Xoay, lật và chia ô trên mô hình YOLO của bản đồ

Giữ trọng số và chuẩn hóa dB của mô hình bản đồ. Thử lật ngang, xoay 90 độ,
giảm kích thước đầu vào và chia bốn ô chồng lấn. Mỗi ô có đệm 64 px quanh
vùng trung tâm 256 px. Trả tọa độ dự đoán về ảnh gốc, loại hộp chạm vùng loại
trừ ven bờ và chỉ giữ tâm trong vùng ảnh/nước hợp lệ. Thử hai cách xếp hạng
theo điểm cao nhất hoặc theo đồng thuận giữa các lượt suy luận.

Trên năm lượt phát triển, khóa phương án xoay/lật cho mức rà của ngưỡng 0,35
và chia ô chồng lấn cho mức rà của ngưỡng 0,05. Trên 12 lượt giữ riêng đã có
kết quả từ các thử nghiệm trước, xoay/lật khớp 81/152 so với 80/152 ở 116 lượt
rà. Chia ô khớp 102/152 so với 96/152 ở 191 lượt rà. Cả sáu nhãn tăng thêm
đến từ một lượt chụp trong vùng khảo sát Quảng Ninh. Mỗi nhãn tối đa một ứng
viên trong 100 m. Số lượt rà khớp theo từng cảnh. Chia ô cần thêm lượt suy
luận cho mỗi ảnh.

Phép xác nhận bổ sung dùng 5 ô ở hai ngày chụp khác tại vùng khảo sát Bắc
Trung Bộ. Giữ khóa 35 m và chia ô chồng lấn. Cùng 6 lượt rà, mức gốc và lọc
35 m đều khớp 5/8. Cùng 10 lượt rà, mức gốc, lọc 35 m và chia ô đều khớp 6/8.
Đây là mẫu nhỏ, ghi nhận chưa có tăng thêm tại vùng đó.

```sh
PYTHONPATH=src python scripts/evaluate_rtc_map_tta.py \
  --development DEV_DIR --held-out FRESH_DIR --cached-neural RANKER_DIR --output OUT_DIR
python scripts/plot_rtc_recall_comparison.py
```

Để lấy lại ảnh của hai ngày xác nhận, sao chép hai tệp `screened.json` và
`rtc-matching-with-lineage.json` trong `confirmation/` vào CONFIRM_DIR và chạy
`PYTHONPATH=src python scripts/fetch_vn_reference_rtc.py CONFIRM_DIR`. Đối
chiếu với `window-manifest.json` và mã băm ảnh của tệp gốc.

```sh
PYTHONPATH=src python scripts/confirm_rtc_equal_review.py --source CONFIRM_DIR \
 --development DEV_DIR --previously-scored FRESH_DIR --evidence reports/final --output CONFIRM_OUT
```

Nhãn điểm từ [Ai2 Vessel Detection with Sentinels](https://github.com/allenai/vessel-detection-sentinels).
Ảnh Copernicus Sentinel-1 RTC qua [Microsoft Planetary Computer](https://planetarycomputer.microsoft.com/dataset/sentinel-1-rtc).
