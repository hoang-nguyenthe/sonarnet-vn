"""Locally controlled place labels: no third-party boundary overlay.

Coordinates are approximate label anchors, not island outlines or borders.
Archipelago naming follows Vietnam's Ministry of Foreign Affairs.
"""
import folium
from html import escape

PLACES = [
    ('Hà Nội', 21.03, 105.85), ('Hải Phòng', 20.86, 106.68),
    ('Đà Nẵng', 16.05, 108.20), ('Quy Nhơn', 13.77, 109.22),
    ('Nha Trang', 12.24, 109.19), ('TP. Hồ Chí Minh', 10.78, 106.70),
    ('Cần Thơ', 10.04, 105.78),
    ('Cô Tô', 20.98, 107.77), ('Bạch Long Vĩ', 20.13, 107.73),
    ('Cồn Cỏ', 17.16, 107.34), ('Lý Sơn', 15.38, 109.12),
    ('Phú Quý', 10.53, 108.96), ('Côn Đảo', 8.68, 106.60),
    ('Phú Quốc', 10.22, 103.97), ('Thổ Chu', 9.30, 103.48),
    ('Quần đảo Hoàng Sa (Việt Nam)', 16.5, 112.0),
    ('Quần đảo Trường Sa (Việt Nam)', 10.0, 114.0),
]
SOURCE = 'https://mofa.gov.vn/tin-chi-tiet/chi-tiet/viet-nam-co-day-du-bang-chung-khang-dinh-chu-quyen-cua-minh-doi-voi-hai-quan-dao-hoang-sa-va-truong-sa-10.html'


def add_place_labels(chart):
    layer = folium.FeatureGroup(name='Địa danh Việt Nam', show=True).add_to(chart)
    for name, latitude, longitude in PLACES:
        archipelago = name.startswith('Quần đảo')
        label = escape(name)
        marker = folium.Marker(
            [latitude, longitude],
            icon=folium.DivIcon(icon_size=(180, 28), icon_anchor=(90, 14),
                html=f'<div style="text-align:center;font: {12 if archipelago else 11}px system-ui;'
                     f'font-weight:600;color:white;text-shadow:0 1px 3px #000,0 0 5px #000;'
                     f'line-height:14px">{label}</div>'),
        )
        content = f'<b>{label}</b><br>Vị trí nhãn khái quát, không phải đường bao địa lý.'
        if archipelago:
            content += f'<br><a href="{SOURCE}" target="_blank" rel="noopener">Nguồn: Bộ Ngoại giao Việt Nam</a>'
        marker.add_child(folium.Popup(content, max_width=280)).add_to(layer)
