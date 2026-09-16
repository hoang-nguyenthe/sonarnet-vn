"""Hợp nhất phát hiện trên ảnh radar với tín hiệu AIS.

Quy trình gồm ba bước, đúng như mô tả trong đề xuất:

1. **Nội suy quỹ đạo AIS** về đúng thời điểm chụp ảnh bằng bộ lọc Kalman.
2. **Ghép cặp tối ưu toàn cục** giữa tập phát hiện và tập vị trí AIS bằng thuật
   toán Hungarian, với ma trận chi phí là khoảng cách địa lý và ngưỡng chặn trên.
3. **Phân loại trạng thái định danh** của từng phát hiện thành một trong ba mức:
   phát tín hiệu trung thực, phát tín hiệu nhưng kích thước khai báo sai lệch,
   hoặc không phát tín hiệu.

Bước thứ ba là điểm mấu chốt: một phương tiện xuất hiện rõ trên ảnh radar mà
không có bản ghi AIS tương ứng chính là dấu hiệu đặc trưng của hành vi chủ động
ngắt định danh.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..data.geo import haversine_m
from ..data.simulator import AIS_MISMATCH, AIS_OK, DARK
from .kalman import ConstantVelocityKalman, KalmanEstimate, linear_interpolate_to_time

try:
    from scipy.optimize import linear_sum_assignment as _hungarian

    _HAS_SCIPY = True
except Exception:  # pragma: no cover
    _HAS_SCIPY = False


def _greedy_assignment(cost: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Ghép cặp tham lam — phương án thay thế khi thiếu SciPy."""
    cost = cost.copy()
    rows, cols = [], []
    n, m = cost.shape
    for _ in range(min(n, m)):
        idx = int(np.argmin(cost))
        r, c = divmod(idx, m)
        if not np.isfinite(cost[r, c]):
            break
        rows.append(r)
        cols.append(c)
        cost[r, :] = np.inf
        cost[:, c] = np.inf
    return np.array(rows, dtype=int), np.array(cols, dtype=int)


def solve_assignment(cost: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Giải bài toán gán tối ưu, ưu tiên thuật toán Hungarian của SciPy."""
    if cost.size == 0:
        return np.array([], dtype=int), np.array([], dtype=int)
    if _HAS_SCIPY:
        # Thay vô cực bằng một chi phí hữu hạn rất lớn để SciPy xử lý được
        big = np.nanmax(cost[np.isfinite(cost)]) if np.any(np.isfinite(cost)) else 1.0
        safe = np.where(np.isfinite(cost), cost, big * 1e6 + 1e6)
        r, c = _hungarian(safe)
        return r, c
    return _greedy_assignment(cost)


@dataclass
class Detection:
    """Một phát hiện trên ảnh radar, đã quy về toạ độ địa lý."""

    det_id: int
    lat: float
    lon: float
    length_m: float          # chiều dài ước lượng từ khung bao
    width_m: float
    bbox: Tuple[float, float, float, float]
    score: float = 1.0


@dataclass
class FusionResult:
    """Kết quả hợp nhất cho một cảnh."""

    scene_id: str
    # Trạng thái dự đoán cho từng phát hiện, cùng thứ tự với danh sách đầu vào
    states: List[str] = field(default_factory=list)
    matched_mmsi: List[Optional[int]] = field(default_factory=list)
    match_distance_m: List[float] = field(default_factory=list)
    # Các MMSI có phát AIS nhưng không ghép được với phát hiện nào
    unmatched_mmsi: List[int] = field(default_factory=list)
    n_detections: int = 0
    n_ais_vessels: int = 0

    def summary(self) -> Dict[str, int]:
        out = {s: 0 for s in (AIS_OK, AIS_MISMATCH, DARK)}
        for s in self.states:
            out[s] = out.get(s, 0) + 1
        return out


class SARAISFusion:
    """Bộ hợp nhất ảnh radar và tín hiệu AIS."""

    def __init__(self, cfg, use_kalman: bool = True) -> None:
        self.cfg = cfg
        self.use_kalman = use_kalman
        self.kf = ConstantVelocityKalman(
            process_noise=cfg.fusion.kalman_process_noise,
            measurement_noise=cfg.fusion.kalman_measurement_noise,
        )

    # -- Bước 1: nội suy --------------------------------------------------
    def interpolate_ais(
        self, ais_records: Sequence[dict], capture_time_s: float
    ) -> Dict[int, KalmanEstimate]:
        """Ước lượng vị trí của mọi phương tiện có AIS tại thời điểm chụp."""
        by_mmsi: Dict[int, List[dict]] = {}
        for rec in ais_records:
            by_mmsi.setdefault(int(rec["mmsi"]), []).append(rec)

        out: Dict[int, KalmanEstimate] = {}
        for mmsi, recs in by_mmsi.items():
            est = (
                self.kf.smooth_to_time(recs, capture_time_s)
                if self.use_kalman
                else linear_interpolate_to_time(recs, capture_time_s)
            )
            if est is not None:
                est_declared = float(recs[0].get("declared_length_m", float("nan")))
                out[mmsi] = est
                setattr(out[mmsi], "declared_length_m", est_declared)
        return out

    # -- Bước 2: ghép cặp -------------------------------------------------
    def match(
        self,
        detections: Sequence[Detection],
        ais_estimates: Dict[int, KalmanEstimate],
    ) -> Tuple[Dict[int, int], Dict[int, float]]:
        """Ghép phát hiện với vị trí AIS. Trả về ánh xạ chỉ số phát hiện → MMSI."""
        if not detections or not ais_estimates:
            return {}, {}

        mmsis = list(ais_estimates.keys())
        det_lat = np.array([d.lat for d in detections])
        det_lon = np.array([d.lon for d in detections])
        ais_lat = np.array([ais_estimates[m].lat for m in mmsis])
        ais_lon = np.array([ais_estimates[m].lon for m in mmsis])

        # Ma trận chi phí: khoảng cách địa lý giữa mọi cặp
        cost = haversine_m(
            det_lat[:, None], det_lon[:, None], ais_lat[None, :], ais_lon[None, :]
        )
        thr = self.cfg.fusion.max_match_distance_m
        cost_masked = np.where(cost <= thr, cost, np.inf)

        rows, cols = solve_assignment(cost_masked)

        det_to_mmsi: Dict[int, int] = {}
        distances: Dict[int, float] = {}
        for r, c in zip(rows, cols):
            d = float(cost[r, c])
            if d <= thr:
                det_to_mmsi[int(r)] = int(mmsis[int(c)])
                distances[int(r)] = d
        return det_to_mmsi, distances

    # -- Bước 3: phân loại trạng thái -------------------------------------
    def classify_states(
        self,
        detections: Sequence[Detection],
        det_to_mmsi: Dict[int, int],
        ais_estimates: Dict[int, KalmanEstimate],
    ) -> List[str]:
        """Gán một trong ba trạng thái định danh cho từng phát hiện."""
        ratio_thr = self.cfg.fusion.size_mismatch_ratio
        states: List[str] = []
        for i, det in enumerate(detections):
            mmsi = det_to_mmsi.get(i)
            if mmsi is None:
                states.append(DARK)
                continue
            declared = getattr(ais_estimates[mmsi], "declared_length_m", float("nan"))
            if not np.isfinite(declared) or declared <= 0 or det.length_m <= 0:
                states.append(AIS_OK)
                continue
            # Sai lệch tương đối giữa kích thước khai báo và kích thước quan sát
            rel = abs(declared - det.length_m) / max(declared, det.length_m)
            states.append(AIS_MISMATCH if rel >= ratio_thr else AIS_OK)
        return states

    # -- Giao diện tổng hợp -----------------------------------------------
    def run(
        self,
        scene_id: str,
        detections: Sequence[Detection],
        ais_records: Sequence[dict],
        capture_time_s: float,
    ) -> FusionResult:
        est = self.interpolate_ais(ais_records, capture_time_s)
        det_to_mmsi, dists = self.match(detections, est)
        states = self.classify_states(detections, det_to_mmsi, est)

        matched = set(det_to_mmsi.values())
        return FusionResult(
            scene_id=scene_id,
            states=states,
            matched_mmsi=[det_to_mmsi.get(i) for i in range(len(detections))],
            match_distance_m=[dists.get(i, float("nan")) for i in range(len(detections))],
            unmatched_mmsi=[m for m in est.keys() if m not in matched],
            n_detections=len(detections),
            n_ais_vessels=len(est),
        )


def detections_from_boxes(
    boxes: np.ndarray, scores: np.ndarray, georef, pixel_spacing_m: float
) -> List[Detection]:
    """Chuyển khung bao trên ảnh thành các phát hiện có toạ độ địa lý."""
    dets: List[Detection] = []
    for i, (b, s) in enumerate(zip(boxes, scores)):
        x1, y1, x2, y2 = [float(v) for v in b]
        cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        lon, lat = georef.pixel_to_lonlat(cx, cy)
        w_px, h_px = abs(x2 - x1), abs(y2 - y1)
        # Chiều dài lấy theo cạnh lớn của khung bao, đã trừ phần đệm khi gán nhãn
        length_m = max(w_px, h_px) * pixel_spacing_m
        width_m = min(w_px, h_px) * pixel_spacing_m
        dets.append(
            Detection(
                det_id=i, lat=float(lat), lon=float(lon),
                length_m=length_m, width_m=width_m,
                bbox=(x1, y1, x2, y2), score=float(s),
            )
        )
    return dets
