# SAR và AIS qua sáu lượt chụp tại ba cảng

Chọn hai lượt chụp Sentinel-1 IW VV tại mỗi cảng theo ngày UTC và độ phủ
catalogue. Chọn xong trước khi đọc pixel hoặc bản tin AIS. Dùng 32 ô RTC
và một checkpoint trên cả sáu lượt. Mặt nạ GSHHG loại tâm khung trên đất.
Cách lọc này giữ phần ảnh vùng cảng cho đối chứng nghiên cứu.

## Hai cách lấy mốc tham chiếu

- Mốc gần giờ dùng bản tin AIS trong ±20 giây quanh giờ giữa cảnh. Giữ
  các bản tin trong khoảng này ngoài đầu vào nội suy AIS.
- Mốc ít dịch chuyển giữ ngoài đầu vào mọi bản tin trong ±120 giây. Cần
  tối thiểu hai bản tin phủ hai phía giờ giữa cảnh, thời gian phủ ít nhất
  30 giây và một bản tin cách giờ giữa cảnh tối đa 65 giây. Các vị trí
  phải nằm trong 35 m từ trung vị. Mốc nằm trên vùng nước có ảnh và cách
  các vị trí cạnh tranh trong cửa sổ trên 250 m.
- Hai phép chấm cần ứng viên radar trong 100 m và sự tách biệt hai chiều
  theo ngưỡng 250 m. Số đếm đánh giá mức đồng thuận vị trí với AIS cùng
  nguồn. Số cặp thiếu mốc chưa được phân loại đúng hay sai.

Có 410 ứng viên radar, 17 mốc gần giờ và 8 mốc ít dịch chuyển. Hai nhóm
mốc có thể giao nhau. So với biên cạnh tranh 100 m, cổng giữ cặp đề xuất
có cùng 6/17 mốc đồng thuận và cùng 11 mốc chưa được ghép ở phép chấm gần
giờ. Số cặp đề xuất thiếu mốc giảm 47 → 31. Trên nhóm ít dịch chuyển,
cả hai có 6/8 mốc đồng thuận, 2 mốc chưa ghép, số cặp thiếu mốc giảm
33 → 19. Bảng chi tiết có cả số cặp khác mốc ở mỗi phương án.

Dữ liệu nghiên cứu này dùng ba cảng Mỹ. Giờ giữa cảnh là mốc catalogue.
Từng mục tiêu vẫn có thể lệch do giờ chiếu radar và chuyển động. Danh tính
và kích thước thân tàu cần nguồn xác minh độc lập.

## Ảnh và dữ liệu

- Thông tin chọn cảnh, ID, thời gian, hình học và mã băm nguồn ghi trong
  `protocol.json`, `catalogue-screen.json` và `results.json`.
- `example-source.png` là ảnh đã dùng trực tiếp cho một ô. `example.jpg`
  phủ khung ứng viên bằng Python. Chọn ô có nhiều mốc ít dịch chuyển
  nhất, rồi ưu tiên có nhiều mốc gần giờ hơn. Số cạnh khung là chỉ số ứng
  viên trong phép chạy, không phải mã nhận dạng tàu. Xem `example.json`.
- Ảnh gốc thuộc Copernicus Sentinel-1 RTC, xử lý Catalyst qua
  [Microsoft Planetary Computer](https://planetarycomputer.microsoft.com/dataset/sentinel-1-rtc).
- Nguồn AIS là kho ngày [NOAA Marine Cadastre 2024](https://coast.noaa.gov/htdata/CMSP/AISDataHandler/2024/).
  Kết quả phát hành chỉ có số đếm và nguồn. Dữ liệu AIS thô ở ngoài gói.
- [Bờ biển GSHHG 2.3.7](https://www.soest.hawaii.edu/pwessel/gshhg/).

## Kiểm tra và tái lập

```sh
python scripts/verify_multiscene_sar_ais.py
```

Lệnh trên kiểm sản phẩm đã khóa, mã nguồn, checkpoint, số đếm và tệp ảnh.
Để chạy lại từ nguồn, đặt hai tệp giao thức trong INPUT_DIR, dùng môi
trường khoa học SonarNet kèm rasterio, pyshp và pandas.

```sh
PYTHONPATH=src python scripts/fetch_multiscene_sar_ais.py INPUT_DIR ais
PYTHONPATH=src python scripts/fetch_multiscene_sar_ais.py INPUT_DIR radar
PYTHONPATH=src python scripts/evaluate_multiscene_sar_ais.py --source INPUT_DIR \
  --coast gshhg-shp-2.3.7.zip --output OUT_DIR
```

Chấm riêng các lượt bằng `--ready-only` khi còn chờ nguồn. Ấn bản công
khai dùng đủ sáu lượt đã khóa.
