# SonarNet-VN — Báo cáo kết quả thực nghiệm

*Thời điểm kết xuất: 15/09/2026 15:12*

Hệ thống giám sát tuân thủ quy định chống khai thác thuỷ sản bất hợp pháp, không khai báo và không theo quy định, trên cơ sở hợp nhất ảnh vệ tinh radar khẩu độ tổng hợp với tín hiệu giám sát hành trình tàu cá.

## 1. Cấu hình lần chạy

| Tham số | Giá trị |
|---|---|
| Chế độ | Đầy đủ |
| Hạt giống ngẫu nhiên | 20260914 |
| Kích thước cảnh | 640 × 640 điểm ảnh |
| Độ phân giải mặt đất | 10 m/điểm ảnh |
| Tỉ lệ phương tiện ngắt định danh | 28% |
| Số chu kỳ huấn luyện | 80 |
| Phương án phát hiện | ultralytics |
| Huấn luyện phân tán | không |
| Ngưỡng ghép cặp | 500 m |

## 2. Bộ dữ liệu

| Tập | Số cảnh | Số phương tiện | Số khung bao | Số bản ghi AIS |
|---|---:|---:|---:|---:|
| train | 500 | 4300 | 4300 | 58718 |
| val | 80 | 702 | 702 | 9226 |
| test | 80 | 672 | 672 | 8803 |

## 3. Tầng phát hiện phương tiện

| Chỉ tiêu | Giá trị | Mục tiêu đề ra |
|---|---:|---:|
| mAP@0.5 | 0.9312 | ≥ 0,70 |
| mAP@0.5:0.95 | 0.4689 | — |
| Độ chính xác | 0.9252 | — |
| Độ nhạy | 0.9568 | ≥ 0,80 |
| F1 | 0.9407 | — |
| Dương tính thật / giả / bỏ sót | 643 / 52 / 29 | — |

![Đường cong chính xác – độ nhạy](02_duong_cong_pr.png)

## 4. Tầng hợp nhất ảnh radar và AIS

| Chỉ tiêu | Giá trị | Mục tiêu đề ra |
|---|---:|---:|
| Tỉ lệ ghép cặp chính xác | 1.0000 | ≥ 0,85 |
| Sai số ghép cặp trung bình | 39.1 m | ≤ 200 m |
| Sai số ghép cặp trung vị | 36.1 m | — |
| Độ chính xác lớp không phát AIS | 1.0000 | ≥ 0,75 |
| Độ nhạy lớp không phát AIS | 0.9552 | ≥ 0,70 |
| F1 lớp không phát AIS | 0.9771 | — |
| Độ chính xác ba trạng thái | 0.9693 | — |
| F1 vĩ mô ba trạng thái | 0.9656 | — |

### So sánh phương pháp nội suy quỹ đạo

| Phương pháp | Sai số trung bình | Sai số trung vị | Bách phân vị 90 |
|---|---:|---:|---:|
| Bộ lọc Kalman | 38.1 m | 35.7 m | 64.8 m |
| Nội suy tuyến tính | 49.0 m | 44.0 m | 84.4 m |

## 5. Tầng phân loại hành vi hoạt động

Thuật toán sử dụng: **xgboost**. Huấn luyện trên 960 quỹ đạo, kiểm tra trên 320 quỹ đạo.

| Chỉ tiêu | Giá trị | Mục tiêu đề ra |
|---|---:|---:|
| Độ chính xác | 1.0000 | — |
| F1 vĩ mô | 1.0000 | ≥ 0,70 |

| Nhóm hành vi | F1 |
|---|---:|
| Câu | 1.0000 |
| Kéo lưới | 1.0000 |
| Neo đậu | 1.0000 |
| Quá cảnh | 1.0000 |

## 6. Phân tích đóng góp của từng thành phần

| Cấu hình | Nội dung | Độ nhạy phát hiện | Chính xác lớp DARK | Độ nhạy lớp DARK | F1 lớp DARK | Chính xác 3 trạng thái | F1 vĩ mô 3 trạng thái | Sai số ghép cặp (m) |
|---|---|---|---|---|---|---|---|---|
| A | Chỉ ảnh radar | 0.9568 | 0.2991 | 1.0000 | 0.4605 | 0.2991 | 0.1535 | — |
| B | Chỉ dữ liệu AIS | 0.7009 | 0.0000 | 0.0000 | 0.0000 | 0.7009 | 0.5939 | 0.0000 |
| C | Hợp nhất, nội suy tuyến tính | 0.9568 | 1.0000 | 0.9552 | 0.9771 | 0.8221 | 0.6109 | 49.7000 |
| D | Hệ thống đầy đủ | 0.9568 | 1.0000 | 0.9552 | 0.9771 | 0.9693 | 0.9656 | 39.1000 |

Bảng trên cho thấy giá trị cốt lõi của việc hợp nhất hai nguồn dữ liệu. Cấu hình chỉ dùng ảnh radar phát hiện được phương tiện nhưng không có căn cứ để xác định trạng thái định danh. Cấu hình chỉ dùng AIS bỏ sót hoàn toàn các phương tiện chủ động ngắt tín hiệu — đúng những trường hợp cần phát hiện nhất. Chỉ khi hợp nhất cả hai nguồn, hệ thống mới đồng thời đạt độ nhạy phát hiện cao và khả năng nhận diện phương tiện ngắt định danh.

## 7. Sản phẩm kết xuất

| Tệp | Nội dung |
|---|---|
| `01_canh_anh_radar.png` | Cảnh ảnh radar kèm đối chứng và phát hiện |
| `02_duong_cong_pr.png` | Đường cong chính xác – độ nhạy |
| `03_ma_tran_hop_nhat.png` | Ma trận nhầm lẫn ba trạng thái định danh |
| `04_sai_so_ghep_cap.png` | Phân bố sai số ghép cặp |
| `05_so_sanh_noi_suy.png` | So sánh hai phương pháp nội suy |
| `06_ma_tran_hanh_vi.png` | Ma trận nhầm lẫn bốn nhóm hành vi |
| `07_quy_dao_hanh_vi.png` | Quỹ đạo tiêu biểu của từng nhóm hành vi |
| `08_dac_trung_quan_trong.png` | Đặc trưng động học quan trọng nhất |
| `09_dong_gop_thanh_phan.png` | Biểu đồ đóng góp của từng thành phần |
| `ban_do_giam_sat.html` | Bảng điều khiển bản đồ giám sát |

## 8. Ghi chú về dữ liệu

Kết quả trong báo cáo này được tạo trên bộ dữ liệu mô phỏng có nhãn đối chứng đầy đủ. Bộ mô phỏng tái tạo các đặc trưng vật lý chính của ảnh radar khẩu độ tổng hợp trên biển: tán xạ nền Rayleigh, nhiễu đốm nhân tính, điều biến do gió, vệt nước sau tàu và bóng ma phương vị. Mục đích là kiểm chứng tính đúng đắn của toàn bộ kiến trúc xử lý và thiết lập mức tham chiếu cho từng tầng.

Để chuyển sang dữ liệu thật, thay thế bước sinh dữ liệu bằng ảnh Sentinel-1 tải từ Copernicus Data Space và dòng AIS từ Global Fishing Watch; toàn bộ các tầng phía sau giữ nguyên không đổi. Hướng dẫn chi tiết nằm trong tệp `README.md`.
