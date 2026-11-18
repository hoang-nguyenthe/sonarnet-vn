# Giữ nguyên cặp đề xuất khi kiểm tra chất lượng AIS

Gán theo khoảng cách trước, với phép gán Hungarian một-một. Cặp đã đề xuất phải qua giới hạn tuổi AIS, độ bất định, bán kính ghép và kiểm xem hai đầu có ứng viên cạnh tranh quá gần hay không. Nếu bị loại, giữ trạng thái thiếu dữ liệu hoặc chưa ghép theo lý do. Cổng không tự ghép sang tàu ở gần kế tiếp.

| Mẫu kiểm tra | Cổng lọc trước, biên 100 m | Giữ đề xuất, kiểm tra sau |
| --- | --- | --- |
| Hai ngày khảo sát, 7.121 điểm AIS giữ lại | 1.819 đúng, 31 sai, 5.271 từ chối | 1.806 đúng, 0 sai, 5.315 từ chối |
| Ngày 13/12 giữ riêng, 3.722 điểm | 898 đúng, 32 sai, 2.792 từ chối | 879 đúng, 0 sai, 2.843 từ chối |
| Cảnh SAR cùng giờ, 77 ứng viên, 4 mốc AIS | 9 đề xuất, 1/4 đồng thuận vị trí | 7 đề xuất, 1/4 đồng thuận vị trí |

Trên hai ngày khảo sát, cấu hình lọc trước gốc đổi đối tác so với đề xuất khoảng cách ở 72 điểm. Trong số đó 71 cặp khác mã AIS giữ lại. Cấu hình gốc có 75 ca sai tổng cộng. Trên cùng dữ liệu, giảm biên giúp giữ nhiều cặp đúng hơn nhưng làm tăng ca sai trong hai kịch bản lệch vị trí. Cấu hình được khóa trước ngày 13/12 vì giữ số ca sai bằng 0 trên cả hai tình huống lệch vị trí trong bộ mô phỏng trước đó. Số 0 chỉ là kết quả trong mẫu. Các vị trí kiểm tra đến từ cùng nguồn AIS với chuỗi đầu vào, còn phép thử có radar chỉ có bốn mốc vị trí gần và tách biệt.

Biên cấu hình sai lệch 100 m cộng tối đa 200 m vào khoảng cách tách biệt hai cặp vì hai khoảng cách có thể thay đổi ngược chiều. Chỉ cặp nằm trong ngưỡng ghép gốc mới được chấp nhận. Biên chưa hiệu chỉnh cho vùng biển Việt Nam.

## Tái lập

Dùng tệp AIS ngày 14/07, 01/10 và 13/12/2024 từ [NOAA Marine Cadastre](https://coast.noaa.gov/htdata/CMSP/AISDataHandler/2024/).

```sh
python scripts/evaluate_frozen_ais_assignment.py \
  --archives AIS_2024_07_14.zip AIS_2024_10_01.zip --output dev.json
python scripts/evaluate_frozen_ais_assignment.py \
  --archives AIS_2024_12_13.zip --held-out dev.json --output held_out.json
python -m pytest -q tests/test_fusion_quality_gates.py
```

Hai tệp JSON đã lưu ghi SHA-256, thống kê cổng gốc, tỷ lệ từ chối, số cặp bị đổi và kết quả theo mật độ. Chúng không chứa mã tàu hoặc vị trí bản tin.
