# Kiểm chứng mô-đun hành vi · Chặng 2

## Chạy và tái lập

Từ thư mục gốc của kho SonarNet, dùng Python, NumPy, SciPy, scikit-learn và XGBoost từ `requirements-full.txt`. Phiên bản thực tế lưu ở `results.json`. Mã được chạy với một luồng OpenMP và BLAS trên máy Mac.

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONPATH=src:scripts python3 scripts/evaluate_chang2.py
python3 scripts/score_chang2_study.py --cases reports/final/chang2/study-cases.json --output reports/final/chang2/study-summary.json DUONG_DAN_PHIEU_1.json DUONG_DAN_PHIEU_2.json
```

Có thể bỏ hai tên phiếu để sinh báo cáo **0 người tham gia**. Cần dùng đúng tệp `study-cases.json` đã công bố khi chấm phiếu. Các runtime XGBoost khác có thể cho dự đoán khác ở một số điểm nên ngân hàng bài thử chính thức được ghim theo SHA-256. Tải báo cáo, bài thử và ZIP từ [trang Chặng 2](https://hoang-nguyenthe.github.io/sonarnet-vn/chang2/).

## Đối chứng 2 × 2 ghép AIS

- Bốn cấu hình giữ ảnh giả lập, điểm AIS, ngưỡng và thuật toán ghép cố định. Bật/tắt Kalman so với nội suy tuyến tính. Bật/tắt bước kích thước sau ghép. Khi tắt kiểm kích thước, ghép thành công được ghi trạng thái đủ để qua bước này, giới hạn từ chối ghép vẫn được giữ.
- Năm seed 101, 203, 307, 409, 503. Mỗi seed chạy 60 cảnh cho từng kịch bản, bốn mục tiêu mỗi cảnh. Tổng 1.200 cảnh và 4.800 mục tiêu mỗi cấu hình. Kịch bản gồm AIS hỗn hợp, tàu cắt nhau, lệch hệ thống và nhiễu kích thước radar.
- Tỉ lệ và khoảng cách sinh theo mô phỏng, không phải phân phối thực địa. Kịch bản nhiễu mạnh giữ thiết lập AIS của nhóm hỗn hợp và thay độ lệch chuẩn của chiều dài SAR từ 9% lên 33%. Chọn mâu thuẫn độc lập với chiều dài thật, nhân 2,25 ở chiều dài khai báo. Mâu thuẫn được đo điều kiện trên cặp ghép đúng để tách lỗi ghép khỏi lỗi kích thước.
- Số cặp đúng/sai/từ chối có tổng bằng số mục tiêu. Số mâu thuẫn đúng và số bỏ sót cộng ra số cặp ghép đúng có mâu thuẫn. Một trạng thái mâu thuẫn chỉ là cờ để rà tiếp.

## Đối chứng mô-đun hành vi

- Mỗi seed sinh riêng 400 quỹ đạo học và 240 quỹ đạo chấm, bằng các luồng RNG tách. Tỉ lệ lớp cân bằng. Không dùng định danh, toạ độ tuyệt đối hoặc nhãn làm đặc trưng. Dùng XGBoost cho tất cả phương án, cùng cấu hình mô hình gốc.
- Năm cách học gồm chỉ SOG gần nhất với 400 mẫu, lịch sử sạch với 48 mẫu hoặc 400 mẫu, lịch sử có nhiễu với cùng 400 mẫu, và 800 hàng bao gồm bản gốc và bản nhiễu của 400 quỹ đạo học. So sánh ở cùng 400 hàng giúp cô lập ảnh hưởng của phân phối huấn luyện. Không dò siêu tham số theo tập chấm.
- Quỹ đạo chấm dùng lại đúng các quỹ đạo tiềm ẩn theo từng điều kiện. Các điều kiện gồm dữ liệu đủ, mất ngẫu nhiên khoảng 60% bản tin, cửa sổ ngắn có nhiễu và kịch bản chồng lấn. Cửa sổ ngắn trích 9–19 mốc trước khi loại ngẫu nhiên và giữ ít nhất 5. Trong kịch bản chồng lấn, thay đổi kênh SOG bằng hệ số và độ lệch mỗi quỹ đạo. Vị trí và hướng nhận nhiễu riêng. Điều này mô phỏng kênh quan sát thiếu nhất quán, không tái tạo quy trình đo của một hệ AIS cụ thể.
- Xem macro-F1 trung bình ± độ lệch chuẩn giữa 5 seed, số điểm theo lớp và ma trận nhầm lẫn trong `results.json`. Sai số ưu tiên rà là một phép quy đổi từ bốn lớp thành hai nhóm, trong đó câu và kéo lưới thuộc nhóm cần rà. Nhãn “cần rà” là quy ước của bài thử.

## Khảo sát người rà

- Chọn chuyên viên hàng hải, thủy sản, giám sát tàu hoặc phân tích SAR/AIS. Mã R01–R04 luân phiên thứ tự và điều kiện. Nếu có hai chuyên viên đầu tiên, ưu tiên R01 và R03. Nhóm sinh viên hoặc thành viên đội báo riêng nếu tham gia.
- Hai lượt có cùng 8 ca mỗi lượt, mỗi lượt gồm hai ca mỗi lớp và bốn ca dương tính theo nhãn mô phỏng. Cả hai lượt có cùng loại đồ thị kiểm tra. Lượt có AI thêm gợi ý từ mô hình huấn luyện với 800 hàng của seed 101, chạy trên quỹ đạo mô phỏng độc lập. Ba gợi ý không khớp nhãn ưu tiên theo thiết kế để có thể quan sát lỗi theo gợi ý. Đây là bộ ca đối chứng có chủ đích, không dùng để ước lượng tần suất sai trên toàn bộ luồng hoạt động.
- Mỗi ca có ba lựa chọn. Ca dương được đánh dấu chưa ưu tiên hoặc chưa đủ dữ liệu đều tính là bỏ sót. Ca âm được đánh dấu ưu tiên là cờ nhầm. Tính trung vị thời gian cho mỗi người và mỗi điều kiện, sau đó tính chênh theo cặp. Khi người dùng đổi tab, thời gian của ca đó bị loại và lựa chọn vẫn được giữ. Thời gian nghỉ giữa hai lượt không tính.
- Bài thử ghi phiếu trong trình duyệt và người tham gia tải JSON. Không cần tên hoặc thông tin định danh. Nhóm chuyên môn khai trong phiếu. Chỉ tổng hợp phiếu thực tế có đồng ý và đủ 16 ca. Kiểm thử trình duyệt dùng tệp đánh dấu riêng và bị loại khỏi kết quả nộp.
- Giới hạn gồm cỡ mẫu, độ khó khác nhau giữa các ca, hiệu ứng thứ tự và thiếu nhãn hành vi ngoài thực địa. Kết quả người tham gia chỉ áp dụng cho bộ ca và điều kiện đo này.

## Kê khai AI

OpenAI Codex hỗ trợ viết công cụ chạy đối chứng, bài thử trên web, kiểm thử và trình bày báo cáo. Chỉ số lấy từ mã chạy và phiếu thu thực tế. Tái sử dụng trình sinh hành vi, bộ trích đặc trưng, Kalman, ghép AIS và XGBoost của SonarNet. Không dùng AI để tạo phiếu chuyên viên.
