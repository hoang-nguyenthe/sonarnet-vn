"""Deterministic, explicitly fictional profiles for the optional walkthrough."""
import hashlib
from html import escape

STATES = {
    'matched': ('AIS khớp', '#0a84ff'),
    'mismatch': ('AIS lệch', '#ffd60a'),
    'missing': ('Chưa có AIS', '#ff453a'),
}

FILTERS = {'Tất cả': None, 'Xanh dương · AIS khớp': 'matched',
           'Vàng · AIS lệch': 'mismatch', 'Đỏ · Chưa có AIS': 'missing'}


def filter_vessels(candidates, selection):
    status = FILTERS[selection]
    return [c for c in candidates if status is None or profile(c)['status'] == status]

def profile(candidate):
    seed = hashlib.sha256(str(candidate['id']).encode()).hexdigest()
    number = int(seed[:8], 16)
    category = ('Tàu cá', 'Tàu hàng', 'Tàu dịch vụ')[number % 3]
    status = ('matched', 'matched', 'mismatch', 'missing')[number % 4]
    owner = ('Nguyễn Văn An', 'Trần Minh Hải', 'Lê Quốc Bình', 'Phạm Văn Hòa')[number % 4]
    port = ('Hòn Rớ · Khánh Hòa', 'Thọ Quang · Đà Nẵng', 'Quy Nhơn · Gia Lai', 'Rạch Giá · An Giang')[number % 4]
    return dict(identifier='MINH-HOA-' + seed[:6].upper(), name='Hải An ' + seed[:6].upper(), category=category,
                owner=owner, port=port, registration='TD-' + seed[:6].upper(),
                length_m=18 + number % 19 if category == 'Tàu cá' else 40 + number % 100,
                crew=6 + number % 12, year=2010 + number % 14,
                status=status, label=STATES[status][0], color=STATES[status][1],
                matched=status == 'matched', speed=round(3 + (number % 120) / 10, 1),
                offset_m=(30 + number % 100) if status == 'matched' else (1200 + number % 3000),
                heading=number % 360)


def popup(candidate):
    p = profile(candidate)
    head = '<div class="vessel-popup-details"><dl>'
    for label, value in [('Mã tàu', p['registration']), ('Loại phương tiện', p['category']),
                         ('Chủ phương tiện', p['owner']), ('Cảng đăng ký', p['port']),
                         ('Chiều dài', f"{p['length_m']} m"), ('Thuyền viên', f"{p['crew']} người"),
                         ('Năm đóng', p['year'])]:
        head += f'<dt>{label}</dt><dd>{escape(str(value))}</dd>'
    head += '</dl>'
    head += f"<div class='vessel-popup-kinematics'>Tốc độ {p['speed']} hl/g · Hướng {p['heading']}°</div>"
    head += f"<span class='marker-status' style='color:{p['color']}'>{p['label']}</span><br></div>"
    if p['status'] == 'missing':
        return head
    return (head +
            f"Độ lệch vị trí: {p['offset_m']:,} m.<br>"
            + ('Tình huống: vị trí gần nhau trong cùng khoảng thời gian.<br>' if p['status'] == 'matched'
               else 'Vị trí báo về lệch điểm quan sát; cần đối chiếu thêm.<br>'))
