"""Hợp nhất phát hiện trên ảnh radar với tín hiệu AIS.

Quy trình gồm ba bước, đúng như mô tả trong đề xuất:

1. **Nội suy quỹ đạo AIS** về đúng thời điểm chụp ảnh bằng bộ lọc Kalman.
2. **Ghép cặp tối ưu toàn cục** giữa tập phát hiện và tập vị trí AIS bằng thuật
   toán Hungarian, với ma trận chi phí là khoảng cách địa lý và ngưỡng chặn trên.
3. Trả trạng thái quan sát: thiếu dữ liệu, không ghép được hoặc chờ xác minh.
Không ghép được AIS không chứng minh tàu ngắt thiết bị hay vi phạm.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..data.geo import haversine_m
from ..data.simulator import AIS_MISMATCH, AIS_OK, DARK
from .status import MISSING_DATA, EVALUATION_STATES
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


def _stable_associations(detections, estimates, rejected, cfg):
    """Propose once using distance, then veto without reassigning either endpoint."""
    keys = list(estimates)
    det_lat, det_lon = (np.array([getattr(d,k) for d in detections]) for k in ('lat','lon'))
    ais_lat, ais_lon = (np.array([getattr(estimates[key],k) for key in keys]) for k in ('lat','lon'))
    valid_points = (np.abs(det_lat) <= 90) & (np.abs(det_lon) <= 180)
    valid_tracks = (np.abs(ais_lat) <= 90) & (np.abs(ais_lon) <= 180)
    # Infinite costs keep invalid coordinates out of the nominal assignment
    # and out of the two-sided search for competitors.
    distance = haversine_m(det_lat[:,None],det_lon[:,None],ais_lat[None,:],ais_lon[None,:])
    distance = np.where(valid_points[:,None] & valid_tracks[None,:],distance,np.inf)
    rows, cols = solve_assignment(np.where(distance <= cfg.max_match_distance_m,distance,np.inf))
    reasons = ['invalid_detection' if not valid else 'out_of_range' for valid in valid_points]
    for i, row in enumerate(distance):
        nearby = np.argmin(row)
        if row[nearby] <= cfg.max_match_distance_m:
            reasons[i] = rejected.get(keys[nearby], 'assigned_elsewhere')
    matches, residuals, competing_points = {}, {}, set()
    for i,j in zip(rows,cols):
        d = float(distance[i,j])
        if d > cfg.max_match_distance_m:
            continue
        key = keys[j]
        if key in rejected:
            reasons[i] = rejected[key]
            continue
        sigma = np.hypot(cfg.sar_position_sigma_m, estimates[key].position_sigma_m)
        if d > cfg.match_sigma_multiplier*sigma:
            reasons[i] = 'out_of_range'
            continue
        row, column = distance[i,:].copy(), distance[:,j].copy()
        row[j] = column[i] = np.inf
        margin = max(cfg.min_assignment_margin_m, sigma) + 2 * max(0.,cfg.systematic_bias_guard_m)
        if min(row.min(),column.min()) <= d+margin:
            reasons[i] = 'ambiguous'
            competing_points.update(np.flatnonzero(column <= d+margin))
            continue
        matches[int(i)] = int(key)
        residuals[int(i)] = d
        reasons[i] = 'matched'
    for i in competing_points:
        if reasons[i] == 'assigned_elsewhere':
            reasons[i] = 'ambiguous'
    return matches, residuals, reasons


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
    match_reasons: List[str] = field(default_factory=list)
    # Các MMSI có phát AIS nhưng không ghép được với phát hiện nào
    unmatched_mmsi: List[int] = field(default_factory=list)
    n_detections: int = 0
    n_ais_vessels: int = 0

    def summary(self) -> Dict[str, int]:
        out = {s: 0 for s in EVALUATION_STATES}
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
            # A missing/invalid record cannot become evidence for identity.
            try:
                mmsi = int(rec['mmsi'])
                timestamp, lat, lon = (float(rec[k]) for k in ('timestamp','lat','lon'))
                if not all(np.isfinite(v) for v in (timestamp,lat,lon)) or abs(lat)>90 or abs(lon)>180:
                    continue
                if mmsi <= 0:
                    continue
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
            by_mmsi.setdefault(mmsi, []).append(dict(rec,timestamp=timestamp,lat=lat,lon=lon))

        out: Dict[int, KalmanEstimate] = {}
        for mmsi, recs in by_mmsi.items():
            est = (
                self.kf.smooth_to_time(recs, capture_time_s)
                if self.use_kalman
                else linear_interpolate_to_time(recs, capture_time_s,
                    measurement_noise=self.cfg.fusion.kalman_measurement_noise,
                    process_noise=self.cfg.fusion.kalman_process_noise)
            )
            if est is not None:
                try:
                    est_declared = float(recs[0].get("declared_length_m", float("nan")))
                except (TypeError, ValueError):
                    est_declared = float('nan')
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
        matches, distances, _ = self.match_with_reasons(detections, ais_estimates)
        return matches, distances

    def match_with_reasons(self, detections, ais_estimates):
        """Abstain when proximity, age, uncertainty or separation is inadequate.

        A narrow spatial residual cannot rescue stale or uncertain AIS. Candidate
        edges must satisfy both the absolute cap and a combined SAR/AIS 3-sigma
        gate. Competing positions are also screened under bounded displacement:
        an alternative may gain up to the guard distance while the original
        edge loses the same amount. Only the original gate can accept an edge.
        The default proposes once and then applies restrictions. The archival
        path is retained to reproduce the filter-first comparison. Reasons are
        aligned to the input detection order.
        """
        if not detections:
            return {}, {}, []
        if not ais_estimates:
            return {}, {}, ["no_ais"] * len(detections)
        cfg = self.cfg.fusion
        rejected = {}
        for m, est in ais_estimates.items():
            values = [est.lat, est.lon, est.gap_to_nearest_s, est.position_sigma_m]
            if (not all(np.isfinite(v) for v in values) or abs(est.lat) > 90
                    or abs(est.lon) > 180 or est.gap_to_nearest_s < 0
                    or est.position_sigma_m < 0 or est.n_observations < 1):
                rejected[m] = "invalid_ais"
            elif est.gap_to_nearest_s > cfg.max_ais_age_s:
                rejected[m] = "stale_ais"
            elif est.position_sigma_m > cfg.max_position_sigma_m:
                rejected[m] = "uncertain_position"
        if cfg.preserve_proposed_pair:
            return _stable_associations(detections,ais_estimates,rejected,cfg)
        mmsis = [m for m in ais_estimates if m not in rejected]
        if not mmsis:
            reason = next(iter(rejected.values())) if len(set(rejected.values())) == 1 else "uncertain_position"
            return {}, {}, [reason] * len(detections)
        det_lat = np.array([d.lat for d in detections])
        det_lon = np.array([d.lon for d in detections])
        ais_lat = np.array([ais_estimates[m].lat for m in mmsis])
        ais_lon = np.array([ais_estimates[m].lon for m in mmsis])

        # Ma trận chi phí: khoảng cách địa lý giữa mọi cặp
        cost = haversine_m(
            det_lat[:, None], det_lon[:, None], ais_lat[None, :], ais_lon[None, :]
        )
        sigma = np.hypot(cfg.sar_position_sigma_m,
                         [ais_estimates[m].position_sigma_m for m in mmsis])
        gate = np.minimum(cfg.max_match_distance_m, cfg.match_sigma_multiplier * sigma)
        cost_masked = np.where(np.isfinite(cost) & (cost <= gate[None, :]), cost, np.inf)
        reasons = ["out_of_range"] * len(detections)
        invalid_detections = set(np.flatnonzero(~np.isfinite(det_lat) | ~np.isfinite(det_lon)
                                               | (np.abs(det_lat)>90) | (np.abs(det_lon)>180)))
        for i in invalid_detections:
            cost_masked[i,:] = np.inf
        # Record nearby discarded AIS so absent usable evidence is not labelled
        # an ordinary spatial mismatch. Never use it to produce a match.
        for i, det in enumerate(detections):
            if not np.any(np.isfinite(cost_masked[i])):
                for m, reason in rejected.items():
                    est = ais_estimates[m]
                    if float(haversine_m(det.lat, det.lon, est.lat, est.lon)) <= cfg.max_match_distance_m:
                        reasons[i] = reason
                        break
        bias_guard = max(0., cfg.systematic_bias_guard_m)
        shadow_gate = np.minimum(cfg.max_match_distance_m, gate + bias_guard)
        plausible_cost = np.where(np.isfinite(cost) & (cost <= shadow_gate[None, :]), cost, np.inf)
        for i in invalid_detections:
            plausible_cost[i, :] = np.inf
        ambiguous = set()
        for i in range(len(detections)):
            candidates = np.flatnonzero(np.isfinite(plausible_cost[i]))
            if len(candidates) >= 2 and np.any(np.isfinite(cost_masked[i])):
                nearest = candidates[np.argsort(plausible_cost[i, candidates])[:2]]
                margin = max(cfg.min_assignment_margin_m, float(max(sigma[nearest]))) + 2 * bias_guard
                if plausible_cost[i, nearest[1]] - plausible_cost[i, nearest[0]] <= margin:
                    ambiguous.add(i)
        for j in range(len(mmsis)):
            candidates = np.flatnonzero(np.isfinite(plausible_cost[:, j]))
            if len(candidates) >= 2 and np.any(np.isfinite(cost_masked[:, j])):
                nearest = candidates[np.argsort(plausible_cost[candidates, j])[:2]]
                margin = max(cfg.min_assignment_margin_m, float(sigma[j])) + 2 * bias_guard
                if plausible_cost[nearest[1], j] - plausible_cost[nearest[0], j] <= margin:
                    ambiguous.update(int(i) for i in nearest)
        for i in range(len(detections)):
            if np.any(np.isfinite(cost_masked[i])):
                reasons[i] = "assigned_elsewhere"
        for i in ambiguous:
            cost_masked[i, :] = np.inf
            reasons[i] = "ambiguous"
        for i in invalid_detections:
            reasons[i] = 'invalid_detection'
        rows, cols = solve_assignment(cost_masked)

        det_to_mmsi: Dict[int, int] = {}
        distances: Dict[int, float] = {}
        for r, c in zip(rows, cols):
            d = float(cost[r, c])
            if np.isfinite(cost_masked[r, c]):
                det_to_mmsi[int(r)] = int(mmsis[int(c)])
                distances[int(r)] = d
                reasons[int(r)] = "matched"
        return det_to_mmsi, distances, reasons

    # -- Bước 3: phân loại trạng thái -------------------------------------
    def classify_states(
        self,
        detections: Sequence[Detection],
        det_to_mmsi: Dict[int, int],
        ais_estimates: Dict[int, KalmanEstimate],
        reasons: Optional[List[str]] = None,
    ) -> List[str]:
        """Describe evidence sufficiency without inferring identity or intent."""
        ratio_thr = self.cfg.fusion.size_mismatch_ratio
        states: List[str] = []
        for i, det in enumerate(detections):
            mmsi = det_to_mmsi.get(i)
            if mmsi is None:
                reason = reasons[i] if reasons else ('no_ais' if not ais_estimates else 'out_of_range')
                states.append(MISSING_DATA if reason in {'no_ais', 'stale_ais', 'uncertain_position', 'invalid_ais', 'invalid_detection'} else DARK)
                continue
            declared = getattr(ais_estimates[mmsi], "declared_length_m", float("nan"))
            if not np.isfinite(declared) or declared <= 0 or not np.isfinite(det.length_m) or det.length_m <= 0:
                states.append(MISSING_DATA)
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
        det_to_mmsi, dists, reasons = self.match_with_reasons(detections, est)
        states = self.classify_states(detections, det_to_mmsi, est, reasons)

        matched = set(det_to_mmsi.values())
        return FusionResult(
            scene_id=scene_id,
            states=states,
            matched_mmsi=[det_to_mmsi.get(i) for i in range(len(detections))],
            match_distance_m=[dists.get(i, float("nan")) for i in range(len(detections))],
            match_reasons=reasons,
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
