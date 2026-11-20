# Gộp thứ hạng trên sáu ngày chụp giữ riêng

Ở cùng **409 lượt rà**, bộ xếp hạng theo đồng thuận YOLO và xView3 khớp **14/15** mốc, từ **12/15** với cấu hình đã công bố. Hai mốc tăng thêm nằm trên hai lượt chụp khác nhau tại Galveston và Houston Ship Channel. Ở mức 1.530 lượt rà, cả ba cách đều khớp đủ 15 mốc trong bán kính 100 m.

| Bán kính | Lượt rà | Cấu hình đã công bố | Gộp thứ hạng | Gộp thứ hạng và giữ đầu danh sách |
| ---: | ---: | ---: | ---: | ---: |
| 50 m | 409 | 8/15 | 10/15 | 10/15 |
| **100 m** | **409** | **12/15** | **14/15** | **14/15** |
| 150 m | 409 | 13/15 | 14/15 | 14/15 |
| 50 m | 1.530 | 15/15 | 14/15 | 15/15 |
| **100 m** | **1.530** | **15/15** | **15/15** | **15/15** |
| 150 m | 1.530 | 15/15 | 15/15 | 15/15 |

## Ảnh và mốc tham chiếu

- Hai cảnh ở mỗi vùng Los Angeles và Long Beach, Galveston và Houston Ship Channel, cảng New York. Sáu ngày UTC tách hoàn toàn khỏi các cảnh AIS đã chấm trước. Lấy lần lượt cảnh chưa dùng có độ phủ danh mục từ 99,9%, theo đúng thứ tự trong [danh mục](catalogue-screen.json) và [kế hoạch đã khóa](schedule.json).
- Cả 32 ô ảnh VV có phủ hợp lệ. VV và VH dùng cùng khung ảnh. [Kết quả theo cảnh](results.json) ghi độ phủ hai kênh và mã băm của tệp nguồn. [Danh mục Sentinel-1 RTC](https://planetarycomputer.microsoft.com/dataset/sentinel-1-rtc)
- Khóa 15 mốc AIS ít dịch chuyển, cách biệt, trong vùng phủ hợp lệ trước khi chạy nhận dạng. Cảng New York ngày 20/09/2024 có 0 mốc đạt điều kiện và giữ đủ lượt rà trong tổng. [Mốc tham chiếu và nguồn theo ngày](references.json) · [Dữ liệu AIS NOAA](https://marinecadastre.gov/ais/)

## Cách chấm

Mỗi cách dùng đúng số ứng viên cần rà của từng cảnh ở hai ngưỡng YOLO 0,35 và 0,05. Ở ngưỡng 0,35, cấu hình đã công bố dùng YOLO với lọc trùng 35 m. Ở ngưỡng 0,05, cấu hình đã công bố kết hợp YOLO ảnh gốc, YOLO ô chồng lấn và xView3. Cách gộp thứ hạng và cách giữ phần đầu danh sách dùng các quy tắc đã công bố trước phép thử này. Ghép một–một theo khoảng cách WGS84, với 100 m là bán kính chính. Đã đối chiếu lại 144 tổ hợp cảnh, phương án và bán kính bằng phép ghép đồ thị độc lập. [Quy tắc gộp](../README.md) · [Phiên bản và mã băm](protocol.json)

Kết quả đo khả năng khớp với nhóm mốc AIS được chọn ở cảng Mỹ. Đây là nhóm nhỏ và khác cả về vùng lẫn loại tham chiếu so với nhãn Ai2 ven biển Việt Nam. Trên tập Việt Nam, phương án giữ đầu danh sách vẫn giảm từ 82/152 xuống 81/152 ở mức 116 lượt rà. Cần thêm cảnh Việt Nam giữ riêng để xác nhận hiệu quả ở mức rà nhỏ trước khi áp dụng lên bản đồ.

## Tái lập

[candidates.json.gz](candidates.json.gz) chứa các điểm ứng viên và mốc dùng để chấm lại, gồm tọa độ, điểm xếp hạng, ngân sách rà và mã cảnh. [review-queues.json](review-queues.json) lưu từng danh sách đã rà. Mã MMSI nằm trong kho nguồn NOAA, các tệp kết quả chỉ dùng tọa độ mốc.

Từ thư mục gốc của dự án, dùng NumPy, SciPy và pyproj để chạy lại bước gộp và chấm.

```sh
PYTHONPATH=scripts python - <<'PY'
import gzip
import json
from pathlib import Path
from evaluate_rtc_rank_fusion import score, totals

source = Path("reports/final/vietnam_rtc_transfer_20261119/rank_fusion/ais-holdout")
with gzip.open(source / "candidates.json.gz", "rt") as archive:
    scenes, queues = score(json.load(archive))
expected = json.loads((source / "results.json").read_text())
assert json.loads(json.dumps(totals(scenes))) == expected["totals"]
assert json.loads(json.dumps(queues)) == json.loads((source / "review-queues.json").read_text())["scenes"]
print("OK", len(scenes), "scenes")
PY
```

Để chạy lại từ ảnh và AIS gốc, đặt `schedule.json` thành `protocol.json` trong thư mục dữ liệu mới và chép `catalogue-screen.json` vào đó. Tải các kho AIS và ảnh VV bằng `scripts/fetch_multiscene_sar_ais.py`, rồi dùng `scripts/fetch_stationary_ais_rtc_bands.py` để lấy VV/VH vào thư mục con `dual-band`. Chạy `scripts/confirm_rtc_rank_with_ais.py --help` để xem các đường dẫn đầu vào. Checkpoint YOLO, checkpoint xView3, mã nguồn xView3 và GSHHG phải khớp với tệp kê khai mã băm.
