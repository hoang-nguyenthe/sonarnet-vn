# SonarNet - hướng dẫn nhận bản cải tiến

## Bản làm việc trên SSD

Do ổ trong hết chỗ, bản tiếp tục phát triển nằm ở `/Volumes/SonarNetWork/sonarnet-final`. Bản cũ trong Documents được giữ lại và có thể không có những sửa đổi sau khi di chuyển. Không chạy đồng thời hai bản nếu muốn tránh nhầm kết quả.

Nếu chưa thấy vùng SonarNetWork sau khi khởi động lại:

```sh
hdiutil attach -nobrowse /Volumes/T7/SonarNet-20261116/workspace.sparseimage
cd /Volumes/SonarNetWork/sonarnet-final
.venv/bin/python -m streamlit run scripts/demo_app.py
```

Ảnh công bố nằm tại `/Volumes/T7/SonarNet-20261116/published-assets`, liên kết vào `assets/real_scan/published`. Đã khôi phục 22.064 tệp của 5.516 ô, kiểm tra Git blob SHA-1 theo revision `3acf068fbfe151c51b96db699fa4cf019f8ca7e6`. Giữ SSD kết nối khi chạy.

## Hồ sơ chặng cải tiến

- Báo cáo PDF: `output/pdf/SonarNet_Bao_cao_cai_tien_Chang1.pdf`.
- Slide sửa được: `output/slides/SonarNet_Chang1_Thuyet_trinh_v2.pptx`.
- Lời thoại và thao tác demo: `output/slides/SonarNet_Kich_ban_5_phut.md`.
- Đối chiếu việc đã làm và việc còn mở: `docs/FINAL_STATUS.md`.
- Kết quả SAR thật: `reports/final/independent_sar/results.json`.
- Kết quả ghép AIS mô phỏng: `reports/final/ais_matching/summary.csv`.
- Checkpoint mới: `assets/models/sonarnet_ls_ssdd_20261117.pt`, có model card cùng thư mục.

Không dùng số liệu của checkpoint mới để ghi đè kết quả hoặc mã mô hình lịch sử trong bản đồ. Chưa xác minh việc cập nhật bản công khai.

## Gói bàn giao và liên kết rà soát

ZIP trên SSD: `/Volumes/T7/SonarNet-20261116/SonarNet_Chang1_Ban_ra_soat_20261117.zip`.
Đọc `docs/PACKAGE_README.md` trước khi chạy. Gói có dự đoán thô và checkpoint,
không chứa toàn bộ ảnh huấn luyện hoặc 13 GB ảnh bản đồ; có công cụ khôi phục ảnh
bản đồ theo revision và checksum. SHA-256 toàn gói nằm trong tệp `.zip.sha256`
bên cạnh; SHA-256 từng thành phần nằm trong `PACKAGE_MANIFEST.json` bên trong.

- Mã nguồn mới: https://github.com/hoang-nguyenthe/sonarnet-vn/tree/final/chang-1
- PR nháp: https://github.com/hoang-nguyenthe/sonarnet-vn/pull/3
- PDF trên nhánh: https://github.com/hoang-nguyenthe/sonarnet-vn/blob/final/chang-1/output/pdf/SonarNet_Bao_cao_cai_tien_Chang1.pdf

Đây là nhánh rà soát, chưa phải bản chạy công khai. Không điền link demo cũ như
thể nó đã có toàn bộ cải tiến mới. Chưa thực hiện cam kết/nộp hồ sơ trên portal.

## Những thông tin tác giả cần chốt

- Tên đội chính thức và thông tin thành viên theo tài khoản BTC.
- Người có chuyên môn thật sự rà soát kết quả. Không tự điền danh tính chuyên viên hoặc xác nhận thay họ.
- Đọc và xác nhận khai báo AI của lượt cải tiến. Nhật ký công việc hiện tại không thay thế lịch sử prompt gốc đã mất.
- Liên kết HTTPS cuối cùng của mã nguồn, demo và PDF; kiểm tra quyền xem trước khi nộp.
- Cam kết và thao tác nộp cuối trên cổng BTC.

Biểu mẫu BTC của vòng trước được giữ nguyên ở thư mục hồ sơ cũ. Các tệp đó hiện là bản lưu iCloud chưa tải về, nên gói cải tiến không được mô tả là đã cập nhật hoặc kiểm tra lại toàn bộ biểu mẫu cũ. Báo cáo cải tiến là tài liệu bổ sung, không thay thế mẫu BTC.

## Tiêu chí chưa được phép đánh dấu hoàn tất

Báo nhầm/km² và sai số mét cần metadata của đúng ảnh sau hiệu chỉnh và resampling. Hiện chỉ có chỉ số pixel và recall theo nhóm ảnh có đất liền. Chưa có AIS thực địa để kiểm định ngưỡng ghép; tên người rà soát trong demo còn tự khai. Các giới hạn này phải đi cùng kết quả.
