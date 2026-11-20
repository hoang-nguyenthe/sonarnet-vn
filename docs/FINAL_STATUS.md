# Trạng thái SonarNet Chặng 1

Xem [đề, hướng dẫn và ba liên kết nộp](../NOP_CHANG_1.md). Mốc đối chiếu là đề riêng Phiên bản 1, hạn hiển thị 23:59 ngày 26/11/2026, giờ Việt Nam.

## Phần đã kiểm tra

| Nội dung | Minh chứng đang dùng |
| --- | --- |
| Thiếu AIS, AIS mâu thuẫn, ca cần xác minh | Phần Minh chứng có hồ sơ ảnh SAR thật thiếu AIS và kịch bản thử thuật toán. Luồng Quan sát cho phép ghi chú và xuất hồ sơ ảnh có mã băm. |
| Ghép với độ bất định | So khoảng cách, tuổi bản tin, bất định và phương tiện cạnh tranh. Trên 3.722 bản tin NOAA giữ riêng, cặp sai 32 → 0 và cặp đúng 898 → 879, so với cổng lọc trước có biên 100 m. Trên cảnh SAR cùng giờ có bốn mốc vị trí để đối chiếu. |
| Đối chứng SAR–AIS sáu lượt chụp | Có 410 ứng viên, 17 mốc gần giờ và 8 mốc ít dịch chuyển. Cổng giữ cặp đồng thuận 6/17 và 6/8. Số liệu chi tiết và ảnh nguồn ở trang 13. |
| SAR có nhãn và số đo địa lý | Các bộ kiểm định tách nhau theo câu hỏi. Xem số liệu theo kích thước bộ dữ liệu, độ trễ, mật độ điểm chưa khớp và sai lệch tâm hộp trong báo cáo. |
| Ảnh ven biển Việt Nam | Trên 12 lượt chụp, ngưỡng 0,05 tăng từ 80/152 lên 96/152 nhãn khớp khi số ứng viên rà tăng từ 116 lên 191. Cùng đúng 116 lượt rà, cả hai ngưỡng đều khớp 80/152. |
| Recall ở cùng số lượt rà | Trên 12 lượt chụp, lọc điểm trong 35 m tăng từ 80/152 lên 82/152 ở 116 lượt rà. Chia ô chồng lấn tăng từ 96/152 lên 102/152 ở 191 lượt rà. Hai cảnh Bắc Trung Bộ bổ sung giữ nguyên số nhãn khớp. |
| Đối chứng thêm về recall | Thử heatmap từ nhãn tâm, tinh chỉnh YOLO, đổi dải dB, dịch tâm ứng viên và phân bổ lượt giữa các cảnh. Phép thử khóa theo tập phát triển đạt cao nhất trong nhóm mới 80/152 ở 116 lượt rà và 100/152 ở 191 lượt rà. |
| Mô hình xView3 và quét tín hiệu yếu | Cùng 191 lượt rà, xView3 phối hợp YOLO khớp 103/152 so với 102/152. Ở Bắc Trung Bộ tăng từ 6/8 lên 8/8 cùng 10 lượt rà. xView3 chạy riêng giảm từ 82/152 xuống 70/152 ở mức 116 lượt rà. Quét tín hiệu yếu không cải thiện số khớp ở hai mức đã khóa. Trang 14. |
| Thêm lượt rà và đối chứng bằng AIS | Ở 12 lượt ảnh Việt Nam, tăng 191 lên 234 lượt rà vẫn khớp 103/152 nhãn. Trên 13 mốc AIS ít dịch chuyển chọn trước ở sáu lượt chụp, chia ô chồng lấn cho 9/13 so với 10/13 ở 410 lượt rà, và 13/13 so với 12/13 ở 1.483 lượt rà. |
| xView3 đối chứng với AIS | Trên cùng 13 mốc, kết hợp xView3 vào danh sách hẹp tăng 10/13 lên 11/13 với 410 lượt rà. Mức 1.483 lượt đạt 13/13 ở cả hai phương án. Khóa trọng số, ảnh và số lượt rà theo cảnh. |
| Thử xếp hạng theo đồng thuận hai mô hình | Phép thử giữ đầu danh sách khớp 106/152 so với 103/152 ở 191 lượt rà, 81/152 so với 82/152 ở 116 lượt rà. Bắc Trung Bộ cùng khớp 8/8 ở 10 lượt rà. Đây là khảo sát trên dữ liệu lịch sử đã dùng. Xem [cách chấm lại](../reports/final/vietnam_rtc_transfer_20261119/rank_fusion/README.md). |
| VV và VH | Chấm 12 lượt trên phần ảnh có cả hai kênh. Cùng 114 ứng viên, cách xếp hạng hiện tại khớp 78/150 và hai cấu hình điều chỉnh khớp 77/150. Có hình đối chiếu từ một ô thật. |
| Khả năng chạy và tải | Streamlit có mục Minh chứng mở trực tiếp. ZIP có hồ sơ mẫu, mã, số liệu và PDF. Lệnh kiểm tra sau giải nén nằm trong hướng dẫn nộp. |

Số chi tiết và bảng từng cảnh nằm trong [PDF cải tiến](../output/pdf/SonarNet_Bao_cao_Chang1_Giu_cap_AIS_20261118.pdf) và [tệp đối chứng](../reports/final/). Quy trình mở ca và đọc chỉ số nằm trong [hướng dẫn demo](DEMO_RUNBOOK.md).

## Kiểm tra đường dẫn chấm

[Lộ trình Vòng Chung kết](https://ai.tainangviet.vn/lo-trinh) yêu cầu sản phẩm ổn định ít nhất 48 giờ trước khi chấm. [Lịch sử kiểm tra công khai](https://github.com/hoang-nguyenthe/sonarnet-vn/actions/workflows/check-web-awake.yml) ghi kết quả theo thời điểm. Bài kiểm tra định kỳ mở đúng trang Minh chứng, chờ kết nối Streamlit ổn định, tải PDF và hồ sơ mẫu rồi so SHA-256 của hai tệp với mã nguồn.

Lịch kiểm tra đặt cách nhau 3 giờ. GitHub có thể khởi chạy trễ nên cần đọc thời gian chạy thực trong từng lượt. Ngày 20/11 lúc 03:36 giờ Việt Nam, một lượt mở trang chủ đã thất bại sau khi yêu cầu đánh thức ứng dụng. Các lượt kiểm tra thành công sau đó xác nhận từng thời điểm. Mốc 48 giờ vẫn cần đối chiếu với thời điểm chấm chính thức. [Lượt kiểm tra bị gián đoạn](https://github.com/hoang-nguyenthe/sonarnet-vn/actions/runs/44610305978)

[Trang minh chứng dự phòng](https://hoang-nguyenthe.github.io/sonarnet-vn/) phục vụ báo cáo, hồ sơ mẫu, ảnh đối chiếu và bảng recall. Khi Streamlit đang khởi động, có thể mở ngay bằng chứng trên trang này.

## Phần cần xác nhận

- Kết quả khớp điểm trên ảnh Việt Nam dùng nhãn công khai Ai2. Kết luận về danh tính, kích thước thân tàu và sai số vị trí tuyệt đối cần nguồn xác nhận độc lập tương ứng.
- Các ảnh, điểm đã ghép và hồ sơ xuất hỗ trợ rà soát. Người có chuyên môn cần ghi căn cứ và tự xác nhận ca. Demo lưu tên tự khai và chưa xác thực vai trò bằng tài khoản.
- Chủ dự án đối chiếu khai báo AI theo công cụ đã dùng, xác nhận cam kết trên cổng và thực hiện nộp chính thức. Biên nhận từ cổng mới xác nhận việc nộp.
