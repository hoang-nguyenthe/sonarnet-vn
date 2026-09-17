"""Public coverage vocabulary; never interpret absent results as no vessels."""


def coverage_rows(plan):
    states = plan.get('states', {})
    labels = [
        ('processed', 'Đã xử lý trên lưới', 'Có kết quả ảnh chi tiết; không đồng nghĩa đã xác nhận tàu.'),
        ('pending', 'Đang chờ xử lý', 'Chưa có kết quả nhận diện.'),
        ('retry_later', 'Đang chờ tải lại', 'Nguồn tạm chưa dùng được; sẽ thử lại.'),
        ('no_observation', 'Chưa thấy ảnh trong lớp phủ hiện tại', 'Không có ảnh không có nghĩa là không có tàu.'),
        ('excluded_land_coast', 'Bỏ qua đất liền và sát bờ', 'Không tìm tàu trong đất liền hoặc dải 500 m sát bờ.'),
        ('blocked_missing_mask', 'Chưa đủ dữ liệu đường bờ', 'Chưa chạy nhận diện để tránh đánh dấu nhầm trên đất.'),
    ]
    return [{'Trạng thái': label, 'Số ô': states.get(key, 0), 'Ý nghĩa': meaning}
            for key, label, meaning in labels if states.get(key, 0)]


def waiting_cells(plan):
    states = plan.get('states', {})
    return states.get('pending', 0) + states.get('retry_later', 0)
