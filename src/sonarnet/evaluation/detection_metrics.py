"""Chỉ tiêu đánh giá tầng phát hiện phương tiện.

Toàn bộ phép tính được cài đặt trực tiếp, không phụ thuộc ``pycocotools``, nhằm
bảo đảm chạy được trong mọi môi trường. Quy ước tính toán tuân theo chuẩn
PASCAL VOC 2010 trở về sau: đường cong chính xác – độ nhạy được nội suy đơn điệu
rồi lấy tích phân toàn phần.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import numpy as np


def box_iou(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Ma trận IoU giữa hai tập khung bao, dạng (Na, Nb)."""
    if a.size == 0 or b.size == 0:
        return np.zeros((len(a), len(b)), dtype=np.float32)

    area_a = np.clip(a[:, 2] - a[:, 0], 0, None) * np.clip(a[:, 3] - a[:, 1], 0, None)
    area_b = np.clip(b[:, 2] - b[:, 0], 0, None) * np.clip(b[:, 3] - b[:, 1], 0, None)

    lt = np.maximum(a[:, None, :2], b[None, :, :2])
    rb = np.minimum(a[:, None, 2:], b[None, :, 2:])
    wh = np.clip(rb - lt, 0, None)
    inter = wh[..., 0] * wh[..., 1]

    union = area_a[:, None] + area_b[None, :] - inter
    return (inter / np.clip(union, 1e-9, None)).astype(np.float32)


@dataclass
class DetectionMetrics:
    """Tập chỉ tiêu của tầng phát hiện."""

    ap50: float
    ap50_95: float
    precision: float
    recall: float
    f1: float
    n_gt: int
    n_pred: int
    n_tp: int
    n_fp: int
    n_fn: int
    pr_curve: Tuple[np.ndarray, np.ndarray]  # (recall, precision)

    def to_dict(self) -> Dict:
        return {
            "mAP@0.5": round(float(self.ap50), 4),
            "mAP@0.5:0.95": round(float(self.ap50_95), 4),
            "precision": round(float(self.precision), 4),
            "recall": round(float(self.recall), 4),
            "f1": round(float(self.f1), 4),
            "n_ground_truth": self.n_gt,
            "n_predictions": self.n_pred,
            "true_positive": self.n_tp,
            "false_positive": self.n_fp,
            "false_negative": self.n_fn,
        }


def _average_precision(recall: np.ndarray, precision: np.ndarray) -> float:
    """Diện tích dưới đường cong chính xác – độ nhạy sau khi nội suy đơn điệu."""
    if recall.size == 0:
        return 0.0
    mrec = np.concatenate(([0.0], recall, [1.0]))
    mpre = np.concatenate(([1.0], precision, [0.0]))
    # Làm cho đường chính xác đơn điệu không tăng
    for i in range(mpre.size - 2, -1, -1):
        mpre[i] = max(mpre[i], mpre[i + 1])
    idx = np.where(mrec[1:] != mrec[:-1])[0]
    return float(np.sum((mrec[idx + 1] - mrec[idx]) * mpre[idx + 1]))


def evaluate_detections(
    predictions: Dict[str, Tuple[np.ndarray, np.ndarray]],
    ground_truth: Dict[str, np.ndarray],
    iou_threshold: float = 0.5,
    score_threshold: float = 0.25,
) -> DetectionMetrics:
    """Đánh giá tầng phát hiện trên toàn bộ tập ảnh.

    ``predictions`` ánh xạ định danh ảnh sang cặp (khung bao, điểm tin cậy).
    ``ground_truth`` ánh xạ định danh ảnh sang khung bao đối chứng.
    """
    records: List[Tuple[float, int]] = []  # (điểm tin cậy, là dương tính thật)
    n_gt_total = 0

    for image_id, gt_boxes in ground_truth.items():
        gt_boxes = np.asarray(gt_boxes, dtype=np.float32).reshape(-1, 4)
        n_gt_total += len(gt_boxes)

        pred_boxes, pred_scores = predictions.get(
            image_id, (np.zeros((0, 4), np.float32), np.zeros((0,), np.float32))
        )
        pred_boxes = np.asarray(pred_boxes, dtype=np.float32).reshape(-1, 4)
        pred_scores = np.asarray(pred_scores, dtype=np.float32).reshape(-1)

        if pred_boxes.size == 0:
            continue

        order = np.argsort(-pred_scores)
        pred_boxes, pred_scores = pred_boxes[order], pred_scores[order]

        ious = box_iou(pred_boxes, gt_boxes)
        taken = np.zeros(len(gt_boxes), dtype=bool)

        for i in range(len(pred_boxes)):
            if gt_boxes.size == 0:
                records.append((float(pred_scores[i]), 0))
                continue
            j = int(np.argmax(np.where(taken, -1.0, ious[i])))
            if ious[i, j] >= iou_threshold and not taken[j]:
                taken[j] = True
                records.append((float(pred_scores[i]), 1))
            else:
                records.append((float(pred_scores[i]), 0))

    if not records or n_gt_total == 0:
        return DetectionMetrics(
            0.0, 0.0, 0.0, 0.0, 0.0, n_gt_total, 0, 0, 0, n_gt_total,
            (np.array([]), np.array([])),
        )

    records.sort(key=lambda r: -r[0])
    tps = np.array([r[1] for r in records], dtype=np.float32)
    scores = np.array([r[0] for r in records], dtype=np.float32)

    cum_tp = np.cumsum(tps)
    cum_fp = np.cumsum(1.0 - tps)
    recall = cum_tp / n_gt_total
    precision = cum_tp / np.clip(cum_tp + cum_fp, 1e-9, None)

    ap50 = _average_precision(recall, precision)

    # Chỉ tiêu tại ngưỡng tin cậy làm việc
    keep = scores >= score_threshold
    n_tp = int(np.sum(tps[keep]))
    n_fp = int(np.sum(1.0 - tps[keep]))
    n_fn = int(n_gt_total - n_tp)
    p = n_tp / max(n_tp + n_fp, 1)
    r = n_tp / max(n_gt_total, 1)
    f1 = 2 * p * r / max(p + r, 1e-9)

    return DetectionMetrics(
        ap50=ap50,
        ap50_95=ap50,  # được ghi đè khi gọi evaluate_multi_iou
        precision=p, recall=r, f1=f1,
        n_gt=n_gt_total, n_pred=int(len(records)),
        n_tp=n_tp, n_fp=n_fp, n_fn=n_fn,
        pr_curve=(recall, precision),
    )


def evaluate_multi_iou(
    predictions: Dict[str, Tuple[np.ndarray, np.ndarray]],
    ground_truth: Dict[str, np.ndarray],
    score_threshold: float = 0.25,
) -> DetectionMetrics:
    """Tính đầy đủ cả mAP@0.5 và mAP trung bình trên dải ngưỡng 0,5 đến 0,95."""
    base = evaluate_detections(
        predictions, ground_truth, iou_threshold=0.5, score_threshold=score_threshold
    )
    aps = []
    for thr in np.arange(0.5, 1.0, 0.05):
        m = evaluate_detections(
            predictions, ground_truth, iou_threshold=float(thr),
            score_threshold=score_threshold,
        )
        aps.append(m.ap50)
    base.ap50_95 = float(np.mean(aps)) if aps else 0.0
    return base


def match_predictions_to_truth(
    pred_boxes: np.ndarray,
    gt_boxes: np.ndarray,
    iou_threshold: float = 0.5,
) -> Dict[int, int]:
    """Ghép từng phát hiện với phương tiện đối chứng tương ứng.

    Trả về ánh xạ chỉ số phát hiện sang chỉ số đối chứng. Kết quả này là cầu nối
    để đánh giá tầng hợp nhất trên chính các phát hiện của mô hình.
    """
    if len(pred_boxes) == 0 or len(gt_boxes) == 0:
        return {}
    ious = box_iou(
        np.asarray(pred_boxes, np.float32), np.asarray(gt_boxes, np.float32)
    )
    mapping: Dict[int, int] = {}
    taken = set()
    # Duyệt theo thứ tự IoU giảm dần để ưu tiên các cặp khớp tốt nhất
    pairs = [
        (float(ious[i, j]), i, j)
        for i in range(ious.shape[0])
        for j in range(ious.shape[1])
        if ious[i, j] >= iou_threshold
    ]
    pairs.sort(reverse=True)
    for _, i, j in pairs:
        if i in mapping or j in taken:
            continue
        mapping[i] = j
        taken.add(j)
    return mapping
