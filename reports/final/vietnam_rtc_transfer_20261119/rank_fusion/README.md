# Xếp hạng theo độ đồng thuận giữa YOLO và xView3

Giữ đúng số ứng viên cần rà của từng lượt chụp. Chấm ghép một–một theo khoảng cách WGS84 ở 50, 100 và 150 m. Bảng dưới dùng 100 m.

| Tập chấm | Lượt rà | Phương án đã công bố | Gộp thứ hạng | Gộp thứ hạng, giữ đầu danh sách |
| --- | ---: | ---: | ---: | ---: |
| 12 lượt ven biển Việt Nam | 116 | 82/152 | 80/152 | 81/152 |
| 12 lượt ven biển Việt Nam | 191 | 103/152 | 105/152 | 106/152 |
| 2 lượt Bắc Trung Bộ | 6 | 5/8 | 5/8 | 5/8 |
| 2 lượt Bắc Trung Bộ | 10 | 8/8 | 7/8 | 8/8 |

Mỗi mô hình có một thứ hạng riêng cho các điểm của mình. Khi hai tâm cách nhau không quá 35 m, mỗi mô hình đóng góp tối đa một hạng cho điểm đó. Cách gộp dùng tổng nghịch đảo theo thứ hạng. Xếp hạng từ điểm radar là phần điều chỉnh theo bài toán SonarNet. [Bài báo gốc về Reciprocal Rank Fusion](https://doi.org/10.1145/1571941.1572114)

So sánh gộp thứ hạng khóa lựa chọn trên 5 lượt phát triển, tách ngày khỏi 12 và 2 lượt trong bảng. Cấu hình giữ đầu danh sách được thiết kế sau khi đọc kết quả gộp thứ hạng trên các tập này. Đó là thử nghiệm thăm dò trên ảnh đã dùng, cần xác nhận bằng ngày chụp mới trước khi dùng mặc định. Quy tắc giữ ít nhất khoảng 75% đầu danh sách, có thể thay 1 mục ở một danh sách ngắn. Số liệu giữ đầu danh sách giảm ở mức rà 116 và tăng ở mức 191.

Tại 191 lượt rà, giới hạn trên của tập ứng viên đã có là 119/152. Giới hạn này giả định biết trước nhãn và không phải một danh sách có thể triển khai. Kết quả chính của phiên bản đang công bố là 103/152 ở mức này.

[Phép kiểm trên sáu ngày chụp giữ riêng](ais-holdout/README.md) đạt 14/15 mốc AIS ở cùng 409 lượt rà, từ 12/15. Bảng trên dùng nhãn Ai2 ở Việt Nam. Phép kiểm mới dùng mốc AIS ít dịch chuyển ở các cảng Mỹ.

## Chấm lại

Từ thư mục mã nguồn hoặc thư mục SonarNet trong ZIP, chạy với NumPy, SciPy và pyproj.

```sh
python scripts/evaluate_rtc_rank_fusion.py --output /tmp/sonarnet-rank-replay
```

`candidates.json.gz` chỉ lưu điểm tham chiếu, điểm đề xuất, giới hạn rà và mã hash của các cache đã dùng. Phép tính kiểm lại từng danh sách công bố từ tọa độ trước khi so sánh. `results.json` có số liệu theo cảnh và bán kính. `review-queues.json` lưu các danh sách để chấm độc lập bằng bộ ghép Hungarian. Tệp thời điểm chạy có thể khác khi tái lập.

Các ảnh và nhãn là dữ liệu Sentinel-1 RTC và Ai2 từ [đối chứng xView3 trước](../README.md). Sáu cảnh AIS lịch sử là phép kiểm riêng.
