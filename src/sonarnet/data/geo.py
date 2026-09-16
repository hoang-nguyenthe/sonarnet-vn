"""Chuyển đổi toạ độ địa lý và toạ độ điểm ảnh.

Vùng thí điểm có kích thước khoảng 100 km nên phép chiếu phẳng cục bộ cho sai
số không đáng kể so với ngưỡng ghép cặp 500 mét của hệ thống.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple

import numpy as np

EARTH_RADIUS_M = 6_371_008.8


def haversine_m(lat1, lon1, lat2, lon2):
    """Khoảng cách vòng lớn giữa hai điểm, tính bằng mét. Hỗ trợ mảng NumPy."""
    lat1, lon1, lat2, lon2 = map(np.asarray, (lat1, lon1, lat2, lon2))
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = np.radians(lat2 - lat1)
    dl = np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def meters_per_degree(lat: float) -> Tuple[float, float]:
    """Số mét ứng với một độ vĩ và một độ kinh tại vĩ độ đã cho."""
    m_per_deg_lat = 111_132.92 - 559.82 * math.cos(2 * math.radians(lat))
    m_per_deg_lon = 111_412.84 * math.cos(math.radians(lat))
    return m_per_deg_lat, max(m_per_deg_lon, 1.0)


@dataclass(frozen=True)
class SceneGeoReference:
    """Hệ quy chiếu của một cảnh ảnh: ánh xạ giữa điểm ảnh và toạ độ địa lý.

    Gốc toạ độ điểm ảnh nằm ở góc trên bên trái, trục y hướng xuống — quy ước
    chuẩn của ảnh raster.
    """

    lat_top: float
    lon_left: float
    width: int
    height: int
    pixel_spacing_m: float

    @property
    def _scales(self) -> Tuple[float, float]:
        m_lat, m_lon = meters_per_degree(self.lat_top)
        return m_lat, m_lon

    def pixel_to_lonlat(self, x, y) -> Tuple[np.ndarray, np.ndarray]:
        m_lat, m_lon = self._scales
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        lon = self.lon_left + (x * self.pixel_spacing_m) / m_lon
        lat = self.lat_top - (y * self.pixel_spacing_m) / m_lat
        return lon, lat

    def lonlat_to_pixel(self, lon, lat) -> Tuple[np.ndarray, np.ndarray]:
        m_lat, m_lon = self._scales
        lon = np.asarray(lon, dtype=float)
        lat = np.asarray(lat, dtype=float)
        x = (lon - self.lon_left) * m_lon / self.pixel_spacing_m
        y = (self.lat_top - lat) * m_lat / self.pixel_spacing_m
        return x, y

    @property
    def bounds(self) -> Tuple[float, float, float, float]:
        """Trả về (lon_min, lat_min, lon_max, lat_max) của cảnh."""
        lon_r, lat_b = self.pixel_to_lonlat(self.width, self.height)
        return float(self.lon_left), float(lat_b), float(lon_r), float(self.lat_top)

    @property
    def center(self) -> Tuple[float, float]:
        lon_c, lat_c = self.pixel_to_lonlat(self.width / 2, self.height / 2)
        return float(lat_c), float(lon_c)
