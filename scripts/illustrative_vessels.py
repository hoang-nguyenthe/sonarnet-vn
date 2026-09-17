"""Deterministic, explicitly fictional profiles for the optional walkthrough."""
import hashlib
from html import escape


def profile(candidate):
    seed = hashlib.sha256(str(candidate['id']).encode()).hexdigest()
    number = int(seed[:8], 16)
    category = ('Tàu cá', 'Tàu hàng', 'Tàu dịch vụ')[number % 3]
    matched = number % 4 != 0
    return dict(identifier='MINH-HOA-' + seed[:6].upper(), category=category,
                matched=matched, speed=round(3 + (number % 120) / 10, 1),
                heading=number % 360)


def popup(candidate):
    p = profile(candidate)
    head = '<hr><strong>Hồ sơ minh hoạ · không phải AIS thật</strong><br>'
    if not p['matched']:
        return head + 'Tình huống: chưa tìm thấy bản tin phù hợp.<br>Không suy ra tàu tắt tín hiệu hoặc vi phạm.'
    return (head + f"Mã minh hoạ: {escape(p['identifier'])}<br>"
            f"Loại phương tiện giả định: {p['category']}<br>"
            f"Tốc độ giả định: {p['speed']} hải lý/giờ · Hướng: {p['heading']}°<br>"
            'Tình huống: có bản tin vị trí phù hợp.<br>'
            'Không phải định danh của mục tiêu trong ảnh. Chưa có MMSI, chủ tàu hay hành trình thật.')
