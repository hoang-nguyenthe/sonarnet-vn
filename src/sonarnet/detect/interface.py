"""Giao diện thống nhất cho các bộ phát hiện phương tiện.

Hệ thống hỗ trợ hai phương án thực thi để bảo đảm chạy được trong mọi điều kiện
của môi trường Kaggle:

* **Ultralytics YOLO** — phương án chính, đúng như mô tả trong đề xuất. Khai thác
  được cả hai card T4 thông qua huấn luyện phân tán.
* **Torchvision Faster R-CNN** — phương án dự phòng, dùng khi không cài đặt được
  gói bổ sung. Torchvision luôn có sẵn trong ảnh Python của Kaggle nên phương án
  này không cần kết nối mạng.

Cả hai đều phơi bày cùng một giao diện nên các tầng phía sau không cần biết
phương án nào đang được dùng.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np


@dataclass
class DetectionOutput:
    """Kết quả phát hiện trên một ảnh."""

    image_id: str
    boxes: np.ndarray   # (N, 4) theo thứ tự x1, y1, x2, y2
    scores: np.ndarray  # (N,)

    def filter_by_score(self, threshold: float) -> "DetectionOutput":
        keep = self.scores >= threshold
        return DetectionOutput(self.image_id, self.boxes[keep], self.scores[keep])


class BaseDetector(ABC):
    """Hợp đồng chung cho mọi bộ phát hiện."""

    name: str = "base"
    devices: List[int]

    @abstractmethod
    def train(self, data_yaml: Path, cfg) -> Dict:
        """Huấn luyện mô hình. Trả về từ điển thông tin của lần chạy."""

    @abstractmethod
    def predict(
        self, image_paths: Sequence[Path], conf: float = 0.25
    ) -> List[DetectionOutput]:
        """Suy luận trên danh sách ảnh."""

    @abstractmethod
    def load(self, weights: Path) -> "BaseDetector":
        """Nạp trọng số đã huấn luyện."""


def select_backend(preference: str = "auto") -> str:
    """Chọn phương án thực thi phù hợp với môi trường hiện tại."""
    from ..utils import package_available

    if preference in ("ultralytics", "torchvision"):
        return preference
    if package_available("ultralytics"):
        return "ultralytics"
    return "torchvision"


def build_detector(cfg, backend: Optional[str] = None) -> BaseDetector:
    """Khởi tạo bộ phát hiện theo cấu hình."""
    from ..utils import get_logger, resolve_devices

    log = get_logger("detect")
    chosen = select_backend(backend or cfg.detect.backend)
    devices = resolve_devices(cfg.detect.devices, allow_multi=cfg.multi_gpu)

    if chosen == "ultralytics":
        from .yolo_backend import YOLODetector

        log.info("Phương án phát hiện: Ultralytics YOLO | GPU: %s", devices or "CPU")
        return YOLODetector(devices=devices, cfg=cfg)

    from .torchvision_backend import TorchvisionDetector

    log.info(
        "Phương án phát hiện: Torchvision Faster R-CNN | GPU: %s",
        devices[:1] or "CPU",
    )
    return TorchvisionDetector(devices=devices[:1], cfg=cfg)
