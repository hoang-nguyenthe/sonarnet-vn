# Khôi phục tải ảnh và xử lý trên GitHub Actions

## Ảnh bằng chứng trong popup

Streamlit Community Cloud đặt ứng dụng bên trong `/~/+/`. URL bắt đầu bằng
`/app/static/...` trỏ ra ngoài ứng dụng và trả về trang chuyển hướng, không phải
JPEG. URL tương đối `app/static/crops/...` giữ đúng đường dẫn nền của iframe.
Ảnh cắt được tạo từ `sar.png` đã lưu, không gọi Copernicus khi người dùng bấm
vào điểm. Kích thước hiển thị được giữ cố định 104 × 104 px; giữ nguyên tỷ lệ
ảnh với `object-fit: contain`. Nguồn thiếu không được thay bằng ảnh của điểm khác.

## Nguồn dự phòng

- Nguồn chính: Copernicus Data Space Sentinel Hub Process API, VV gamma0 ellipsoid.
- Nguồn dự phòng: Sentinel-1 RTC do Catalyst xử lý, Microsoft Planetary Computer lưu trữ.
- Tìm cảnh mới nhất trong 30 ngày, chỉ băng VV ở chế độ IW, pixel spacing ≤25 m.
- Đọc các block COG cần thiết qua HTTP Range; không tải toàn cảnh vài GB.
- Đưa về lưới EPSG:4326 1024 × 1024 theo bbox ô, nội suy nearest-neighbour;
  giá trị không có dữ liệu được giữ trong kênh alpha.
- Chuyển gamma0 tuyến tính sang dB bằng `10 log10(x)` rồi ánh xạ cố định
  khoảng [-25,+5] dB sang [0,255]. Không tự tăng tương phản theo từng ảnh.
- RTC đã hiệu chỉnh địa hình, không đồng nhất với gamma0 ellipsoid. Phiên bản
  xử lý và nguồn được lưu riêng trong từng manifest và mã chính sách inference.
- Giữ model hiện có, ngưỡng 0,35 và mask đất liền +500 m gần bờ. Không thay
  weights, không tuyên bố mô hình đã được kiểm định độ chính xác trên RTC.

Mỗi ô có mã cảnh, URL STAC, URL asset **không có SAS token**, thời gian chụp
chính xác, hash ảnh/weights, tỷ lệ pixel hợp lệ và mô tả phép chuyển đổi. Token
ngắn hạn chỉ nằm trong bộ nhớ. Nếu kho yêu cầu tài khoản hoặc báo giới hạn,
worker dừng và giữ bằng chứng cũ; không tự đăng ký tài khoản, mua dịch vụ hoặc
chuyển sang nguồn có thu phí. Khả năng tải ẩn danh cần kiểm tra mỗi lần chạy,
không phải cam kết nguồn sẽ luôn miễn phí hay không giới hạn.

## Kiểm thử và vận hành

Workflow `probe-rtc-source.yml` đọc một ô thực, kiểm tra ảnh/tọa độ/mask, chạy
model hiện có và lưu artifact kiểm tra; **không công bố kết quả lên bản đồ**.
Sau khi lượt thử đạt, chạy `refresh-sentinel-mosaic.yml` với `max_updates=3`
để kiểm tra ghi checkpoint và xuất bản trước khi chạy hàng đợi bình thường.

Worker chính chỉ xử lý Việt Nam, chạy CPU trên GitHub Actions; một downloader
với prefetch=1 và một tiến trình nhận diện. Không chạy song song ghi báo cáo
trên Mac. Các workflow dùng chung khóa `sentinel-asset-refresh`.

Lỗi HTTP 403 đúng thông báo hết processing units được phân loại riêng với lỗi
quyền truy cập. Khi hết quota, dừng dùng Process API và thử nguồn RTC; lần
kiểm tra lại nguồn chính cách 24 giờ. Nếu nguồn dự phòng cũng bị chặn, dừng
cả hàng đợi, lưu trạng thái và nghỉ 24 giờ thay vì lặp lại cho từng ô.

Mỗi lượt có ngân sách 45 phút đọc/nhận diện, kiểm tra còn ít nhất 5 GiB trống,
lưu checkpoint sau từng ô. Artifact chỉ gồm file thay đổi trong lượt đó, không
upload lại toàn bộ kho ảnh. Mỗi ảnh mới phải vượt qua kiểm tra kích thước,
hash, tọa độ và dữ liệu phát hiện trước khi được tham chiếu trong report.

`assets/real_scan/refresh_status.json` chứa trạng thái và URL lượt chạy.
`ready` nghĩa là lượt chạy kết thúc bình thường, **không có nghĩa đã phủ kín**.
`coverage.json` vẫn phân biệt processed/pending/retry_later/no_observation.
Ảnh nền toàn cảnh cũ được giữ nếu nguồn chính không tạo được ảnh mới; không
đổi ngày chụp của ảnh cũ thành ngày chạy. Kết quả RTC ở ảnh chi tiết có thời
gian và nguồn riêng. Tích hợp nguồn thành công không chứng minh độ chính xác
nhận diện tàu; vẫn cần bộ nhãn thật độc lập để đánh giá.

## Tài liệu nguồn

- https://planetarycomputer.microsoft.com/api/stac/v1/collections/sentinel-1-rtc
- https://planetarycomputer.microsoft.com/docs/concepts/sas/
- https://rasterio.readthedocs.io/en/stable/topics/virtual-warping.html
- https://documentation.dataspace.copernicus.eu/Quotas.html
