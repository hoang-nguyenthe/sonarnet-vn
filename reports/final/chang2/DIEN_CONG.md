# Điền cổng Chặng 2 SonarNet

| Trường trên cổng | Giá trị |
| --- | --- |
| Liên kết mã nguồn | <https://github.com/hoang-nguyenthe/sonarnet-vn/tree/chang-2> |
| Liên kết sản phẩm chạy thử | <https://hoang-nguyenthe.github.io/sonarnet-vn/chang2/> |
| Liên kết báo cáo cải tiến PDF/Word | <https://hoang-nguyenthe.github.io/sonarnet-vn/chang2/SonarNet_Bao_cao_cai_tien_Chang2.pdf> |
| Link minh chứng cải tiến | <https://hoang-nguyenthe.github.io/sonarnet-vn/chang2/evidence.html> |

**Hướng dẫn chạy thử**\
Mở ứng dụng Chặng 2, chọn **So sánh hai giao diện trên 200 ca**. Để thực hành quy trình, mở **Thử quy trình với 16 ca**. Người rà chọn nhóm kinh nghiệm, nhập mã R01–R04, hoàn thành hai lượt và tải phiếu JSON. Trang minh chứng có báo cáo, kết quả theo seed và lệnh tái lập. Không cần tài khoản dùng thử.

**Khai báo AI và nguồn**\
Đội dùng OpenAI Codex hỗ trợ viết mã đối chứng, bài thử, kiểm thử và trình bày báo cáo. Mô-đun hành vi và ghép AIS tái sử dụng mã SonarNet, XGBoost, NumPy, SciPy và scikit-learn. Đối chứng gồm mô phỏng nhiều seed và hai nguồn AIS có nhãn, gồm Đan Mạch (Song Wu, 2022, DOI 10.5281/zenodo.7283281) và Global Fishing Watch Training Data, cùng CC BY 4.0. Phép đối chứng chính dùng 10 seed, 7.200 cảnh ghép và 5 điều kiện hành vi. Thử riêng 12 tổ hợp trên 4.400 cảnh để đo số ca đưa vào hàng ưu tiên. Độ bền trên AIS thật được kiểm tra qua 25 lượt giữ riêng tàu. Có 32 phiên đối chứng trình duyệt với quy tắc giả lập. Hai giao diện được đối chiếu trên 200 ca cân bằng (4 hành vi × 5 mức chất lượng × 10 ca) và 8 quy tắc. Thời gian là 3.200 cặp thao tác tự động, ghép theo ca, quy tắc và vị trí lượt. Bộ thử thách 16 ca giữ riêng. Khảo sát chỉ tổng hợp phiếu tự nguyện từ người tham gia thật. Phạm vi và giới hạn ghi trong báo cáo.

**Khi mất mạng**\
Mở `demo-offline/chang2/index.html` bằng Chrome. Bài thử, bảng và báo cáo chạy từ các tệp đi kèm. Phiếu JSON được tải xuống máy. Báo cáo trình bày cách rà ở hai giao diện và kết quả kiểm tra trình duyệt tự động. Chưa đo thời gian ra quyết định của chuyên viên.

[Cổng BTC](https://ai.tainangviet.vn/dashboard/final)
