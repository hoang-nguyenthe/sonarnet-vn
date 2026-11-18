# Huấn luyện YOLO trên Sentinel-1 SLC VV

## Kết quả và cách sử dụng

| Phép đo | Phương pháp | Nhãn khớp | Không khớp nhãn | Trong 500 m từ bờ | Điểm không khớp/km² |
| --- | --- | ---: | ---: | ---: | ---: |
| 218 ô / 3 cảnh | YOLO LS-SSDD | 3/147 | 36 | 1/35 | 0,0138 |
| 218 ô / 3 cảnh | YOLO học trên SLC VV | 51/147 | 211 | 11/35 | 0,0809 |
| 218 ô / 3 cảnh | Danh sách giới hạn theo diện tích | 36/147 | 93 | 6/35 | 0,0357 |
| 218 ô / 3 cảnh | Cùng giới hạn, ưu tiên ven bờ | 37/147 | 92 | 7/35 | 0,0353 |
| 196 ô / Biển Bắc | CFAR vòng nền | 0/146 | 1 | 0/14 | 0,0004 |
| 196 ô / Biển Bắc | YOLO học trên SLC VV | 69/146 | 943 | 2/14 | 0,3674 |
| 196 ô / Biển Bắc | Danh sách giới hạn theo diện tích | 20/146 | 108 | 0/14 | 0,0421 |
| 196 ô / Biển Bắc | Cùng giới hạn, ưu tiên ven bờ | 21/146 | 107 | 2/14 | 0,0417 |

Mật độ dùng diện tích biển hợp lệ theo từng lượt chụp, ước tính từ hộp ảnh và GSHHG. Một điểm không khớp nhãn chưa được xác nhận là báo nhầm ngoài thực địa. Các hộp nguồn có thể lệch hoặc chưa đầy đủ. Ngưỡng IoU 0,50 áp dụng cho nhãn HIGH/MEDIUM. Tâm khung YOLO trung vị lệch 18,54 m trên 51 hộp khớp ở ba cảnh, 19,91 m trên 69 hộp khớp ở Biển Bắc. Kết quả này chỉ so với hộp nhãn. Độ trễ trung vị trên CPU 4 luồng lần lượt 43,02 ms và 44,01 ms/ô, gồm chuẩn hóa và lọc vùng chấm, bỏ thời gian đọc ảnh. Xem `results.json` để lấy p95, kích thước hộp hai trục và bảng từng cảnh.

Hai danh sách giới hạn là phép phát lại sau kiểm thử với cùng dự đoán đã khóa. Mỗi cảnh giữ tối đa ⌊0,05 × diện tích biển hợp lệ tính bằng km²⌋ ứng viên theo điểm mô hình. Bản ưu tiên ven bờ dành trước tối đa 20% số lượt cho tâm dự đoán trong dải 500 m của GSHHG rồi bổ sung theo điểm. Khoảng cách tính từ hình học, không dùng nhãn để chọn ứng viên. Giữ riêng kết quả trước và sau giới hạn để thấy số nhãn mất đi. Chưa dùng mô hình SLC VV cho bản đồ Copernicus hiện hành.

## Phân tập dữ liệu và chọn ngưỡng

- Nguồn [OpenSAR Insight, bản e90a0c0](https://huggingface.co/datasets/opensar-insight/vessel-detection-dataset/tree/e90a0c0465cfb8484b4f356ef968d976054f453a), SLC VV phức 512 × 512. Biên độ chuẩn hóa log1p và phân vị 1–99,9. Bộ lọc loại ảnh có trên 5% pixel đầu vào không hợp lệ và giữ ảnh nền đạt yêu cầu. Tập học 1.669 ô / 7 cảnh, gồm 1.020 hộp và 1.086 ô nền. Tập chọn ngưỡng 48 ô / 1 cảnh, có 29 nhãn trong vùng chấm sau khi gán phần biển chồng nhau.
- Cách ly 6 ô học trong khoảng 20 km tới vùng chọn ngưỡng. Ngày chụp tách giữa tập học, tập chọn ngưỡng và tập kiểm tra. SHA-256 pixel và dHash ≤ 3 không tìm thấy cặp trùng giữa các tập mới đã kiểm. Chi tiết ở `data_policy.json` và `audit.json`. Không dùng hai cảnh Tây Phi đã chấm ở lượt trước vì vùng của chúng gần tập học mới.
- YOLO11n khởi tạo từ COCO. M1 Pro, PyTorch 2.8.0, Ultralytics 8.3.253. Dừng sớm sau 9/12 epoch. So checkpoint AP tốt nhất và checkpoint cuối trên cùng tập chọn ngưỡng, khóa phương án có F1 IoU 0,50 cao nhất. Chọn checkpoint cuối, ảnh 512, ngưỡng 0,025. SHA-256 checkpoint `b610df7fb3b732646540257194e075b52012e434755e77595227a9dde9a31a1b`.
- Ba cảnh so sánh trực tiếp đã dùng để phát hiện vấn đề của mô hình cũ. Chúng không đi vào huấn luyện hoặc chọn ngưỡng cho mô hình mới. Cảnh Biển Bắc 28/09/2020 chưa đem ra chấm trước lần này và tách vùng với tập học mới. So với CFAR cùng CPU. Dòng LS-SSDD không dùng làm đối chứng độc lập ở Biển Bắc vì lịch sử vùng huấn luyện của nó giao vùng ở đó.

## Tái lập

Dùng cấu trúc cache và các gói nguồn ghi trong `../opensar_geo_20261118/README.md`, cùng `train_patches.tar.zst`. Chuẩn bị manifest của ba cảnh bằng `scripts/prepare_opensar_confirmation.py`. Môi trường hình học dùng pyproj, shapely, pyshp, tifffile và zstd. Gói này chứa manifest nén, checksum và kết quả đầy đủ. Ảnh thô lấy từ kho nguồn.

```sh
python scripts/prepare_opensar_adaptation.py --data DATA \
  --source-audit AUDIT_GOC/source_screen.json --diagnostic BA_CANH --out FIT
python scripts/train_final_sar.py --data FIT/data.yaml --output RUN \
  --initial yolo11n.pt --epochs 12 --batch 16 --imgsz 512
python scripts/evaluate_opensar_adaptation.py --data DATA --adaptation FIT \
  --diagnostic BA_CANH --candidate RUN/weights/best.pt \
  --reference assets/models/sonarnet_ls_ssdd_20261117.pt --out EVAL
python scripts/evaluate_sar_review_budget.py --data DATA --adaptation FIT \
  --diagnostic BA_CANH --evaluation EVAL --nearshore-share .20 --out UU_TIEN_VEN_BO
python scripts/export_opensar_adaptation_examples.py --data DATA --adaptation FIT \
  --diagnostic BA_CANH --evaluation EVAL --out ANH_KIEM_TRA
python scripts/plot_opensar_adaptation_geography.py --screen AUDIT_GOC/source_screen.json \
  --policy FIT/data_policy.json --coast DATA/gshhg-shp-2.3.7.zip --output scene_split.png
```

Nguồn ảnh và nhãn do Indra Space, INTA và Universidad de Alcalá phát hành trong dự án OpenSAR Insight do ESA Φ-lab tài trợ. Contains modified Copernicus Sentinel data. Đường bờ dùng GSHHG 2.3.7.
