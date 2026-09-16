# Thích ứng với bộ dữ liệu mới

Tài liệu này dành cho hai tình huống: chuyển hệ thống sang **dữ liệu vệ tinh
thật**, và **thích ứng nhanh với bộ dữ liệu thô do Ban Tổ chức cung cấp tại Vòng
Khu vực**, nơi hệ thống thi hackathon liên tục trong hai ngày.

Kiến trúc được thiết kế để việc thay nguồn dữ liệu chỉ tác động đến tầng thu
nhận. Ba tầng còn lại — phát hiện, hợp nhất, phân tích hành vi — giữ nguyên
không đổi.

---

## 1. Điểm cần thay đổi và điểm giữ nguyên

```
        THAY ĐỔI                          GIỮ NGUYÊN
  ┌──────────────────┐        ┌────────────────────────────────┐
  │ data/simulator   │        │ detect/     — phát hiện        │
  │ data/dataset     │  ───▶  │ fusion/     — hợp nhất         │
  │ (nguồn ảnh, AIS) │        │ behavior/   — hành vi          │
  └──────────────────┘        │ evaluation/ — chỉ tiêu         │
                              │ viz/        — kết xuất         │
                              └────────────────────────────────┘
```

Toàn bộ giao tiếp giữa tầng thu nhận và các tầng sau diễn ra qua **ba cấu trúc
dữ liệu**. Chỉ cần tạo ra đúng ba cấu trúc này là hệ thống chạy được.

### 1.1. Ảnh và nhãn

Thư mục theo quy ước YOLO:

```
data/yolo/
  images/{train,val,test}/<scene_id>.png     ảnh xám 8 bit
  labels/{train,val,test}/<scene_id>.txt     mỗi dòng: 0 xc yc w h  (đã chuẩn hoá)
  data.yaml
```

### 1.2. Siêu dữ liệu cảnh

Tệp `data/yolo/scenes/{split}.jsonl`, mỗi dòng là một cảnh:

```json
{
  "scene_id": "test_00001",
  "capture_time_s": 43512.0,
  "georef": {"lat_top": 10.02, "lon_left": 108.55,
             "width": 640, "height": 640, "pixel_spacing_m": 10.0},
  "vessels": [
    {"mmsi": 574000123, "lat": 9.97, "lon": 108.61,
     "length_m": 142.0, "width_m": 31.0,
     "heading_deg": 78.5, "speed_kn": 11.2,
     "identity_state": "AIS_OK", "declared_length_m": 142.0,
     "behaviour": "qua_canh", "bbox": [301.2, 188.7, 317.9, 201.4]}
  ]
}
```

Trên dữ liệu thật, trường `identity_state` chỉ cần thiết khi có nhãn đối chứng.
Nếu không có, để trống và bỏ qua phần đánh giá tầng hợp nhất; hệ thống vẫn sinh
được cảnh báo.

### 1.3. Dòng AIS

Tệp `data/yolo/ais/{split}.jsonl`, mỗi dòng là một bản ghi:

```json
{"scene_id": "test_00001", "mmsi": 574000123, "timestamp": 43200.0,
 "lat": 9.9685, "lon": 108.6072, "sog_kn": 11.4, "cog_deg": 78.1,
 "declared_length_m": 142.0}
```

Bắt buộc: `scene_id`, `mmsi`, `timestamp`, `lat`, `lon`. Các trường còn lại là
tuỳ chọn.

---

## 2. Chuyển sang ảnh Sentinel-1 thật

### Bước 1 — Đăng ký truy cập

Tạo tài khoản tại <https://dataspace.copernicus.eu>, sau đó lấy khoá truy cập.
Trên Kaggle, lưu khoá bằng chức năng **Add-ons → Secrets**, không đặt trực tiếp
trong mã nguồn.

### Bước 2 — Tải và tiền xử lý

Quy trình tiền xử lý ảnh Ground Range Detected gồm bốn bước bắt buộc:

```python
# Gợi ý dùng PyroSAR điều khiển bộ công cụ SNAP của ESA
from pyroSAR.snap import geocode

geocode(
    infile="S1A_IW_GRDH_....zip",
    outdir="processed/",
    t_srs=4326,                 # hệ toạ độ địa lý WGS-84
    spacing=10,                 # mét trên mỗi điểm ảnh
    polarizations=["VV"],       # phân cực VV nhạy nhất với mục tiêu trên biển
    removeS1BorderNoise=True,   # khử nhiễu viền
    terrainFlattening=False,    # không cần với mặt biển
    speckleFilter="Refined Lee",# khử nhiễu đốm
    refarea="gamma0",
)
```

Bốn bước tương ứng: hiệu chuẩn bức xạ, khử nhiễu đốm, chỉnh hình học địa hình và
chuyển về thang decibel.

### Bước 3 — Cắt ô và gắn hệ quy chiếu

Cắt ảnh lớn thành các ô 640 × 640 điểm ảnh. Với mỗi ô, ghi lại `lat_top`,
`lon_left` và `pixel_spacing_m` vào siêu dữ liệu cảnh. Mô-đun
`data/geo.py` dùng đúng ba giá trị này để chuyển đổi toạ độ, không cần sửa gì thêm.

### Bước 4 — Gán nhãn

Ba lựa chọn theo thứ tự ưu tiên:

1. Tinh chỉnh mô hình trên SARDet-100K rồi dùng nó gán nhãn sơ bộ, sau đó rà soát
   thủ công. Đây là cách nhanh nhất.
2. Dùng chính vị trí AIS làm nhãn yếu cho các phương tiện có phát tín hiệu. Cách
   này miễn phí nhưng bỏ sót đúng nhóm cần quan tâm nhất.
3. Gán nhãn thủ công bằng công cụ như Label Studio hoặc CVAT.

---

## 3. Lấy dữ liệu AIS thật

```python
import os, requests

TOKEN = os.environ["GFW_TOKEN"]          # trên Kaggle: dùng Secrets
resp = requests.get(
    "https://gateway.api.globalfishingwatch.org/v3/events",
    headers={"Authorization": f"Bearer {TOKEN}"},
    params={
        "datasets[0]": "public-global-fishing-events:latest",
        "start-date": "2026-09-01",
        "end-date": "2026-09-30",
        # Vùng biển quan tâm, dạng GeoJSON
    },
    timeout=60,
)
```

Chuyển kết quả về đúng cấu trúc mô tả ở mục 1.3 rồi ghi ra tệp `jsonl`. Sau bước
này, các tầng phía sau chạy được ngay.

---

## 4. Thích ứng nhanh tại hackathon hai ngày

Trong tình huống thực chiến, đội nhận **một bộ dữ liệu thô và một yêu cầu thực tiễn** do
Ban Tổ chức công bố tại chỗ. Trình tự dưới đây giúp đưa hệ thống vào trạng thái
chạy được trong thời gian ngắn nhất.

### Giờ thứ nhất — Khảo sát dữ liệu

```bash
python scripts/inspect_dataset.py --path <thư-mục-dữ-liệu-BTC>
```

Tệp lệnh này in ra cấu trúc thư mục, định dạng tệp, thống kê kích thước ảnh, các
trường có trong dữ liệu bảng, và gợi ý ánh xạ sang cấu trúc của hệ thống.

### Giờ thứ hai đến thứ tư — Viết bộ nạp dữ liệu

Tạo một tệp mới `src/sonarnet/data/loader_btc.py` với đúng một hàm:

```python
def build_dataset_from_btc(cfg, raw_dir) -> dict:
    """Đọc dữ liệu thô của Ban Tổ chức, ghi ra đúng cấu trúc ở mục 1."""
    ...
```

Chỉ cần hàm này tạo ra ảnh, nhãn, `scenes/*.jsonl` và `ais/*.jsonl` đúng định
dạng. Sau đó thay lời gọi trong `pipeline.step_build_data`.

### Giờ thứ năm trở đi — Chạy toàn tuyến

```bash
python scripts/run_pipeline.py --quick      # kiểm tra thông tuyến trước
python scripts/run_pipeline.py              # chạy đầy đủ
```

### Nếu bài toán khác hoàn toàn

Ba thành phần dưới đây dùng lại được cho hầu hết bài toán giám sát hoặc phát hiện
bất thường, không phụ thuộc vào miền ứng dụng cụ thể:

| Thành phần | Dùng lại được cho |
|---|---|
| `fusion/kalman.py` | Mọi bài toán cần nội suy chuỗi thời gian có nhiễu về một mốc xác định |
| `fusion/matching.py` | Mọi bài toán đối chiếu hai nguồn dữ liệu theo không gian và thời gian |
| `behavior/features.py` | Mọi bài toán phân loại từ dữ liệu quỹ đạo hoặc chuỗi thời gian |
| `evaluation/` | Chỉ tiêu phát hiện và phân tích đóng góp thành phần |

---

## 5. Danh mục kiểm tra trước khi chạy trên dữ liệu mới

- [ ] Ảnh đọc được, đúng kích thước, không có giá trị khuyết
- [ ] Nhãn nằm trong khoảng hợp lệ sau chuẩn hoá
- [ ] `georef` cho phép chuyển đổi hai chiều nhất quán (chạy `tests/test_smoke.py`)
- [ ] Mốc thời gian của ảnh và của AIS dùng chung một hệ quy chiếu thời gian
- [ ] Sai số nội suy trung vị nhỏ hơn ngưỡng ghép cặp
- [ ] Ngưỡng `max_match_distance_m` phù hợp với độ phân giải ảnh
- [ ] Chạy `--quick` thông toàn tuyến trước khi chạy đầy đủ
