# Kiểm tra ghép AIS có cơ chế từ chối

Dữ liệu mô phỏng có chủ đích, 100 lần mỗi tình huống, 2 ứng viên/lần. Cùng đầu vào cho baseline khoảng cách (500 m) và phương pháp mới. Không dùng kết quả này làm độ chính xác trên AIS thực địa.

| Tình huống | Phương pháp | Ghép đúng danh tính | Ghép sai danh tính | Từ chối | Ghép dù dữ liệu không đủ an toàn |
|---|---|---:|---:|---:|---:|
| fresh_separated | distance_only | 200 | 0 | 0 | 0 |
| fresh_separated | quality_gated | 200 | 0 | 0 | 0 |
| crossing_ambiguous | distance_only | 122 | 78 | 0 | 200 |
| crossing_ambiguous | quality_gated | 0 | 0 | 200 | 0 |
| noisy_ais | distance_only | 152 | 25 | 23 | 177 |
| noisy_ais | quality_gated | 0 | 0 | 200 | 0 |
| stale_ais | distance_only | 200 | 0 | 0 | 200 |
| stale_ais | quality_gated | 0 | 0 | 200 | 0 |
| missing_ais | distance_only | 0 | 0 | 200 | 0 |
| missing_ais | quality_gated | 0 | 0 | 200 | 0 |
| unknown_sigma | distance_only | 200 | 0 | 0 | 200 |
| unknown_sigma | quality_gated | 0 | 0 | 200 | 0 |

Đúng danh tính là so với nhãn mô phỏng. Ghép tình cờ đúng nhưng quá cũ/nhiễu/cắt nhau vẫn tính là ghép không đủ an toàn. Từ chối có đánh đổi giảm số ghép, cần chuyên viên kiểm tra.

Ngưỡng nghiên cứu mặc định: tuổi ≤180 giây, sigma vị trí ≤150 m, khoảng cách ≤min(500 m, 3 × sqrt(sigma_AIS² + 30²)). Từ chối khi hai ứng viên cạnh tranh có chênh khoảng cách ≤max(30 m, sigma kết hợp). Chưa hiệu chỉnh trên AIS thực địa.

Lệnh tái hiện: `python scripts/evaluate_ais_matching.py --output reports/final/ais_matching`
Kiểm thử: `python -m unittest discover -s tests -p test_fusion_quality_gates.py`

CSV giữ bảng đếm; cases.json giữ 600 ca, lý do và khoảng cách ghép. Độ bất định đầu vào trong stress test được điều khiển rõ ràng. Test riêng trong unittest kiểm tra Kalman tăng sigma khi quỹ đạo nhiễu.