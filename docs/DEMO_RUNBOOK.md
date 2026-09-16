# Kịch bản demo SonarNet‑VN trong 5 phút

Mục tiêu của demo là để người xem hiểu ngay một câu: **ảnh radar độc lập cho
biết nơi cần rà soát; hệ thống không tự kết luận tàu cá hay vi phạm**. Luôn
tách ba loại bằng chứng: ảnh Sentinel‑1 thật, ứng viên YOLO và lớp tham khảo
GFW. Các mốc ngày/giờ trong giao diện là thời gian dữ liệu, không phải thời
gian mô phỏng.

## Chuẩn bị

1. Mở <https://sonarnet.streamlit.app> và chờ trang tải xong.
2. Giữ mặc định **Khám phá → Xem ảnh toàn cảnh**. Bản đồ bắt đầu ở khung Việt
   Nam, lớp nền Esri và các lớp Sentinel‑1 đã kiểm tra được hiển thị sẵn.
3. Khi cần đi sâu, chuyển sang **Kiểm tra ảnh thật**. Hiện bộ bằng chứng YOLO
   công khai là lưới 12 ô ở ngoài khơi Bình Thuận, mỗi ô có ngày quan sát riêng;
   đây là vùng thử nghiệm, không phải tuyên bố phủ YOLO toàn quốc.

## Lời dẫn và thao tác

### 0:00–0:45 · Bài toán

Nói: “AIS chỉ cho biết phương tiện đang phát tín hiệu. Sentinel‑1 SAR là một
lớp quan sát độc lập, hoạt động cả ban đêm và khi nhiều mây. SonarNet dùng lớp
ảnh này để tìm **ứng viên** cần kiểm tra khi tín hiệu AIS không khớp hoặc không
có.”

Mở phần **Cách dùng** nếu hội đồng cần sơ đồ luồng. Không gọi “không có AIS” là
vi phạm.

### 0:45–2:00 · Ảnh thật và nguồn gốc

Trong **Xem ảnh toàn cảnh**, kéo bản đồ và bật/tắt lớp **Ảnh radar Sentinel‑1**.
Chọn một vùng có ảnh sẵn; chạm vào lớp ảnh để xem Copernicus, khoảng ghép,
mốc mới nhất trong catalog và thời điểm tạo asset. Giải thích rằng một mosaic
là nhiều lượt bay, nên ngày của từng pixel có thể khác nhau; giao diện không
được phép suy đoán ngày riêng nếu catalog không cung cấp.

Lớp **Tham khảo GFW** mặc định tắt. Khi bật, nói rõ đây là lớp độc lập để tham
khảo vùng có phát hiện SAR, không phải đầu ra YOLO và không phải danh sách tàu
duy nhất.

### 2:00–3:30 · YOLO và rà soát con người

Ngay trên ảnh toàn cảnh, bật **Hiện ứng viên YOLO** và chạm một điểm vàng.
Popup có ảnh radar cắt tại vị trí đó, nguồn và ngày ảnh. Viền xanh là phạm vi
đã quét ở độ phân giải chi tiết; không dùng mosaic thu nhỏ để nhận diện tàu.
**Hiện đối chiếu AIS minh hoạ** mô tả ba tình huống khớp, lệch và không có tín
hiệu. Các định danh bắt đầu bằng DEMO; không có AIS thì danh tính chưa xác định.
Đây là kịch bản thuyết trình, chưa phải kết quả ghép AIS thật.

Chuyển sang **Kiểm tra ảnh thật**, chọn một ô, mở một ứng viên và xem ảnh cắt.
Nói: “YOLO chỉ khoanh vùng điểm sáng giống tàu. Người dùng quyết định ứng viên
nào cần kiểm tra, đánh dấu ô, viết ghi chú và xuất gói bằng chứng.” Có thể lưu
đánh giá ứng viên (**Có khả năng là tàu** / **Nhiễu**) để màu điểm trên bản đồ
được cập nhật. Đây là nhãn rà soát của con người, không phải nhãn sự thật.

Gói ZIP gồm ảnh gốc, ảnh đánh dấu, HTML đọc/in, JSON và SHA‑256 để người khác
kiểm tra lại đúng asset. Hồ sơ phiên chỉ lưu trong trình duyệt hiện tại; tải
JSON nếu cần mở lại trên máy khác.

### 3:30–4:20 · Phần nghiên cứu

Mở **Nghiên cứu** chỉ khi cần giải thích phương pháp: mô phỏng đội tàu, ghép
radar–AIS, Kalman/Hungarian và ablation. Nhấn mạnh các mAP/F1 ở đây là kết quả
trên dữ liệu mô phỏng hoặc benchmark riêng; không gán chúng cho mosaic thật.

### 4:20–5:00 · Giới hạn và giá trị

Kết: “Bản demo đã nối được asset Sentinel‑1 thật và một quy trình rà soát có
bằng chứng. Ảnh vệ tinh không phải video trực tiếp: chỉ cập nhật khi có lượt
bay và Copernicus công bố sản phẩm. YOLO ảnh thật hiện là vùng thử nghiệm, chưa
được quảng bá như mô hình nghiệp vụ toàn quốc. Bước triển khai tiếp theo là
thu thập nhãn VV đại diện cho Việt Nam, đánh giá mù và chỉ khi đạt cổng chất
lượng mới thay mô hình công bố.”

## Câu hỏi thường gặp

**Dữ liệu nào là thật?** Lớp Sentinel‑1 trong Khám phá lấy từ Copernicus Data
Space. Bộ YOLO 12 ô là asset thật đã lưu, nhưng mô hình baseline được ghi rõ là
học từ ảnh mô phỏng và chưa được xác minh trên Việt Nam.

**GFW dùng để làm gì?** Là lớp tham khảo độc lập giúp đặt các phát hiện SAR vào
bối cảnh. SonarNet không dùng GFW làm nhãn train và không biến nó thành kết
luận vi phạm.

**Có phải hệ thống theo dõi mọi tàu theo thời gian thực?** Không. SAR quan sát
theo lần bay; AIS chỉ là nguồn bổ sung khi có quyền truy cập phù hợp.

**Vì sao ảnh không phủ kín?** Catalog Sentinel‑1 không có một ảnh đồng thời
toàn cầu. Mosaic chỉ ghép những cảnh đã tải được trong cửa sổ đã ghi; vùng
trống là chưa có pixel hợp lệ, không phải bằng chứng không có tàu.
