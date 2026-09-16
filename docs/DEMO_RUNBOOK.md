# Kịch bản demo SonarNet VN trong 5 phút

Mục tiêu của phần demo là chứng minh ba điều: hệ thống có kiến trúc hợp lý,
chạy được toàn tuyến và đã kết nối được ảnh Sentinel 1 thật. Không trình bày
kết quả mô phỏng như kết quả trên dữ liệu thật.

## Chuẩn bị trước khi mở đầu

1. Mở https://sonarnet.streamlit.app và kiểm tra trang tải xong.
2. Mở tab **Sentinel 1 thật** ở cuối thanh tab. Cảnh GRD đã đóng gói sẵn phải
   hiển thị kể cả khi bản Streamlit Cloud chưa cài secrets.
3. Chuẩn bị liên kết GitHub để Hội đồng xem mã nguồn và lịch sử commit.

## Lời dẫn và thao tác

### 0:00 đến 0:40 Bài toán

Nói: “AIS cho biết vị trí các tàu đang phát tín hiệu. Nhưng AIS không giải thích
được các vật thể xuất hiện trên mặt biển mà không có tín hiệu tương ứng.
SonarNet VN dùng Sentinel 1 SAR như một lớp quan sát độc lập để đối chiếu với
AIS.”

Mở tab **Mô phỏng hoạt động**. Nêu rõ đây là mô phỏng đội tàu, dùng để minh hoạ
luồng dữ liệu và các trạng thái hệ thống.

### 0:40 đến 1:30 Phát hiện và hợp nhất

Mở tab **Phát hiện trên ảnh radar**. Chọn một cảnh, bật dự báo YOLO và ground
truth. Chuyển sang **Hợp nhất radar AIS**. Giải thích ba trạng thái: AIS khớp,
AIS sai lệch và không có AIS. Không gọi trạng thái không AIS là hành vi vi phạm.

### 1:30 đến 2:10 Lý do dùng Kalman và Hungarian

Mở tab **Nội suy quỹ đạo**. Chỉ vào biểu đồ Kalman RTS so với nội suy tuyến
tính và bảng ablation. Nói rằng Kalman ước lượng vị trí AIS tại đúng thời điểm
vệ tinh chụp; Hungarian đảm bảo ghép cặp một tàu với một quan sát.

### 2:10 đến 3:00 Dữ liệu Sentinel 1 thật

Mở tab **Sentinel 1 thật**. Chỉ vào ảnh GRD thật ngoài khơi Bình Thuận, thời
điểm chụp và mã sản phẩm Copernicus. Nói: “Đây là cảnh thật lấy qua Catalog API
và Process API. Chúng tôi chưa báo cáo mAP trên cảnh này vì chưa có nhãn độc lập
đủ chất lượng.” Nếu secrets backend đã cài, bấm tìm ảnh mới và tải ảnh VV.

### 3:00 đến 4:00 Kiểm chứng độc lập

Nói: “Mô hình được huấn luyện trên các bộ dữ liệu SAR công khai. Khi đánh giá
cảnh thật, chúng tôi dùng GFW SAR Vessel Detections như nguồn đối chiếu ngoài hệ
thống, không dùng chúng làm nhãn huấn luyện. Điều này giảm nguy cơ mô hình chỉ
học lại đầu ra của một hệ thống có sẵn.”

### 4:00 đến 5:00 Giới hạn và giá trị

Nói: “SonarNet VN là giám sát vệ tinh gần thời gian thực. Sentinel 1 chỉ quan
sát khi vệ tinh bay qua, vì vậy hệ thống không thay thế AIS hoặc radar bờ. Giá
trị của nó là chỉ ra phần chênh lệch giữa tín hiệu tự khai báo và quan sát SAR,
để cơ quan có thẩm quyền kiểm chứng thêm.”

Kết bằng việc mở GitHub và nhắc rằng credentials không nằm trong mã nguồn, còn
mọi dữ liệu và công cụ AI được kê khai trong hồ sơ.

## Câu trả lời ngắn cho phản biện thường gặp

**Có phải dữ liệu thật không?** Tab Sentinel 1 thật dùng cảnh GRD thật từ
Copernicus. Các chỉ tiêu mAP và F1 hiện công bố là trên dữ liệu mô phỏng có đối
chứng, được ghi rõ trong app và hồ sơ.

**Có theo dõi mọi tàu thời gian thực không?** Không. SAR cho quan sát theo lần
bay qua; AIS có thể cập nhật thường xuyên hơn khi có nguồn phù hợp. Hệ thống hợp
nhất hai lớp thay vì thay thế một lớp bằng lớp kia.

**Không có AIS có đồng nghĩa vi phạm không?** Không. Đây chỉ là tín hiệu cần rà
soát; mất tín hiệu có thể có nhiều nguyên nhân.

**Sao không dùng GFW để train luôn?** Vì GFW SAR detections là đầu ra của một
hệ thống phát hiện khác. Dùng chúng làm nhãn train và test sẽ làm giảm tính độc
lập của đánh giá.
