# Kiểm tra quét tín hiệu yếu và mô hình SAR hai kênh

Hai phép thử giữ đúng số lượt rà của từng lượt chụp. Tiêu chí khóa là
số nhãn điểm Ai2 khớp trong 100 m trên năm lượt phát triển. Phép chấm theo
tọa độ WGS84, ghép một–một, giữ vùng nước hợp lệ và chấm thêm ở 50 và 150 m.
Có 12 lượt đối chứng đã dùng trong các thí nghiệm SonarNet trước và hai
lượt giữ riêng ở Bắc Trung Bộ. Cả hai nhóm đều tách ngày UTC khỏi phát triển.

- Quét tín hiệu yếu dùng cùng checkpoint của SonarNet. Chạy ảnh nguyên và
  lưới 3×3 với đệm 48 px ở ngưỡng 0,01. Thử mở thêm vùng nước sát bờ cùng
  mức ưu tiên thấp hơn, giảm điểm đề xuất trùng và kiểm tra đồng thuận giữa
  các lượt quét. Lớp đất và vùng thiếu dữ liệu vẫn được loại.
- Đối chứng mô hình ngoài lấy đúng một checkpoint ResNet34 U-Net của
  [bản phát hành xView3](https://github.com/selimsef/xview3_solution/releases/tag/weights).
  Dùng cường độ VV/VH đồng vị trí từ Sentinel-1 RTC, chuẩn hóa theo mã gốc.
  Lấy cực đại cục bộ từ bản đồ tâm. Thử kết hợp với xác suất tàu, xoay 180°
  và ứng viên YOLO của SonarNet. Với ô thiếu VH, vùng chấm, nhãn và đối
  chứng YOLO được giữ. Checkpoint có trước các lượt chụp Ai2 năm 2022 theo
  lịch của [bài báo xView3-SAR](https://proceedings.neurips.cc/paper_files/paper/2022/hash/f4d4a021f9051a6c18183b059117e8b5-Abstract.html).
  Đây là phép chuyển mô hình trên RTC, thay đổi khâu hậu xử lý và dùng một
  checkpoint. Mô hình nguồn và trọng số thuộc tác giả gốc.

Mở `summary.json` để xem số nhãn khớp ở cùng số lượt rà và khi rà tất cả
ứng viên. Điểm không khớp có thể gồm mục tiêu chưa được gắn nhãn. Kết quả
chỉ áp dụng cho những ô ảnh, mốc thời gian và định nghĩa nhãn đã dùng.

## Chấm lại trong hồ sơ Chặng 1

```sh
python -m pip install numpy scipy pyproj
python scripts/replay_rtc_transfer.py
```

Trình phát lại dùng nghiệm Hungarian thay cho đồ thị ghép cặp thưa dùng
trong lần chấm đầu. Tệp tọa độ đủ để kiểm lại số ghép ở cả ba bán kính. Tệp
`selection.json` giữ kết quả phát triển và cách đã khóa cho mỗi số lượt rà.

## Chạy lại suy luận

Tạo các thư mục DEV_DIR, FRESH_DIR, CONFIRM_DIR, RANKER_DIR, VIEWS_DIR và
CONFIRM_RUN theo các bước trong [đối chứng trước](../vietnam_rtc_tta_20261119/README.md).
Để tái tạo quét tín hiệu yếu chạy `python scripts/evaluate_rtc_weak_echoes.py --help`.
Để chạy xView3, tải thêm kênh VH trên ba nhóm bằng
`PYTHONPATH=src python scripts/fetch_vn_reference_rtc.py SOURCE_DIR --band vh`.
Dùng Python 3.11, NumPy 2, PyTorch 2.8 và timm 1.0.22 cho đối chứng xView3.

```sh
git clone https://github.com/selimsef/xview3_solution.git XVIEW3_DIR
git -C XVIEW3_DIR checkout 558c15a979f889851b86a797518268944866e820
gh release download weights --repo selimsef/xview3_solution \
  --pattern val_only_TimmUnet_resnet34_77_xview --dir MODEL_DIR
PYTHONPATH=src python scripts/evaluate_rtc_xview3_transfer.py \
  --upstream XVIEW3_DIR --checkpoint MODEL_DIR/val_only_TimmUnet_resnet34_77_xview \
  --development DEV_DIR --held-out FRESH_DIR --confirmation CONFIRM_DIR \
  --cached-neural RANKER_DIR --tta VIEWS_DIR --confirmation-cache CONFIRM_RUN --out OUT_DIR
```

Mã ghi SHA-256 của từng manifest, checkpoint, cache đối chứng và bộ lựa chọn.
Ảnh nguồn từ [Sentinel-1 RTC](https://planetarycomputer.microsoft.com/dataset/sentinel-1-rtc).
Nhãn điểm từ [Ai2 Vessel Detection with Sentinels](https://github.com/allenai/vessel-detection-sentinels).
