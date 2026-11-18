# Huấn luyện tiếp detector SLC VV ở 640 px

Khởi tạo từ checkpoint SLC VV 512 px đã phát hành. Huấn luyện tiếp sáu epoch ở 640 px, batch 12 trên Apple MPS, giữ nguyên tập học SLC 1.669 ô và vùng kiểm tra. Chọn checkpoint và cấu hình suy luận trên 48 ô phát triển trước khi chấm lại bốn cảnh đã báo cáo. Phương án khóa dùng checkpoint tốt nhất theo AP, đọc hai tỷ lệ và lật ngang, ngưỡng 0,005. Đây là đối chứng lại trên ảnh SLC của OpenSAR Insight. Checkpoint này chưa được dùng để tạo bản đồ.

| Nhóm | Điều kiện rà | Nhãn khớp trước → sau | Điểm không khớp trước → sau |
| --- | --- | ---: | ---: |
| Ba cảnh · 147 nhãn | Mọi điểm qua ngưỡng | 60 → 67 | 837 → 1.307 |
| Ba cảnh · 147 nhãn | Cùng giới hạn | 38 → 38 | 91 → 91 |
| Biển Bắc · 146 nhãn | Mọi điểm qua ngưỡng | 87 → 93 | 1.453 → 1.866 |
| Biển Bắc · 146 nhãn | Cùng giới hạn | 22 → 28 | 106 → 100 |

Mức trần 1 ứng viên/20 km² mỗi cảnh. Các nhóm dùng cùng dữ liệu chấm và cùng ngưỡng IoU 0,50. Điểm không khớp nhãn vẫn cần rà. Dải 500 m tới bờ, dưới cùng giới hạn, ba cảnh giảm 7/35 → 6/35, Biển Bắc tăng 0/14 → 1/14. Trung vị CPU 4 luồng là 223–235 ms/ô, chưa tính đọc ảnh.

Để tái lập, dùng tập đã kiểm tra từ mục opensar_adaptation_20261118. Chạy scripts/train_final_sar.py với --epochs 6 --batch 12 --imgsz 640 và --initial trỏ tới assets/models/sonarnet_slc_vv_20261118.pt. So sánh bằng scripts/evaluate_sar_finetune.py với --training, --adaptation, --control, --diagnostic, --data và --out. Cờ --control trỏ đến thư mục thí nghiệm đa tỷ lệ đã khóa. Checkpoint đã chọn nằm trong assets/models/sonarnet_slc_vv_640_20261118.pt. Mã băm chính xác trong protocol.json.
