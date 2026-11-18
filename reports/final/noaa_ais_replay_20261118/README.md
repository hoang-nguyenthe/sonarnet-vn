# Đối chứng ghép bằng AIS lịch sử NOAA

## Kết quả

Hai ngày khảo sát có **7.121 điểm đối chiếu** qua 138 cửa sổ. Thuật toán khoảng cách ghép đúng 7.066 và sai 54. Cổng gốc khớp đúng 3.316, sai 75. Biên cạnh tranh 100 m khớp đúng 1.819, sai 31. Trong 3.920 điểm có điểm khác trong 250 m, biên 100 m khớp đúng 5, sai 5, từ chối 3.910.

Ngày 15/12 giữ riêng có **3.757 điểm** qua 69 cửa sổ. Kết quả cổng gốc là 1.651 đúng và 42 sai, biên 100 m là 847 đúng và 16 sai. Cách khoảng cách có 3.737 đúng, 20 sai. Không biên nào được chọn vì không có cấu hình giảm số ghép sai trên cả hai ngày khảo sát đồng thời mất không quá 5 điểm phần trăm số cặp ghép đúng ở từng ngày.

Ở các cửa sổ này, hầu hết mục tiêu có dữ liệu AIS khác quanh giờ chụp giả định. Các điểm đối chiếu lấy từ cùng hệ AIS với chuỗi đầu vào, không có sai lệch đăng ký vị trí của ảnh radar. Hiệu quả của đối chứng khoảng cách trong bài kiểm tra này chưa nói lên hiệu quả ghép SAR–AIS. Biên 100 m được giữ để minh họa tình huống lệch vị trí mô phỏng, chưa được hiệu chuẩn cho cảng đông tàu. Số điểm gồm nhiều lần quan sát lại cùng tàu trong ngày.

## Cách chạy

Tải ZIP theo ngày 14/07, 01/10 và 15/12/2024 từ [NOAA Marine Cadastre, dữ liệu AIS 2024](https://coast.noaa.gov/htdata/CMSP/AISDataHandler/2024/). Chương trình đọc trực tiếp thành viên CSV trong ZIP, kiểm CRC và ghi SHA-256. Mỗi cửa sổ 01:00 đến 23:00 UTC trong ba vùng được xác định bằng tọa độ trong tệp kết quả. Mỗi MMSI giữ một điểm gần nhất trong ±20 s. Mọi điểm trong ±20 s bị loại khỏi đầu vào; các điểm trong ±10 phút còn lại dùng để nội suy. Tách kết quả có tàu khác trong 250 m dựa trên vị trí đối chiếu giữ lại. Tất cả chính sách nhận cùng đầu vào, không đưa mã MMSI vào điểm truy vấn.

```sh
python scripts/evaluate_noaa_ais_replay.py --archives NOAA --output DEV
python scripts/evaluate_noaa_ais_replay.py --archives NOAA --output CONF \
  --confirmation DEV/results.json
```

`development/results.json` ghi bảng theo ngày, khu vực, giờ và nhóm khoảng cách. `confirmation/results.json` ghi checksum của báo cáo khảo sát và không chọn lại ngưỡng. Cả hai chỉ lưu số đếm và tham số, không chứa danh tính hoặc vị trí từng tàu.
