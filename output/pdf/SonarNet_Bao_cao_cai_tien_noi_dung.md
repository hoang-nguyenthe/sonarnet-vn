SONARNET / BẢNG C / BÁO CÁO CẢI TIẾN

Từ một điểm sáng<br/>đến bằng chứng<br/>có thể kiểm tra.

Quan sát biển bằng SAR và đối chiếu AIS có kiểm soát độ tin cậy. Hỗ trợ người phân tích nhận biết điều cần xem xét, đồng thời biết khi nào dữ liệu chưa đủ để kết luận.

3.000 ảnh SAR thật | 600 kịch bản AIS | 24 epoch

Kiểm thử độc lập theo cảnh, nhóm vùng và ngày UTC. | 1.200 điểm mô phỏng, đếm cả ghép đúng, ghép sai và từ chối. | Huấn luyện lại YOLO11n; checkpoint tốt nhất chọn bằng validation.

Điều thay đổi có ý nghĩa nhất

SonarNet chuyển từ việc trình bày một kết quả sang trình bày <b>kết quả cùng điều kiện tin cậy của nó</b>. Thiếu AIS được ghi là thiếu dữ liệu; ứng viên mơ hồ được giữ lại để xác minh; mỗi bản xuất mang theo dấu vết ảnh nguồn, mô hình và nhận xét của người rà soát.

Kết quả đã đo, giới hạn đã thấy

YOLO mới đạt precision <b>69,25%</b>, recall <b>63,54%</b> và AP50 <b>0,6618</b> trên tập kiểm thử riêng. Tuy nhiên, recall ở nhóm ảnh có đất liền chỉ <b>27,86%</b>. Đây là hạn chế thực chất cần ưu tiên giải quyết, không thể che bằng chỉ số trung bình.

Bản bằng chứng kỹ thuật: 17/11/2026. Chưa xác nhận hoàn tất nộp cổng BTC. Một số chỉ tiêu vật lý và liên kết công khai còn cần hoàn tất; xem trang cuối.


---


CHẶNG 1 / 02

Đối chiếu yêu cầu BTC

Đối chiếu đề cải tiến phiên bản 1 tại cổng vòng chung kết. Hạn hiển thị khi đọc ngày 16/11/2026: 23:59 ngày 26/11/2026 (giờ Việt Nam). Bảng dưới phân biệt phần đã có bằng chứng và phần còn mở.

Yêu cầu | Thực hiện / bằng chứng | Trạng thái

Không suy diễn từ dữ liệu thiếu | Bốn trạng thái nhất quán; thiếu AIS, thiếu kích thước, quá cũ và độ bất định được xử lý riêng. Demo tương tác và kiểm thử tự động. | Đã triển khai cục bộ

Xác nhận bởi người có chuyên môn | Người rà soát, quyết định, căn cứ, thời điểm và xác nhận gắn với mã bằng chứng; nguồn đổi thì xác nhận mất hiệu lực. | Đã có quy trình; tên còn tự khai

Ghép có tuổi dữ liệu và sigma | Kalman trả độ bất định; cổng thời gian, vị trí, khoảng cách; từ chối mơ hồ. Đối chứng 600 kịch bản / 1.200 điểm. | Đã đo bằng mô phỏng

SAR độc lập, tách cảnh/vùng/ngày | 3.491 train / 594 val / 3.000 test; audit SHA256, trùng pixel và dHash; baseline cùng CPU; bảng theo cảnh và ảnh lỗi. | Đã huấn luyện và đo

Báo nhầm / diện tích, sai số vị trí và kích thước | Đã có số đếm, báo nhầm/triệu pixel, sai số pixel. Chưa kiểm chứng phép quy đổi sau hiệu chỉnh hình học và resampling. | Chưa đủ đơn vị mét/km²

Ba liên kết HTTPS | Mã nguồn, demo chạy được và báo cáo cải tiến PDF/Word. Phải kiểm tra truy cập sau khi cập nhật. | Chưa cập nhật / nộp bản mới

Không đánh dấu “đạt” chỉ vì đã viết công cụ. Các mục cần phép đo hoặc kiểm tra truy cập chỉ hoàn tất khi có kết quả chạy và bằng chứng tương ứng.


---


CHẶNG 1 / 03

Không để khoảng trống dữ liệu thành kết luận

Một điểm sáng SAR và một bản tin AIS đều có điều kiện quan sát riêng. Ảnh radar không tự xác nhận danh tính; AIS có thể thiếu, đến trễ hoặc có sai số. Thiết kế mới giữ những khác biệt đó ở cả giao diện lẫn bản xuất.

Trạng thái hiển thị | Ý nghĩa được phép hiểu

Thiếu dữ liệu | Không có AIS, AIS không hợp lệ/quá cũ, vị trí quá bất định hoặc thiếu kích thước để đối chiếu. Cần bổ sung bằng chứng.

Không ghép được | Chưa tìm được cặp đạt điều kiện hoặc ứng viên còn mơ hồ. Không suy ra tàu cố tình tắt AIS.

Đang xác minh: kích thước lệch | Kích thước từ ảnh và khai báo không khớp trong mô hình. Chưa chứng minh khai báo sai hoặc vi phạm.

Ghép được; chờ xác minh | Đạt điều kiện ghép vị trí. Danh tính, hoạt động và kết luận nghiệp vụ vẫn cần người có chuyên môn.

Vòng kiểm tra do con người chịu trách nhiệm

Người dùng mở ảnh nguồn, đọc ngày chụp và tọa độ, xem điểm nghi vấn cùng bối cảnh, rồi ghi nhận xét. Quy trình xác nhận yêu cầu người rà soát, căn cứ và quyết định rõ ràng. Khi ảnh, mô hình hoặc phiên bản xử lý thay đổi, nhận xét cũ không tự trở thành xác nhận cho kết quả mới.

JSON, HTML và gói bằng chứng giữ cùng trạng thái, kèm mã ảnh và mô hình. Dữ liệu phương tiện mô phỏng tắt mặc định và được ghi nhãn khi bật. Các minh họa AIS không được nhập nhằng với ảnh SAR thật.

Giới hạn của bản thử nghiệm

Tên người rà soát hiện là thông tin tự khai, chưa có tài khoản xác thực hay chữ ký số. Quy trình này hỗ trợ truy vết trong bản thử nghiệm, chưa tạo ra một xác nhận nghiệp vụ có thẩm quyền. SonarNet không đưa ra kết luận vi phạm IUU.


---


CHẶNG 1 / 04

Ghép ít hơn khi chưa đủ chắc chắn

Phương pháp mới dùng khoảng cách cùng tuổi dữ liệu và độ bất định của vị trí. Điều này tạo ra một đánh đổi có chủ đích: giảm các cặp ghép thiếu căn cứ, đồng thời giảm độ phủ ở tình huống khó.

<b>Cổng chất lượng:</b> AIS cách thời điểm chụp không quá 180 giây; sigma không quá 150 m. Khoảng cách phải nhỏ hơn min(500 m, 3 × √(sigma AIS² + 30²)). Các ứng viên cạnh tranh quá gần nhau được từ chối để rà soát.

Trong tình huống giao nhau, baseline chỉ khoảng cách ghép sai 78/200 điểm; phương pháp mới từ chối cả 200 điểm mơ hồ. Với AIS nhiễu, baseline ghép sai 25 điểm và từ chối 23; phương pháp mới từ chối toàn bộ 200. Khi AIS mới và tách biệt, cả hai ghép đúng 200/200.

<b>Không diễn giải thành “độ chính xác 100%”.</b> Kết quả này đến từ stress test mô phỏng có kiểm soát, chưa đo trên AIS thực địa. Phương pháp mới chấp nhận 200/1.200 điểm trong toàn bộ bộ thử; 1.000 điểm còn lại cần bổ sung hoặc kiểm tra. Các ngưỡng chưa được hiệu chỉnh bằng hành trình thực.

Tái hiện: scripts/evaluate_ais_matching.py. Bảng đếm, 600 ca và nguyên nhân từ chối: reports/final/ais_matching/. Seed 20261116; 100 ca cho mỗi nhóm, 2 điểm/ca.


---


CHẶNG 1 / 05

Tách tập trước khi chọn mô hình

Checkpoint cũ bị xóa theo xác nhận của tác giả. Lượt này huấn luyện lại YOLO11n từ trọng số COCO do Ultralytics phát hành trên LS-SSDD, một bộ ảnh Sentinel-1 thật có nhãn nguồn. Không coi đây là khôi phục chính xác kết quả lịch sử.

Dữ liệu gốc có 9.000 ảnh kèm nhãn. Loại ba cảnh có nguy cơ gần nhóm vùng kiểm thử/validation, sau đó cách ly 115 ảnh train/validation có dHash gần ảnh thuộc tập khác. Tập giữ lại gồm 7.085 ảnh. Cách ly là biện pháp thận trọng; chữ ký gần giống không tự chứng minh hai ảnh là bản sao.

Nguồn ngày UTC lấy từ mã sản phẩm Sentinel-1 trong tài liệu gốc; nhóm vùng và cảnh được định trước. Sau cách ly không có pixel trùng hoặc cặp dHash ≤ 3 đi qua các tập giữ lại. Việc chia nhóm vùng không thay thế một chứng nhận hình học về mọi mức chồng lấn địa lý.

Huấn luyện MPS trên Apple M1 Pro; 640 px, batch 16, AdamW, seed 20261116; tối đa 40 epoch, patience 8. Dừng ở epoch 24. Checkpoint tốt nhất theo validation; không dùng test để chọn ngưỡng. Tệp provenance, đường cong và phiên bản thư viện được lưu.


---


CHẶNG 1 / 06

Đo khả năng tổng quát, giữ cả điểm yếu

Ngưỡng confidence 0,25 chọn từ lưới validation 0,1/0,25/0,4/0,6. Kiểm thử 3.000 ảnh gồm 2.378 nhãn tàu; có 1.511 phát hiện đúng, 671 báo nhầm và 867 bỏ sót tại IoU ≥ 0,5.

Chỉ tiêu | YOLO11n mới | Ngưỡng sáng toàn cục

AP50 / AP50-95 | 0,6618 / 0,2389 | 0,0139 / 0,0030

Precision / Recall | 69,25% / 63,54% | 0,07% / 51,14%

Báo nhầm / triệu pixel | 0,349 | 852,143

Độ trễ trung vị / p95 (ms) | 61,47 / 65,05 | 11,49 / 44,04

Recall nhóm ảnh có đất liền: <b>27,86%</b> trên 883 nhãn. Đây là nhóm khó nhất, đặc biệt ở cảnh 11. Sai số tâm trung vị 1,82 pixel và p95 4,41 pixel chỉ tính trên các cặp đúng; không đại diện cho 867 tàu bị bỏ sót.

Cả hai phương pháp đo trên cùng CPU macOS ARM64, 4 luồng; thời gian gồm tiền xử lý/suy luận/NMS, loại đọc tệp và có 3 lượt khởi động. AP tích phân VOC không đồng nhất COCO/Ultralytics; không so trực tiếp số 0,2389 với mAP 0,444 trong hồ sơ cũ. Baseline ngưỡng sáng đơn giản không đại diện cho mô hình SAR mạnh khác.


---


CHẶNG 1 / 07

Những ảnh hệ thống vẫn xử lý chưa tốt

Ảnh dưới được chọn tự động theo số lỗi cao nhất, không chọn theo vẻ đẹp trình diễn. Khung lam là nhãn nguồn, khung cam là dự đoán ở ngưỡng đã chốt. Mỗi ảnh minh họa một câu hỏi cần giải quyết trước ứng dụng thực tế.

Báo nhầm: cảnh 14, ô 16_6

Có 12 dự đoán không khớp nhãn và 3 nhãn bị bỏ sót. Cần xem bối cảnh bờ, cảng và kết cấu sáng trước khi gọi một điểm là phương tiện. Với nhãn nguồn hiện có, đây là lỗi đánh giá; chưa có rà soát độc lập để xác định có nhãn bỏ thiếu hay không.

Bỏ sót: cảnh 15, ô 15_22

Có 37 nhãn không được phát hiện ở ngưỡng chọn. Các mục tiêu nhỏ, sát nhau hoặc kém tương phản là giả thuyết cần kiểm tra thêm, chưa phải nguyên nhân đã chứng minh. Ưu tiên nghiên cứu tiếp theo là độ phân giải suy luận, nhãn sát bờ và cách lấy mẫu huấn luyện, chỉ chọn phương án theo validation.

Toàn bộ danh sách ảnh lỗi, chỉ số khung ghép và dự đoán được lưu để tái kiểm tra. Các thay đổi sau khi xem test phải được ghi là nghiên cứu tiếp nối; không dùng lại test như tập tối ưu rồi gọi là đánh giá độc lập mới.


---


CHẶNG 1 / 08

Quy đổi pixel sang đơn vị vật lý

Bài báo LS-SSDD mô tả hiệu chỉnh hình học, chuyển định dạng, sau đó resample toàn cảnh về 24.000 × 16.000 pixel trước khi cắt thành ô 800 × 800. Đặc tả Sentinel-1 IW GRD HR công bố pixel spacing sản phẩm 10 × 10 m, nhưng chưa đủ để khẳng định lưới của JPEG sau toàn bộ chuỗi xử lý vẫn giữ đúng phép đổi đó.

Vì vậy, báo cáo giữ các trường báo nhầm/km² và sai số mét là <b>chưa xác minh</b>. Đã đo báo nhầm trên triệu pixel của toàn ảnh (gồm cả đất), sai số tâm và kích thước khung theo pixel. Không đổi tên các chỉ tiêu này thành mật độ báo nhầm trên diện tích biển hoặc sai số chiều dài thân tàu.

Cách hoàn tất đúng yêu cầu

Cần geotransform/CRS hoặc lưới tọa độ của đúng ảnh sau hiệu chỉnh, quy tắc resampling, và mặt nạ vùng hợp lệ. Từ đó xác định diện tích đánh giá cùng quy đổi cục bộ theo trục ảnh. Chỉ số vị trí tuyệt đối cần điểm tham chiếu độc lập; sai số kích thước cần xác định đang đo khung ảnh hay kích thước thân tàu.

Các phần đã sẵn sàng chạy lại

Công cụ operational_metrics đã hỗ trợ gsd_x_m, gsd_y_m và valid_area_km2 khi có metadata đủ chứng cứ. Dự đoán gốc được lưu nên có thể tính bổ sung mà không huấn luyện lại; phiên bản báo cáo bổ sung phải giữ hash manifest, checkpoint và nguồn hiệu chuẩn.

Nguồn kiểm chứng

1. Zhang và cộng sự (2020), LS-SSDD-v1.0, mục 3.1-3.4: <link href="https://doi.org/10.3390/rs12182997" color="#007F86">doi.org/10.3390/rs12182997</link>.

2. Tài liệu dữ liệu gốc và user manual: <link href="https://github.com/TianwenZhang0825/LS-SSDD-v1.0-OPEN" color="#007F86">github.com/TianwenZhang0825/LS-SSDD-v1.0-OPEN</link>.

3. Copernicus SentiWiki, đặc tả sản phẩm Sentinel-1: <link href="https://sentiwiki.copernicus.eu/web/s1-products" color="#007F86">sentiwiki.copernicus.eu/web/s1-products</link>.

Dữ liệu LS-SSDD có điều kiện sử dụng phi thương mại trong tài liệu gốc. Gói mã nguồn và hồ sơ không phân phối lại toàn bộ 9.000 ảnh nguồn.


---


CHẶNG 1 / 09

Tái hiện, khai báo AI và việc cần chốt

Lệnh kiểm tra chính

python -m pytest -q

python scripts/evaluate_ais_matching.py --output reports/final/ais_matching

python scripts/evaluate_independent_sar.py --manifest /PATH/manifest.json --weights assets/models/sonarnet_ls_ssdd_20261117.pt --output /PATH/evaluation

streamlit run scripts/demo_app.py

Dữ liệu tải và chuẩn bị qua download_ls_ssdd.py và prepare_independent_ls_ssdd.py. Môi trường huấn luyện cần PyTorch 2.8.0, Ultralytics 8.3.253; tệp khóa phiên bản nằm trong bản lưu lượt huấn luyện. Không ghi đè checkpoint mới lên mô hình lịch sử của bản đồ vì hai nguồn kết quả có hash khác nhau.

Dấu vết kiểm chứng

Checkpoint SHA256: 5b1eef4e8e45b17ea3f071285af5693dcb5ecc2c98d272264a570f58a1eb2bb1

Manifest SHA256: 6c697535593fbbee8ada0e02f265675e0b0167ddc89ccb4e9923c642035fd62a

Thư mục reports/final/ chứa kết quả SAR, bảng AIS, audit dữ liệu và kết quả kiểm thử. JSON kết quả lưu hash mã đánh giá và định nghĩa chỉ số. Bộ kiểm thử đầy đủ ngày 17/11 trên SSD: 121 test và 11 subtest đạt, không có lỗi. Có một cảnh báo do hàm smoke cũ trả về tuple. Đã khôi phục đủ 22.064 tệp ảnh/metadata của 5.516 ô, kiểm tra mã Git từng tệp.

Khai báo sử dụng AI

Codex hỗ trợ phân tích yêu cầu BTC, sửa mã, viết kiểm thử, tìm và tải dữ liệu công khai, chuẩn bị tập, chạy huấn luyện/đánh giá, tạo biểu đồ và soạn báo cáo. Số liệu trong tài liệu lấy từ tệp kết quả đã chạy. Nội dung này là khai báo của lượt cải tiến hiện tại, không phải lịch sử prompt nguyên bản của các cuộc trò chuyện đã mất. Tác giả cần đọc, xác nhận nội dung và chịu trách nhiệm cho bản nộp.

Danh sách còn mở trước khi nộp

1. Hoàn tất hiệu chuẩn mét/diện tích hoặc bổ sung đánh giá thực địa có georeference.<br/>2. Kiểm tra quy trình trên bản triển khai công khai sau khi cập nhật.<br/>3. Cập nhật mã nguồn/demo; đưa PDF lên URL HTTPS truy cập được.<br/>4. Chốt họ tên, đội, người rà soát và khai báo AI theo mẫu BTC.<br/>5. Tác giả xem lại cam kết và thực hiện bước nộp cuối trên cổng.

Trạng thái bản này: có kết quả huấn luyện và đánh giá thật, còn các mục mở nêu trên. Không tự nhận đã hoàn thành 100% yêu cầu BTC.