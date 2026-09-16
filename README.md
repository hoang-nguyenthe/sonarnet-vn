# SonarNet-VN

**Hệ thống giám sát tuân thủ quy định chống khai thác thuỷ sản bất hợp pháp,
không khai báo và không theo quy định, trên cơ sở hợp nhất ảnh vệ tinh radar
khẩu độ tổng hợp với tín hiệu giám sát hành trình tàu cá.**

Dự án nghiên cứu và bản trình diễn: kiến trúc phát hiện phương tiện, hợp nhất dữ liệu đa nguồn và phân loại hành vi phục vụ giám sát tuân thủ.
---

## 1. Bài toán

Tháng 10 năm 2017, Uỷ ban châu Âu áp dụng cảnh báo thẻ vàng đối với thuỷ sản
Việt Nam vì chưa kiểm soát được hoạt động khai thác bất hợp pháp, không khai báo
và không theo quy định. Gần một thập kỷ sau, cảnh báo này vẫn còn hiệu lực. Chính
phủ đặt mục tiêu gỡ thẻ vàng trong năm 2026, với hạn chót ngày 31 tháng 8 năm
2026 để tạo chuyển biến thực chất và ngày 01 tháng 10 năm 2026 để gửi báo cáo
phản hồi các khuyến nghị của Uỷ ban châu Âu.

Đây trước hết là một bài toán kinh tế. Thuỷ sản là ngành xuất khẩu chủ lực, và
thị trường châu Âu là một trong những thị trường có giá trị cao nhất. Cảnh báo
thẻ vàng làm tăng chi phí kiểm tra, kéo dài thời gian thông quan và làm giảm sức
cạnh tranh của toàn ngành. Người chịu ảnh hưởng cuối cùng là hàng trăm nghìn ngư
dân và các doanh nghiệp chế biến.

Bốn nhóm khuyến nghị mà Uỷ ban châu Âu đưa ra tập trung vào quản lý đội tàu, thực
thi pháp luật, truy xuất nguồn gốc và **giám sát**. Đề tài này nhắm vào nhóm cuối.

### Vì sao giám sát vẫn là điểm nghẽn

Việt Nam hiện có khoảng 80.300 tàu cá đăng ký trên cơ sở dữ liệu nghề cá quốc
gia. Trong đó **99,6 phần trăm tàu từ 15 mét trở lên đã lắp thiết bị giám sát
hành trình**. Nói cách khác, giai đoạn trang bị thiết bị về cơ bản đã hoàn tất.

Điểm nghẽn còn lại nằm ở chỗ khác: **thiết bị được lắp nhưng không phải lúc nào
cũng phát tín hiệu**. Mất kết nối có thể do sự cố kỹ thuật, nhưng cũng có thể do
chủ động ngắt. Khi tín hiệu biến mất, cơ quan quản lý không còn cách nào biết
phương tiện đang ở đâu và làm gì — đúng vào những tình huống cần biết nhất.

Đây là giới hạn cố hữu của mọi phương thức giám sát chỉ dựa trên tín hiệu do
chính phương tiện phát ra.

### Hướng giải quyết

Ảnh vệ tinh radar khẩu độ tổng hợp không phụ thuộc vào việc phương tiện có phát
tín hiệu hay không. Nó ghi nhận mọi vật thể phản xạ sóng radar trên mặt biển, kể
cả khi trời nhiều mây và vào ban đêm — điều kiện quyết định với vùng biển nhiệt
đới như Biển Đông.

Khi đối chiếu tập phương tiện *nhìn thấy trên ảnh* với tập phương tiện *đang phát
tín hiệu giám sát hành trình*, phần chênh lệch chính là các phương tiện mất kết
nối. Hệ thống không kết luận nguyên nhân, mà cung cấp cho cơ quan quản lý một
danh sách trường hợp cần rà soát, kèm bằng chứng ảnh và toạ độ cụ thể.

SonarNet-VN hiện thực hoá ý tưởng đó thành hệ thống bốn tầng hoàn chỉnh, sử dụng
hoàn toàn dữ liệu mở.

---

## 2. Kiến trúc hệ thống

```
   Sentinel-1 SAR          Global Fishing Watch (AIS)
         │                            │
         ▼                            │
┌────────────────────┐                │
│ Tầng 1             │                │
│ Thu nhận và        │                │
│ tiền xử lý ảnh     │                │
└─────────┬──────────┘                │
          ▼                           │
┌────────────────────┐                │
│ Tầng 2             │                │
│ Phát hiện          │                │
│ phương tiện        │                │
└─────────┬──────────┘                │
          │                           │
          ▼                           ▼
      ┌───────────────────────────────────┐
      │ Tầng 3 — Hợp nhất radar và AIS    │
      │  • nội suy Kalman về thời điểm    │
      │    chụp ảnh                       │
      │  • ghép cặp tối ưu Hungarian      │
      │  • phân loại ba trạng thái        │
      └─────────────────┬─────────────────┘
                        ▼
      ┌───────────────────────────────────┐
      │ Tầng 4 — Phân tích hành vi        │
      │ và sinh cảnh báo trên bản đồ      │
      └───────────────────────────────────┘
```

**Ba trạng thái định danh** mà hệ thống phân biệt:

| Trạng thái | Ý nghĩa |
|---|---|
| `AIS_OK` | Phương tiện phát tín hiệu đầy đủ và trung thực |
| `AIS_MISMATCH` | Có phát tín hiệu nhưng kích thước khai báo sai lệch lớn so với quan sát trên ảnh radar |
| `DARK` | Không phát tín hiệu tại thời điểm chụp — dấu hiệu chủ động ngắt định danh |

**Bốn nhóm hành vi** mà tầng bốn nhận diện: di chuyển quá cảnh, câu, kéo lưới,
neo đậu hoặc tụ tập.

---

## 3. Chạy trên Kaggle

Xem hướng dẫn chi tiết trong [`QUICKSTART_KAGGLE.md`](QUICKSTART_KAGGLE.md).
Tóm tắt ba bước:

1. Tải `notebooks/SonarNet_VN_Kaggle.ipynb` lên Kaggle.
2. Chọn **Accelerator → GPU T4 × 2**, bật **Internet**.
3. Bấm **Run All**.

Notebook tự ghi ra toàn bộ mã nguồn nên không cần tải kho mã lên dưới dạng bộ dữ
liệu. Toàn bộ quy trình chạy thông từ đầu đến cuối không cần can thiệp.

---

## 4. Chạy trên máy cá nhân

```bash
git clone <địa-chỉ-kho-mã> sonarnet-vn
cd sonarnet-vn

python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Kiểm thử nhanh toàn bộ thành phần, chạy được trên CPU trong khoảng một phút
python tests/test_smoke.py

# Chạy rút gọn để kiểm tra toàn tuyến
python scripts/run_pipeline.py --quick

# Chạy đầy đủ
python scripts/run_pipeline.py
```

Các tuỳ chọn dòng lệnh:

| Tuỳ chọn | Ý nghĩa |
|---|---|
| `--quick` | Chế độ rút gọn: 60 cảnh, 8 chu kỳ huấn luyện |
| `--single-gpu` | Chỉ dùng một GPU |
| `--epochs N` | Ghi đè số chu kỳ huấn luyện |
| `--backend ultralytics\|torchvision` | Chọn phương án phát hiện |
| `--root ĐƯỜNG_DẪN` | Thư mục làm việc |

---

## 5. Cấu trúc kho mã nguồn

```
sonarnet-vn/
├── README.md                      Tài liệu này
├── QUICKSTART_KAGGLE.md           Hướng dẫn chạy trên Kaggle
├── requirements.txt               Danh mục thư viện
├── notebooks/
│   └── SonarNet_VN_Kaggle.ipynb   Notebook tự chứa, bấm Run All là chạy
├── scripts/
│   ├── run_pipeline.py            Chạy toàn bộ quy trình từ dòng lệnh
│   ├── train_detector.py          Huấn luyện phân tán trên nhiều GPU
│   └── build_notebook.py          Dựng lại notebook từ mã nguồn
├── src/sonarnet/
│   ├── config.py                  Cấu hình tập trung
│   ├── utils.py                   Hạt giống ngẫu nhiên, thiết bị, nhật ký
│   ├── pipeline.py                Điều phối các bước
│   ├── reporting.py               Kết xuất hình và báo cáo
│   ├── data/
│   │   ├── geo.py                 Hệ toạ độ địa lý và điểm ảnh
│   │   ├── sar_render.py          Dựng ảnh radar mô phỏng
│   │   ├── simulator.py           Mô phỏng liên kết cảnh ảnh và dòng AIS
│   │   ├── tracks.py              Sinh quỹ đạo theo nhóm hành vi
│   │   └── dataset.py             Ghi và đọc bộ dữ liệu
│   ├── detect/
│   │   ├── interface.py           Giao diện thống nhất
│   │   ├── yolo_backend.py        Ultralytics YOLO, hỗ trợ đa GPU
│   │   └── torchvision_backend.py Faster R-CNN dự phòng
│   ├── fusion/
│   │   ├── kalman.py              Nội suy quỹ đạo AIS
│   │   └── matching.py            Ghép cặp và phân loại trạng thái
│   ├── behavior/
│   │   ├── features.py            Trích xuất đặc trưng động học
│   │   └── classifier.py          Bộ phân loại hành vi
│   ├── evaluation/
│   │   ├── detection_metrics.py   mAP, độ chính xác, độ nhạy
│   │   ├── fusion_metrics.py      Chỉ tiêu tầng hợp nhất
│   │   └── ablation.py            Phân tích đóng góp thành phần
│   └── viz/
│       ├── figures.py             Hình minh hoạ
│       └── dashboard.py           Bản đồ giám sát
└── tests/
    └── test_smoke.py              Kiểm thử toàn bộ thành phần
```

---

## 6. Về dữ liệu

### 6.1. Dữ liệu dùng trong lần chạy mặc định

Bộ mã nguồn đi kèm một **bộ mô phỏng** sinh ra cảnh ảnh radar và dòng tín hiệu
AIS gắn chặt với nhau. Đây là lựa chọn có chủ đích, vì hai lý do.

Thứ nhất, nó cho phép toàn bộ hệ thống chạy được từ đầu đến cuối mà không cần
khoá truy cập Copernicus hay Global Fishing Watch — điều kiện cần để người đọc
có thể tự kiểm chứng kết quả chỉ bằng một lần bấm.

Thứ hai, và quan trọng hơn, bộ mô phỏng cung cấp **nhãn đối chứng tuyệt đối
chính xác cho tầng hợp nhất**. Trên dữ liệu thật, việc biết chắc một phương tiện
có thực sự ngắt AIS hay chỉ mất sóng tạm thời là rất khó; trên dữ liệu mô phỏng,
thông tin này được biết chính xác, nhờ đó mọi chỉ tiêu của tầng ba đều kiểm chứng
được.

Bộ mô phỏng tái tạo các đặc trưng vật lý chính của ảnh radar biển: tán xạ nền
theo phân bố Rayleigh, nhiễu đốm nhân tính theo mô hình đa nhìn, điều biến quy mô
lớn do gió và sóng lừng, tán xạ tử điểm trên thượng tầng phương tiện, vệt nước
sau tàu, bóng ma phương vị, và vùng đất liền có kết cấu thô. Dòng AIS được sinh
với nhịp phát không đều, nhiễu vị trí và các khoảng mất sóng ngẫu nhiên.

### 6.2. Chuyển sang dữ liệu thật

Kiến trúc được thiết kế để việc thay thế nguồn dữ liệu chỉ tác động đến tầng một.
Ba tầng còn lại giữ nguyên hoàn toàn.

**Ảnh vệ tinh Sentinel-1** — miễn phí, cần đăng ký tài khoản:

- Copernicus Data Space Ecosystem: <https://dataspace.copernicus.eu>
- Thư viện truy xuất: <https://github.com/sentinel-hub/sentinelhub-py>
- Tài liệu kỹ thuật: <https://sentinels.copernicus.eu/web/sentinel/user-guides/sentinel-1-sar>

**Dữ liệu AIS** — miễn phí cho mục đích học thuật:

- Global Fishing Watch API: <https://globalfishingwatch.org/our-apis>
- Đăng ký khoá truy cập: <https://globalfishingwatch.org/our-apis/tokens>

**Bộ dữ liệu chuẩn có nhãn** để tinh chỉnh mô hình phát hiện:

| Bộ dữ liệu | Quy mô | Địa chỉ |
|---|---|---|
| SARDet-100K | 116.598 ảnh, 245.653 đối tượng | <https://github.com/zcablii/SARDet_100K> |
| HRSID | 5.604 ảnh, có mặt nạ phân vùng | <https://github.com/chaozhong2010/HRSID> |
| SSDD | 1.160 ảnh | <https://github.com/TianwenZhang0825/Official-SSDD> |
| xView3-SAR | chuyên biệt cho phương tiện ngắt định danh | <https://iuu.xview.us> |

**Ranh giới vùng biển**: <https://www.marineregions.org>

Các bước cần thực hiện khi chuyển sang dữ liệu thật:

1. Thay `data/simulator.py` bằng một mô-đun tải ảnh Sentinel-1 theo lịch quỹ đạo,
   thực hiện hiệu chuẩn bức xạ, khử nhiễu đốm và chỉnh hình học địa hình.
2. Thay `data/dataset.py` ở phần sinh dữ liệu bằng bước cắt ảnh thành ô và nạp
   nhãn từ SARDet-100K hoặc HRSID.
3. Thay nguồn AIS bằng lệnh gọi API của Global Fishing Watch, giữ nguyên định
   dạng bản ghi gồm `mmsi`, `timestamp`, `lat`, `lon`.
4. Giữ nguyên toàn bộ `detect/`, `fusion/`, `behavior/`, `evaluation/`, `viz/`.

### 6.3. Đối chứng độc lập với Global Fishing Watch

Sau khi có GFW API token, SonarNet-VN sẽ dùng **SAR Vessel Detections** của
Global Fishing Watch (`public-global-sar-presence:latest`) như một lớp đối
chiếu ngoài hệ thống. Nguồn này được xây dựng từ ảnh Sentinel-1, có độ trễ xấp
xỉ 5 ngày và vẫn có thể có dương tính giả; vì vậy **không dùng làm nhãn để huấn
luyện YOLO**, cũng không xem là ground truth tuyệt đối.

Quy trình đánh giá đúng là:

1. Huấn luyện SonarNet trên SARDet-100K, HRSID, SSDD và xView3-SAR.
2. Chạy SonarNet trên cảnh Sentinel-1 GRD thật lấy trực tiếp từ Copernicus.
3. Ghép đầu ra với AIS bằng Kalman + Hungarian.
4. So sánh theo không gian-thời gian với GFW SAR Vessel Detections, rồi báo cáo
   mức độ đồng thuận, các ca chỉ SonarNet/GFW phát hiện được và các giới hạn.

Điều này bổ sung kiểm chứng độc lập mà không làm mô hình học lại đầu ra của một
hệ thống khác. SonarNet-VN vì vậy là hệ thống **giám sát vệ tinh gần thời gian
thực**, không phải công cụ theo dõi liên tục thời gian thực: AIS có thể cập nhật
theo luồng khi có nguồn phù hợp, còn SAR chỉ tạo quan sát khi vệ tinh đi qua.

### 6.4. Chạy tab Sentinel-1 thật

Dashboard có tab **Sentinel-1 thật** để truy vấn các cảnh GRD theo khu vực và
thời gian, sau đó dựng ảnh xem nhanh VV đã hiệu chỉnh địa hình qua Copernicus
Process API. Cấu hình secrets cục bộ trước khi chạy:

```toml
# .streamlit/secrets.toml (không commit)
[copernicus]
client_id = "sh-…"
client_secret = "…"
```

Có mẫu an toàn tại `.streamlit/secrets.example.toml`. Trên Streamlit Community
Cloud, đưa hai khoá trên vào **App settings → Secrets**, không thêm chúng vào
repository.

---

## 7. Chỉ tiêu đánh giá

Hệ thống tính đầy đủ các chỉ tiêu sau, tự động lưu vào
`results/tong_hop_ket_qua.json`:

**Tầng phát hiện** — mAP@0.5, mAP@0.5:0.95, độ chính xác, độ nhạy, F1, số lượng
dương tính thật, dương tính giả và bỏ sót.

**Tầng hợp nhất** — tỉ lệ ghép cặp chính xác, sai số ghép cặp trung bình và trung
vị, độ chính xác và độ nhạy đối với lớp phương tiện ngắt định danh, ma trận nhầm
lẫn ba trạng thái.

**Tầng hành vi** — độ chính xác, F1 vĩ mô, F1 theo từng nhóm, ma trận nhầm lẫn,
xếp hạng độ quan trọng của đặc trưng.

**Phân tích đóng góp thành phần** — bốn cấu hình so sánh:

| Cấu hình | Nội dung |
|---|---|
| A | Chỉ ảnh radar — phát hiện được phương tiện nhưng không xác định được định danh |
| B | Chỉ dữ liệu AIS — bỏ sót hoàn toàn phương tiện ngắt tín hiệu |
| C | Hợp nhất với nội suy tuyến tính, chưa kiểm tra kích thước khai báo |
| D | Hệ thống đầy đủ — nội suy Kalman và có kiểm tra kích thước |

Phép so sánh này trả lời trực tiếp câu hỏi trọng tâm của đề tài: mỗi thành phần
đóng góp bao nhiêu vào năng lực phát hiện phương tiện chủ động ngắt định danh.

---

## 8. Sản phẩm kết xuất

Sau một lần chạy hoàn chỉnh, thư mục `results/` chứa:

| Tệp | Nội dung |
|---|---|
| `BAO_CAO_KET_QUA.md` | Báo cáo tổng hợp toàn bộ chỉ tiêu |
| `tong_hop_ket_qua.json` | Toàn bộ kết quả dạng máy đọc được |
| `ban_do_giam_sat.html` | Bản đồ giám sát tương tác |
| `ablation.csv` | Bảng phân tích đóng góp thành phần |
| `figures/01_canh_anh_radar.png` | Cảnh ảnh kèm đối chứng và phát hiện |
| `figures/02_duong_cong_pr.png` | Đường cong chính xác – độ nhạy |
| `figures/03_ma_tran_hop_nhat.png` | Ma trận nhầm lẫn ba trạng thái |
| `figures/04_sai_so_ghep_cap.png` | Phân bố sai số ghép cặp |
| `figures/05_so_sanh_noi_suy.png` | So sánh Kalman và nội suy tuyến tính |
| `figures/06_ma_tran_hanh_vi.png` | Ma trận nhầm lẫn bốn nhóm hành vi |
| `figures/07_quy_dao_hanh_vi.png` | Quỹ đạo tiêu biểu từng nhóm |
| `figures/08_dac_trung_quan_trong.png` | Đặc trưng động học quan trọng nhất |
| `figures/09_dong_gop_thanh_phan.png` | Biểu đồ phân tích đóng góp |

---

## 9. Yêu cầu môi trường

| Thành phần | Yêu cầu |
|---|---|
| Python | 3.9 trở lên |
| PyTorch | 2.0 trở lên (có sẵn trên Kaggle) |
| GPU | Không bắt buộc; khuyến nghị hai card T4 để huấn luyện phân tán |
| Bộ nhớ | 8 GB RAM trở lên |
| Dung lượng đĩa | Khoảng 2 GB cho bộ dữ liệu và kết quả |

Các thư viện `ultralytics`, `xgboost` và `folium` là **tuỳ chọn**. Khi thiếu bất
kỳ thư viện nào trong số này, hệ thống tự động chuyển sang phương án thay thế có
sẵn trong thư viện chuẩn hoặc trong ảnh Python của Kaggle, và vẫn chạy đầy đủ mọi
bước.

---

## 10. Tuyên bố về phạm vi sử dụng

Sản phẩm này là **công cụ hỗ trợ nghiên cứu khoa học**. Toàn bộ dữ liệu sử dụng
đều là dữ liệu mở, được cung cấp công khai cho mục đích nghiên cứu và học thuật.

Hệ thống không tham gia vào bất kỳ quy trình ra quyết định thực thi pháp luật nào,
không thực hiện theo dõi cá nhân, và không đưa ra kết luận pháp lý về hành vi của
bất kỳ phương tiện hay tổ chức nào. Mọi kết quả phát hiện đều mang tính chất tín
hiệu cảnh báo kỹ thuật, cần được cơ quan có thẩm quyền kiểm chứng độc lập trước
khi sử dụng cho bất kỳ mục đích nào khác.
