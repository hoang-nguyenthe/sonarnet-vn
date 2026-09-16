"""Tổng hợp ảnh radar khẩu độ tổng hợp mô phỏng.

Ảnh được dựng theo các đặc trưng vật lý chính của ảnh SAR biển:

* **Tán xạ nền biển** tuân theo phân bố Rayleigh, phản ánh tổng hợp ngẫu nhiên
  của vô số tán xạ tử nhỏ trên mặt nước.
* **Nhiễu đốm (speckle)** nhân tính, đặc trưng của mọi hệ radar kết hợp pha.
* **Điều biến quy mô lớn** do gió và sóng lừng, tạo các vệt sáng tối trên mặt biển.
* **Phương tiện** có hệ số tán xạ ngược cao hơn nền hàng chục lần, hình dạng
  thuôn dài theo hướng mũi tàu, kèm một số tán xạ tử điểm rất sáng.
* **Bóng ma phương vị** (azimuth ambiguity): bản sao mờ của mục tiêu sáng, lệch
  theo hướng phương vị — một giả tượng thường gây dương tính giả trong thực tế.
* **Vệt nước sau tàu** (wake): dải tối kéo dài phía sau phương tiện đang chạy.

Ảnh được lượng tử hoá về thang 8 bit sau khi nén theo hàm lô-ga-rít, đúng như
cách sản phẩm Ground Range Detected được hiển thị trong thực tế.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

try:  # Lọc Gauss của SciPy cho chất lượng tốt hơn, có sẵn trên Kaggle
    from scipy.ndimage import gaussian_filter as _gaussian_filter

    _HAS_SCIPY = True
except Exception:  # pragma: no cover
    _HAS_SCIPY = False


def _smooth(arr: np.ndarray, sigma: float) -> np.ndarray:
    """Làm trơn Gauss, có phương án thay thế khi thiếu SciPy."""
    if sigma <= 0:
        return arr
    if _HAS_SCIPY:
        return _gaussian_filter(arr, sigma=sigma, mode="reflect")
    # Phương án thay thế: tích chập tách được bằng nhân Gauss rời rạc
    radius = max(1, int(3 * sigma))
    k = np.exp(-0.5 * (np.arange(-radius, radius + 1) / sigma) ** 2)
    k /= k.sum()
    out = np.apply_along_axis(lambda m: np.convolve(m, k, mode="same"), 0, arr)
    out = np.apply_along_axis(lambda m: np.convolve(m, k, mode="same"), 1, out)
    return out


@dataclass
class ShipFootprint:
    """Dấu vết của một phương tiện trên mặt phẳng ảnh."""

    cx: float          # tâm theo trục x, đơn vị điểm ảnh
    cy: float          # tâm theo trục y, đơn vị điểm ảnh
    length_px: float   # chiều dài thân tàu
    width_px: float    # chiều rộng thân tàu
    heading_deg: float # hướng mũi tàu, 0 độ là hướng đông, tăng ngược chiều kim đồng hồ
    rcs: float         # cường độ tán xạ ngược tương đối
    moving: bool       # có đang chạy hay không, quyết định việc vẽ vệt nước

    def bbox(self, pad: float = 1.5) -> Tuple[float, float, float, float]:
        """Khung bao trục chuẩn của phương tiện, dạng (x1, y1, x2, y2)."""
        th = np.radians(self.heading_deg)
        hl, hw = self.length_px / 2.0, self.width_px / 2.0
        # Bốn đỉnh của hình chữ nhật xoay
        dx = np.array([hl, hl, -hl, -hl])
        dy = np.array([hw, -hw, hw, -hw])
        xs = self.cx + dx * np.cos(th) - dy * np.sin(th)
        ys = self.cy + dx * np.sin(th) + dy * np.cos(th)
        return (
            float(xs.min() - pad),
            float(ys.min() - pad),
            float(xs.max() + pad),
            float(ys.max() + pad),
        )


class SARRenderer:
    """Bộ dựng ảnh SAR mô phỏng cho một cảnh biển."""

    def __init__(
        self,
        size: int = 640,
        sea_scale: float = 0.24,
        wind_strength: float = 0.30,
        speckle_looks: int = 3,
        azimuth_ambiguity: bool = True,
    ) -> None:
        self.size = size
        self.sea_scale = sea_scale
        self.wind_strength = wind_strength
        self.speckle_looks = max(1, speckle_looks)
        self.azimuth_ambiguity = azimuth_ambiguity

    # -- Nền biển ----------------------------------------------------------
    def _sea_background(self, rng: np.random.Generator) -> np.ndarray:
        n = self.size
        # Tán xạ nền Rayleigh
        base = rng.rayleigh(scale=self.sea_scale, size=(n, n))
        # Điều biến quy mô lớn do gió và sóng lừng
        coarse = _smooth(rng.standard_normal((n, n)), sigma=n / 14.0)
        coarse = coarse / (np.abs(coarse).max() + 1e-9)
        # Vệt gió có hướng ưu thế
        angle = rng.uniform(0, np.pi)
        yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
        streak_phase = (xx * np.cos(angle) + yy * np.sin(angle)) / rng.uniform(45, 130)
        streaks = 0.5 * np.sin(streak_phase + rng.uniform(0, 2 * np.pi))
        modulation = 1.0 + self.wind_strength * (coarse + 0.45 * streaks)
        return base * np.clip(modulation, 0.25, 2.2)

    # -- Vùng đất liền -----------------------------------------------------
    def _add_land(self, img: np.ndarray, rng: np.random.Generator) -> np.ndarray:
        """Chèn một vùng đất liền hoặc đảo với tán xạ mạnh và kết cấu thô."""
        n = self.size
        mask = np.zeros((n, n), dtype=np.float32)
        # Dựng biên đất bằng một hàm sóng ngẫu nhiên dọc một cạnh ảnh
        edge = rng.integers(0, 4)
        depth = rng.uniform(0.12, 0.34) * n
        coords = np.arange(n)
        wobble = np.zeros(n)
        for _ in range(3):
            wobble += rng.uniform(0.05, 0.22) * depth * np.sin(
                2 * np.pi * coords / rng.uniform(60, 320) + rng.uniform(0, 6.28)
            )
        boundary = np.clip(depth + wobble, 4, n - 4)
        yy, xx = np.mgrid[0:n, 0:n]
        if edge == 0:
            mask[yy < boundary[None, :]] = 1.0
        elif edge == 1:
            mask[yy > (n - boundary[None, :])] = 1.0
        elif edge == 2:
            mask[xx < boundary[:, None]] = 1.0
        else:
            mask[xx > (n - boundary[:, None])] = 1.0

        mask = _smooth(mask, sigma=1.6)
        land_tex = rng.rayleigh(scale=self.sea_scale * 3.6, size=(n, n))
        land_tex *= 1.0 + 0.8 * _smooth(rng.standard_normal((n, n)), sigma=2.2)
        return img * (1 - mask) + land_tex * mask, mask

    # -- Phương tiện -------------------------------------------------------
    def _draw_ship(
        self, img: np.ndarray, ship: ShipFootprint, rng: np.random.Generator
    ) -> None:
        n = self.size
        pad = int(max(ship.length_px, ship.width_px)) + 12
        x0 = int(max(0, ship.cx - pad))
        x1 = int(min(n, ship.cx + pad))
        y0 = int(max(0, ship.cy - pad))
        y1 = int(min(n, ship.cy + pad))
        if x1 <= x0 or y1 <= y0:
            return

        yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        th = np.radians(ship.heading_deg)
        dx = xx - ship.cx
        dy = yy - ship.cy
        # Quay về hệ toạ độ gắn với thân tàu
        u = dx * np.cos(th) + dy * np.sin(th)     # dọc thân
        v = -dx * np.sin(th) + dy * np.cos(th)    # ngang thân

        hl, hw = ship.length_px / 2.0, ship.width_px / 2.0
        # Thân tàu: siêu ê-líp cho cạnh sắc hơn hình ê-líp thường
        body = np.exp(-(((u / hl) ** 4 + (v / hw) ** 4)) * 1.6)

        # Tán xạ tử điểm: cấu trúc thượng tầng, cần cẩu, góc phản xạ ba mặt
        n_scat = rng.integers(2, 6)
        scat = np.zeros_like(body)
        for _ in range(n_scat):
            su = rng.uniform(-hl * 0.85, hl * 0.85)
            sv = rng.uniform(-hw * 0.6, hw * 0.6)
            amp = rng.uniform(0.8, 2.4)
            sig = rng.uniform(0.7, 1.7)
            scat += amp * np.exp(-(((u - su) ** 2 + (v - sv) ** 2) / (2 * sig**2)))

        patch = ship.rcs * (body + 0.55 * scat)
        img[y0:y1, x0:x1] += patch

        # Vệt nước sau tàu: dải tối do mặt biển bị san phẳng
        if ship.moving and rng.random() < 0.55:
            wake_len = ship.length_px * rng.uniform(3.5, 9.0)
            wake_wid = ship.width_px * rng.uniform(0.8, 1.6)
            u_w = u + wake_len / 2.0
            wake = np.exp(-((u_w / (wake_len / 2.0)) ** 6) - (v / wake_wid) ** 2)
            wake *= (u < 0).astype(np.float32)
            img[y0:y1, x0:x1] *= 1.0 - 0.45 * wake

        # Bóng ma phương vị: bản sao mờ lệch theo trục dọc ảnh
        if self.azimuth_ambiguity and rng.random() < 0.16:
            shift = int(rng.choice([-1, 1]) * rng.uniform(0.06, 0.13) * n)
            gy0, gy1 = y0 + shift, y1 + shift
            if 0 <= gy0 and gy1 <= n:
                img[gy0:gy1, x0:x1] += patch * rng.uniform(0.05, 0.13)

    # -- Giao diện chính ---------------------------------------------------
    def render(
        self,
        ships: List[ShipFootprint],
        rng: np.random.Generator,
        with_land: bool = False,
    ) -> Tuple[np.ndarray, Optional[np.ndarray]]:
        """Dựng một cảnh ảnh SAR 8 bit.

        Trả về ảnh dạng ``uint8`` và mặt nạ đất liền (hoặc ``None``).
        """
        img = self._sea_background(rng)
        land_mask = None
        if with_land:
            img, land_mask = self._add_land(img, rng)

        for ship in ships:
            self._draw_ship(img, ship, rng)

        # Nhiễu đốm nhân tính, mô hình đa nhìn (multi-look) phân bố Gamma
        L = self.speckle_looks
        speckle = rng.gamma(shape=L, scale=1.0 / L, size=img.shape)
        img = img * speckle

        # Nén lô-ga-rít về thang decibel rồi lượng tử hoá 8 bit
        img = np.clip(img, 1e-4, None)
        db = 20.0 * np.log10(img)
        lo, hi = np.percentile(db, [1.0, 99.6])
        if hi - lo < 1e-6:
            hi = lo + 1.0
        out = np.clip((db - lo) / (hi - lo), 0.0, 1.0)
        return (out * 255.0).astype(np.uint8), land_mask
