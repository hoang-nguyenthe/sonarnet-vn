# Trạng thái SonarNet Chặng 1

Xem [đề, hướng dẫn và ba liên kết nộp](../NOP_CHANG_1.md). Mốc đối chiếu là đề riêng Phiên bản 1, hạn hiển thị 23:59 ngày 26/11/2026, giờ Việt Nam.

## Phần đã kiểm tra

| Nội dung | Minh chứng đang dùng |
| --- | --- |
| Thiếu AIS, AIS mâu thuẫn, ca cần xác minh | Phần Minh chứng có hồ sơ ảnh SAR thật thiếu AIS và kịch bản thử thuật toán. Luồng Quan sát cho phép ghi chú và xuất hồ sơ ảnh có mã băm. |
| Ghép với độ bất định | So khoảng cách, tuổi bản tin, bất định và phương tiện cạnh tranh. Trên 3.722 bản tin NOAA giữ riêng, cặp sai 32 → 0 và cặp đúng 898 → 879, so với cổng lọc trước có biên 100 m. Trên cảnh SAR cùng giờ có bốn mốc vị trí để đối chiếu. |
| SAR có nhãn và số đo địa lý | Các bộ kiểm định tách nhau theo câu hỏi. Xem số liệu theo kích thước bộ dữ liệu, độ trễ, mật độ điểm chưa khớp và sai lệch tâm hộp trong báo cáo. |
| Ảnh ven biển Việt Nam | Trên 12 lượt chụp, ngưỡng 0,05 tăng từ 80/152 lên 96/152 nhãn khớp khi số ứng viên rà tăng từ 116 lên 191. Cùng đúng 116 lượt rà, cả hai ngưỡng đều khớp 80/152. |
| Recall ở cùng số lượt rà | Trên 12 lượt chụp, lọc điểm trong 35 m tăng từ 80/152 lên 82/152 ở 116 lượt rà. Chia ô chồng lấn tăng từ 96/152 lên 102/152 ở 191 lượt rà. Hai cảnh Bắc Trung Bộ bổ sung giữ nguyên số nhãn khớp. |
| VV và VH | Chấm 12 lượt trên phần ảnh có cả hai kênh. Cùng 114 ứng viên, cách xếp hạng hiện tại khớp 78/150 và hai cấu hình điều chỉnh khớp 77/150. Có hình đối chiếu từ một ô thật. |
| Khả năng chạy và tải | Streamlit có mục Minh chứng mở trực tiếp. ZIP có hồ sơ mẫu, mã, số liệu và PDF. Lệnh kiểm tra sau giải nén nằm trong hướng dẫn nộp. |

Số chi tiết và bảng từng cảnh nằm trong [PDF cải tiến](../output/pdf/SonarNet_Bao_cao_Chang1_Giu_cap_AIS_20261118.pdf) và [tệp đối chứng](../reports/final/). Quy trình mở ca và đọc chỉ số nằm trong [hướng dẫn demo](DEMO_RUNBOOK.md).

## Phần cần xác nhận

- Kết quả khớp điểm trên ảnh Việt Nam dùng nhãn công khai Ai2. Kết luận về danh tính, kích thước thân tàu và sai số vị trí tuyệt đối cần nguồn xác nhận độc lập tương ứng.
- Các ảnh, điểm đã ghép và hồ sơ xuất hỗ trợ rà soát. Người có chuyên môn cần ghi căn cứ và tự xác nhận ca. Demo lưu tên tự khai và chưa xác thực vai trò bằng tài khoản.
- Chủ dự án đối chiếu khai báo AI theo công cụ đã dùng, xác nhận cam kết trên cổng và thực hiện nộp chính thức. Biên nhận từ cổng mới xác nhận việc nộp.
