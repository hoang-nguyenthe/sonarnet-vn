"""Chỉ tiêu đánh giá tầng hợp nhất ảnh radar và tín hiệu AIS.

Ba nhóm chỉ tiêu được tính:

1. **Chất lượng ghép cặp** — tỉ lệ phương tiện có AIS được ghép đúng với chính
   nó, và sai số vị trí của phép ghép.
2. **Chất lượng phát hiện phương tiện ngắt định danh** — độ chính xác và độ nhạy
   đối với lớp ``DARK``. Đây là chỉ tiêu quan trọng nhất của toàn hệ thống.
3. **Chất lượng phân loại ba trạng thái** — ma trận nhầm lẫn đầy đủ.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..data.simulator import AIS_MISMATCH, AIS_OK, DARK, IDENTITY_STATES


@dataclass
class FusionMetrics:
    """Tập chỉ tiêu của tầng hợp nhất."""

    # Ghép cặp
    match_accuracy: float
    mean_match_error_m: float
    median_match_error_m: float
    p90_match_error_m: float
    # Phát hiện phương tiện ngắt định danh
    dark_precision: float
    dark_recall: float
    dark_f1: float
    # Phân loại ba trạng thái
    state_accuracy: float
    state_macro_f1: float
    confusion_matrix: np.ndarray
    per_state_f1: Dict[str, float] = field(default_factory=dict)
    n_evaluated: int = 0

    def to_dict(self) -> Dict:
        return {
            "match_accuracy": round(float(self.match_accuracy), 4),
            "mean_match_error_m": round(float(self.mean_match_error_m), 2),
            "median_match_error_m": round(float(self.median_match_error_m), 2),
            "p90_match_error_m": round(float(self.p90_match_error_m), 2),
            "dark_precision": round(float(self.dark_precision), 4),
            "dark_recall": round(float(self.dark_recall), 4),
            "dark_f1": round(float(self.dark_f1), 4),
            "state_accuracy": round(float(self.state_accuracy), 4),
            "state_macro_f1": round(float(self.state_macro_f1), 4),
            "confusion_matrix": self.confusion_matrix.tolist(),
            "confusion_labels": list(IDENTITY_STATES),
            "per_state_f1": {k: round(float(v), 4) for k, v in self.per_state_f1.items()},
            "n_evaluated": self.n_evaluated,
        }


def _prf(tp: int, fp: int, fn: int) -> Tuple[float, float, float]:
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f = 2 * p * r / (p + r) if (p + r) else 0.0
    return p, r, f


def evaluate_fusion(
    true_states: Sequence[str],
    pred_states: Sequence[str],
    true_mmsi: Sequence[Optional[int]],
    pred_mmsi: Sequence[Optional[int]],
    match_errors_m: Sequence[float],
) -> FusionMetrics:
    """Tính toàn bộ chỉ tiêu của tầng hợp nhất.

    Bốn dãy đầu vào có cùng độ dài và cùng thứ tự, mỗi phần tử ứng với một phát
    hiện đã được ghép với một phương tiện đối chứng.
    """
    true_states = [str(s) for s in true_states]
    pred_states = [str(s) for s in pred_states]
    n = len(true_states)

    if n == 0:
        return FusionMetrics(
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
            np.zeros((3, 3), dtype=int), {}, 0,
        )

    # -- Ghép cặp ----------------------------------------------------------
    # Chỉ xét các phương tiện thực sự có phát AIS
    correct, total_with_ais = 0, 0
    for ts, tm, pm in zip(true_states, true_mmsi, pred_mmsi):
        if ts == DARK:
            continue
        total_with_ais += 1
        if tm is not None and pm is not None and int(tm) == int(pm):
            correct += 1
    match_acc = correct / total_with_ais if total_with_ais else 0.0

    errs = np.array(
        [e for e in match_errors_m if e is not None and np.isfinite(e)], dtype=float
    )
    mean_e = float(np.mean(errs)) if errs.size else float("nan")
    med_e = float(np.median(errs)) if errs.size else float("nan")
    p90_e = float(np.percentile(errs, 90)) if errs.size else float("nan")

    # -- Phát hiện phương tiện ngắt định danh -------------------------------
    tp = sum(1 for t, p in zip(true_states, pred_states) if t == DARK and p == DARK)
    fp = sum(1 for t, p in zip(true_states, pred_states) if t != DARK and p == DARK)
    fn = sum(1 for t, p in zip(true_states, pred_states) if t == DARK and p != DARK)
    d_p, d_r, d_f = _prf(tp, fp, fn)

    # -- Phân loại ba trạng thái -------------------------------------------
    idx = {s: i for i, s in enumerate(IDENTITY_STATES)}
    cm = np.zeros((len(IDENTITY_STATES), len(IDENTITY_STATES)), dtype=int)
    for t, p in zip(true_states, pred_states):
        if t in idx and p in idx:
            cm[idx[t], idx[p]] += 1

    acc = float(np.trace(cm) / max(cm.sum(), 1))
    per_state: Dict[str, float] = {}
    for s in IDENTITY_STATES:
        i = idx[s]
        s_tp = int(cm[i, i])
        s_fp = int(cm[:, i].sum() - s_tp)
        s_fn = int(cm[i, :].sum() - s_tp)
        per_state[s] = _prf(s_tp, s_fp, s_fn)[2]
    macro_f1 = float(np.mean(list(per_state.values())))

    return FusionMetrics(
        match_accuracy=match_acc,
        mean_match_error_m=mean_e,
        median_match_error_m=med_e,
        p90_match_error_m=p90_e,
        dark_precision=d_p, dark_recall=d_r, dark_f1=d_f,
        state_accuracy=acc, state_macro_f1=macro_f1,
        confusion_matrix=cm, per_state_f1=per_state,
        n_evaluated=n,
    )


def compare_interpolation_methods(
    scenes_meta: Sequence[Dict],
    ais_by_scene: Dict[str, List[Dict]],
    cfg,
) -> Dict[str, Dict[str, float]]:
    """So sánh bộ lọc Kalman với nội suy tuyến tính.

    Chỉ tiêu là sai số giữa vị trí nội suy và vị trí thật của phương tiện tại
    đúng thời điểm chụp ảnh. Phép so sánh này lượng hoá đóng góp riêng của bước
    nội suy trong toàn bộ tầng hợp nhất.
    """
    from ..data.geo import haversine_m
    from ..fusion.kalman import ConstantVelocityKalman, linear_interpolate_to_time

    kf = ConstantVelocityKalman(
        process_noise=cfg.fusion.kalman_process_noise,
        measurement_noise=cfg.fusion.kalman_measurement_noise,
    )
    errors = {"kalman": [], "linear": []}

    for meta in scenes_meta:
        sid = meta["scene_id"]
        t_cap = float(meta["capture_time_s"])
        recs = ais_by_scene.get(sid, [])
        by_mmsi: Dict[int, List[Dict]] = {}
        for r in recs:
            by_mmsi.setdefault(int(r["mmsi"]), []).append(r)

        for v in meta["vessels"]:
            if v["identity_state"] == DARK:
                continue
            rs = by_mmsi.get(int(v["mmsi"]))
            if not rs:
                continue
            for name, fn in (
                ("kalman", lambda rr: kf.smooth_to_time(rr, t_cap)),
                ("linear", lambda rr: linear_interpolate_to_time(rr, t_cap)),
            ):
                est = fn(rs)
                if est is None:
                    continue
                err = float(
                    haversine_m(v["lat"], v["lon"], est.lat, est.lon)
                )
                errors[name].append(err)

    out: Dict[str, Dict[str, float]] = {}
    for name, vals in errors.items():
        arr = np.array(vals, dtype=float)
        out[name] = {
            "mean_error_m": float(np.mean(arr)) if arr.size else float("nan"),
            "median_error_m": float(np.median(arr)) if arr.size else float("nan"),
            "p90_error_m": float(np.percentile(arr, 90)) if arr.size else float("nan"),
            "n": int(arr.size),
        }
    return out
