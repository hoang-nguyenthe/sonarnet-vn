"""Trích xuất đặc trưng động học từ quỹ đạo phương tiện.

Bộ đặc trưng được thiết kế để phân biệt bốn nhóm hành vi khai thác dựa trên các
dấu hiệu vật lý bền vững, không phụ thuộc vào vị trí địa lý tuyệt đối:

* **Thống kê tốc độ** — phân biệt quá cảnh (nhanh, ổn định) với neo đậu (gần như
  đứng yên) và các hoạt động khai thác (trung bình, biến động).
* **Thống kê đổi hướng** — câu có bước ngẫu nhiên mạnh về hướng, trong khi kéo
  lưới giữ hướng ổn định trên từng luống rồi quay đầu gấp.
* **Tỉ lệ dừng** — tỉ lệ thời gian tốc độ dưới ngưỡng, rất cao ở nhóm neo đậu.
* **Độ thẳng của đường đi** — tỉ số giữa khoảng cách hai đầu và tổng quãng đường,
  gần 1 với quá cảnh và rất nhỏ với neo đậu.
* **Bán kính hồi chuyển** — đo mức độ trải rộng không gian của quỹ đạo.
* **Đặc trưng phổ của chuỗi hướng** — nắm bắt tính tuần hoàn của mẫu răng lược
  đặc trưng cho hoạt động kéo lưới.
"""

from __future__ import annotations

from typing import Dict, List, Sequence

import numpy as np

from ..data.geo import meters_per_degree
from ..data.tracks import KNOT_TO_MS, Track

# Ngưỡng coi là đang dừng, tính theo hải lý trên giờ
STOP_SPEED_KN = 0.8

FEATURE_NAMES: List[str] = [
    "speed_mean", "speed_std", "speed_median", "speed_p10", "speed_p90",
    "speed_max", "speed_cv",
    "turn_abs_mean", "turn_abs_std", "turn_abs_p90", "turn_sign_changes",
    "stop_fraction", "moving_fraction",
    "straightness", "radius_gyration_m", "path_length_m", "net_displacement_m",
    "bbox_diag_m", "area_coverage_ratio",
    "accel_abs_mean", "accel_abs_std",
    "course_autocorr_lag1", "course_spectral_peak", "course_spectral_ratio",
    "speed_autocorr_lag1", "n_points",
]


def _angular_difference(a: np.ndarray) -> np.ndarray:
    """Chênh lệch hướng liên tiếp, quy về khoảng [-180, 180] độ."""
    d = np.diff(a)
    return (d + 180.0) % 360.0 - 180.0


def _local_xy(lats: np.ndarray, lons: np.ndarray) -> tuple:
    """Quy đổi kinh vĩ độ về toạ độ phẳng cục bộ, đơn vị mét."""
    lat0 = float(np.mean(lats))
    m_lat, m_lon = meters_per_degree(lat0)
    x = (lons - float(np.mean(lons))) * m_lon
    y = (lats - lat0) * m_lat
    return x, y


def extract_features(track: Track) -> Dict[str, float]:
    """Tính toàn bộ đặc trưng cho một quỹ đạo."""
    sp = np.asarray(track.speeds_kn, dtype=float)
    co = np.asarray(track.courses_deg, dtype=float)
    t = np.asarray(track.times_s, dtype=float)
    x, y = _local_xy(np.asarray(track.lats), np.asarray(track.lons))

    n = len(sp)
    dt = float(np.median(np.diff(t))) if n > 1 else 1.0

    # -- Tốc độ ------------------------------------------------------------
    speed_mean = float(np.mean(sp))
    speed_std = float(np.std(sp))
    f: Dict[str, float] = {
        "speed_mean": speed_mean,
        "speed_std": speed_std,
        "speed_median": float(np.median(sp)),
        "speed_p10": float(np.percentile(sp, 10)),
        "speed_p90": float(np.percentile(sp, 90)),
        "speed_max": float(np.max(sp)),
        "speed_cv": float(speed_std / (speed_mean + 1e-6)),
    }

    # -- Đổi hướng ---------------------------------------------------------
    turns = _angular_difference(co) if n > 1 else np.zeros(1)
    abs_turns = np.abs(turns)
    signs = np.sign(turns)
    f.update(
        {
            "turn_abs_mean": float(np.mean(abs_turns)),
            "turn_abs_std": float(np.std(abs_turns)),
            "turn_abs_p90": float(np.percentile(abs_turns, 90)),
            "turn_sign_changes": float(
                np.mean(np.abs(np.diff(signs)) > 0) if len(signs) > 1 else 0.0
            ),
        }
    )

    # -- Dừng và di chuyển -------------------------------------------------
    stop_frac = float(np.mean(sp < STOP_SPEED_KN))
    f["stop_fraction"] = stop_frac
    f["moving_fraction"] = 1.0 - stop_frac

    # -- Hình học đường đi --------------------------------------------------
    seg = np.hypot(np.diff(x), np.diff(y)) if n > 1 else np.zeros(1)
    path_len = float(np.sum(seg))
    net_disp = float(np.hypot(x[-1] - x[0], y[-1] - y[0])) if n > 1 else 0.0
    f["path_length_m"] = path_len
    f["net_displacement_m"] = net_disp
    f["straightness"] = float(net_disp / (path_len + 1e-6))

    cx, cy = float(np.mean(x)), float(np.mean(y))
    f["radius_gyration_m"] = float(np.sqrt(np.mean((x - cx) ** 2 + (y - cy) ** 2)))

    w = float(np.ptp(x))
    h = float(np.ptp(y))
    f["bbox_diag_m"] = float(np.hypot(w, h))
    f["area_coverage_ratio"] = float(path_len / (np.hypot(w, h) + 1e-6))

    # -- Gia tốc -----------------------------------------------------------
    acc = np.diff(sp * KNOT_TO_MS) / dt if n > 1 else np.zeros(1)
    f["accel_abs_mean"] = float(np.mean(np.abs(acc)))
    f["accel_abs_std"] = float(np.std(np.abs(acc)))

    # -- Tự tương quan và phổ ----------------------------------------------
    def _autocorr1(v: np.ndarray) -> float:
        if len(v) < 3:
            return 0.0
        v = v - np.mean(v)
        denom = float(np.dot(v, v))
        if denom < 1e-9:
            return 0.0
        return float(np.dot(v[:-1], v[1:]) / denom)

    f["course_autocorr_lag1"] = _autocorr1(turns)
    f["speed_autocorr_lag1"] = _autocorr1(sp)

    # Phổ của chuỗi đổi hướng: mẫu răng lược của kéo lưới tạo đỉnh phổ rõ rệt
    if len(turns) >= 8:
        sig = turns - np.mean(turns)
        spec = np.abs(np.fft.rfft(sig)) ** 2
        spec = spec[1:]  # bỏ thành phần một chiều
        if spec.size and float(np.sum(spec)) > 1e-12:
            peak = int(np.argmax(spec))
            f["course_spectral_peak"] = float(peak / len(spec))
            f["course_spectral_ratio"] = float(spec[peak] / np.sum(spec))
        else:
            f["course_spectral_peak"] = 0.0
            f["course_spectral_ratio"] = 0.0
    else:
        f["course_spectral_peak"] = 0.0
        f["course_spectral_ratio"] = 0.0

    f["n_points"] = float(n)
    return f


def features_matrix(tracks: Sequence[Track]) -> tuple:
    """Xây ma trận đặc trưng và vector nhãn từ danh sách quỹ đạo."""
    rows = [extract_features(tr) for tr in tracks]
    X = np.array([[r[name] for name in FEATURE_NAMES] for r in rows], dtype=np.float32)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    y = np.array([tr.behaviour for tr in tracks])
    return X, y
