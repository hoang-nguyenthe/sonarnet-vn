"""Sinh quỹ đạo phương tiện theo bốn nhóm hành vi hoạt động.

Mỗi nhóm hành vi có dấu hiệu động học riêng biệt, phản ánh đúng thực tế khai
thác trên biển:

* ``qua_canh``  — di chuyển quá cảnh: tốc độ cao, hướng gần như không đổi.
* ``cau``       — câu: tốc độ thấp, hướng đổi liên tục theo kiểu bước ngẫu nhiên,
  xen kẽ nhiều lần dừng khi thu và thả câu.
* ``keo_luoi``  — kéo lưới: tốc độ trung bình ổn định, chạy theo các đoạn thẳng
  dài rồi quay đầu gấp, tạo thành đường đi hình răng lược.
* ``neo_dau``   — neo đậu hoặc tụ tập: gần như đứng yên, chỉ trôi quanh một điểm
  theo dòng triều.

Các đặc trưng trích từ quỹ đạo là đầu vào cho bộ phân loại hành vi ở tầng bốn.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np

from .geo import meters_per_degree

KNOT_TO_MS = 0.514444


@dataclass
class Track:
    """Một quỹ đạo phương tiện đã lấy mẫu theo thời gian."""

    mmsi: int
    behaviour: str
    times_s: np.ndarray      # (T,) mốc thời gian, giây
    lats: np.ndarray         # (T,) vĩ độ
    lons: np.ndarray         # (T,) kinh độ
    speeds_kn: np.ndarray    # (T,) tốc độ trên mặt nước
    courses_deg: np.ndarray  # (T,) hướng đi

    def __len__(self) -> int:
        return len(self.times_s)


def _step(lat, lon, speed_kn, course_deg, dt_s):
    """Dịch chuyển một bước theo tốc độ và hướng đã cho."""
    m_lat, m_lon = meters_per_degree(lat)
    dist = speed_kn * KNOT_TO_MS * dt_s
    rad = np.radians(course_deg)
    # Quy ước: 0 độ là hướng bắc, tăng theo chiều kim đồng hồ
    north = dist * np.cos(rad)
    east = dist * np.sin(rad)
    return lat + north / m_lat, lon + east / m_lon


def _gen_transit(n, dt, lat0, lon0, rng) -> Tuple[np.ndarray, ...]:
    speed = rng.uniform(10.0, 17.0)
    course = rng.uniform(0, 360)
    lats, lons, sp, co = [lat0], [lon0], [], []
    for _ in range(n):
        # Dao động nhỏ quanh giá trị danh nghĩa do sóng và bánh lái
        s = max(0.0, speed + rng.normal(0, 0.55))
        c = course + rng.normal(0, 2.2)
        course = 0.97 * course + 0.03 * c  # trôi hướng rất chậm
        sp.append(s)
        co.append(c % 360)
        la, lo = _step(lats[-1], lons[-1], s, c, dt)
        lats.append(la)
        lons.append(lo)
    return np.array(lats[:-1]), np.array(lons[:-1]), np.array(sp), np.array(co)


def _gen_fishing(n, dt, lat0, lon0, rng) -> Tuple[np.ndarray, ...]:
    course = rng.uniform(0, 360)
    lats, lons, sp, co = [lat0], [lon0], [], []
    for _ in range(n):
        # Bước ngẫu nhiên mạnh về hướng, đặc trưng của thao tác thả và thu câu
        course = (course + rng.normal(0, 34.0)) % 360
        if rng.random() < 0.18:
            s = rng.uniform(0.0, 0.6)          # dừng để thu câu
        else:
            s = max(0.0, rng.uniform(1.8, 4.5) + rng.normal(0, 0.4))
        sp.append(s)
        co.append(course)
        la, lo = _step(lats[-1], lons[-1], s, course, dt)
        lats.append(la)
        lons.append(lo)
    return np.array(lats[:-1]), np.array(lons[:-1]), np.array(sp), np.array(co)


def _gen_trawling(n, dt, lat0, lon0, rng) -> Tuple[np.ndarray, ...]:
    base_course = rng.uniform(0, 360)
    leg_len = int(rng.integers(8, 18))   # số bước của một đoạn thẳng
    speed = rng.uniform(3.2, 6.0)
    lats, lons, sp, co = [lat0], [lon0], [], []
    course = base_course
    since_turn = 0
    flip = 1
    for _ in range(n):
        if since_turn >= leg_len:
            # Quay đầu gần 180 độ rồi dịch ngang sang luống kế tiếp
            course = (base_course + (180 if flip > 0 else 0) + rng.normal(0, 6)) % 360
            flip *= -1
            since_turn = 0
            leg_len = int(rng.integers(8, 18))
        s = max(0.0, speed + rng.normal(0, 0.3))
        c = course + rng.normal(0, 3.0)
        sp.append(s)
        co.append(c % 360)
        la, lo = _step(lats[-1], lons[-1], s, c, dt)
        lats.append(la)
        lons.append(lo)
        since_turn += 1
    return np.array(lats[:-1]), np.array(lons[:-1]), np.array(sp), np.array(co)


def _gen_loitering(n, dt, lat0, lon0, rng) -> Tuple[np.ndarray, ...]:
    # Trôi quanh điểm neo theo một vòng triều khép kín
    radius_m = rng.uniform(60, 260)
    period = rng.uniform(6, 14) * 3600.0
    phase = rng.uniform(0, 2 * np.pi)
    m_lat, m_lon = meters_per_degree(lat0)
    lats, lons, sp, co = [], [], [], []
    prev = None
    for i in range(n):
        t = i * dt
        ang = 2 * np.pi * t / period + phase
        la = lat0 + (radius_m * np.sin(ang)) / m_lat + rng.normal(0, 8) / m_lat
        lo = lon0 + (radius_m * np.cos(ang)) / m_lon + rng.normal(0, 8) / m_lon
        lats.append(la)
        lons.append(lo)
        if prev is None:
            sp.append(rng.uniform(0.0, 0.4))
            co.append(rng.uniform(0, 360))
        else:
            dn = (la - prev[0]) * m_lat
            de = (lo - prev[1]) * m_lon
            dist = float(np.hypot(dn, de))
            sp.append(dist / dt / KNOT_TO_MS)
            co.append(float(np.degrees(np.arctan2(de, dn)) % 360))
        prev = (la, lo)
    return np.array(lats), np.array(lons), np.array(sp), np.array(co)


_GENERATORS = {
    "qua_canh": _gen_transit,
    "cau": _gen_fishing,
    "keo_luoi": _gen_trawling,
    "neo_dau": _gen_loitering,
}


def generate_track(
    behaviour: str, mmsi: int, cfg, rng: np.random.Generator
) -> Track:
    """Sinh một quỹ đạo thuộc nhóm hành vi đã cho."""
    dt = cfg.behavior.track_step_min * 60.0
    n = int(cfg.behavior.track_hours * 3600.0 / dt)
    g = cfg.geo
    lat0 = float(rng.uniform(g.lat_min, g.lat_max))
    lon0 = float(rng.uniform(g.lon_min, g.lon_max))

    lats, lons, sp, co = _GENERATORS[behaviour](n, dt, lat0, lon0, rng)
    times = np.arange(n, dtype=float) * dt
    return Track(
        mmsi=mmsi, behaviour=behaviour,
        times_s=times, lats=lats, lons=lons,
        speeds_kn=sp, courses_deg=co,
    )


def generate_track_dataset(cfg, rng: np.random.Generator) -> List[Track]:
    """Sinh toàn bộ tập quỹ đạo dùng để huấn luyện bộ phân loại hành vi."""
    tracks: List[Track] = []
    mmsi = 574_900_000
    for behaviour in cfg.behavior.classes:
        for _ in range(cfg.behavior.n_tracks_per_class):
            mmsi += int(rng.integers(3, 400))
            tracks.append(generate_track(behaviour, mmsi, cfg, rng))
    rng.shuffle(tracks)
    return tracks
