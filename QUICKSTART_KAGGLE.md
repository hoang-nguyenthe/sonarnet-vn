# Hướng dẫn chạy nhanh trên Kaggle

Tài liệu này mô tả đúng các thao tác cần làm để chạy toàn bộ hệ thống SonarNet-VN
trên Kaggle với hai card đồ hoạ Tesla T4. Tổng thời gian từ lúc bắt đầu đến khi
có đầy đủ kết quả là khoảng **25 đến 40 phút** ở chế độ đầy đủ, hoặc **6 đến 10
phút** ở chế độ rút gọn.

---

## Cách nhanh nhất: dùng notebook tự chứa

Notebook `notebooks/SonarNet_VN_Kaggle.ipynb` **tự ghi ra toàn bộ mã nguồn** khi
chạy, nên không cần tải kho mã lên Kaggle dưới dạng bộ dữ liệu. Chỉ cần tải lên
đúng một tệp notebook rồi bấm chạy.

### Bước 1 — Tạo notebook mới

Vào <https://www.kaggle.com/code>, chọn **New Notebook**, sau đó chọn
**File → Import Notebook** và tải lên tệp `SonarNet_VN_Kaggle.ipynb`.

### Bước 2 — Bật hai GPU T4

Mở bảng điều khiển bên phải, mục **Session options**:

| Thiết lập | Giá trị cần chọn |
|---|---|
| Accelerator | **GPU T4 × 2** |
| Persistence | Files only (khuyến nghị) |
| Internet | **On** (khuyến nghị, xem ghi chú bên dưới) |
| Language | Python |

> **Về thiết lập Internet.** Khi bật, hệ thống cài đặt Ultralytics và tải trọng số
> YOLO đã huấn luyện trước, cho kết quả tốt nhất. Khi tắt, notebook **vẫn chạy
> đầy đủ** bằng phương án dự phòng Faster R-CNN của Torchvision — thư viện này có
> sẵn trong ảnh Python của Kaggle. Không có bước nào bị bỏ qua, chỉ khác về mô
> hình phát hiện được sử dụng.
>
> Việc bật Internet yêu cầu tài khoản Kaggle đã xác minh số điện thoại.

### Bước 3 — Chạy

Bấm **Run All**. Toàn bộ các ô lệnh sẽ chạy tuần tự từ đầu đến cuối mà không cần
can thiệp. Notebook tự động:

1. kiểm tra phần cứng và cài đặt thư viện cần thiết;
2. ghi ra toàn bộ mã nguồn của gói `sonarnet`;
3. sinh bộ dữ liệu ảnh radar và dòng tín hiệu AIS;
4. huấn luyện mô hình phát hiện trên cả hai GPU;
5. đánh giá, hợp nhất dữ liệu, phân loại hành vi;
6. chạy phân tích đóng góp thành phần;
7. kết xuất hình minh hoạ, bản đồ giám sát và báo cáo tổng hợp.

### Bước 4 — Lấy kết quả

Toàn bộ sản phẩm nằm trong `/kaggle/working/sonarnet_run/results/`:

| Tệp | Nội dung |
|---|---|
| `BAO_CAO_KET_QUA.md` | Báo cáo tổng hợp đầy đủ các chỉ tiêu |
| `ban_do_giam_sat.html` | Bản đồ giám sát tương tác |
| `ablation.csv` | Bảng phân tích đóng góp thành phần |
| `figures/*.png` | Chín hình minh hoạ cho báo cáo và video |
| `tong_hop_ket_qua.json` | Toàn bộ chỉ tiêu dạng máy đọc được |

Ô lệnh cuối cùng của notebook đóng gói tất cả vào một tệp nén để tải về bằng một
lần bấm.

---

## Chế độ rút gọn

Nếu chỉ muốn kiểm tra toàn tuyến chạy thông trước khi chạy đầy đủ, sửa ô lệnh
cấu hình:

```python
CFG.apply_quick_mode()   # 60 cảnh, 8 chu kỳ huấn luyện — khoảng 6 phút
```

Sau khi xác nhận mọi bước chạy thông, xoá dòng này và chạy lại để có kết quả đầy đủ.

---

## Cách thứ hai: dùng kho mã nguồn dưới dạng bộ dữ liệu

Phù hợp khi muốn chỉnh sửa mã nguồn bằng trình soạn thảo thay vì trong notebook.

1. Nén thư mục dự án và tải lên Kaggle qua **Datasets → New Dataset**, đặt tên
   `sonarnet-vn`.
2. Trong notebook, chọn **Add Input** và thêm bộ dữ liệu vừa tạo.
3. Chạy các lệnh sau trong ô đầu tiên:

```python
import shutil, sys
from pathlib import Path

src = next(Path("/kaggle/input/sonarnet-vn").rglob("src/sonarnet")).parent
shutil.copytree(src, "/kaggle/working/src", dirs_exist_ok=True)
sys.path.insert(0, "/kaggle/working/src")

from sonarnet.config import CFG
```

4. Sau đó gọi lần lượt các bước của pipeline như trong notebook tự chứa, hoặc
   chạy thẳng tệp lệnh tổng:

```python
!python /kaggle/working/scripts/run_pipeline.py
```

---

## Xử lý sự cố thường gặp

| Hiện tượng | Nguyên nhân và cách xử lý |
|---|---|
| `ModuleNotFoundError: ultralytics` | Internet đang tắt. Không cần xử lý — hệ thống tự chuyển sang Faster R-CNN. Nếu muốn dùng YOLO, bật Internet rồi chạy lại. |
| Huấn luyện phân tán bị treo | Đặt `CFG.multi_gpu = False` rồi chạy lại ô huấn luyện. Kết quả không đổi, chỉ chậm hơn khoảng hai lần. |
| `CUDA out of memory` | Giảm `CFG.detect.batch_size` xuống 16 hoặc 8. |
| Phiên chạy hết thời gian | Dùng `CFG.apply_quick_mode()`, hoặc giảm `CFG.detect.epochs`. |
| Chỉ thấy một GPU | Kiểm tra lại mục Accelerator đã chọn **GPU T4 × 2** chưa. Hệ thống vẫn chạy bình thường trên một GPU. |
| Bản đồ không hiển thị | Thư viện `folium` chưa có. Hệ thống tự kết xuất biểu đồ phân bố tĩnh thay thế. |

---

## Thời gian tham khảo

Đo trên Kaggle với hai card Tesla T4, chế độ đầy đủ, mô hình YOLO11n:

| Bước | Thời gian |
|---|---|
| Sinh bộ dữ liệu (380 cảnh) | 2 – 4 phút |
| Huấn luyện phát hiện (40 chu kỳ, 2 GPU) | 14 – 22 phút |
| Đánh giá và suy luận | 1 – 2 phút |
| Hợp nhất radar và AIS | dưới 1 phút |
| Phân loại hành vi | 1 – 2 phút |
| Phân tích đóng góp thành phần | dưới 1 phút |
| Kết xuất hình và báo cáo | dưới 1 phút |
| **Tổng cộng** | **khoảng 25 – 35 phút** |
