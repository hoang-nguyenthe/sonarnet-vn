# Đối chứng điểm Sentinel-1 ở ven biển Việt Nam

Nhãn điểm công khai từ [Ai2 Vessel Detection](https://github.com/allenai/vessel-detection-sentinels/tree/60b003d059937a9fcddbf6e1c9b64c00c33c0279). Dùng tệp SQLite gốc theo SHA-256 d3a8bbd6c6685a6f8bb685f122b37fda613649d6da4c450e3240cace353ca2ac. Không dùng tên hay mã nhận dạng tàu. Giữ mỗi tọa độ một lần trên từng cảnh, trong vùng nhãn nguồn. Trong ba vùng kiểm tra đầu vào có nhãn phù hợp ở Đà Nẵng và Vũng Tàu.

Cảnh nguồn và STAC RTC khớp vệ tinh, quỹ đạo tuyệt đối và mốc bắt đầu chụp trong một giây. Ảnh gốc Copernicus Sentinel-1 GRD, xử lý RTC bởi Catalyst, lưu tại Microsoft Planetary Computer. Cắt 81 cửa sổ từ 5 lượt chụp, kích thước 512 × 512. Không tải hoặc công bố tập ảnh nguồn đầy đủ. Kiểm SHA-256 đầu vào từng cửa sổ. Vùng chấm là phần nước hữu hiệu trong vùng ảnh có nhãn, cắt theo đất liền và pixel không hợp lệ. Phần chồng giữa các ô cùng cảnh chỉ tính một lần.

Một lượt chụp Đà Nẵng ngày 06/04/2022 để chọn cấu hình. Ba lượt còn lại ở Đà Nẵng và một lượt ở Vũng Tàu dùng để đánh giá. Trong phép thử mở rộng, thêm các cách giữ ứng viên gốc và bổ sung ứng viên bằng ngân sách còn lại. Lựa chọn được khóa từ cảnh phát triển trước khi chấm lại bốn cảnh. Đây là lần kiểm tra lại trên các cảnh đã báo cáo của phép thử đầu, không phải bốn cảnh mới.

- Phép đo chính khớp một–một bằng bán kính 100 m trên WGS84. Bán kính 50 m và 150 m là kiểm tra độ nhạy. Nhãn điểm không chấm được hộp, kích thước thân tàu hay danh tính.
- Giới hạn rà là tối đa một ứng viên trên 20 km² biển hợp lệ mỗi cảnh, làm tròn xuống. Một phương án có thể không dùng hết lượt. Điểm ngoài nhãn chưa chắc là báo nhầm ngoài thực địa.
- Các phương án bổ sung dùng hết hoặc ít hơn ngân sách rà. Giữ ứng viên gốc theo điểm, thêm ứng viên khác vị trí và loại điểm cách nhau không quá 35 m. Phương án đồng thuận yêu cầu một điểm đa tỷ lệ trong 65 m.
- Giữ riêng số nhãn ven bờ và số nhãn toàn vùng. Khu vực, ngày chụp, nhãn và xử lý địa hình khác phép kiểm SLC VV IoU. Kết quả chưa đủ căn cứ thay cấu hình bản đồ trực tiếp.

## Lệnh tái lập

Môi trường cần numpy, Pillow, PyTorch, Ultralytics, rasterio, pyproj, scipy, shapely, tifffile và các phụ thuộc trong README dự án. Dùng Python 3.11 hoặc 3.12. Chạy từ thư mục gốc SonarNet.

```bash
export PYTHONPATH=src
python scripts/prepare_vn_reference_rtc.py DATA_DIR
python scripts/fetch_vn_reference_rtc.py DATA_DIR
python scripts/score_vn_reference_rtc.py DATA_DIR --hybrids --out OUT_DIR
```

Có thể tiếp tục lượt tải nếu đã có một số ô hợp lệ trong DATA_DIR/rtc-512. Tệp protocol.json ghi quy tắc chấm, SHA-256 checkpoint và đầu vào. results.json chứa số đếm theo ảnh chụp, phạm vi rà và bán kính. Các điểm tọa độ nguồn và mã định danh công khai truy lại được qua script chuẩn bị.
