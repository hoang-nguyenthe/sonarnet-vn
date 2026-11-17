# SonarNet - theo dõi hoàn thiện chặng 1

Nguồn yêu cầu: https://ai.tainangviet.vn/dashboard/final, đề cải tiến phiên bản 1.
Hạn hiển thị khi đối chiếu: 23:59 ngày 26/11/2026, giờ Việt Nam.

## Yêu cầu và bằng chứng

| Yêu cầu | Đã thực hiện trong mã nguồn | Việc cần hoàn tất |
|---|---|---|
| Không suy diễn từ dữ liệu thiếu | Trạng thái thiếu dữ liệu/không ghép/chờ xác minh; dữ liệu giả lập tắt mặc định; người rà soát, căn cứ và xác nhận gắn với bằng chứng; JSON/HTML xuất cùng trạng thái | Kiểm tra lại bản triển khai công khai |
| Ghép AIS theo độ tin cậy | Cổng tuổi AIS, sigma, khoảng cách kết hợp; từ chối cặp mơ hồ; 600 kịch bản mô phỏng đối chứng khoảng cách-only | Hiệu chỉnh ngưỡng trên AIS thực địa khi có dữ liệu; không tuyên bố mô phỏng là độ chính xác thực địa |
| Đánh giá SAR độc lập | Dữ liệu gốc LS-SSDD tải đủ; split riêng theo cảnh/vùng/ngày UTC; checksum từng tệp; cách ly ảnh tương tự; công cụ đánh giá baseline và YOLO cùng CPU | Đã đo holdout; còn kiểm chứng quy đổi mét/diện tích |
| Sản phẩm dễ kiểm tra | Trang Minh chứng cải tiến, 7 tình huống tương tác; cụm điểm bản đồ; chỉnh độ đậm radar; đã khôi phục 22.064 tệp và xác minh checksum | Kiểm tra bản triển khai công khai và bản xuất từ bản đó |
| Ba liên kết nộp bài HTTPS | Có repository và demo cũ | Cập nhật nguồn/demo, tải báo cáo mới, kiểm tra quyền truy cập; chưa nộp chính thức |

## Dữ liệu và huấn luyện lại

Lượt 17/11/2026: đã tải đủ 9.000 ảnh/nhãn; audit đạt sau khi cách ly 115 ảnh. Tập cuối: 3.491 train, 594 val, 3.000 test. Không còn cặp dHash <= 3 đi qua các tập trong cohort giữ lại. Chứng từ tại `reports/final/dataset_audit/`.

Huấn luyện hoàn tất lúc 02:14 ngày 17/11/2026 (giờ Việt Nam), dừng sớm ở epoch 24/40. Run: `/Volumes/SonarNetWork/runs/final_ls_ssdd_20261117`. Kiểm thử độc lập đã chạy xong, kết quả tại `reports/final/independent_sar/results.json`. Không cần chạy lại huấn luyện để sử dụng checkpoint.

Checkpoint mới: `assets/models/sonarnet_ls_ssdd_20261117.pt`; SHA256 `5b1eef4e8e45b17ea3f071285af5693dcb5ecc2c98d272264a570f58a1eb2bb1`. Có bản sao riêng trên SSD tại `/Volumes/T7/SonarNet-20261116/model-backup-20261117/`.

Trên 3.000 ảnh test / 2.378 nhãn, ngưỡng confidence 0,25 chọn bằng validation: precision 69,25%; recall 63,54%; AP50 0,6618; AP50-95 0,2389 (tích phân VOC). Có 1.511 TP, 671 FP, 867 FN; recall ảnh có đất liền 27,86%. CPU cùng phần cứng, 4 luồng: 61,47 ms trung vị, 65,05 ms p95. Không so trực tiếp AP mới với mAP Ultralytics lịch sử. Mô hình mới là ứng viên nghiên cứu, chưa thay hash mô hình trong kết quả bản đồ cũ.

Trang Minh chứng cải tiến đã hiển thị kết quả mới và giới hạn qua Chrome. Đã khôi phục 22.064 tệp ảnh/metadata của 5.516 ô từ revision ghim, kiểm tra Git blob SHA-1 từng tệp. Bộ test đầy đủ trên SSD: 121 passed, 11 subtests passed, 1 cảnh báo do hàm smoke cũ trả về tuple; không có lỗi (276,09 giây). Bằng chứng: reports/final/full-suite-20261117.txt.

Ổ trong hết chỗ trong quá trình làm việc. Bản tiếp tục hiện tại nằm tại /Volumes/SonarNetWork/sonarnet-final, ảnh công bố tại /Volumes/T7/SonarNet-20261116/published-assets. Bản Documents giữ lại nhưng không còn là bản mới nhất. Xem docs/FINAL_HANDOFF.md.

Đã tạo báo cáo 9 trang và slide 12 trang với kịch bản dự kiến 300 giây. File PowerPoint cuối đã import/render lại, 12 ảnh khớp pixel với bản đã kiểm tra. Chưa cập nhật source/demo công khai hoặc nộp portal.

Checkpoint SAR cũ đã bị xoá theo xác nhận của tác giả. Lượt mới khởi tạo từ YOLO11n COCO do Ultralytics phát hành, không coi là khôi phục chính xác kết quả cũ.

SSD: `/Volumes/T7/SonarNet-20261116/workspace.sparseimage`, vùng làm việc `/Volumes/SonarNetWork`.
Nếu máy khởi động lại, gắn bằng:

```sh
hdiutil attach -nobrowse /Volumes/T7/SonarNet-20261116/workspace.sparseimage
```

Ảnh và nhãn gốc: `ls_ssdd_raw/LS-SSDD-v1.0-OPEN` trong vùng làm việc.
`download_manifest.json` lưu CRC của ZIP và SHA256 từng tệp. Vì tải theo HTTP range, không có checksum toàn bộ ZIP; không được tự điền giá trị này.

Split đã định trước: train cảnh 01/02/03/04/05/08; val 10; test 11-15. Loại cảnh 06/09 gần vùng test và 07 gần vùng val. Ngày UTC lấy từ mã Sentinel-1 trong tài liệu gốc; ngày trong bảng bài báo khác UTC ở cảnh 08 và 13. Ảnh gần giống được cách ly theo ưu tiên giữ test, rồi val, rồi train. Nhật ký cách ly phải đi cùng báo cáo.

Nguồn: https://github.com/TianwenZhang0825/LS-SSDD-v1.0-OPEN ; https://doi.org/10.3390/rs12182997 . Tài liệu gốc hạn chế sử dụng thương mại; bản phân phối mã nguồn không kèm toàn bộ ảnh.

## Giới hạn cần giữ nguyên trong báo cáo

- Nhãn ven bờ là định nghĩa chính thức “ảnh có đất liền”, không phải khoảng cách tới bờ 500 m.
- Sai số khung bao không phải sai số chiều dài thân tàu hay sai số vị trí tuyệt đối đã đối chiếu AIS.
- Phải xác minh pixel spacing sau resampling trước khi báo đơn vị mét hoặc km²; không dùng độ phân giải radar thay cho pixel spacing.
- AP của bộ đánh giá nội bộ dùng tích phân VOC; không so trực tiếp với số Ultralytics cũ như thể cùng một phép đo.
- Kết quả mới phải qua đánh giá trước khi thay mô hình công khai. Không tự kết luận vi phạm IUU.
- Tên chuyên viên trong bản thử nghiệm là tự khai; chưa có xác thực tài khoản hoặc chữ ký số.

## Khai báo hỗ trợ AI cho lượt cải tiến này

Codex hỗ trợ đọc yêu cầu, chỉnh mã nguồn, viết kiểm thử, tải và kiểm tra dữ liệu công khai, chuẩn bị chia tập/huấn luyện và lập bảng bằng chứng. Nhật ký này mô tả các thao tác của lượt cải tiến hiện tại, không thay thế lịch sử prompt nguyên bản của các lượt phát triển đã mất. Các chỉ số chỉ được điền sau khi chương trình chạy; tên chuyên viên và xác nhận tác giả cần do người có trách nhiệm cung cấp.
