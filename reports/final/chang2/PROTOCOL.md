# Kiểm chứng mô-đun hành vi · Chặng 2

## Chạy và tái lập

Từ thư mục gốc của kho SonarNet, dùng Python, NumPy, SciPy, scikit-learn và XGBoost từ `requirements-full.txt`. Phiên bản thực tế lưu ở `results.json`. Mã được chạy với một luồng OpenMP và BLAS trên máy Mac.

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONPATH=src:scripts python3 scripts/evaluate_chang2.py
python3 scripts/score_chang2_study.py --cases reports/final/chang2/study-cases.json --output reports/final/chang2/study-summary.json DUONG_DAN_PHIEU_1.json DUONG_DAN_PHIEU_2.json
```

Có thể bỏ hai tên phiếu để sinh báo cáo **0 người tham gia**. Cần dùng đúng tệp `study-cases.json` đã công bố khi chấm phiếu. Các runtime XGBoost khác có thể cho dự đoán khác ở một số điểm nên ngân hàng bài thử chính thức được ghim theo SHA-256. Tải báo cáo, bài thử và ZIP từ [trang Chặng 2](https://hoang-nguyenthe.github.io/sonarnet-vn/chang2/).

## Đối chứng 2 × 2 ghép AIS

- Bốn cấu hình giữ ảnh giả lập, điểm AIS, ngưỡng và thuật toán ghép cố định. Bật/tắt Kalman so với nội suy tuyến tính. Bật/tắt bước kích thước sau ghép. Khi tắt kiểm kích thước, ghép thành công được ghi trạng thái đủ để qua bước này, giới hạn từ chối ghép vẫn được giữ.
- Năm seed 101, 203, 307, 409, 503. Mỗi seed chạy 60 cảnh cho từng kịch bản, bốn mục tiêu mỗi cảnh. Tổng 1.200 cảnh và 4.800 mục tiêu mỗi cấu hình. Kịch bản gồm AIS hỗn hợp, tàu cắt nhau, lệch hệ thống và nhiễu kích thước radar.
- Tỉ lệ và khoảng cách sinh theo mô phỏng, không phải phân phối thực địa. Kịch bản nhiễu mạnh giữ thiết lập AIS của nhóm hỗn hợp và thay độ lệch chuẩn của chiều dài SAR từ 9% lên 33%. Chọn mâu thuẫn độc lập với chiều dài thật, nhân 2,25 ở chiều dài khai báo. Mâu thuẫn được đo điều kiện trên cặp ghép đúng để tách lỗi ghép khỏi lỗi kích thước.
- Số cặp đúng/sai/từ chối có tổng bằng số mục tiêu. Số mâu thuẫn đúng và số bỏ sót cộng ra số cặp ghép đúng có mâu thuẫn. Một trạng thái mâu thuẫn chỉ là cờ để rà tiếp.

## Đối chứng mô-đun hành vi

- Mỗi seed sinh riêng 400 quỹ đạo học và 240 quỹ đạo chấm, bằng các luồng RNG tách. Tỉ lệ lớp cân bằng. Không dùng định danh, toạ độ tuyệt đối hoặc nhãn làm đặc trưng. Dùng XGBoost cho tất cả phương án, cùng cấu hình mô hình gốc.
- Năm cách học gồm chỉ SOG gần nhất với 400 mẫu, lịch sử sạch với 48 mẫu hoặc 400 mẫu, lịch sử có nhiễu với cùng 400 mẫu, và 800 hàng bao gồm bản gốc và bản nhiễu của 400 quỹ đạo học. So sánh ở cùng 400 hàng giúp cô lập ảnh hưởng của phân phối huấn luyện. Không dò siêu tham số theo tập chấm.
- Quỹ đạo chấm dùng lại đúng các quỹ đạo tiềm ẩn theo từng điều kiện. Các điều kiện gồm dữ liệu đủ, mất ngẫu nhiên khoảng 60% bản tin, cửa sổ ngắn có nhiễu và kịch bản chồng lấn. Cửa sổ ngắn trích 9–19 mốc trước khi loại ngẫu nhiên và giữ ít nhất 5. Trong kịch bản chồng lấn, thay đổi kênh SOG bằng hệ số và độ lệch mỗi quỹ đạo. Vị trí và hướng nhận nhiễu riêng. Điều này mô phỏng kênh quan sát thiếu nhất quán, không tái tạo quy trình đo của một hệ AIS cụ thể.
- Xem macro-F1 trung bình ± độ lệch chuẩn giữa 5 seed, số điểm theo lớp và ma trận nhầm lẫn trong `results.json`. Sai số ưu tiên rà là một phép quy đổi từ bốn lớp thành hai nhóm, trong đó câu và kéo lưới thuộc nhóm cần rà. Nhãn “cần rà” là quy ước của bài thử.

## Khảo sát người rà

- Chọn chuyên viên hàng hải, thủy sản, giám sát tàu hoặc phân tích SAR/AIS. Mã R01–R04 luân phiên thứ tự và điều kiện. Nếu có hai chuyên viên đầu tiên, ưu tiên R01 và R03. Nhóm sinh viên hoặc thành viên đội báo riêng nếu tham gia.
- Hai lượt có cùng 8 ca mỗi lượt, mỗi lượt gồm hai ca mỗi lớp và bốn ca dương tính theo nhãn mô phỏng. Cả hai lượt có cùng loại đồ thị kiểm tra. Lượt có AI thêm gợi ý từ mô hình huấn luyện với 800 hàng của seed 101, chạy trên quỹ đạo mô phỏng độc lập. Ba gợi ý không khớp nhãn ưu tiên theo thiết kế để có thể quan sát lỗi theo gợi ý. Đây là bộ ca đối chứng có chủ đích, không dùng để ước lượng tần suất sai trên toàn bộ luồng hoạt động.
- Mỗi ca có ba lựa chọn. Ca dương được đánh dấu chưa ưu tiên hoặc chưa đủ dữ liệu đều tính là bỏ sót. Ca âm được đánh dấu ưu tiên là cờ nhầm. Tính trung vị thời gian cho mỗi người và mỗi điều kiện, sau đó tính chênh theo cặp. Khi người dùng đổi tab hoặc thao tác dưới 250 ms, thời gian của ca đó bị loại và lựa chọn vẫn được giữ. Phân tích chính yêu cầu ít nhất 6 thời lượng hợp lệ mỗi lượt. Phân tích độ nhạy dùng tất cả người có ít nhất một thời lượng hợp lệ mỗi lượt. Thời gian nghỉ giữa hai lượt không tính.
- Bài thử ghi phiếu trong trình duyệt và người tham gia tải JSON. Không cần tên hoặc thông tin định danh. Nhóm chuyên môn khai trong phiếu. Chỉ tổng hợp phiếu thực tế có đồng ý và đủ 16 ca. Kiểm thử trình duyệt dùng tệp đánh dấu riêng và bị loại khỏi kết quả nộp.
- Giới hạn gồm cỡ mẫu, độ khó khác nhau giữa các ca, hiệu ứng thứ tự và thiếu nhãn hành vi bốn lớp và bộ ca đã xác nhận ở Việt Nam. Kết quả người tham gia chỉ áp dụng cho bộ ca và điều kiện đo này.

## Kê khai AI

OpenAI Codex hỗ trợ viết công cụ chạy đối chứng, bài thử trên web, kiểm thử và trình bày báo cáo. Chỉ số lấy từ mã chạy, AIS có nguồn đối chiếu và phiếu do người tham gia thực hiện. Tái sử dụng trình sinh hành vi, bộ trích đặc trưng, Kalman, ghép AIS và XGBoost của SonarNet. Không dùng AI để tạo phiếu chuyên viên.

## Đối chứng bằng AIS thật

Song Wu (2022), *Dataset for Semantic Segmentation of Fishing Trajectories*, Zenodo,
[DOI 10.5281/zenodo.7283281](https://doi.org/10.5281/zenodo.7283281), CC BY 4.0.
Dữ liệu liên quan bài báo [MDM 2022](https://doi.org/10.1109/MDM55031.2022.00092).
Tác giả gán nhãn thủ công trên quỹ đạo AIS của Đan Mạch. Trang của tác giả mô tả 128 quỹ đạo. SonarNet đếm được 123 giá trị mã chuyến phân biệt trong CSV gốc và dùng số đếm trực tiếp khi lập báo cáo. Dữ liệu gốc có thông tin
định danh tàu. Gói minh chứng chỉ có số liệu nhóm và hướng dẫn tải bản gốc.

```sh
curl -fL 'https://zenodo.org/records/7283281/files/128_fishing_trajs.csv' -o 128_fishing_trajs.csv
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONPATH=src:scripts python3 scripts/evaluate_chang2_real_ais.py 128_fishing_trajs.csv
```

- Script xác minh MD5 công bố của Zenodo. Lọc các điểm thiếu nhãn khai thác hoặc
  di chuyển, vị trí ngoài miền hợp lệ, hướng ngoài 0–360 độ hoặc tốc độ ngoài 0–40
  hải lý/giờ. Chia mỗi chuyến thành cửa sổ UTC hai giờ không chồng lấn, cần ít
  nhất 9/12 ô 10 phút có quan sát. Lấy trung vị vị trí và tốc độ, tính hướng
  trung bình vòng tròn. Tên tàu, vùng biển và thời gian tuyệt đối không đi vào mô hình.
- Nhãn mỗi ô là trạng thái của đa số bản ghi. Nhãn cửa sổ là trạng thái chiếm
  nhiều ô hơn. Bỏ cửa sổ hòa. Giữ các cửa sổ hỗn hợp để chấm chính, báo thêm nhóm
  có ít nhất 80% ô đồng thuận và nhóm còn lại. Cách này chấm trạng thái trội
  của cửa sổ, chưa đo ranh giới sự kiện theo phút. Cửa sổ thiếu bản tin nhiều
  bị loại theo tiêu chí trước khi chấm, nên kết quả tập trung vào AIS đủ dày.
- Giữ nguyên huấn luyện mô phỏng 800 hàng theo 5 seed và quy đổi dự đoán câu/kéo
  lưới thành khai thác. Sau đó, thử ba mô hình nhị phân cùng cấu hình XGBoost học
  AIS thật, lần lượt với tốc độ ở ô cuối, đặc trưng chuỗi tốc độ và toàn quỹ đạo.
  Dùng cùng 5 fold theo mã tàu tách từ mã chuyến. Tàu chấm không có trong tập
  huấn luyện của fold. Không dò ngưỡng hoặc siêu tham số trên tập chấm. Bootstrap
  mô tả 2.000 lần theo tàu từ dự đoán ngoài tập học, không huấn luyện lại mô hình
  trong mỗi lần lấy mẫu.
- Kết quả hai lớp tại Đan Mạch. Nhãn do người gán từ quỹ đạo, chưa đối chiếu với
  nhật ký khai thác hoặc quan sát trực tiếp. Mô hình AIS nhị phân được đánh giá
  như một phương án nghiên cứu và chưa đưa vào demo sản xuất.

## Kiểm tra thao tác tự động

Với Node.js, Playwright và Chromium, chạy từ thư mục gốc:

```sh
node scripts/replay_chang2_proxy.cjs
```

Có thể đặt `SONARNET_PLAYWRIGHT_PATH` và `SONARNET_CHROME` để dùng bản cài sẵn.
Bốn ngưỡng và hai trọng số gợi ý tạo 8 quy tắc giả lập. Mỗi quy tắc chạy đủ bốn
bố trí. Kết quả theo quy tắc gộp hai lần lặp của mỗi bộ ca trong mỗi điều kiện.
Số liệu phiên và thời gian trong `proxy-study.json` đo trình duyệt tự động. Tệp
này có đánh dấu `browser_simulation_only` và không chứa phiếu chuyên viên.

## Kiểm thử độ bền và độ dài cửa sổ

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONPATH=src:scripts python3 scripts/stress_chang2_real_ais.py 128_fishing_trajs.csv
```

- Năm seed cho năm cách chia theo tàu, mỗi cách chia có năm lượt chấm ngoài tập
  học. Một cửa sổ xuất hiện một lần trong từng lần chia. Các lần chia dùng lại
  cùng tàu và cùng cửa sổ, nên độ lệch giữa chúng là độ nhạy khi chia dữ liệu.
- Xóa 3 mốc 10 phút liên tiếp ở bên trong cửa sổ hoặc lấy ngẫu nhiên khoảng một
  nửa số mốc. Giữ nguyên nhãn của cửa sổ trước khi xóa. Chỉ tạo biến thể từ tập
  huấn luyện cho phương án XGBoost tăng cường. Tập chấm được làm thưa độc lập.
- Quy tắc theo chất lượng dùng XGBoost tăng cường khi dưới 9 mốc hoặc có khoảng
  trống bên trong lớn hơn 30 phút. Quy tắc được thử sau khi xem kết quả tăng cường
  ban đầu, nên cần kiểm tra trên tập mới trước khi đưa vào vận hành.
- Ba họ mô hình so sánh là Logistic, Extra Trees và HistGradientBoosting. Dùng
  3 fold theo tàu bên trong để chọn họ mô hình và ngưỡng. Mục tiêu chọn chính là
  macro-F1 tối đa hoặc recall tối đa khi precision ít nhất 0,95 ở vòng trong.
  Tàu chấm của vòng ngoài không đi vào các bước chọn.
- Cửa sổ 60, 120 và 240 phút có ngưỡng quan sát tương ứng 5, 9 và 18 mốc. Các
  độ dài cho ra số cửa sổ và nhãn khác nhau. Giá trị là phân tích độ nhạy, không
  phải phép thay đổi độ dài trên một tập mẫu ghép cặp.

## Đối chứng chuyển nguồn Global Fishing Watch

Dùng [Global Fishing Watch Training Data](https://github.com/GlobalFishingWatch/training-data/tree/58815d23bb0924d03fc4cad99953613e3c36d28f)
(CC BY 4.0), chấm trên quỹ đạo và nhãn đã được phát hành trong tập huấn luyện
lịch sử. Các bộ con đại diện tàu lưới vây, câu dây và lưới kéo. Nhãn phân số
thể hiện mức độ đồng thuận trong dữ liệu đã công bố. Dùng trung bình nhãn trong
mỗi ô 10 phút và đa số theo ô của cửa sổ, bỏ trường hợp hòa. Chỉ dùng tọa độ,
thời gian, tốc độ và hướng, bỏ các đặc trưng tính sẵn của GFW. Loại bản ghi
trùng, tốc độ/hướng không hợp lệ. Không công bố mã tàu, tọa độ và bản ghi gốc.

```sh
mkdir -p gfw
base='https://media.githubusercontent.com/media/GlobalFishingWatch/training-data/58815d23bb0924d03fc4cad99953613e3c36d28f/data/labeled'
curl -fL "$base/pybossa_project_3_Purse_seines.measures.labels.npz" -o gfw/gfw-purse-seines.npz
curl -fL "$base/kristina_longliner_Drifting_longlines.measures.labels.npz" -o gfw/gfw-longlines.npz
curl -fL "$base/kristina_trawl_Trawlers.measures.labels.npz" -o gfw/gfw-trawlers.npz
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONPATH=src:scripts python3 scripts/transfer_chang2_gfw.py 128_fishing_trajs.csv gfw
```

- So sánh mô hình gốc học mô phỏng với mô hình chỉ học Đan Mạch giữ toàn bộ GFW
  ngoài tập học. Cấu hình chuẩn hóa đặt cùng công thức tốc độ và hướng từ
  chênh vị trí giữa các mốc. Khi cân bằng nhãn, lặp ngẫu nhiên lớp thiểu số
  trong tập học đến số hàng bằng lớp đa số, không tái cân bằng tập chấm.
- Bổ sung 5 lượt giữ riêng tàu trong GFW và một phép giữ riêng nhóm nghề, học
  bằng Đan Mạch cùng hai nhóm nghề còn lại. Ở phép giữ nghề, loại mã tàu thuộc
  nhóm chấm khỏi mọi nhóm GFW dùng để học. Các phương án chuẩn hóa và học đa
  nguồn là đối chứng khám phá sau khi thấy lỗi chuyển nguồn ban đầu.
- Kết quả chính dùng tối thiểu 9/12 mốc, độ nhạy dùng 5/12. Nhóm câu dây
  gần như không đại diện ở ngưỡng cao. Các số đếm và nhãn của hai nguồn khác
  nhau về thời điểm, nghề và mật độ bản tin. Nhãn AIS từ chuyên gia và cộng
  tác viên là nhãn tham chiếu, chưa xác nhận bằng nhật ký cho các ca của SonarNet.

## Phân tích ô SAR 4048

Tái lập bằng `PYTHONPATH=src python3 scripts/audit_chang2_sar_tile.py`. Script lấy
hai nhãn tàu từ manifest OpenSAR, dùng nguyên các ngưỡng điểm đã khóa và đối
chiếu các cặp khớp với tệp lỗi lưu ở Chặng 1. Thứ tự ưu tiên theo điểm dự đoán.
Mỗi nhãn chỉ dùng một lần. Trong `sar-tile-4048.json`, `duplicate` là hộp có IoU
ít nhất 0,50 với nhãn đã ghép. `below_iou` là hộp có phần giao nhưng dưới 0,50.
`no_overlap` là hộp có IoU bằng 0 với mọi nhãn chấm. Các lỗi này có ý nghĩa khác
nhau khi xem ảnh. Bảng độ nhạy IoU 0,30, 0,50 và 0,75 mô tả riêng ô 4048.
Kết quả chính của tập ảnh giữ IoU 0,50. Các bảng SAR này đo phát hiện hộp,
tách với đánh giá ghép SAR–AIS và nhãn hành vi của Chặng 2.

## Đối chứng chính mở rộng theo đề BTC

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONPATH=src:scripts python3 scripts/deep_ablation_chang2.py
```

**Kalman.** Dùng 10 seed độc lập và 90 cảnh cho mỗi trong tám kịch bản. Có
28.800 mục tiêu trong 7.200 cảnh. Kịch bản điểm nhiễu có thêm 900 điểm không
phải mục tiêu. Cả hai bộ ước lượng nhận chính xác cùng dữ liệu và các ngưỡng
ghép giữ nguyên. Mỗi mục tiêu thuộc một trong bốn nhóm, chỉ đúng tuyến tính,
chỉ đúng Kalman, cả hai đúng hoặc cả hai chưa đúng. Báo riêng nhầm tàu và gán
AIS vào điểm nhiễu trong JSON. Bootstrap 4.000 lần ở cấp seed giữ cặp dữ
liệu cùng nhau và tránh đếm các mục tiêu cùng cảnh như mẫu độc lập.

**Kích thước.** Ghép danh tính trước khi bấm bật hoặc tắt bước kích thước.
Thử tỷ lệ khai báo 1,00, 1,30, 1,60, 1,80, 2,25 và 0,55; có nhóm thiếu khai
báo. Các mức được gán ngẫu nhiên độc lập độ dài thật. Cả hai cấu hình dùng
cùng sai số đo và khai báo. Nhiễu chiều dài có độ lệch chuẩn 9% ở bảy kịch
bản và 33% ở kịch bản nhiễu đo trong thử bật/tắt. Phép thử bổ sung áp cả
hai mức vào cùng từng cặp đã ghép đúng, nhân cùng số chuẩn hóa với 0,09
hoặc 0,33. Nhờ đó số ca đủ điều kiện trùng nhau và đọc được ca chỉ cờ ở
một mức. Tỷ lệ cờ đo có điều kiện trên cặp ghép đúng.
Sai lệch tương đối là chênh tuyệt đối chia cho giá trị lớn hơn. Ngưỡng 0,42
lấy từ hệ thống hiện tại. Báo số ca đúng tàu và khai đúng qua kiểm tra cùng
số ca khai lệch, thiếu số đo hoặc nhầm danh tính đi qua. Một cờ kích thước
chỉ làm thay đổi trạng thái bằng chứng.

**Dữ liệu hành vi.** Dùng 800 quỹ đạo huấn luyện độc lập mỗi seed. Mỗi lớp
chọn lồng nhau 12, 100 hoặc 200 quỹ đạo, cho tổng 48, 400 hoặc 800. So sạch
và hỗn hợp trên cùng tập con. Hỗn hợp có 25% sạch và 25% mỗi kiểu mất bản tin,
cửa sổ ngắn và tín hiệu chồng lấn. So riêng tốc độ mới nhất và đặc trưng
chuỗi ở cùng 400 mẫu, với cả điều kiện sạch và hỗn hợp. Mỗi seed dùng
240 quỹ đạo chấm độc lập, xuất hiện qua năm biến thể. “Mất liên tục” loại
55 mốc liền trước khi giảm mật độ các mốc còn lại, được giữ ngoài huấn luyện.
Lưu ma trận nhầm lẫn, F1 bốn lớp, bỏ sót và cờ nhầm. Khoảng bootstrap
được tính trên chênh lệch giữa hai cấu hình ghép theo seed. Số ca mô phỏng
không đại diện tần suất ngoài thực địa.

**Khảo sát.** Luân phiên bốn bố trí để hai tập ca và thứ tự làm bài cùng
xuất hiện ở mỗi điều kiện. Phân tích theo người tham gia. Thời gian là chênh
lệch trung vị giây trong từng người, kèm tỷ lệ phần trăm so với lượt không
AI. Báo số người nhanh hơn và chậm hơn, số bỏ sót, cờ nhầm, số ca chưa đủ
dữ liệu và số thời lượng bị loại theo lý do. Nếu có ít nhất năm chênh lệch
khác 0, báo phép thử dấu hai phía như phân tích khám phá. Số chuyên viên
hiện có là 0. Phiên trình duyệt tự động chỉ kiểm tra quy trình và đo các
quy tắc giả lập.

### Nội dung mời chuyên viên thực hiện bài thử

Mời anh/chị tham gia thử quy trình rà AIS của SonarNet trong Chung kết AI
2026. Bài thử có hai lượt, mỗi lượt tám tình huống mô phỏng. Mỗi lượt dùng
một nhóm ca khác nhau và một lượt có gợi ý bổ sung. Hệ thống ghi lựa chọn
và thời gian cho từng ca. Anh/chị có thể dừng bất kỳ lúc nào. Phiếu dùng mã
người rà và nhóm chuyên môn tự khai.

1. Mở [bài thử](https://hoang-nguyenthe.github.io/sonarnet-vn/chang2/study.html).
2. Nhập mã do đội gửi và chọn nhóm chuyên môn. Làm bài trong cùng một tab.
3. Tải phiếu JSON sau hai lượt và gửi lại đội để tổng hợp. Mỗi người dùng
   một mã. Đội phân lần lượt R01, R02, R03, R04 để phủ cả bốn bố trí.
4. Đội chỉ công bố kết quả tổng hợp. Các phiếu gốc do người điều phối giữ.
