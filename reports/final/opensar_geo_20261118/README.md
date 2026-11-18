# Kiểm thử SAR có tọa độ bằng OpenSAR Insight

**Kết quả ngày 18/11/2026.** YOLO11n học trên LS-SSDD, không huấn luyện lại bằng OpenSAR. Trên 503 ô test SLC VV, có 298 nhãn tàu HIGH/MEDIUM trong vùng biển hợp lệ: **96 khớp, 650 dự đoán không khớp nhãn, 202 bỏ sót** tại IoU ≥ 0,5. Tổng diện tích biển dùng làm mẫu số **6.742,76 km² theo lượt chụp**, ước tính từ XML và đường bờ. Mật độ không khớp nhãn **0,0964/km²**. Đây là chỉ số đối chứng theo nhãn nguồn, không phải mật độ báo nhầm ngoài thực địa đã kiểm hết tàu.

| Phương án (cùng CPU 4 luồng) | Precision | Recall | AP50 (VOC) | Không khớp/km² | Thời gian trung vị / p95 |
|---|---:|---:|---:|---:|---:|
| YOLO11n, confidence 0,10 | 12,87% | 32,21% | 0,0878 | 0,0964 | 58,31 / 63,99 ms |
| Ngưỡng sáng 0,70 | 0,02% | 22,82% | 0,0018 | 52,6066 | 20,41 / 82,60 ms |
| Tương phản cục bộ 5,0 | 0,00% | 0,00% | 0,0000 | 0,0000 | 13,39 / 14,99 ms |

Hai đối chứng cơ sở là mốc tối thiểu. Ngưỡng sáng cho lượng nền phải rà rất lớn, tương phản cục bộ ở ngưỡng đã khóa không tìm được tàu. Không diễn giải thành ưu thế trước hệ phát hiện SAR chuyên dụng. Độ trễ gồm chuẩn hóa, suy luận/cụm thành phần và lọc hỗ trợ chấm điểm, không gồm I/O.

## Đo ven bờ và đo sai lệch

- Đến 500 m từ đường bờ bản đồ: **4/14** nhãn khớp (28,57%); đến 1 km: 5/29 (17,24%); đến 2 km: 18/53 (33,96%). Các nhóm lồng nhau, mẫu nhỏ và nhạy với sai số đường bờ. Mô hình không dùng quy tắc loại 500 m ở phép thử này; bản đồ công khai vẫn có quy tắc đó.
- Trong **96 hộp đã khớp**, sai lệch tâm so với **hộp nhãn** sau chiếu là trung vị **17,95 m**, p95 **39,49 m**. Sai lệch ngang/dọc hộp trung vị **37,69/32,81 m**, p95 **108,60/89,20 m**. Trục ảnh và hộp bao không phải chiều dài/rộng thân tàu.
- So với tâm WGS84 ghi trong nhãn nguồn: trung vị **45,92 m**, p95 **80,86 m**. Riêng chênh lệch giữa tâm pixel của nhãn khi nội suy bốn góc và tâm WGS84 của chính nhãn là **49,29 m** trung vị, p95 **70,47 m** trên 298 nhãn; không ghi giá trị tâm hộp 17,95 m thành độ chính xác định vị tuyệt đối. Không có GPS/AIS độc lập cho từng ca và không kiểm định kích thước thân tàu.

## Phân tập, hỗ trợ chấm điểm và tái lập

1. Tải kho [OpenSAR Insight](https://huggingface.co/datasets/opensar-insight/vessel-detection-dataset) ở revision `e90a0c0465cfb8484b4f356ef968d976054f453a`; dùng `train/val/test` labels, `val/test` patches. Chỉ đọc nhãn train của nguồn để kiểm tra phạm vi, không dùng để học. SHA-256 đầy đủ theo LFS trong `source_screen.json`. Dùng **SLC VV 512×512** vì tọa độ hộp XML theo SLC; GRD có kích thước khác và không được gán trực tiếp nhãn này.
2. `scripts/prepare_opensar_geo.py`: đối chiếu hình học footprint của đúng 7 sản phẩm train/val LS-SSDD lấy từ [ASF Search API](https://docs.asf.alaska.edu/api/basics/). Lấy ngày chụp UTC từ mã cảnh/giờ XML, không lấy ngày tạo XML. Cách ly cảnh Biển Bắc (405 ô) vì gần vùng dùng trong LS-SSDD; dùng hai cảnh test tháng 1–2/2020 ở Tây Phi. Cách ly 128 ô validation gần hull test hơn 20 km; giữ các ô còn lại thuộc hai lượt chụp khác. Định nghĩa vùng là khoảng cách hình học của footprint, không dựa vào tên ghi tay. Metadata được sàng lọc trước suy luận. dHash và SHA-256 pixel không phát hiện cặp qua val/test; không chứng minh không có bất kỳ ảnh tương tự dưới mọi biến đổi. Báo riêng 70 validation / 503 test sau lọc chất lượng.
3. Tải `gshhg-shp-2.3.7.zip` từ [GSHHG](https://www.soest.hawaii.edu/pwessel/gshhg/). Dùng đa giác L1 phân đất và biển, không dùng ảnh màu nền bản đồ. Chiếu LAEA cục bộ từng cảnh, nội suy song tuyến tính từ bốn tâm pixel góc trong XML. Chỉ giữ ô có ≥95% pixel SLC hữu hạn, khác 0, >1 km² biển hợp lệ và nhãn hợp lệ; trừ chính xác hình học của pixel rỗng. Phần biển chồng giữa các ô cùng cảnh gán cho ID nhỏ hơn, cho cả mẫu số và chọn nhãn/dự đoán theo tâm; cộng qua các lượt chụp. Không phải phép đo toàn biển Tây Phi, chỉ trên các ô nhà phát hành cung cấp. Dữ liệu đường bờ không đồng thời với ngày chụp; bốn góc là đồng đăng ký xấp xỉ, không phải mô hình quỹ đạo/địa hình đầy đủ.
4. `scripts/evaluate_opensar_geo.py`: xác minh SHA-256 từng TIFF và manifest, đọc SLC quanh điểm vận hành log1p/P1–P99,9 theo ảnh, giữ nhãn HIGH/MEDIUM, bỏ hộp trùng nhãn tàu độ tin cậy thấp khi không đụng nhãn mục tiêu. Khóa ngưỡng theo F1 trên 70 validation trước khi chấm test. Tập test có 2 cảnh, nên không giả định 503 ảnh là 503 lượt chụp độc lập. Các tệp `*_predictions.json.gz` đã lọc đến vùng chấm, giữ confidence; `*_failures.json.gz` là chỉ mục khớp/không khớp theo điểm vận hành.
5. Tái lập bằng môi trường huấn luyện đã khóa, cộng `pyproj==3.7.2`, `shapely==2.1.2`, `pyshp==2.3.1`, `tifffile==2025.10.16` và `zstd`. Đặt đầu vào cùng thư mục trên SSD, theo tên gốc, thêm `ls_ssdd_asf_footprints.geojson` là phản hồi ASF tra `granule_list` bảy ID trong `configs/ls_ssdd_scenes.json`. Bản trích footprint trong ZIP chỉ có trường định danh và hình học. Chạy:

```sh
python scripts/prepare_opensar_geo.py --data DATA --output AUDIT_MOI
python scripts/evaluate_opensar_geo.py --data DATA --audit AUDIT_MOI --output EVAL_MOI --weights assets/models/sonarnet_ls_ssdd_20261117.pt
python scripts/export_opensar_geo_examples.py --data DATA --audit AUDIT_MOI --evaluation EVAL_MOI --output GALLERY_MOI
```

Nguồn ảnh và nhãn: OpenSAR Insight (Indra Space / INTA / Universidad de Alcalá, ESA Φ-lab); contains modified Copernicus Sentinel data. Kho nguồn công bố MIT. Mặt nạ đường bờ dùng GSHHG 2.3.7 L1 theo LGPL; nguồn và checksum ở trên, bản quyền/giấy phép kèm trong `assets/land_mask/`. Không đưa ảnh SLC thô hoặc toàn bộ shapefile vào ZIP.
