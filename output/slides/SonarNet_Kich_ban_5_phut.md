# Kịch bản SonarNet - mục tiêu khoảng 5 phút

Tổng mốc dự kiến: 300 giây. Thời lượng phụ thuộc tốc độ nói và thao tác, cần bấm giờ tập trước. Mốc gồm khoảng 10 giây chuyển tình huống ở slide 10.

## Slide 1 | 0:00 - 0:24

Kính thưa ban giám khảo, trên màn hình là ảnh radar thật. Những điểm sáng có thể gợi ý mục tiêu, nhưng một điểm sáng chưa đủ để gọi tên một con tàu. SonarNet được xây dựng để giúp người phân tích đi tiếp từ quan sát đó: tìm đúng ảnh nguồn, kiểm tra thời điểm, đối chiếu dữ liệu vị trí và giữ lại căn cứ cho từng nhận xét. Trong chặng cải tiến, em tập trung vào một câu hỏi: khi dữ liệu chưa chắc chắn, hệ thống phải thể hiện điều đó như thế nào?

## Slide 2 | 0:24 - 0:47

Một người xem có thể thấy cùng một điểm sáng và đưa ra những suy luận khác nhau. Nó có thể nằm gần bờ, trong cụm mục tiêu, hoặc không có bản tin AIS phù hợp thời điểm chụp. Vì vậy, nếu phần mềm gắn một nhãn quá mạnh, người sử dụng có thể hiểu dữ liệu thiếu thành một hành vi vi phạm. Cải tiến đầu tiên của SonarNet là sửa ngay cách hệ thống diễn đạt kết quả, để mức độ chắc chắn luôn đi cùng bằng chứng đang có.

## Slide 3 | 0:47 - 1:10

Quy trình gồm bốn bước. Đầu tiên, ảnh có nguồn và ngày chụp cụ thể. Tiếp theo, mô hình đưa ra điểm cần kiểm tra. Khi có dữ liệu AIS phù hợp, thuật toán xét cả thời gian và độ bất định vị trí để ghép. Cuối cùng, người rà soát mở bằng chứng, ghi căn cứ và xác nhận đánh giá. JSON và báo cáo HTML giữ cùng trạng thái với giao diện. Khi ảnh hoặc mô hình thay đổi, xác nhận cũ không tự áp dụng cho kết quả mới.

## Slide 4 | 1:10 - 1:33

Bốn trạng thái này giải quyết trực tiếp yêu cầu của ban giám khảo. Thiếu dữ liệu là khi không có đủ thông tin để đối chiếu. Không ghép được là khi chưa chọn được cặp phù hợp. Nếu kích thước khác nhau, hệ thống báo đang xác minh, thay vì kết luận khai báo sai. Ngay cả khi ghép được vị trí, danh tính và tính hợp pháp vẫn chưa được xác nhận. Cách phân biệt này xuất hiện đồng nhất trong thuật toán, giao diện và hồ sơ xuất ra.

## Slide 5 | 1:33 - 1:57

Một cặp ở gần nhau chưa chắc là một cặp đáng tin. SonarNet kiểm tra AIS có cách thời điểm chụp quá một trăm tám mươi giây hay không và độ bất định vị trí có vượt một trăm năm mươi mét hay không. Ngưỡng khoảng cách là giá trị nhỏ hơn giữa năm trăm mét và ba lần độ bất định kết hợp. Nếu hai ứng viên gần như ngang nhau, hệ thống từ chối chọn. Đây là ngưỡng nghiên cứu mặc định, còn cần hiệu chỉnh với AIS thực địa.

## Slide 6 | 1:57 - 2:24

Để kiểm tra cơ chế này, em chạy sáu trăm kịch bản, tổng cộng một nghìn hai trăm điểm SAR mô phỏng. Khi AIS mới và các tàu tách biệt, cả hai phương pháp ghép đúng hai trăm điểm. Ở tình huống giao nhau, baseline chỉ dùng khoảng cách ghép sai bảy mươi tám điểm. Phương pháp mới từ chối cả hai trăm điểm mơ hồ. Kết quả có lợi về độ thận trọng nhưng làm giảm độ phủ. Vì thế em công bố cả số từ chối, và không gọi đây là độ chính xác một trăm phần trăm ngoài thực địa.

## Slide 7 | 2:24 - 2:50

Phần thứ ba là đánh giá trên ảnh SAR thật. Do checkpoint cũ đã bị xóa, em huấn luyện lại từ trọng số nền YOLO11n. Bộ chia được xác định trước huấn luyện: ba nghìn bốn trăm chín mươi mốt ảnh train, năm trăm chín mươi bốn ảnh validation và ba nghìn ảnh test. Em loại các cảnh gần nhóm vùng kiểm thử, kiểm tra ngày chụp và cách ly thêm một trăm mười lăm ảnh tương tự qua các tập. Checkpoint và ngưỡng đều chọn bằng validation, không chọn theo test.

## Slide 8 | 2:50 - 3:17

Trên ba nghìn ảnh test, mô hình đạt precision sáu mươi chín phẩy hai mươi lăm phần trăm và recall sáu mươi ba phẩy năm mươi bốn phần trăm. AP năm mươi là không phẩy sáu sáu một tám. Nhưng biểu đồ cho thấy khả năng phát hiện giảm rõ ở nhóm ảnh có đất liền, chỉ còn hai mươi bảy phẩy tám mươi sáu phần trăm. Em giữ kết quả này ngay trên slide vì nó quyết định phạm vi sử dụng của sản phẩm. Không có phát hiện không có nghĩa là vùng biển không có tàu.

## Slide 9 | 3:17 - 3:40

Hai ảnh này được chọn tự động theo số lỗi, không chọn để làm đẹp kết quả. Ảnh bên trái có mười hai báo nhầm. Ảnh bên phải có ba mươi bảy nhãn bị bỏ sót. Cần rà soát mục tiêu nhỏ, vùng bờ và cụm tàu, đồng thời xem lại chất lượng nhãn. Đó là các hướng cần thử trên validation, chưa phải nguyên nhân đã được chứng minh. Những thay đổi sau khi xem test phải được ghi rõ là nghiên cứu tiếp nối.

## Slide 10 | 3:40 - 4:15

Bây giờ em mở mục Minh chứng cải tiến. Với kịch bản thiếu AIS, hệ thống giữ trạng thái thiếu dữ liệu. Khi chuyển sang kích thước mâu thuẫn, kết quả chuyển sang đang xác minh. Cả hai trường hợp đều ghi rõ đây là dữ liệu mô phỏng. Người dùng có thể tải JSON để kiểm tra trạng thái và điều kiện ghép. [Thao tác trực tiếp: chọn hai tình huống, giữ bảng kết quả khoảng năm giây mỗi trường hợp. Nếu không có mạng, dùng bản chạy localhost hoặc giữ slide và đọc kết quả đã kiểm thử.]

## Slide 11 | 4:15 - 4:37

Ba giới hạn cần nói rõ. Thứ nhất, em chưa quy đổi sai số pixel sang mét khi thiếu metadata của đúng ảnh sau xử lý. Thứ hai, kết quả ghép AIS hiện là mô phỏng, cần nguồn thực địa được cấp phép để kiểm chứng. Thứ ba, tên người rà soát trong bản thử nghiệm còn tự khai. Em không dùng các phần chưa đủ bằng chứng để tuyên bố hệ thống đã sẵn sàng đưa ra kết luận nghiệp vụ. Báo cáo có checklist riêng cho từng mục còn mở.

## Slide 12 | 4:37 - 5:00

Giá trị SonarNet hướng tới là giúp người phân tích kiểm tra một quan sát đến tận nguồn của nó. Chặng cải tiến đã bổ sung cơ chế từ chối khi dữ liệu chưa đủ, đồng bộ trạng thái với hồ sơ, và tạo được một lượt đánh giá SAR có thể tái hiện. Em cũng giữ rõ các điểm yếu để quyết định bước nghiên cứu tiếp theo. Với SonarNet, mỗi dấu chấm cần có căn cứ đi cùng, và mỗi kết luận cần có người chịu trách nhiệm xác minh. Em xin cảm ơn ban giám khảo.


## Chuẩn bị demo

Mở sẵn mục Minh chứng cải tiến. Kiểm tra hai tình huống trước khi trình bày. Giữ một bản JSON xuất sẵn. Không gõ thông tin chuyên viên giả hoặc gọi mô phỏng là kết quả thực địa. Nếu demo trục trặc quá 5 giây, quay lại slide và tiếp tục.
