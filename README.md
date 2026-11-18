---
title: SonarNet
emoji: 🌊
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 7860
---

# SonarNet-VN

**Ứng dụng hỗ trợ rà soát ảnh Sentinel-1 và thử nghiệm đối chiếu vị trí với AIS.**

SonarNet lưu ảnh nguồn, thời gian, vị trí và lý do hệ thống đề xuất hoặc giữ lại
một cặp ghép. Người xem có thể tải hồ sơ để chuyên viên đối chiếu thêm nguồn.

**Chặng 1 Vòng Chung kết Bảng C.** Mở **Minh chứng cải tiến** để thử ba trường hợp
thiếu AIS, thông tin mâu thuẫn và quỹ đạo giao nhau. Bản báo cáo, lệnh tái lập và
hướng dẫn nộp nằm trong [hồ sơ Chặng 1](NOP_CHANG_1.md).
---

## 1. Bài toán

Giám sát, kiểm soát và theo dõi hoạt động trên biển là một phần của công tác
chống khai thác bất hợp pháp, không khai báo và không theo quy định (IUU).
Tháng 7/2026, FAO công bố hỗ trợ Việt Nam xây dựng chiến lược và kế hoạch thực
hiện Hiệp định về các biện pháp quốc gia có cảng. SonarNet nghiên cứu một bài
toán cụ thể trong khâu rà soát bằng chứng ảnh.
[FAO về hỗ trợ Việt Nam triển khai PSMA](https://www.fao.org/port-state-measures/news-events/detail/en/c/1759884/)

### Vì sao giám sát vẫn là điểm nghẽn

Bản tin hành trình có thể vắng trong nguồn đối chiếu vì phạm vi thu nhận, thời
điểm, chất lượng dữ liệu hoặc vì hệ thống dùng một nguồn khác. AIS và hệ thống
giám sát tàu cá (VMS) là hai nguồn cần phân biệt. Chặng 1 đánh giá ghép trên AIS
nghiên cứu và hồ sơ mẫu. Bản đồ công khai chưa có nguồn AIS hoặc VMS đồng bộ cho
các ảnh Việt Nam đang rà soát.

### Hướng giải quyết

Radar vệ tinh cung cấp quan sát độc lập với bản tin hành trình, kể cả qua mây
và vào ban đêm. Một điểm phản xạ có thể là phương tiện, nhiễu hoặc vật thể khác.
SonarNet gắn ứng viên với ảnh, thời gian và phạm vi chụp. Khi có AIS đủ chất lượng,
hệ thống đề xuất một cặp về vị trí. Các ca thiếu dữ liệu, mâu thuẫn hoặc không
ghép được được giữ lại để người có chuyên môn kiểm tra.

---

## 2. Kiến trúc hệ thống

```
   Sentinel-1 SAR          AIS phù hợp theo thời điểm
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
      │  • giữ hoặc từ chối cặp đề xuất    │
      └─────────────────┬─────────────────┘
                        ▼
      ┌───────────────────────────────────┐
      │ Tầng 4 — Hồ sơ để người xem rà    │
      │ Ghi chú, ảnh nguồn, xuất bằng chứng│
      └───────────────────────────────────┘
```

**Trạng thái đối chiếu** trên bản cải tiến:

| Trạng thái | Ý nghĩa |
|---|---|
| `AIS_OK` | Ghép được vị trí và có dữ liệu kích thước để đối chiếu. Chờ xác minh. |
| `AIS_MISMATCH` | Kích thước khai báo lệch so với hộp quan sát. Cần kiểm tra thêm. |
| `DARK` | Mã kỹ thuật cũ cho trạng thái **Không ghép được**. |
| `MISSING_DATA` | Dữ liệu sẵn có thiếu hoặc chưa qua kiểm tra chất lượng. |

Nhánh nghiên cứu hành vi mô phỏng các nhóm di chuyển quá cảnh, câu, kéo lưới,
neo đậu hoặc tụ tập. Đầu ra này dành cho nghiên cứu trên dữ liệu có nhãn.

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
git clone https://github.com/hoang-nguyenthe/sonarnet-vn.git
cd sonarnet-vn

python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m streamlit run scripts/demo_app.py
```

Mở `http://localhost:8501/?trang=minh-chung` để vào thẳng phần kiểm tra.
Để chạy pipeline nghiên cứu, cài thêm `requirements-full.txt`.

```bash
# Kiểm thử nhanh toàn bộ thành phần, chạy được trên CPU trong khoảng một phút
python tests/test_smoke.py

# Chạy rút gọn để kiểm tra toàn tuyến
python scripts/run_pipeline.py --quick

# Chạy đầy đủ
python scripts/run_pipeline.py

# Kiểm chứng các số liệu dùng trong báo cáo nghiên cứu
python scripts/verify_report_evidence.py
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

Kiến trúc nghiên cứu được thiết kế để việc thay thế nguồn dữ liệu chỉ tác động
đến tầng một. Bản public hiện đã có asset Sentinel‑1 GRD thật được xuất bản
theo cửa sổ 14 ngày; phần YOLO ảnh thật vẫn là vùng thử nghiệm có cổng kiểm
chứng riêng, không được gắn nhãn là mô hình nghiệp vụ toàn quốc.

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
| xView3-SAR | ảnh Sentinel-1 và nhãn mục tiêu phục vụ nghiên cứu | <https://iuu.xview.us> |

**Ranh giới vùng biển**: <https://www.marineregions.org>

Các bước nghiên cứu tiếp theo khi mở rộng sang dữ liệu thật:

1. Thay `data/simulator.py` bằng một mô-đun tải ảnh Sentinel-1 theo lịch quỹ đạo,
   thực hiện hiệu chuẩn bức xạ, khử nhiễu đốm và chỉnh hình học địa hình.
2. Thay `data/dataset.py` ở phần sinh dữ liệu bằng bước cắt ảnh thành ô và nạp
   nhãn từ SARDet-100K hoặc HRSID.
3. Thay nguồn AIS bằng lệnh gọi API của Global Fishing Watch, giữ nguyên định
   dạng bản ghi gồm `mmsi`, `timestamp`, `lat`, `lon`.
4. Giữ nguyên toàn bộ `detect/`, `fusion/`, `behavior/`, `evaluation/`, `viz/`.

### 6.3. Đối chứng độc lập với Global Fishing Watch

SonarNet‑VN dùng **SAR Vessel Detections** của Global Fishing Watch
(`public-global-sar-presence:latest`) như một lớp đối chiếu ngoài hệ thống.
Nguồn này được xây dựng từ ảnh Sentinel‑1 và vẫn có thể có dương tính giả; vì
vậy **không dùng làm nhãn để huấn luyện YOLO**, cũng không xem là ground truth
tuyệt đối. Bản public hiển thị lớp này mặc định tắt để người xem không nhầm nó
với đầu ra mô hình.

Quy trình đánh giá đúng là:

1. Cố định mắt xích huấn luyện và tách cảnh đánh giá theo vùng, ngày chụp.
2. Chạy detector trên nguồn đã xác định geometry và ngày chụp.
3. Ghép bằng Kalman và Hungarian với ngưỡng chất lượng khi có AIS cùng giờ.
4. Ghi số ca đồng thuận, khác nhau và chưa đủ mốc xác minh nếu đối chiếu GFW.

Chặng 1 có đối chứng ảnh LS-SSDD, OSSDD, OpenSAR Insight, ảnh Sentinel-1 RTC
ven biển Việt Nam với nhãn điểm Ai2 và phép phát lại AIS lịch sử NOAA.
Phép thử trực tiếp SAR–AIS có bốn mốc vị trí tham chiếu. Phép thử ở Việt Nam
đo khớp với nhãn điểm trong 100 m và ghi riêng số ứng viên cần rà.
Phương pháp và giới hạn đo có trong [báo cáo cải tiến](output/pdf/SonarNet_Bao_cao_Chang1_Giu_cap_AIS_20261118.pdf).
Mở [bảng đối chiếu minh chứng Chặng 1](NOP_CHANG_1.md) để kiểm tra từng phần.

### 6.4. Dashboard public và cập nhật dữ liệu

1. **Quan sát → Xem toàn cảnh** hiển thị ảnh ghép Sentinel‑1, phạm vi và trạng thái
   cập nhật. Lớp điểm ứng viên lấy từ ô ảnh chi tiết có bằng chứng.
2. **Quan sát → Kiểm tra chi tiết** mở ảnh, lưu đánh giá và xuất hồ sơ ZIP kèm
   SHA‑256. Khi chưa có kho ảnh chi tiết, ứng dụng mở một hồ sơ ảnh thật đã lưu.
3. **Minh chứng cải tiến** có ca tương tác AIS mô phỏng, đối chứng AIS lịch sử
   NOAA, một cảnh SAR–AIS cùng giờ và kết quả SAR độc lập. **Nghiên cứu** và
   **Hướng dẫn** giải thích phạm vi, cách đọc và cách kiểm chứng.

Job GitHub Actions kiểm tra nguồn định kỳ. Ảnh cũ tiếp tục hiển thị khi không
có lần xuất bản mới đạt kiểm tra chất lượng. Khi lỗi nguồn kéo dài, giao diện
cho biết giờ thử lại cùng thời gian thực tế của ảnh đang xem.

Job còn kiểm tra catalog cho từng ô ảnh chi tiết đã khai báo. Nếu có sản phẩm
mới, tải ảnh ~11 m/pixel, chạy YOLO và kiểm tra checksum trước khi công bố.
Ảnh không đủ 90% pixel hợp lệ giữ lại kết quả cũ cùng ngày quan sát cũ.
Baseline hiện vẫn là mô hình thử nghiệm học từ ảnh mô phỏng, chưa đạt chất
lượng nghiệp vụ. Các điểm ứng viên không được diễn giải thành tàu đã xác minh.
Lưới ảnh toàn cảnh có 22 vùng yêu cầu trên các hành lang biển, chỉ hiển thị
những vùng tải được; phạm vi đó không tương đương quét YOLO toàn cầu.

Để chạy job cục bộ, cấu hình secrets (không commit):

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
