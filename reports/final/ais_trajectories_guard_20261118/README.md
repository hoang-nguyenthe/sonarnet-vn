# Ghép AIS với chuỗi bản tin có sai lệch vị trí

Các thử nghiệm trước đặt trực tiếp tuổi và độ bất định của từng ước tính AIS. Lượt này tạo bản tin có timestamp, nhiễu và khoảng trống, rồi chạy **nội suy Kalman của SonarNet** để có vị trí tại giờ chụp. Sau đó đối chiếu ba phương pháp nhận cùng đầu vào. Tất cả bản tin và nhãn đều mô phỏng.

- 7 tình huống × 120 lần = **840 kịch bản**. Có 3.360 điểm gắn mục tiêu và 120 điểm nhiễu gần một mục tiêu. Seed `20261121`; lượt phát hiện lỗi trước đó dùng seed `20261119` và biên lệch cố định 160 m.
- Trong tình huống lệch 128–185 m, hai chuỗi lân cận bị dịch theo hướng ngược nhau. Cổng cũ ghép nhầm 240 lần. Sau khi kiểm tra ứng viên cạnh tranh, có 0 lần ghép sai trong tình huống này và vẫn giữ 120 cặp đúng ở ngoài cặp bị dịch.
- Khi lệch 208–242 m, số ghép sai giảm 240 → 130. Chuỗi lệch lớn có thể vẫn trông rất nhất quán qua thời gian. Bản ghi này giữ kết quả đó để tránh suy rộng rằng có thể xác nhận danh tính từ vị trí.
- Toàn bộ phép thử, số ghép đúng giảm 1.357 → 1.306. Nhóm hai tàu đã tách sau giao nhau giữ 245 cặp đúng so với 251 trước đó. Mức thận trọng làm tăng khối lượng rà soát.

## Quy tắc kiểm tra cạnh tranh

1. Giữ cổng gốc cho tuổi bản tin, độ bất định và khoảng cách chấp nhận.
2. Để phát hiện cạnh tranh, xét thêm ứng viên có khoảng cách nằm trong cổng gốc cộng 100 m, với trần 500 m. Nếu ứng viên này có thể thay đổi thứ tự khi hai sai số khoảng cách biến thiên, trả về trạng thái chưa ghép. Sai số của một khoảng cách có thể tăng tối đa 100 m trong phép thử độ nhạy, trong khi khoảng cách kia có thể giảm tối đa 100 m.
3. Chỉ cặp qua cổng ban đầu mới được thuật toán ghép. Việc ghép vị trí vẫn chờ người có chuyên môn kiểm tra.

Biên 100 m là cấu hình nghiên cứu, cần hiệu chỉnh trên AIS được cấp phép và ảnh có mốc chụp đồng bộ. Các kết quả trên bao gồm tình huống thiết kế để bộc lộ lỗi, nên không đại diện tần suất ngoài thực địa.

```sh
python scripts/evaluate_ais_trajectories.py --output MOT_THU_MUC_MOI
python -m pytest -q tests/test_fusion_quality_gates.py
```

`summary.csv` cho phép đối chiếu toàn bộ nhóm. `cases.json.gz` chứa vị trí đúng trong mô phỏng, từng bản tin đầu vào, độ bất định sau làm trơn và kết quả từng phương pháp. Bảng đếm của bộ 600 kịch bản cũ giữ nguyên sau khi chạy lại bằng cổng mới.
