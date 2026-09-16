"""Bộ phát hiện dựa trên Ultralytics YOLO, khai thác đồng thời hai GPU T4.

Huấn luyện phân tán được kích hoạt bằng cách truyền danh sách nhiều thiết bị cho
tham số ``device``. Ultralytics tự khởi tạo tiến trình phân tán ở phía sau; để
quá trình này ổn định trên Kaggle, việc huấn luyện nên được gọi từ một tiến trình
con độc lập thay vì gọi trực tiếp trong nhân của notebook. Tệp
``scripts/train_detector.py`` đảm nhiệm vai trò đó.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

from ..utils import get_logger
from .interface import BaseDetector, DetectionOutput

LOG = get_logger("detect.yolo")


def resolve_model_spec(preferred: str = "yolo11n.pt") -> str:
    """Chọn điểm khởi tạo mô hình phù hợp với điều kiện kết nối mạng.

    Trọng số đã huấn luyện trước cần tải về từ máy chủ của Ultralytics. Khi
    notebook chạy ở chế độ ngắt mạng, hệ thống chuyển sang khởi tạo mô hình từ
    tệp mô tả kiến trúc — quá trình huấn luyện vẫn diễn ra bình thường, chỉ cần
    thêm một số chu kỳ để hội tụ.
    """
    local = Path(preferred)
    if local.exists():
        return str(local)

    try:
        import urllib.request

        urllib.request.urlopen("https://github.com", timeout=6)
        return preferred
    except Exception:
        fallback = preferred.replace(".pt", ".yaml")
        LOG.warning(
            "Không có kết nối mạng: khởi tạo mô hình từ kiến trúc %s thay vì "
            "trọng số huấn luyện trước.", fallback,
        )
        return fallback


class YOLODetector(BaseDetector):
    name = "ultralytics"

    def __init__(self, devices: List[int], cfg) -> None:
        self.devices = list(devices)
        self.cfg = cfg
        self.model = None
        self.weights_path: Optional[Path] = None

    # -- Huấn luyện --------------------------------------------------------
    def train(self, data_yaml: Path, cfg=None) -> Dict:
        """Huấn luyện trực tiếp trong tiến trình hiện tại."""
        from ultralytics import YOLO

        cfg = cfg or self.cfg
        spec = resolve_model_spec(cfg.detect.yolo_model)
        self.model = YOLO(spec)

        # Ưu tiên: CUDA (T4×2 trên Kaggle) → MPS (Apple Silicon) → CPU
        from ..utils import probe_devices
        info = probe_devices()
        if info.kind == "cuda":
            device_arg = self.devices if len(self.devices) > 1 else (
                self.devices[0] if self.devices else "cpu"
            )
        elif info.kind == "mps":
            device_arg = "mps"
        else:
            device_arg = "cpu"
        LOG.info("Bắt đầu huấn luyện YOLO trên thiết bị: %s (%s)", device_arg, info.kind)

        results = self.model.train(
            data=str(data_yaml),
            epochs=cfg.detect.epochs,
            imgsz=cfg.detect.imgsz,
            batch=cfg.detect.batch_size,
            workers=cfg.detect.workers,
            lr0=cfg.detect.lr0,
            patience=cfg.detect.patience,
            device=device_arg,
            project=str(cfg.dir_runs),
            name="yolo_sar",
            exist_ok=True,
            seed=cfg.seed,
            pretrained=spec.endswith(".pt"),
            verbose=True,
            plots=True,
            # Ảnh radar là ảnh cường độ đơn kênh: tắt các phép tăng cường màu
            hsv_h=0.0, hsv_s=0.0, hsv_v=0.25,
            degrees=180.0,   # hướng tàu là bất kỳ nên xoay toàn dải là hợp lý
            fliplr=0.5, flipud=0.5,
            mosaic=0.6, mixup=0.0, translate=0.08, scale=0.35,
            # Số epoch cuối tắt mosaic để tinh chỉnh độ khớp hộp bao — nâng mAP@0.5:0.95
            close_mosaic=getattr(cfg.detect, "close_mosaic_epochs", 10),
            cos_lr=True,     # lịch giảm tốc độ học cosine — hội tụ ổn định hơn ở cuối
            # Nhấn vào regression để hộp bao khớp chặt hơn với thân tàu; ước lượng
            # chiều dài phương tiện từ hộp trở nên chính xác hơn — MISMATCH detection
            # dựa trực tiếp trên length_m.
            box=8.5,   # mặc định 7.5
            dfl=1.8,   # mặc định 1.5
            cls=0.5,
        )

        best = Path(cfg.dir_runs) / "yolo_sar" / "weights" / "best.pt"
        self.weights_path = best if best.exists() else None
        return {
            "backend": self.name,
            "weights": str(best),
            "devices": self.devices,
            "epochs": cfg.detect.epochs,
        }

    # -- Nạp trọng số ------------------------------------------------------
    def load(self, weights: Path) -> "YOLODetector":
        from ultralytics import YOLO

        self.model = YOLO(str(weights))
        self.weights_path = Path(weights)
        LOG.info("Đã nạp trọng số: %s", weights)
        return self

    # -- Suy luận ----------------------------------------------------------
    def predict(
        self, image_paths: Sequence[Path], conf: float = 0.25
    ) -> List[DetectionOutput]:
        if self.model is None:
            raise RuntimeError("Chưa nạp mô hình. Gọi train() hoặc load() trước.")

        from ..utils import probe_devices
        info = probe_devices()
        if info.kind == "cuda":
            device = self.devices[0] if self.devices else "cpu"
        elif info.kind == "mps":
            device = "mps"
        else:
            device = "cpu"
        outs: List[DetectionOutput] = []
        batch = 32
        paths = [Path(p) for p in image_paths]

        for i in range(0, len(paths), batch):
            chunk = paths[i : i + batch]
            results = self.model.predict(
                [str(p) for p in chunk],
                conf=conf,
                imgsz=self.cfg.detect.imgsz,
                device=device,
                verbose=False,
                # Bật tăng cường suy luận nếu cấu hình yêu cầu — chậm hơn nhưng bù
                # bằng tăng trung bình 1-2% mAP nhờ tổng hợp nhiều biến thể ảnh.
                augment=bool(getattr(self.cfg.detect, "tta_inference", False)),
            )
            for p, r in zip(chunk, results):
                if r.boxes is None or len(r.boxes) == 0:
                    outs.append(
                        DetectionOutput(p.stem, np.zeros((0, 4), np.float32), np.zeros((0,), np.float32))
                    )
                else:
                    outs.append(
                        DetectionOutput(
                            p.stem,
                            r.boxes.xyxy.cpu().numpy().astype(np.float32),
                            r.boxes.conf.cpu().numpy().astype(np.float32),
                        )
                    )
        return outs

    # -- Suy luận phân tán trên hai GPU ------------------------------------
    def predict_sharded(
        self, image_paths: Sequence[Path], conf: float = 0.25
    ) -> List[DetectionOutput]:
        """Chia đôi khối lượng suy luận cho hai GPU nhằm rút ngắn thời gian.

        Khi chỉ có một GPU, hàm này tương đương với ``predict``.
        """
        if len(self.devices) < 2:
            return self.predict(image_paths, conf)

        import threading

        paths = [Path(p) for p in image_paths]
        mid = len(paths) // 2
        shards = [paths[:mid], paths[mid:]]
        results: Dict[int, List[DetectionOutput]] = {}

        def worker(idx: int, subset: Sequence[Path], dev: int) -> None:
            from ultralytics import YOLO

            local = YOLO(str(self.weights_path)) if self.weights_path else self.model
            outs: List[DetectionOutput] = []
            for i in range(0, len(subset), 32):
                chunk = subset[i : i + 32]
                rs = local.predict(
                    [str(p) for p in chunk], conf=conf,
                    imgsz=self.cfg.detect.imgsz, device=dev, verbose=False,
                )
                for p, r in zip(chunk, rs):
                    if r.boxes is None or len(r.boxes) == 0:
                        outs.append(DetectionOutput(p.stem, np.zeros((0, 4), np.float32), np.zeros((0,), np.float32)))
                    else:
                        outs.append(
                            DetectionOutput(
                                p.stem,
                                r.boxes.xyxy.cpu().numpy().astype(np.float32),
                                r.boxes.conf.cpu().numpy().astype(np.float32),
                            )
                        )
            results[idx] = outs

        threads = [
            threading.Thread(target=worker, args=(i, shards[i], self.devices[i]))
            for i in range(2)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        return results.get(0, []) + results.get(1, [])
