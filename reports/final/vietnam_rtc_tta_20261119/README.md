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

## Chấm lại từ tọa độ đã xuất

`review-queues.json` chứa các nhãn Ai2 nằm trong vùng chấm và bốn danh sách
đã rà của mỗi lượt chụp. Dùng lệnh sau trong gói Chặng 1 để tính lại số ghép
một–một ở 50, 100 và 150 m. Phép kiểm tính khoảng cách WGS84 và ghép bằng
Hungarian. Mã đánh giá ban đầu kiểm tra theo ghép cặp cực đại trên đồ thị
thưa. Hai cách cho cùng số nhãn khớp ở 144 phép đối chiếu theo ngày, cách
xếp hạng và bán kính. Tệp đã lưu đủ để chấm lại từ tọa độ mà không tải ảnh,
chạy YOLO hoặc cần thông tin đăng nhập.

```sh
python -m pip install numpy scipy pyproj
python scripts/replay_rtc_equal_review.py
```

Ảnh minh họa cho thấy ba nhãn tìm thêm trong ô 44544 của lượt chụp
23/08/2022. Cả lượt chụp khớp 58 → 64 nhãn với cùng 78 lượt rà. Màu và vòng
trong ảnh chỉ những điểm tăng thêm được chọn theo phép ghép một–một.
`recovered-example.json` lưu định danh ô, tọa độ, khoảng cách và hash của
ô raster đã đọc. Nguồn ảnh Copernicus Sentinel-1, xử lý RTC bởi Catalyst và
phân phối qua Microsoft Planetary Computer. Ảnh minh họa được trích và phủ
ký hiệu. Nhãn Ai2 theo [giấy phép Apache-2.0 của nguồn](AI2-LICENSE.txt).

Tạo lại ảnh và gói tọa độ từ cache đã tạo ở trên.

```sh
PYTHONPATH=src python scripts/export_rtc_review_evidence.py \
  --source FRESH_DIR --cache RANKER_DIR/fresh_features.json.gz \
  --views OUT_DIR/held-out-views.json --font /path/to/DejaVuSans.ttf
```
