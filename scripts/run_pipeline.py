#!/usr/bin/env python
"""Chạy toàn bộ quy trình SonarNet-VN từ dòng lệnh.

Tệp lệnh này thực hiện đúng chuỗi bước mà notebook trên Kaggle thực hiện, phục
vụ cho việc chạy lại kết quả ngoài môi trường notebook hoặc tích hợp vào quy
trình kiểm thử tự động.

Ví dụ sử dụng::

    # Chạy đầy đủ
    python scripts/run_pipeline.py

    # Chạy rút gọn để kiểm tra toàn tuyến trong vài phút
    python scripts/run_pipeline.py --quick

    # Chỉ dùng một GPU
    python scripts/run_pipeline.py --single-gpu
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sonarnet.config import CFG  # noqa: E402
from sonarnet.utils import get_logger, timed  # noqa: E402

LOG = get_logger("scripts.pipeline")


def main() -> int:
    parser = argparse.ArgumentParser(description="Chạy toàn bộ quy trình SonarNet-VN.")
    parser.add_argument("--quick", action="store_true", help="Chế độ rút gọn")
    parser.add_argument("--single-gpu", action="store_true", help="Chỉ dùng một GPU")
    parser.add_argument("--epochs", type=int, default=0, help="Ghi đè số chu kỳ")
    parser.add_argument("--root", default="", help="Thư mục làm việc")
    parser.add_argument(
        "--backend", default="auto",
        choices=["auto", "ultralytics", "torchvision"],
        help="Phương án phát hiện",
    )
    args = parser.parse_args()

    cfg = CFG
    if args.root:
        cfg.root = Path(args.root)
    if args.quick:
        cfg.apply_quick_mode()
    if args.single_gpu:
        cfg.multi_gpu = False
        cfg.detect.devices = [0]
    if args.epochs > 0:
        cfg.detect.epochs = args.epochs
    cfg.detect.backend = args.backend

    from sonarnet import pipeline as P
    from sonarnet.reporting import step_report

    LOG.info("Cấu hình lần chạy:\n%s", __import__("sonarnet").describe(cfg))

    with timed("TOÀN BỘ QUY TRÌNH"):
        prep = P.step_prepare(cfg)
        rng = prep["rng"]

        dataset_summary = P.step_build_data(cfg, rng)
        train_info = P.step_train_detector(cfg)
        eval_out = P.step_eval_detector(cfg)
        fusion_out = P.step_fusion(cfg, eval_out)
        behaviour_out = P.step_behavior(cfg, rng)
        ablation_out = P.step_ablation(cfg, eval_out, fusion_out)
        report_out = step_report(
            cfg, dataset_summary, eval_out, fusion_out,
            behaviour_out, ablation_out, train_info,
        )

    LOG.info("Báo cáo tổng hợp: %s", report_out["report"])
    LOG.info("Bảng điều khiển : %s", report_out["dashboard"])
    LOG.info("Thư mục kết quả : %s", cfg.dir_results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
