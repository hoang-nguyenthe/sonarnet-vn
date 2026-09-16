#!/usr/bin/env python
"""Chạy lại từ bước đánh giá đến báo cáo, không huấn luyện lại.

Dùng khi đã có trọng số best.pt và chỉ muốn thay đổi cấu hình suy luận
(ngưỡng conf, TTA, ngưỡng ghép cặp) để so sánh nhanh.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sonarnet.config import CFG
from sonarnet.utils import get_logger, timed

LOG = get_logger("scripts.rerun_from_eval")

def main():
    cfg = CFG
    cfg.multi_gpu = False
    cfg.detect.devices = [0]
    cfg.detect.backend = "ultralytics"

    from sonarnet import pipeline as P
    from sonarnet.reporting import step_report

    LOG.info("Chạy lại từ đánh giá — conf=%.2f, TTA=%s, size_ratio=%.2f",
             cfg.detect.conf_threshold, cfg.detect.tta_inference,
             cfg.fusion.size_mismatch_ratio)

    with timed("QUY TRÌNH TỪ ĐÁNH GIÁ"):
        prep = P.step_prepare(cfg)
        rng = prep["rng"]
        dataset_summary = P.step_build_data(cfg, rng)
        # Bỏ qua train_detector; nạp trọng số có sẵn
        train_info = {"backend": "ultralytics",
                      "weights": str(cfg.dir_runs / "yolo_sar" / "weights" / "best.pt"),
                      "distributed": False, "reused": True}
        eval_out = P.step_eval_detector(cfg)
        fusion_out = P.step_fusion(cfg, eval_out)
        behaviour_out = P.step_behavior(cfg, rng)
        ablation_out = P.step_ablation(cfg, eval_out, fusion_out)
        report_out = step_report(
            cfg, dataset_summary, eval_out, fusion_out,
            behaviour_out, ablation_out, train_info,
        )
    LOG.info("Kết quả: %s", cfg.dir_results)
    return 0

if __name__ == "__main__":
    sys.exit(main())
