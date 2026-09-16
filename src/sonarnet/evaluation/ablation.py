"""Phân tích đóng góp của từng thành phần trong hệ thống.

Bốn cấu hình được so sánh, đúng theo kế hoạch nêu trong đề xuất:

======  ==========================================================
Cấu hình  Nội dung
======  ==========================================================
A        Chỉ dùng ảnh radar. Hệ thống phát hiện được phương tiện
         nhưng không có căn cứ nào để xác định trạng thái định danh.
B        Chỉ dùng dữ liệu AIS. Mọi phương tiện chủ động ngắt tín
         hiệu đều vô hình đối với hệ thống.
C        Hợp nhất hai nguồn, nội suy tuyến tính, chưa kiểm tra
         kích thước khai báo.
D        Hệ thống đầy đủ: hợp nhất có bộ lọc Kalman và có kiểm tra
         kích thước khai báo.
======  ==========================================================

Phép so sánh này cho phép trả lời câu hỏi trọng tâm: mỗi thành phần đóng góp
bao nhiêu vào năng lực phát hiện phương tiện ngắt định danh.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..data.simulator import AIS_MISMATCH, AIS_OK, DARK
from ..utils import get_logger
from .fusion_metrics import FusionMetrics, evaluate_fusion

LOG = get_logger("evaluation.ablation")

CONFIG_LABELS = {
    "A": "Chỉ ảnh radar",
    "B": "Chỉ dữ liệu AIS",
    "C": "Hợp nhất, nội suy tuyến tính",
    "D": "Hệ thống đầy đủ",
}


@dataclass
class AblationRow:
    """Một dòng kết quả của bảng phân tích đóng góp."""

    config: str
    label: str
    vessel_recall: float
    dark_precision: float
    dark_recall: float
    dark_f1: float
    state_accuracy: float
    state_macro_f1: float
    mean_match_error_m: float

    def to_dict(self) -> Dict:
        return {
            "Cấu hình": self.config,
            "Nội dung": self.label,
            "Độ nhạy phát hiện": round(self.vessel_recall, 4),
            "Chính xác lớp DARK": round(self.dark_precision, 4),
            "Độ nhạy lớp DARK": round(self.dark_recall, 4),
            "F1 lớp DARK": round(self.dark_f1, 4),
            "Chính xác 3 trạng thái": round(self.state_accuracy, 4),
            "F1 vĩ mô 3 trạng thái": round(self.state_macro_f1, 4),
            "Sai số ghép cặp (m)": (
                round(self.mean_match_error_m, 1)
                if np.isfinite(self.mean_match_error_m) else None
            ),
        }


def _vessel_recall(records: Sequence[Dict]) -> float:
    """Tỉ lệ phương tiện đối chứng được hệ thống nhìn thấy."""
    if not records:
        return 0.0
    seen = sum(1 for r in records if r.get("detected", False))
    return seen / len(records)


def run_ablation(
    fusion_runner,
    cfg,
    scenes_meta: Sequence[Dict],
    ais_by_scene: Dict[str, List[Dict]],
    detections_by_scene: Dict[str, Tuple[np.ndarray, np.ndarray]],
) -> Tuple[List[AblationRow], Dict[str, FusionMetrics]]:
    """Chạy bốn cấu hình và tổng hợp kết quả.

    ``fusion_runner`` là hàm nhận ``(cfg, scenes_meta, ais, detections, options)``
    và trả về bản ghi chi tiết theo từng phát hiện đã ghép với đối chứng.
    """
    rows: List[AblationRow] = []
    metrics_map: Dict[str, FusionMetrics] = {}

    # ---- Cấu hình D: hệ thống đầy đủ -------------------------------------
    recs_d = fusion_runner(
        cfg, scenes_meta, ais_by_scene, detections_by_scene,
        use_kalman=True, use_size_check=True,
    )
    m_d = _metrics_from_records(recs_d)
    metrics_map["D"] = m_d
    rows.append(
        AblationRow(
            "D", CONFIG_LABELS["D"], _vessel_recall(recs_d),
            m_d.dark_precision, m_d.dark_recall, m_d.dark_f1,
            m_d.state_accuracy, m_d.state_macro_f1, m_d.mean_match_error_m,
        )
    )

    # ---- Cấu hình C: nội suy tuyến tính, không kiểm tra kích thước --------
    recs_c = fusion_runner(
        cfg, scenes_meta, ais_by_scene, detections_by_scene,
        use_kalman=False, use_size_check=False,
    )
    m_c = _metrics_from_records(recs_c)
    metrics_map["C"] = m_c
    rows.append(
        AblationRow(
            "C", CONFIG_LABELS["C"], _vessel_recall(recs_c),
            m_c.dark_precision, m_c.dark_recall, m_c.dark_f1,
            m_c.state_accuracy, m_c.state_macro_f1, m_c.mean_match_error_m,
        )
    )

    # ---- Cấu hình A: chỉ ảnh radar ---------------------------------------
    # Không có AIS nên hệ thống không thể xác nhận định danh của bất kỳ
    # phương tiện nào; mọi phát hiện đều phải bị coi là chưa xác định.
    recs_a = [dict(r) for r in recs_d]
    for r in recs_a:
        r["pred_state"] = DARK
        r["pred_mmsi"] = None
        r["match_error_m"] = float("nan")
    m_a = _metrics_from_records(recs_a)
    metrics_map["A"] = m_a
    rows.append(
        AblationRow(
            "A", CONFIG_LABELS["A"], _vessel_recall(recs_a),
            m_a.dark_precision, m_a.dark_recall, m_a.dark_f1,
            m_a.state_accuracy, m_a.state_macro_f1, float("nan"),
        )
    )

    # ---- Cấu hình B: chỉ dữ liệu AIS -------------------------------------
    # Phương tiện không phát tín hiệu hoàn toàn không xuất hiện trong hệ thống.
    recs_b = []
    for r in recs_d:
        rb = dict(r)
        if rb["true_state"] == DARK:
            rb["detected"] = False
            rb["pred_state"] = None      # hệ thống không biết phương tiện này tồn tại
        else:
            rb["detected"] = True
            rb["pred_state"] = rb["true_state"]
            rb["pred_mmsi"] = rb["true_mmsi"]
            rb["match_error_m"] = 0.0
        recs_b.append(rb)
    m_b = _metrics_from_records(recs_b)
    metrics_map["B"] = m_b
    rows.append(
        AblationRow(
            "B", CONFIG_LABELS["B"], _vessel_recall(recs_b),
            m_b.dark_precision, m_b.dark_recall, m_b.dark_f1,
            m_b.state_accuracy, m_b.state_macro_f1, m_b.mean_match_error_m,
        )
    )

    rows.sort(key=lambda r: r.config)
    return rows, metrics_map


def _metrics_from_records(records: Sequence[Dict]) -> FusionMetrics:
    """Quy đổi danh sách bản ghi chi tiết thành tập chỉ tiêu.

    Phương tiện mà hệ thống hoàn toàn không nhìn thấy — do mô hình phát hiện bỏ
    sót, hoặc do cấu hình không có nguồn dữ liệu tương ứng — mang ``pred_state``
    bằng ``None``. Những trường hợp này không tham gia ma trận nhầm lẫn nhưng
    vẫn được tính là bỏ sót đối với lớp thật của chúng, để chỉ tiêu độ nhạy
    phản ánh đúng năng lực thực tế của toàn hệ thống.
    """
    visible = [r for r in records if r.get("pred_state") is not None]
    invisible = [r for r in records if r.get("pred_state") is None]

    true_states = [r["true_state"] for r in visible]
    pred_states = [r["pred_state"] for r in visible]
    true_mmsi = [r.get("true_mmsi") for r in visible]
    pred_mmsi = [r.get("pred_mmsi") for r in visible]
    errs = [r.get("match_error_m", float("nan")) for r in visible]

    # Bổ sung các phương tiện ngắt định danh bị bỏ sót hoàn toàn
    for r in invisible:
        if r["true_state"] != DARK:
            continue
        true_states.append(DARK)
        pred_states.append(AIS_OK)  # nhãn giữ chỗ, chắc chắn khác DARK
        true_mmsi.append(None)
        pred_mmsi.append(None)
        errs.append(float("nan"))

    return evaluate_fusion(true_states, pred_states, true_mmsi, pred_mmsi, errs)


def format_ablation_table(rows: Sequence[AblationRow]) -> str:
    """Kết xuất bảng phân tích đóng góp dưới dạng văn bản căn cột."""
    from ..utils import format_table

    return format_table([r.to_dict() for r in rows])
