"""Deterministic, explicitly fictional profiles for the optional walkthrough."""
import hashlib
from html import escape

STATES = {
    'matched': ('AIS khớp', '#64d8c6'),
    'mismatch': ('AIS lệch', '#f0a45d'),
    'missing': ('Chưa có AIS', '#c1ccd4'),
}

def profile(candidate):
    seed = hashlib.sha256(str(candidate['id']).encode()).hexdigest()
    number = int(seed[:8], 16)
    category = ('Tàu cá', 'Tàu hàng', 'Tàu dịch vụ')[number % 3]
    status = ('matched', 'matched', 'mismatch', 'missing')[number % 4]
    return dict(identifier='MINH-HOA-' + seed[:6].upper(), name='Hải An ' + seed[:6].upper(), category=category,
                status=status, label=STATES[status][0], color=STATES[status][1],
                matched=status == 'matched', speed=round(3 + (number % 120) / 10, 1),
                offset_m=(30 + number % 100) if status == 'matched' else (1200 + number % 3000),
                heading=number % 360)


def popup(candidate):
    p = profile(candidate)
    head = f"<hr><strong>{escape(p['name'])}</strong><br><small>Dữ liệu trình diễn · hồ sơ hư cấu, không phải AIS thật</small><br>"
    head += f"Mã: {p['identifier']}<br>Loại tàu trong kịch bản: {p['category']}<br>"
    head += f"Tốc độ kịch bản: {p['speed']} hải lý/giờ · Hướng: {p['heading']}°<br>"
    head += f"<span style='color:{p['color']}'>{p['label']}</span><br>"
    if p['status'] == 'missing':
        return head + 'Kịch bản: không nhận được AIS. Hồ sơ trên là thông tin dựng sẵn cho trình diễn, không được suy ra từ radar.<br>Không suy ra tàu tắt tín hiệu hoặc vi phạm.'
    return (head +
            f"Khoảng cách vị trí giả định: {p['offset_m']:,} m.<br>"
            + ('Tình huống: vị trí gần nhau trong cùng khoảng thời gian.<br>' if p['status'] == 'matched'
               else 'Tình huống: vị trí báo về lệch điểm quan sát; cần kiểm tra thời gian bản tin, sai số hoặc nhầm mục tiêu. Không kết luận AIS giả.<br>') +
            'Không phải định danh của mục tiêu trong ảnh. Chưa có MMSI, chủ tàu hay hành trình thật.')
