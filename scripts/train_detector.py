#!/usr/bin/env python
"""Huấn luyện mô hình phát hiện phương tiện trong một tiến trình độc lập.

Khi chạy trên máy có nhiều GPU, Ultralytics tự khởi tạo cơ chế huấn luyện phân
tán. Việc khởi tạo này ổn định hơn khi được thực hiện trong một tiến trình
Python riêng thay vì trong nhân của notebook, nên bước huấn luyện được tách ra
thành tệp lệnh này.

Ví dụ sử dụng::

    python scripts/train_detector.py \\
        --data /kaggle/working/sonarnet_run/data/yolo/data.yaml \\
        --config /kaggle/working/sonarnet_run/results/config.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Cho phép chạy trực tiếp từ thư mục gốc của kho mã nguồn
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sonarnet.config import CFG, RunConfig  # noqa: E402
from sonarnet.utils import get_logger, probe_devices, set_seed  # noqa: E402

LOG = get_logger("scripts.train")


def load_config(path: Path) -> RunConfig:
    """Khôi phục cấu hình từ tệp JSON đã ghi ở bước chuẩn bị."""
    cfg = RunConfig()
    if not path or not Path(path).exists():
        LOG.warning("Không tìm thấy tệp cấu hình, dùng giá trị mặc định.")
        return cfg

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    cfg.root = Path(data.get("root", cfg.root))
    cfg.seed = int(data.get("seed", cfg.seed))
    cfg.quick_mode = bool(data.get("quick_mode", cfg.quick_mode))
    cfg.multi_gpu = bool(data.get("multi_gpu", cfg.multi_gpu))

    for section in ("data", "detect", "fusion", "behavior", "geo"):
        src = data.get(section, {})
        dst = getattr(cfg, section)
        for key, value in src.items():
            if hasattr(dst, key):
                setattr(dst, key, value)
    return cfg


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Huấn luyện mô hình phát hiện phương tiện trên ảnh radar."
    )
    parser.add_argument("--data", required=True, help="Đường dẫn tới data.yaml")
    parser.add_argument("--config", default="", help="Đường dẫn tới config.json")
    parser.add_argument("--epochs", type=int, default=0, help="Ghi đè số chu kỳ")
    parser.add_argument("--batch", type=int, default=0, help="Ghi đè kích thước lô")
    parser.add_argument(
        "--single-gpu", action="store_true", help="Chỉ dùng một GPU"
    )
    args = parser.parse_args()

    cfg = load_config(Path(args.config)) if args.config else CFG
    if args.epochs > 0:
        cfg.detect.epochs = args.epochs
    if args.batch > 0:
        cfg.detect.batch_size = args.batch
    if args.single_gpu:
        cfg.multi_gpu = False

    cfg.make_dirs()
    set_seed(cfg.seed)

    info = probe_devices()
    LOG.info("Phần cứng:\n%s", info.summary)

    from sonarnet.detect.interface import build_detector

    detector = build_detector(cfg)
    result = detector.train(Path(args.data), cfg)

    out = Path(cfg.dir_results) / "train_info.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    LOG.info("Hoàn tất huấn luyện. Thông tin lưu tại %s", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
