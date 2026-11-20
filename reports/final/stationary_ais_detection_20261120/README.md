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
