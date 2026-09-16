"""Điều phối toàn bộ quy trình SonarNet-VN.

Mỗi hàm ``step_*`` tương ứng với một ô lệnh trong notebook và có thể chạy độc
lập. Trạng thái trung gian được ghi ra đĩa nên có thể chạy lại từng bước mà
không phải thực hiện lại các bước trước đó.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .data.dataset import (
    build_dataset,
    read_ais,
    read_scene_meta,
    georef_from_dict,
)
from .data.simulator import AIS_MISMATCH, AIS_OK, DARK
from .evaluation.ablation import format_ablation_table, run_ablation
from .evaluation.detection_metrics import (
    evaluate_multi_iou,
    match_predictions_to_truth,
)
from .evaluation.fusion_metrics import compare_interpolation_methods, evaluate_fusion
from .fusion.matching import Detection, SARAISFusion
from .utils import (
    format_table,
    get_logger,
    gpu_utilisation,
    probe_devices,
    save_json,
    set_seed,
    timed,
)

LOG = get_logger("pipeline")


# ===========================================================================
# Bước 1 — Chuẩn bị môi trường
# ===========================================================================
def step_prepare(cfg) -> Dict:
    """Tạo thư mục, đặt hạt giống ngẫu nhiên và kiểm tra phần cứng."""
    cfg.make_dirs()
    rng = set_seed(cfg.seed)

    info = probe_devices()
    LOG.info("Môi trường tính toán:\n%s", info.summary)

    util = gpu_utilisation()
    if util:
        LOG.info("Trạng thái GPU hiện tại:\n%s", util)

    cfg.to_json(cfg.dir_results / "config.json")
    return {
        "rng": rng,
        "n_gpu": info.n_gpu,
        "gpu_names": info.names,
        "root": str(cfg.root),
    }


# ===========================================================================
# Bước 2 — Sinh dữ liệu
# ===========================================================================
def step_build_data(cfg, rng: np.random.Generator) -> Dict:
    """Sinh toàn bộ ba tập dữ liệu và ghi ra đĩa."""
    with timed("Sinh bộ dữ liệu ảnh radar và dòng AIS"):
        summary = build_dataset(cfg, rng)
    save_json(summary, cfg.dir_results / "dataset_summary.json")

    LOG.info("Tóm tắt bộ dữ liệu:\n%s", format_table(summary["splits"]))
    return summary


# ===========================================================================
# Bước 3 — Huấn luyện mô hình phát hiện
# ===========================================================================
def step_train_detector(cfg, use_subprocess: bool = True) -> Dict:
    """Huấn luyện mô hình phát hiện phương tiện.

    Khi có từ hai GPU trở lên và phương án Ultralytics khả dụng, việc huấn luyện
    được thực hiện trong một tiến trình con để quá trình khởi tạo phân tán diễn
    ra ổn định. Đây là cách làm được khuyến nghị khi chạy trong nhân notebook.
    """
    from .detect.interface import build_detector, select_backend

    data_yaml = cfg.dir_yolo / "data.yaml"
    if not data_yaml.exists():
        raise FileNotFoundError(
            f"Chưa có mô tả dữ liệu tại {data_yaml}. Hãy chạy bước sinh dữ liệu trước."
        )

    backend = select_backend(cfg.detect.backend)
    n_gpu = probe_devices().n_gpu
    multi = cfg.multi_gpu and n_gpu >= 2 and backend == "ultralytics"

    if multi and use_subprocess:
        script = Path(__file__).resolve().parents[2] / "scripts" / "train_detector.py"
        if script.exists():
            LOG.info(
                "Huấn luyện phân tán trên %d GPU thông qua tiến trình con.", n_gpu
            )
            cmd = [
                sys.executable, str(script),
                "--data", str(data_yaml),
                "--config", str(cfg.dir_results / "config.json"),
            ]
            with timed("Huấn luyện mô hình phát hiện (phân tán)"):
                proc = subprocess.run(cmd, text=True)
            if proc.returncode != 0:
                LOG.warning(
                    "Tiến trình con kết thúc với mã %d. Chuyển sang huấn luyện "
                    "trong tiến trình hiện tại.", proc.returncode
                )
            else:
                best = cfg.dir_runs / "yolo_sar" / "weights" / "best.pt"
                return {"backend": backend, "weights": str(best),
                        "distributed": True, "n_gpu": n_gpu}

    detector = build_detector(cfg)
    with timed("Huấn luyện mô hình phát hiện"):
        info = detector.train(data_yaml, cfg)
    info["distributed"] = False
    save_json(info, cfg.dir_results / "train_info.json")
    return info


# ===========================================================================
# Bước 4 — Đánh giá mô hình phát hiện
# ===========================================================================
def step_eval_detector(cfg, weights: Optional[Path] = None, split: str = "test") -> Dict:
    """Suy luận trên tập kiểm tra và tính các chỉ tiêu phát hiện."""
    from .detect.interface import build_detector

    detector = build_detector(cfg)

    if weights is None:
        candidates = [
            cfg.dir_runs / "yolo_sar" / "weights" / "best.pt",
            cfg.dir_runs / "frcnn_sar" / "weights" / "best.pt",
        ]
        weights = next((c for c in candidates if c.exists()), None)
    if weights is None or not Path(weights).exists():
        raise FileNotFoundError("Không tìm thấy trọng số mô hình đã huấn luyện.")

    detector.load(Path(weights))

    img_dir = cfg.dir_yolo / "images" / split
    paths = sorted(img_dir.glob("*.png"))
    LOG.info("Suy luận trên %d ảnh của tập %s.", len(paths), split)

    with timed(f"Suy luận tập {split}"):
        outs = detector.predict_sharded(paths, conf=cfg.detect.conf_threshold)

    predictions = {o.image_id: (o.boxes, o.scores) for o in outs}

    # Khung bao đối chứng lấy từ siêu dữ liệu cảnh
    meta = read_scene_meta(cfg.dir_yolo, split)
    ground_truth = {
        m["scene_id"]: np.array([v["bbox"] for v in m["vessels"]], dtype=np.float32)
        if m["vessels"] else np.zeros((0, 4), np.float32)
        for m in meta
    }

    metrics = evaluate_multi_iou(
        predictions, ground_truth, score_threshold=cfg.detect.conf_threshold
    )
    LOG.info("Chỉ tiêu phát hiện: %s", json.dumps(metrics.to_dict(), ensure_ascii=False))

    save_json(metrics.to_dict(), cfg.dir_results / f"detection_metrics_{split}.json")

    # Lưu dự đoán để các bước sau dùng lại mà không phải suy luận lại
    np.savez_compressed(
        cfg.dir_results / f"predictions_{split}.npz",
        **{f"{k}__boxes": v[0] for k, v in predictions.items()},
        **{f"{k}__scores": v[1] for k, v in predictions.items()},
    )

    return {
        "metrics": metrics,
        "predictions": predictions,
        "ground_truth": ground_truth,
        "scene_meta": meta,
        "weights": str(weights),
    }


def load_predictions(cfg, split: str = "test") -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
    """Nạp lại dự đoán đã lưu ở bước đánh giá."""
    path = cfg.dir_results / f"predictions_{split}.npz"
    data = np.load(path)
    out: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
    for key in data.files:
        if key.endswith("__boxes"):
            sid = key[: -len("__boxes")]
            out[sid] = (data[key], data[f"{sid}__scores"])
    return out


# ===========================================================================
# Bước 5 — Hợp nhất ảnh radar và AIS
# ===========================================================================
def run_fusion_records(
    cfg,
    scenes_meta: Sequence[Dict],
    ais_by_scene: Dict[str, List[Dict]],
    detections_by_scene: Dict[str, Tuple[np.ndarray, np.ndarray]],
    use_kalman: bool = True,
    use_size_check: bool = True,
) -> List[Dict]:
    """Chạy tầng hợp nhất và trả về bản ghi chi tiết theo từng phương tiện.

    Mỗi bản ghi tương ứng với một phương tiện đối chứng, gồm trạng thái thật,
    trạng thái dự đoán, định danh ghép được và sai số ghép cặp. Phương tiện bị
    mô hình phát hiện bỏ sót mang ``pred_state`` bằng ``None``.
    """
    import copy as _copy

    local_cfg = _copy.deepcopy(cfg)
    if not use_size_check:
        # Đặt ngưỡng vượt quá giá trị tối đa có thể để vô hiệu hoá phép kiểm tra
        local_cfg.fusion.size_mismatch_ratio = 10.0

    fusion = SARAISFusion(local_cfg, use_kalman=use_kalman)
    records: List[Dict] = []

    for meta in scenes_meta:
        sid = meta["scene_id"]
        vessels = meta["vessels"]
        if not vessels:
            continue

        georef = georef_from_dict(meta["georef"])
        gt_boxes = np.array([v["bbox"] for v in vessels], dtype=np.float32)

        pred_boxes, pred_scores = detections_by_scene.get(
            sid, (np.zeros((0, 4), np.float32), np.zeros((0,), np.float32))
        )

        # Ghép phát hiện với phương tiện đối chứng theo IoU
        det_to_gt = match_predictions_to_truth(
            pred_boxes, gt_boxes, iou_threshold=cfg.detect.iou_threshold
        )
        gt_to_det = {g: d for d, g in det_to_gt.items()}

        # Chỉ đưa vào tầng hợp nhất những phát hiện khớp với đối chứng, để chỉ
        # tiêu của tầng này không bị pha trộn với sai số của tầng phát hiện
        det_indices = sorted(det_to_gt.keys())
        dets = []
        for new_i, di in enumerate(det_indices):
            x1, y1, x2, y2 = [float(v) for v in pred_boxes[di]]
            cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
            lon, lat = georef.pixel_to_lonlat(cx, cy)
            w_px, h_px = abs(x2 - x1), abs(y2 - y1)
            spacing = cfg.geo.pixel_spacing_m
            dets.append(
                Detection(
                    det_id=new_i, lat=float(lat), lon=float(lon),
                    length_m=max(w_px, h_px) * spacing,
                    width_m=min(w_px, h_px) * spacing,
                    bbox=(x1, y1, x2, y2), score=float(pred_scores[di]),
                )
            )

        result = fusion.run(
            sid, dets, ais_by_scene.get(sid, []), float(meta["capture_time_s"])
        )

        # Lập bản ghi cho từng phương tiện đối chứng
        for gi, v in enumerate(vessels):
            di = gt_to_det.get(gi)
            if di is None:
                records.append(
                    {
                        "scene_id": sid,
                        "true_state": v["identity_state"],
                        "pred_state": None,
                        "true_mmsi": v["mmsi"],
                        "pred_mmsi": None,
                        "match_error_m": float("nan"),
                        "detected": False,
                    }
                )
                continue
            new_i = det_indices.index(di)
            records.append(
                {
                    "scene_id": sid,
                    "true_state": v["identity_state"],
                    "pred_state": result.states[new_i],
                    "true_mmsi": v["mmsi"],
                    "pred_mmsi": result.matched_mmsi[new_i],
                    "match_error_m": result.match_distance_m[new_i],
                    "detected": True,
                }
            )

    return records


def step_fusion(cfg, eval_out: Dict, split: str = "test") -> Dict:
    """Chạy tầng hợp nhất trên tập kiểm tra và tính các chỉ tiêu."""
    scenes_meta = eval_out["scene_meta"]
    ais_by_scene = read_ais(cfg.dir_yolo, split)
    detections = eval_out["predictions"]

    with timed("Hợp nhất ảnh radar và tín hiệu AIS"):
        records = run_fusion_records(
            cfg, scenes_meta, ais_by_scene, detections,
            use_kalman=True, use_size_check=True,
        )

    visible = [r for r in records if r["pred_state"] is not None]
    missed_dark = [
        r for r in records if r["pred_state"] is None and r["true_state"] == DARK
    ]

    true_states = [r["true_state"] for r in visible] + [DARK] * len(missed_dark)
    pred_states = [r["pred_state"] for r in visible] + [AIS_OK] * len(missed_dark)
    true_mmsi = [r["true_mmsi"] for r in visible] + [None] * len(missed_dark)
    pred_mmsi = [r["pred_mmsi"] for r in visible] + [None] * len(missed_dark)
    errs = [r["match_error_m"] for r in visible] + [float("nan")] * len(missed_dark)

    metrics = evaluate_fusion(true_states, pred_states, true_mmsi, pred_mmsi, errs)
    LOG.info(
        "Chỉ tiêu hợp nhất: %s",
        json.dumps(metrics.to_dict(), ensure_ascii=False),
    )
    save_json(metrics.to_dict(), cfg.dir_results / "fusion_metrics.json")

    # So sánh riêng hai phương pháp nội suy
    with timed("So sánh bộ lọc Kalman với nội suy tuyến tính"):
        interp = compare_interpolation_methods(scenes_meta, ais_by_scene, cfg)
    save_json(interp, cfg.dir_results / "interpolation_comparison.json")
    LOG.info(
        "Sai số nội suy — Kalman %.1f m | Tuyến tính %.1f m (trung vị)",
        interp["kalman"]["median_error_m"], interp["linear"]["median_error_m"],
    )

    return {
        "metrics": metrics,
        "records": records,
        "interpolation": interp,
        "ais_by_scene": ais_by_scene,
    }


# ===========================================================================
# Bước 6 — Phân loại hành vi
# ===========================================================================
def step_behavior(cfg, rng: np.random.Generator) -> Dict:
    """Sinh quỹ đạo, trích đặc trưng và huấn luyện bộ phân loại hành vi."""
    from .behavior.classifier import train_and_evaluate
    from .behavior.features import FEATURE_NAMES, features_matrix
    from .data.tracks import generate_track_dataset

    with timed("Sinh tập quỹ đạo phương tiện"):
        tracks = generate_track_dataset(cfg, rng)
    LOG.info("Đã sinh %d quỹ đạo trên %d nhóm hành vi.",
             len(tracks), len(cfg.behavior.classes))

    with timed("Trích xuất đặc trưng động học"):
        X, y = features_matrix(tracks)
    LOG.info("Ma trận đặc trưng: %s", X.shape)

    with timed("Huấn luyện bộ phân loại hành vi"):
        clf, report = train_and_evaluate(X, y, FEATURE_NAMES, cfg)

    clf.save(cfg.dir_runs / "behavior" / "model.pkl")
    save_json(report.to_dict(), cfg.dir_results / "behavior_metrics.json")
    return {"classifier": clf, "report": report, "X": X, "y": y, "tracks": tracks}


# ===========================================================================
# Bước 7 — Phân tích đóng góp thành phần
# ===========================================================================
def step_ablation(cfg, eval_out: Dict, fusion_out: Dict, split: str = "test") -> Dict:
    """Chạy bốn cấu hình so sánh và kết xuất bảng tổng hợp."""
    with timed("Phân tích đóng góp thành phần"):
        rows, metrics_map = run_ablation(
            run_fusion_records,
            cfg,
            eval_out["scene_meta"],
            fusion_out["ais_by_scene"],
            eval_out["predictions"],
        )

    table = format_ablation_table(rows)
    LOG.info("Bảng phân tích đóng góp thành phần:\n%s", table)

    payload = {
        "rows": [r.to_dict() for r in rows],
        "metrics": {k: v.to_dict() for k, v in metrics_map.items()},
    }
    save_json(payload, cfg.dir_results / "ablation.json")
    (cfg.dir_results / "ablation_table.txt").write_text(table, encoding="utf-8")

    try:
        import pandas as pd

        pd.DataFrame([r.to_dict() for r in rows]).to_csv(
            cfg.dir_results / "ablation.csv", index=False, encoding="utf-8-sig"
        )
    except Exception:
        pass

    return {"rows": rows, "metrics": metrics_map, "table": table}
