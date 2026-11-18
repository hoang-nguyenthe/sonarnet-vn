# Đối chứng VV và VH với đúng số lượt rà

Dùng các cảnh đã kiểm tra trong đối chứng xếp hạng Việt Nam. Lấy hai kênh VV và VH của cùng mục Sentinel-1 RTC qua [Microsoft Planetary Computer](https://planetarycomputer.microsoft.com/dataset/sentinel-1-rtc). Ghép cửa sổ bằng mã ô, tọa độ lưới, mục STAC và SHA-256. Cả hai cách xếp hạng dùng cùng ứng viên gốc ở ngưỡng 0,05. Các đặc trưng gồm đỉnh và tương phản radar cục bộ, độ phân tán nền và cờ pixel hợp lệ. Hồi quy logistic điều chỉnh logit điểm gốc với các trọng số 0,125, 0,25, 0,5 và 1.

Chọn trọng số riêng cho từng nhóm bằng kiểm tra chéo giữ lại từng lượt chụp trong năm lượt phát triển. Hai nhóm tính điểm cùng chọn 0,125. Trên tập đối chứng, đo lại bằng nhãn điểm Ai2 và phép ghép một–một tối đa trong 100 m. Một cửa sổ không tải được kênh VH và được bỏ khỏi mọi cách đo. Kết quả chấm trên 12 lượt chụp, 85 cửa sổ và 150 điểm nhãn. Mỗi cách xếp hạng giữ đúng 114 ứng viên, bằng số ứng viên của bản đồ trong miền chấm chung.

| Cách xếp hạng | Nhãn khớp | Điểm cần rà |
| --- | ---: | ---: |
| Bản đồ hiện tại | **78/150** | 114 |
| Điều chỉnh theo VV | 77/150 | 114 |
| Điều chỉnh theo VV và VH | 77/150 | 114 |

Phép thử chưa cho thấy lợi ích từ đặc trưng VH ở cùng số điểm rà. Các cấu hình vẫn dùng cùng ứng viên VV. Kết quả không đánh giá một detector huấn luyện trực tiếp bằng cả hai kênh hoặc dự đoán dựa trên VH riêng. Lượt đối chứng dùng 12 cảnh đã chấm ở bước trước, được giữ ngoài quá trình khớp trọng số. Phạm vi bị thu hẹp một ô nên số đếm gốc khác 80/152 trong đối chứng VV đầy đủ.

## Tái lập

Từ dữ liệu đầu vào và cache đặc trưng cùng kết quả trong vietnam_rtc_ranking_20261118, lấy thêm kênh VH. Tiếp tục dùng các tệp NPZ VV nguyên gốc. Môi trường cần các thư viện trong mục đối chứng RTC và scikit-learn 1.9.1.

```bash
export PYTHONPATH=src
python scripts/fetch_vn_reference_rtc.py DEV_DIR --band vh
python scripts/fetch_vn_reference_rtc.py FRESH_DIR --band vh
OMP_NUM_THREADS=2 python scripts/evaluate_polarimetric_ranking.py --dev DEV_DIR --test FRESH_DIR --cache RANK_OUTPUT --output OUT_DIR
```

protocol.json ghi checksum các manifest và cache đặc trưng. selection.json lưu kết quả phát triển và cấu hình khóa. results.json có số đếm từng lượt chụp và số ô thiếu VH. Nếu nguồn ảnh phục hồi cửa sổ bị thiếu, tập chấm của lượt tái lập sẽ có thêm ô và số đếm có thể khác.
