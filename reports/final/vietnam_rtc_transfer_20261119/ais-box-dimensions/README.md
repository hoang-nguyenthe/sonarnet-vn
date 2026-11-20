# Sai lệch tâm và kích thước hộp SAR trên dữ liệu AIS lịch sử

So sánh với 15 mốc AIS ít dịch chuyển được chọn trước trên sáu ngày chụp Sentinel-1 RTC ở các cảng Mỹ. Ở ngưỡng YOLO 0,35, ghép được 12 mốc trong 100 m. Trung vị lệch tâm là **41,1 m**. Trên 11 cặp có đủ metadata, sai số tuyệt đối trung bình của hai cạnh hộp lần lượt là **77,2 m** và **143,4 m**. [Kết quả từng cặp](results.json)

Chỉ đưa kích thước của mốc vào phép so khi có ít nhất hai giây quan sát với cùng cặp chiều dài và chiều rộng hợp lệ. Chấm vị trí một-một theo WGS84. Chiều dài và chiều rộng của metadata được so với cạnh lớn và cạnh nhỏ của hộp radar. Hướng tàu, vệt phản xạ, vị trí anten và độ trễ ảnh hưởng các sai số. Mẫu nhỏ đủ để nhận diện giới hạn của hộp SAR. Kích thước thân tàu cần nguồn xác nhận độc lập. [Metadata NOAA 2024](https://www.fisheries.noaa.gov/inport/item/73064)

Tái lập từ ảnh và bản tin gốc của [sáu cảnh đã khóa](../rank_fusion/ais-holdout/README.md). Dùng cùng checkpoint, bộ bờ GSHHG và môi trường YOLO CPU. Xem tùy chọn đường dẫn bằng `PYTHONPATH=src:scripts python scripts/evaluate_rtc_ais_dimensions.py --help`. Mã băm nguồn và quy tắc cố định nằm trong [giao thức chấm](protocol.json).
