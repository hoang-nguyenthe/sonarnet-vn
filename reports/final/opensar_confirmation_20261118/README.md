# Kiểm tra mức lặp lại của nhận diện SAR ở ba cảnh mới

**Kết luận: không thay checkpoint của bản đồ.** Cùng mô hình YOLO11n học từ LS-SSDD, cấu hình ảnh 640 và ngưỡng confidence 0,10 không cho kết quả lặp lại ổn định khi chuyển sang các cảnh SLC khác. Đây là kết quả âm hữu ích, không phải chứng minh mọi hệ SAR không thể làm tốt hơn.

## Chọn trên validation, không chọn trên ba cảnh xác nhận

Trên 70 ô validation OpenSAR đã có, thử ảnh nguyên, tăng tương phản CLAHE, chia 4 ô chồng lấn và kết hợp nguyên ảnh/chia ô. Chọn tối đa nhãn khớp trong 1 km đến bờ, với số dự đoán không khớp không cao hơn 115% mức gốc (31 → tối đa 35). Ngưỡng và tiêu chí ghi vào `followup/protocol.json` trước suy luận. Phương án gốc 0,10 vẫn thắng: **10/17** nhãn trong 1 km, 31 điểm không khớp. Các phương án chia ô/tăng tương phản không cải thiện ở giới hạn này. Trên 503 ô test cũ đã dùng cho báo cáo trước, cấu hình giữ nguyên cho **96/298** nhãn khớp, **4/14** trong 500 m và 650 điểm không khớp; đây là phép chạy lại, không tính thành bằng chứng độc lập bổ sung. AP thay đổi nhẹ vì lần này lưu dự đoán confidence từ 0,01 thay cho 0,001.

Đối chứng CFAR kiểu vòng bảo vệ dùng pixel nước hợp lệ quanh mục tiêu để tính trung bình/độ lệch chuẩn, loại vùng lân cận mục tiêu khỏi ước lượng nền. Cảm hứng: [ESA SNAP Ocean Object Detection](https://eo4society.esa.int/wp-content/uploads/2022/01/OCEA01_ShipDetection_Trieste.pdf). Bản cài đặt này dùng điểm tương phản trên biên độ đã chuẩn hóa; không được gọi là triển khai SNAP chính thức hoặc khẳng định xác suất báo nhầm thực địa đã hiệu chuẩn. Cả sáu cấu hình CFAR đều không khớp nhãn validation ở IoU 0,50. Cấu hình giữ: cửa sổ bảo vệ 7, cửa sổ ngoài 29, ngưỡng 4,4; trên tập test cũ chỉ khớp 1/298 và có 21 điểm không khớp.

## Ba cảnh xác nhận mới

- Nguồn OpenSAR Insight revision `e90a0c0465cfb8484b4f356ef968d976054f453a`. Ba cảnh nằm trong thư mục `train` của nhà phát hành, nhưng SonarNet **không dùng chúng để huấn luyện hoặc chỉnh ngưỡng**. Chọn bằng metadata trước suy luận: loại các cảnh chung ngày hoặc cách footprint đã dùng không quá 20 km. Kiểm tra SHA-256 pixel/dHash giữa các ô mới và 573 ô đã dùng không phát hiện cặp tương tự trong ngưỡng kiểm. Không tuyên bố bao phủ mọi cách ảnh có thể giống nhau.
- Từ 424 ô ở 3 cảnh đạt sàng lọc, loại 189 ô thiếu pixel hợp lệ, 16 ô có không quá 1 km² biển và 1 ô nhãn lỗi. Còn **218 ô, 147 nhãn HIGH/MEDIUM**, **2.606,85 km² biển ước tính** theo phương pháp đã công bố trong báo cáo OpenSAR trước. Không trộn chung với tập 503 ô.

| Ngày UTC | Ô ảnh | Nhãn khớp / tổng | Không khớp nhãn |
|---|---:|---:|---:|
| 21/04/2020 | 79 | 0/56 | 10 |
| 11/05/2020 | 92 | 3/67 | 22 |
| 06/07/2020 | 47 | 0/24 | 4 |
| **Tổng YOLO** | **218** | **3/147** | **36** |

YOLO recall 2,04%, precision 7,69%, **1/35** nhãn trong 500 m đến bờ; 0,0138 dự đoán không khớp nhãn/km². Con số trên diện tích thấp đi cùng việc bỏ sót 144/147 nhãn, không phải cải thiện. CFAR 0/147, 1 điểm không khớp. Sai lệch tâm hộp YOLO trung vị 24,69 m chỉ trên **3** hộp khớp; không dùng để suy rộng độ chính xác vị trí. Sai lệch giữa phép nội suy góc và tọa độ của chính nhãn trung vị 55,85 m. Không có đối chiếu GPS độc lập, chiều dài thân tàu hoặc xác nhận nghề nghiệp mới. Các mốc tương ứng tháng 4, tháng 5 và tháng 7 năm 2020, không phải dữ liệu trực tiếp.

## Chẩn đoán, không tối ưu lại trên tập mới

Giữ ngưỡng 0,10 và nới IoU từ 0,50 xuống 0,25 thấy 14/147 nhãn khớp, thay vì 3/147. Hạ cả ngưỡng confidence về 0,01 cho 15/147 ở IoU 0,50 nhưng sinh 160 điểm không khớp. Ngay với cả hai điều kiện nới lỏng, chỉ đạt 34/147. Nghĩa là lỗi không chỉ do ngưỡng khắt khe hoặc sai hình học hộp; chưa tách được phần do chất lượng nhãn và phần do suy giảm chuyển miền. Không dùng số đo hậu kiểm để chọn cấu hình vận hành.

Nên bổ sung tập training từ nhiều vùng bờ, giữ set test mới độc lập theo footprint/ngày, rồi thử huấn luyện thích nghi SLC với nhãn có xác nhận; không trộn các cảnh West Africa chồng địa lý với test cũ để làm đẹp kết quả. Giữ cảnh báo rõ trên bản đồ rằng vùng 500 m không được đánh dấu và thiếu điểm không cho phép suy ra không có tàu.

## Tái lập

Tệp `selection.json` chứa chính sách và checksum gói ảnh train SLC gốc; `confirmation_manifest.json.gz` chứa manifest đã chuẩn bị (giải nén nguyên byte để so SHA-256). `protocol.json` khóa cấu hình trước khi đọc pixel xác nhận; `pixel_audit.json` lưu lần kiểm trùng. Dùng cùng môi trường và cache OpenSAR đã chỉ trong `../opensar_geo_20261118/README.md` và thêm OpenCV như trong môi trường huấn luyện.

```sh
python scripts/evaluate_sar_recall_candidates.py --data DATA --audit AUDIT_CU --pixel-audit PIXEL_AUDIT_CU --weights WEIGHTS --output MOT_RUN_MOI --run-test
python scripts/prepare_opensar_confirmation.py --data DATA --audit AUDIT_CU --output MANIFEST_MOI
python scripts/confirm_opensar_operating_point.py --data DATA --audit AUDIT_CU --fresh MANIFEST_MOI --prior MOT_RUN_MOI --weights WEIGHTS --output XAC_NHAN_MOI
python scripts/diagnose_sar_recall.py --manifest MANIFEST_MOI/confirmation_manifest.json --audit XAC_NHAN_MOI/pixel_audit.json --predictions XAC_NHAN_MOI/yolo_predictions.json.gz --output DOI_CHIEU.json
```

Ảnh và nhãn: [OpenSAR Insight](https://huggingface.co/datasets/opensar-insight/vessel-detection-dataset), Indra Space / INTA / Universidad de Alcalá, ESA Φ-lab, kho MIT. Contains modified Copernicus Sentinel data. Không kèm TIFF gốc; tài liệu chỉ cung cấp chỉ số/nhãn/metadata cần thiết để kiểm chứng.
