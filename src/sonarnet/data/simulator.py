"""Mô phỏng liên kết giữa cảnh ảnh SAR và dòng tín hiệu AIS.

Đây là thành phần cho phép toàn bộ pipeline chạy được từ đầu đến cuối mà không
cần khoá truy cập Copernicus hay Global Fishing Watch. Mỗi cảnh mô phỏng gồm ba
lớp thông tin gắn chặt với nhau:

1. Danh sách phương tiện thật sự có mặt trong vùng ảnh, kèm toạ độ địa lý,
   kích thước, hướng và tốc độ.
2. Ảnh SAR dựng từ chính danh sách đó.
3. Dòng bản ghi AIS phát ra bởi các phương tiện *có* định danh, kèm nhiễu vị trí
   và nhịp phát không đều như trong thực tế.

Nhờ cấu trúc này, mọi chỉ tiêu của tầng hợp nhất đều có nhãn đối chứng chính xác.

Ba trạng thái định danh được mô phỏng, tương ứng với phân loại mà hệ thống cần
nhận ra:

* ``AIS_OK``       — phát tín hiệu đầy đủ và trung thực;
* ``AIS_MISMATCH`` — có phát tín hiệu nhưng kích thước khai báo sai lệch lớn so
  với kích thước quan sát được trên ảnh radar;
* ``DARK``         — không phát tín hiệu tại thời điểm chụp.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from .geo import SceneGeoReference
from .sar_render import SARRenderer, ShipFootprint

# Ba trạng thái định danh
AIS_OK = "AIS_OK"
AIS_MISMATCH = "AIS_MISMATCH"
DARK = "DARK"
IDENTITY_STATES = (AIS_OK, AIS_MISMATCH, DARK)

# Bốn nhóm hành vi hoạt động
BEHAVIOURS = ("qua_canh", "cau", "keo_luoi", "neo_dau")

# Đặc tả các lớp phương tiện: (tên, dài tối thiểu, dài tối đa, tỉ lệ rộng/dài)
VESSEL_CLASSES = [
    ("tau_ca_nho", 60.0, 110.0, 0.26),
    ("tau_ca_von_sat", 110.0, 190.0, 0.22),
    ("tau_hau_can", 170.0, 260.0, 0.18),
    ("tau_van_tai", 220.0, 330.0, 0.15),
]

# Dải tốc độ đặc trưng cho từng nhóm hành vi, đơn vị hải lý trên giờ
BEHAVIOUR_SPEED = {
    "qua_canh": (9.5, 17.0),
    "cau": (1.8, 4.5),
    "keo_luoi": (3.0, 6.2),
    "neo_dau": (0.0, 0.9),
}


@dataclass
class Vessel:
    """Một phương tiện trong cảnh, kèm toàn bộ thông tin đối chứng."""

    mmsi: int
    lat: float
    lon: float
    length_m: float
    width_m: float
    heading_deg: float
    speed_kn: float
    vessel_class: str
    behaviour: str
    identity_state: str
    # Kích thước khai báo qua AIS; khác length_m ở các trường hợp AIS_MISMATCH
    declared_length_m: float
    # Toạ độ điểm ảnh và khung bao trên ảnh
    cx: float = 0.0
    cy: float = 0.0
    bbox: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)

    @property
    def has_ais(self) -> bool:
        return self.identity_state != DARK


@dataclass
class Scene:
    """Một cảnh ảnh hoàn chỉnh cùng dữ liệu AIS đi kèm."""

    scene_id: str
    image: np.ndarray
    georef: SceneGeoReference
    vessels: List[Vessel]
    ais_records: List[Dict]
    capture_time_s: float
    land_mask: Optional[np.ndarray] = None
    meta: Dict = field(default_factory=dict)

    @property
    def boxes(self) -> np.ndarray:
        """Khung bao đối chứng, dạng mảng (N, 4) theo thứ tự x1, y1, x2, y2."""
        if not self.vessels:
            return np.zeros((0, 4), dtype=np.float32)
        return np.array([v.bbox for v in self.vessels], dtype=np.float32)

    def count_by_state(self) -> Dict[str, int]:
        out = {s: 0 for s in IDENTITY_STATES}
        for v in self.vessels:
            out[v.identity_state] += 1
        return out


class SceneSimulator:
    """Sinh các cảnh mô phỏng theo cấu hình đã cho."""

    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self.renderer = SARRenderer(
            size=cfg.data.scene_size,
            azimuth_ambiguity=cfg.data.azimuth_ambiguity,
        )
        self._mmsi_counter = 574_000_000  # Dải MMSI của Việt Nam bắt đầu bằng 574

    # -- Trợ giúp ----------------------------------------------------------
    def _next_mmsi(self, rng: np.random.Generator) -> int:
        self._mmsi_counter += int(rng.integers(7, 900))
        return self._mmsi_counter

    def _sample_vessel_class(self, rng: np.random.Generator) -> Tuple[str, float, float]:
        idx = rng.choice(len(VESSEL_CLASSES), p=[0.42, 0.30, 0.17, 0.11])
        name, lo, hi, ratio = VESSEL_CLASSES[idx]
        length = float(rng.uniform(lo, hi))
        width = float(length * ratio * rng.uniform(0.85, 1.15))
        return name, length, width

    def _sample_identity_state(self, rng: np.random.Generator) -> str:
        p_dark = self.cfg.data.dark_vessel_ratio
        # Tăng từ 0,10 lên 0,18 sau khi thấy MISMATCH F1 kém trên bản chạy đầu:
        # số mẫu MISMATCH quá ít so với AIS_OK, lớp bị dưới đại diện; tăng để bộ
        # phân loại nhận đủ ví dụ.
        p_mismatch = 0.18
        r = rng.random()
        if r < p_dark:
            return DARK
        if r < p_dark + p_mismatch:
            return AIS_MISMATCH
        return AIS_OK

    # -- Sinh phương tiện --------------------------------------------------
    def _make_vessels(
        self, georef: SceneGeoReference, rng: np.random.Generator,
        land_mask: Optional[np.ndarray],
    ) -> List[Vessel]:
        lo, hi = self.cfg.data.ships_per_scene
        n = int(rng.integers(lo, hi + 1))
        spacing = self.cfg.geo.pixel_spacing_m
        size = self.cfg.data.scene_size
        margin = 26

        vessels: List[Vessel] = []
        placed: List[Tuple[float, float, float]] = []  # (cx, cy, bán kính chiếm chỗ)

        attempts = 0
        while len(vessels) < n and attempts < n * 60:
            attempts += 1
            cx = float(rng.uniform(margin, size - margin))
            cy = float(rng.uniform(margin, size - margin))

            # Không đặt phương tiện lên vùng đất liền
            if land_mask is not None and land_mask[int(cy), int(cx)] > 0.25:
                continue

            cls, length_m, width_m = self._sample_vessel_class(rng)
            length_px = length_m / spacing
            width_px = width_m / spacing
            radius = 0.5 * length_px + 8.0

            # Tránh chồng lấn để nhãn đối chứng không nhập nhằng
            if any(
                (cx - px) ** 2 + (cy - py) ** 2 < (radius + pr) ** 2
                for px, py, pr in placed
            ):
                continue

            behaviour = str(rng.choice(BEHAVIOURS, p=[0.34, 0.27, 0.23, 0.16]))
            s_lo, s_hi = BEHAVIOUR_SPEED[behaviour]
            speed = float(rng.uniform(s_lo, s_hi))
            heading = float(rng.uniform(0, 360))
            state = self._sample_identity_state(rng)

            declared = length_m
            if state == AIS_MISMATCH:
                # Khai báo sai lệch mạnh theo một trong hai hướng
                factor = rng.choice([rng.uniform(0.22, 0.42), rng.uniform(2.1, 3.4)])
                declared = float(length_m * factor)

            lon, lat = georef.pixel_to_lonlat(cx, cy)
            footprint = ShipFootprint(
                cx=cx, cy=cy,
                length_px=length_px, width_px=width_px,
                heading_deg=heading,
                rcs=float(rng.uniform(2.6, 7.5)),
                moving=speed > 3.0,
            )
            v = Vessel(
                mmsi=self._next_mmsi(rng),
                lat=float(lat), lon=float(lon),
                length_m=length_m, width_m=width_m,
                heading_deg=heading, speed_kn=speed,
                vessel_class=cls, behaviour=behaviour,
                identity_state=state, declared_length_m=declared,
                cx=cx, cy=cy, bbox=footprint.bbox(),
            )
            vessels.append(v)
            placed.append((cx, cy, radius))
            # Lưu tạm footprint để dựng ảnh
            v_meta = getattr(self, "_footprints", None)
            if v_meta is None:
                self._footprints = {}
            self._footprints[v.mmsi] = footprint

        return vessels

    # -- Sinh bản ghi AIS --------------------------------------------------
    def _make_ais(
        self, vessels: List[Vessel], capture_time_s: float, rng: np.random.Generator
    ) -> List[Dict]:
        """Sinh dòng bản ghi AIS quanh thời điểm chụp ảnh.

        Quỹ đạo thật của mỗi phương tiện được tích phân từ một chuỗi gia tốc
        nhiễu trắng biên độ nhỏ, thay vì giả định vận tốc không đổi tuyệt đối.
        Đây là điểm quan trọng: trên biển, tàu luôn đổi tốc và đổi hướng nhẹ do
        sóng, dòng chảy và thao tác bánh lái. Một mô phỏng tuyến tính hoàn hảo sẽ
        khiến mọi phép so sánh giữa các phương pháp nội suy mất ý nghĩa.

        Quỹ đạo được neo sao cho vị trí tại đúng thời điểm chụp ảnh trùng khớp
        với vị trí đối chứng của phương tiện. Trên nền quỹ đạo đó, hệ thống lấy
        mẫu tại các mốc thời gian không đều và cộng thêm nhiễu đo của thiết bị.

        Phương tiện ở trạng thái ``DARK`` hoàn toàn không xuất hiện trong dòng
        dữ liệu này — đúng như tình huống tàu chủ động ngắt thiết bị.
        """
        window = self.cfg.data.ais_window_s
        noise_m = self.cfg.data.ais_position_noise_m
        int_lo, int_hi = self.cfg.data.ais_interval_s
        # Biên độ gia tốc nhiễu, mét trên giây bình phương. Giá trị nhỏ phản ánh
        # quán tính lớn của phương tiện đường thuỷ.
        accel_sigma = 0.012
        step = 15.0  # bước tích phân quỹ đạo, giây

        records: List[Dict] = []

        for v in vessels:
            if not v.has_ais:
                continue

            speed_ms = v.speed_kn * 0.514444
            course = np.radians(v.heading_deg)
            vx0 = speed_ms * np.cos(course)   # thành phần đông
            vy0 = speed_ms * np.sin(course)   # thành phần bắc

            # ---- Tích phân quỹ đạo thật trên lưới thời gian đều ----------
            grid = np.arange(-window - 60.0, window + 60.0 + step, step)
            n = len(grid)
            ax = rng.normal(0.0, accel_sigma, size=n)
            ay = rng.normal(0.0, accel_sigma, size=n)
            # Vận tốc là tích phân của gia tốc, lấy mốc không tại thời điểm chụp
            i0 = int(np.argmin(np.abs(grid)))
            vx = vx0 + np.cumsum(ax) * step
            vy = vy0 + np.cumsum(ay) * step
            vx -= vx[i0] - vx0
            vy -= vy[i0] - vy0
            # Vị trí là tích phân của vận tốc, neo về gốc tại thời điểm chụp
            px = np.cumsum(vx) * step
            py = np.cumsum(vy) * step
            px -= px[i0]
            py -= py[i0]

            m_lat = 111_132.0
            m_lon = 111_320.0 * np.cos(np.radians(v.lat))

            # ---- Lấy mẫu tại các mốc phát tín hiệu không đều -------------
            t = capture_time_s - window
            times = []
            while t <= capture_time_s + window:
                times.append(t)
                t += float(rng.uniform(int_lo, int_hi))

            # Một phần phương tiện có khoảng trống ngắn trong dòng tín hiệu,
            # phản ánh mất sóng do nhiễu hoặc che khuất
            if rng.random() < 0.22 and len(times) > 6:
                g0 = int(rng.integers(1, len(times) - 4))
                g1 = min(len(times), g0 + int(rng.integers(2, 5)))
                times = times[:g0] + times[g1:]

            for ts in times:
                dt = ts - capture_time_s
                east = float(np.interp(dt, grid, px)) + rng.normal(0.0, noise_m)
                north = float(np.interp(dt, grid, py)) + rng.normal(0.0, noise_m)
                sog = float(np.hypot(
                    np.interp(dt, grid, vx), np.interp(dt, grid, vy)
                )) / 0.514444
                records.append(
                    {
                        "mmsi": v.mmsi,
                        "timestamp": float(ts),
                        "lat": float(v.lat + north / m_lat),
                        "lon": float(v.lon + east / m_lon),
                        "sog_kn": float(max(0.0, sog + rng.normal(0, 0.2))),
                        "cog_deg": float((v.heading_deg + rng.normal(0, 3.5)) % 360.0),
                        "declared_length_m": float(v.declared_length_m),
                    }
                )

        records.sort(key=lambda r: r["timestamp"])
        return records

    # -- Giao diện chính ---------------------------------------------------
    def generate_scene(self, scene_id: str, rng: np.random.Generator) -> Scene:
        size = self.cfg.data.scene_size
        spacing = self.cfg.geo.pixel_spacing_m
        g = self.cfg.geo

        # Chọn ngẫu nhiên một ô con trong vùng thí điểm
        span_deg_lat = (size * spacing) / 111_132.0
        lat_top = float(rng.uniform(g.lat_min + span_deg_lat, g.lat_max))
        span_deg_lon = (size * spacing) / (111_320.0 * np.cos(np.radians(lat_top)))
        lon_left = float(rng.uniform(g.lon_min, g.lon_max - span_deg_lon))

        georef = SceneGeoReference(
            lat_top=lat_top, lon_left=lon_left,
            width=size, height=size, pixel_spacing_m=spacing,
        )

        # Vùng đất liền được quyết định trước để tránh đặt phương tiện lên bờ
        with_land = bool(rng.random() < self.cfg.data.land_probability)
        land_mask = None
        if with_land:
            probe = self.renderer._sea_background(rng)
            _, land_mask = self.renderer._add_land(probe, rng)

        self._footprints = {}
        vessels = self._make_vessels(georef, rng, land_mask)
        footprints = [self._footprints[v.mmsi] for v in vessels]

        image, rendered_mask = self.renderer.render(
            footprints, rng, with_land=with_land
        )
        if rendered_mask is not None:
            land_mask = rendered_mask

        capture_time_s = float(rng.uniform(0, 86_400))
        ais = self._make_ais(vessels, capture_time_s, rng)

        return Scene(
            scene_id=scene_id,
            image=image,
            georef=georef,
            vessels=vessels,
            ais_records=ais,
            capture_time_s=capture_time_s,
            land_mask=land_mask,
            meta={
                "with_land": with_land,
                "n_vessels": len(vessels),
                "n_ais_records": len(ais),
            },
        )

    def generate_split(
        self, n_scenes: int, prefix: str, rng: np.random.Generator
    ) -> List[Scene]:
        """Sinh một tập cảnh với định danh liên tiếp."""
        return [
            self.generate_scene(f"{prefix}_{i:05d}", rng) for i in range(n_scenes)
        ]
