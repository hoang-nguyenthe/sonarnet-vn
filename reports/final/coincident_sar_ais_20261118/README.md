# Sentinel-1 và AIS NOAA trong cùng lượt chụp

## Phép đo

New York Harbor, **13/12/2024 22:51:42 UTC** theo giữa cảnh Sentinel-1 RTC VV. Bốn ô 1.024 × 1.024 pixel đều đủ ảnh. YOLO hiện dùng cho lượt quét khảo sát đưa ra **77 ứng viên**. Có **3.712 bản tin AIS** trong cửa sổ đầu vào, tạo 567 ước lượng quỹ đạo, và 11 vị trí trong khoảng ±20 giây được giữ lại. Bốn ứng viên radar nằm trong 100 m của một vị trí giữ lại, với cả hai phía cách ứng viên cạnh tranh trên 250 m. Trung vị khoảng cách của 4 cặp mốc là 50,22 m.

| Phương án | Cặp đề xuất | Đồng thuận trên 4 mốc vị trí | Đề xuất thiếu mốc đối chiếu | Giữ lại để rà |
| --- | ---: | ---: | ---: | ---: |
| Theo khoảng cách | 36 | 4/4 | 32 | 41 |
| Cổng ghép gốc | 12 | 3/4 | 9 | 65 |
| Cổng biên cạnh tranh 100 m | 9 | 1/4 | 8 | 68 |
| Giữ cặp đề xuất rồi kiểm tra | 7 | 1/4 | 6 | 70 |

Bốn phương án nhận cùng ứng viên ảnh và cùng ước lượng AIS. Cổng giữ đề xuất được bổ sung sau, phát lại trên cảnh đã chấm. Các mốc tham chiếu lấy từ cùng nguồn AIS và kiểm theo khoảng cách. Đây là bằng chứng luồng ghép chạy trên hai nguồn cùng thời điểm, với 4 mốc cần xác minh thêm. Dữ liệu chưa đủ để tính precision của detector, xác nhận danh tính, xếp hạng cách ghép hoặc nâng checkpoint lên bản đồ. Mốc giữa cảnh có thể khác giờ pixel SAR. Chuyển động của tàu có thể làm lệch vị trí radar. Mốc NOAA có độ phủ không đồng đều. 77 ứng viên là số khung của mô hình.

## Nguồn và tái lập

- [Sentinel-1 RTC, Microsoft Planetary Computer](https://planetarycomputer.microsoft.com/dataset/sentinel-1-rtc), contains modified Copernicus Sentinel data processed by Catalyst. ID, URL item, URL tài nguyên không chứa token và SHA-256 từng raster nằm trong `raster_provenance.json`.
- [NOAA Marine Cadastre 2024](https://coast.noaa.gov/htdata/CMSP/AISDataHandler/2024/), tệp ngày 13/12. Bản bàn giao chỉ chứa các số đếm, không có tên tàu, MMSI hoặc điểm hành trình AIS.
- [GSHHG](https://www.soest.hawaii.edu/pwessel/gshhg/) 2.3.7 dùng để loại tâm khung rơi trên đất. Phép thử không loại dải ven bờ 500 m, nhằm giữ các ứng viên cần đối chiếu trong cảng. Lớp xử lý này dành cho thí nghiệm và có phạm vi khác bản đồ đã công bố.

Đặt tệp NOAA `AIS_2024_12_13.zip` cùng các ô gốc và `raster_provenance.json` trong thư mục đầu vào. Dùng môi trường huấn luyện đã khóa kèm pandas, shapely, pyshp. Khi chỉ có tệp AIS, thêm `--fetch-rtc` và rasterio để lấy bốn ô khớp giao thức đã lưu.

```sh
python scripts/evaluate_coincident_sar_ais.py \
  --protocol reports/final/coincident_sar_ais_20261118/protocol.json \
  --input DAU_VAO --coast gshhg-shp-2.3.7.zip --output KET_QUA_MOI
```
