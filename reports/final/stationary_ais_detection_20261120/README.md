# Đối chứng phát hiện radar với mốc AIS ít dịch chuyển

Sáu lượt Sentinel-1 RTC lịch sử tại Los Angeles/Long Beach, Galveston/Houston
và New York dùng lại đúng 32 ô, nguồn đường bờ và trọng số của [phép kiểm
ghép SAR–AIS](../multiscene_sar_ais_20261119/README.md). Lần này, tập đối
chiếu có 13 vị trí được khóa từ chuỗi AIS và vùng ảnh hợp lệ trước khi chạy
bất kỳ phương án phát hiện nào. Tiêu chí giữ gồm có bản tin hai phía giờ
chụp, ít dịch chuyển và cách tín hiệu AIS cạnh tranh ít nhất 250 m.

| Cấu hình | Lượt rà | Mốc khớp trong 100 m |
| --- | ---: | ---: |
| Ảnh nguyên · ngưỡng 0,35 | 410 | 10/13 |
| Lọc điểm gần nhau trong 35 m | 410 | 10/13 |
| Thêm ô chồng lấn · mức rà hẹp | 410 | 9/13 |
| Ảnh nguyên · ngưỡng 0,05 | 1.483 | 12/13 |
| Thêm ô chồng lấn · mức rà rộng | 1.483 | 13/13 |

Cùng số lượt rà theo từng cảnh. Phép ghép một–một tính ở 50, 100 và 150 m.
Các mốc AIS chỉ đại diện vị trí của nhóm phát tín hiệu ít dịch chuyển.
Số điểm chưa khớp còn gồm mục tiêu thiếu tham chiếu, nên bảng này dùng để
đối chiếu phạm vi phát hiện trên 13 mốc. Tệp lưu tọa độ đánh giá và mã băm
ảnh nguồn. Các danh sách xuất ghi tọa độ mà không kèm bản tin AIS hay MMSI.

## Kiểm lại từ ZIP Chặng 1

```sh
python -m pip install numpy scipy pyproj
python scripts/replay_rtc_additional_trials.py
```

Chạy lại nhận dạng sau khi phục hồi sáu cảnh và tệp AIS theo hướng dẫn phép
kiểm ghép. Dùng đường bờ GSHHG 2.3.7, môi trường chạy YOLO và các cờ sau.

```sh
PYTHONPATH=src python scripts/evaluate_rtc_stationary_ais_reference.py \
  --source SOURCE_DIR --coast gshhg-shp-2.3.7.zip \
  --association reports/final/multiscene_sar_ais_20261119/results.json --output OUT_DIR
```

Nguồn ảnh [Sentinel-1 RTC](https://planetarycomputer.microsoft.com/dataset/sentinel-1-rtc).
Nguồn vị trí [NOAA Marine Cadastre](https://coast.noaa.gov/htdata/CMSP/AISDataHandler/2024/).

## Đối chứng mô hình VV/VH với cùng 13 mốc AIS

Giữ đúng sáu cảnh, mốc AIS, số điểm cần rà theo cảnh và trọng số xView3
đã dùng cho thử nghiệm Việt Nam. Tải 32 cặp dải VV/VH vào cùng lưới gốc
1.024 px. Kiểm từng ảnh VV dựng lại khớp ảnh đã dùng để chấm YOLO.
Gộp đề xuất theo điểm lớn nhất rồi lọc các tâm trong 35 m. Chốt cách
so sánh theo phương án đã thử trước trên dữ liệu Ai2.

| Mức rà | Lượt rà | Danh sách đối chứng | Phối hợp xView3 |
| --- | ---: | ---: | ---: |
| Hẹp, lọc trùng 35 m | 410 | 10/13 | 11/13 |
| Rộng, gồm ô chồng lấn | 1.483 | 13/13 | 13/13 |

Ở mức 410 điểm, xếp ứng viên xView3 lên trước cho 9/13. Chênh lệch được
đo trên 13 mốc ít dịch chuyển. Các tệp trong `dual-band` giữ kết quả cả
ba bán kính, tọa độ chấm và mã băm dữ liệu từng ô. Tùy chọn xem ảnh cho
thấy một ca bổ sung mốc khớp, với số lượt rà của cảnh giữ đúng như đối chứng.

```sh
PYTHONPATH=src python scripts/fetch_stationary_ais_rtc_bands.py \
  --source SOURCE_DIR --output VV_VH_DIR
PYTHONPATH=src python scripts/evaluate_xview3_stationary_ais.py \
  --source SOURCE_DIR --raster VV_VH_DIR --coast gshhg-shp-2.3.7.zip \
  --ais-evidence reports/final/stationary_ais_detection_20261120 \
  --upstream XVIEW3_DIR --weights RESNET34_WEIGHT --output OUT_DIR
PYTHONPATH=src python scripts/replay_rtc_additional_trials.py
```

Xem [phiên bản mã và trọng số xView3](../vietnam_rtc_transfer_20261119/README.md).
Dùng Rasterio 1.4.4 để đọc các ô Sentinel-1 từ Microsoft Planetary Computer.
