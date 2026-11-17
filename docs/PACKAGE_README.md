# Đọc trước khi sử dụng gói SonarNet

Gói này chứa bản cải tiến ngày 17/11/2026, báo cáo PDF 9 trang, PowerPoint 12 slide,
kịch bản dự kiến 5 phút, checkpoint SAR mới, mã nguồn và bằng chứng đánh giá.
Đây là bản để rà soát và chuẩn bị nộp; các mục còn thiếu được ghi trong
`docs/FINAL_STATUS.md`. Không coi gói này là xác nhận đã nộp thành công cho BTC.

## Mở tài liệu

- Báo cáo: `output/pdf/SonarNet_Bao_cao_cai_tien_Chang1.pdf`.
- Slide: `output/slides/SonarNet_Chang1_Thuyet_trinh_v2.pptx`.
- Kịch bản: `output/slides/SonarNet_Kich_ban_5_phut.md`.
- Khai báo AI: `docs/AI_DECLARATION_CHANG1.md`; tác giả đọc và xác nhận.
- Hồ sơ xuất từ ảnh thật: `reports/final/export_verification/sample_evidence.zip`.
- Bằng chứng SAR: `reports/final/independent_sar/`, gồm cả dự đoán thô.
- Biểu mẫu BTC vòng trước chưa tải được từ iCloud, chưa nằm trong gói này.

## Chạy bản trình diễn

Dùng Python 3.11 hoặc 3.12. Mở terminal trong thư mục SonarNet đã giải nén:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run scripts/demo_app.py
```

Trang “Minh chứng cải tiến” đọc số liệu đóng gói sẵn, không cần huấn luyện lại.
Phần bản đồ đầy đủ cần khoảng 13 GB ảnh công bố. Xem trường
`includes_published_map_images` trong `PACKAGE_MANIFEST.json`: nếu là `false`,
khôi phục bằng lệnh dưới đây trước khi đánh giá độ phủ bản đồ. Khi chưa khôi phục,
các ô thiếu ảnh được đánh dấu không khả dụng; không coi là biển không có tàu.

```sh
python -m pip install requests
python scripts/restore_published_assets.py --output assets/real_scan/published
```

Công cụ tải đúng revision và kiểm tra Git blob SHA-1 từng tệp; có thể chạy lại
để tiếp tục các tệp còn thiếu. Dung lượng mạng tải thực tế có thể lớn hơn 13 GB
do nguồn là bản lưu GitHub. Ảnh đã có trên SSD của tác giả không cần tải lại.

## Kiểm chứng và tái lập

`PACKAGE_MANIFEST.json` lưu SHA-256 từng tệp trong ZIP và danh sách tệp Git
không đóng gói. Tệp `.zip.sha256` bên cạnh ZIP kiểm chứng toàn bộ gói.
Không đóng gói môi trường ảo, thông tin đăng nhập hoặc toàn bộ ảnh huấn luyện.

Môi trường huấn luyện, tham số, đường cong, checksum checkpoint và mã đánh giá
được giữ trong `reports/final/independent_sar/`. Để tái chạy huấn luyện/đánh giá,
xem `reports/final/independent_sar/README.md` và `scripts/rebuild_final.sh`;
cần tải LS-SSDD, dựng lại manifest và đổi đường dẫn SSD theo máy sử dụng.

Kết quả nghiên cứu lịch sử trong `sonarnet_run/results/` là lượt cũ, có mô phỏng.
Không thay thế số liệu mới hoặc gộp chúng thành một phép đo trên dữ liệu thực.
Checkpoint mới là ứng viên nghiên cứu; kết quả bản đồ cũ giữ nguyên nguồn gốc.

Các hạn chế còn mở: quy đổi mét/km², kiểm định AIS thực địa, xác nhận của người
có chuyên môn và kiểm tra các liên kết nộp công khai. Xem chi tiết trong báo cáo.
