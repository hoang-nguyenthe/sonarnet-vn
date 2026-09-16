"""Bộ phát hiện dự phòng dựa trên Faster R-CNN của Torchvision.

Phương án này tồn tại để bảo đảm pipeline chạy được ngay cả khi notebook bị ngắt
kết nối mạng và không cài đặt được gói bổ sung, vì Torchvision luôn có sẵn trong
ảnh Python của Kaggle. Mô hình được khởi tạo từ đầu, không dùng trọng số huấn
luyện trước, nên hoàn toàn không phụ thuộc vào việc tải tệp từ Internet.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..utils import get_logger
from .interface import BaseDetector, DetectionOutput

LOG = get_logger("detect.torchvision")


class YoloFormatDataset:
    """Đọc bộ dữ liệu bố trí theo quy ước YOLO và trả về định dạng Torchvision."""

    def __init__(self, root: Path, split: str, size: int) -> None:
        import torch  # noqa: F401

        self.img_dir = Path(root) / "images" / split
        self.lbl_dir = Path(root) / "labels" / split
        self.size = size
        self.files = sorted(self.img_dir.glob("*.png"))
        if not self.files:
            raise FileNotFoundError(f"Không tìm thấy ảnh trong {self.img_dir}")

    def __len__(self) -> int:
        return len(self.files)

    def __getitem__(self, idx: int):
        import torch

        from ..data.dataset import load_image

        path = self.files[idx]
        img = load_image(path).astype(np.float32) / 255.0
        # Nhân bản kênh xám thành ba kênh cho tương thích với mạng nền tiêu chuẩn
        tensor = torch.from_numpy(img).unsqueeze(0).repeat(3, 1, 1)

        lbl_path = self.lbl_dir / f"{path.stem}.txt"
        boxes: List[List[float]] = []
        if lbl_path.exists():
            for line in lbl_path.read_text(encoding="utf-8").splitlines():
                parts = line.split()
                if len(parts) != 5:
                    continue
                _, xc, yc, w, h = map(float, parts)
                x1 = (xc - w / 2) * self.size
                y1 = (yc - h / 2) * self.size
                x2 = (xc + w / 2) * self.size
                y2 = (yc + h / 2) * self.size
                if x2 - x1 > 1 and y2 - y1 > 1:
                    boxes.append([x1, y1, x2, y2])

        if boxes:
            boxes_t = torch.tensor(boxes, dtype=torch.float32)
            labels_t = torch.ones((len(boxes),), dtype=torch.int64)
        else:
            boxes_t = torch.zeros((0, 4), dtype=torch.float32)
            labels_t = torch.zeros((0,), dtype=torch.int64)

        target = {"boxes": boxes_t, "labels": labels_t,
                  "image_id": torch.tensor([idx])}
        return tensor, target, path.stem


def _collate(batch):
    imgs, targets, ids = zip(*batch)
    return list(imgs), list(targets), list(ids)


class TorchvisionDetector(BaseDetector):
    name = "torchvision"

    def __init__(self, devices: List[int], cfg) -> None:
        self.devices = list(devices)
        self.cfg = cfg
        self.model = None
        self.weights_path: Optional[Path] = None

    def _device(self):  # dùng probe_devices để hỗ trợ CUDA / MPS / CPU
        from ..utils import torch_device
        return torch_device(self.devices[0] if self.devices else 0)

    def _device_cuda_only(self):
        import torch

        return torch.device(f"cuda:{self.devices[0]}") if self.devices else torch.device("cpu")

    def _build_model(self):
        import torchvision
        from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
        from torchvision.models.detection.rpn import AnchorGenerator

        # Kích thước neo nhỏ vì phương tiện chỉ chiếm vài chục điểm ảnh
        anchor_gen = AnchorGenerator(
            sizes=((8,), (16,), (32,), (64,), (128,)),
            aspect_ratios=((0.5, 1.0, 2.0),) * 5,
        )
        model = torchvision.models.detection.fasterrcnn_resnet50_fpn(
            weights=None,
            weights_backbone=None,
            num_classes=2,            # nền và phương tiện
            rpn_anchor_generator=anchor_gen,
            min_size=self.cfg.detect.imgsz,
            max_size=self.cfg.detect.imgsz,
            box_detections_per_img=64,
        )
        return model

    # -- Huấn luyện --------------------------------------------------------
    def train(self, data_yaml: Path, cfg=None) -> Dict:
        import torch
        from torch.utils.data import DataLoader

        cfg = cfg or self.cfg
        root = Path(data_yaml).parent
        device = self._device()

        train_ds = YoloFormatDataset(root, "train", cfg.data.scene_size)
        val_ds = YoloFormatDataset(root, "val", cfg.data.scene_size)

        # Faster R-CNN tiêu tốn bộ nhớ hơn YOLO nên giảm kích thước lô
        batch = max(2, cfg.detect.batch_size // 8)
        use_amp = device.type == "cuda"
        train_dl = DataLoader(
            train_ds, batch_size=batch, shuffle=True,
            num_workers=2, collate_fn=_collate, pin_memory=(device.type == "cuda"),
        )

        self.model = self._build_model().to(device)
        params = [p for p in self.model.parameters() if p.requires_grad]
        optimizer = torch.optim.SGD(params, lr=0.005, momentum=0.9, weight_decay=5e-4)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            optimizer, T_max=max(1, cfg.detect.epochs)
        )
        scaler = torch.amp.GradScaler("cuda", enabled=use_amp)

        LOG.info(
            "Huấn luyện Faster R-CNN: %d chu kỳ, lô %d, thiết bị %s",
            cfg.detect.epochs, batch, device,
        )

        for epoch in range(cfg.detect.epochs):
            self.model.train()
            running = 0.0
            for imgs, targets, _ in train_dl:
                imgs = [i.to(device, non_blocking=True) for i in imgs]
                targets = [
                    {k: v.to(device) for k, v in t.items()} for t in targets
                ]
                optimizer.zero_grad(set_to_none=True)
                with torch.amp.autocast("cuda", enabled=use_amp):
                    loss_dict = self.model(imgs, targets)
                    loss = sum(loss_dict.values())
                scaler.scale(loss).backward()
                scaler.step(optimizer)
                scaler.update()
                running += float(loss.detach())
            scheduler.step()
            LOG.info(
                "  chu kỳ %2d/%d — hàm mất mát trung bình %.4f",
                epoch + 1, cfg.detect.epochs, running / max(1, len(train_dl)),
            )

        out_dir = Path(cfg.dir_runs) / "frcnn_sar" / "weights"
        out_dir.mkdir(parents=True, exist_ok=True)
        self.weights_path = out_dir / "best.pt"
        torch.save(self.model.state_dict(), self.weights_path)
        LOG.info("Đã lưu trọng số: %s", self.weights_path)

        return {
            "backend": self.name,
            "weights": str(self.weights_path),
            "devices": self.devices,
            "epochs": cfg.detect.epochs,
        }

    # -- Nạp trọng số ------------------------------------------------------
    def load(self, weights: Path) -> "TorchvisionDetector":
        import torch

        self.model = self._build_model()
        state = torch.load(str(weights), map_location="cpu")
        self.model.load_state_dict(state)
        self.model.to(self._device()).eval()
        self.weights_path = Path(weights)
        return self

    # -- Suy luận ----------------------------------------------------------
    def predict(
        self, image_paths: Sequence[Path], conf: float = 0.25
    ) -> List[DetectionOutput]:
        import torch

        from ..data.dataset import load_image

        if self.model is None:
            raise RuntimeError("Chưa nạp mô hình. Gọi train() hoặc load() trước.")

        device = self._device()
        self.model.eval()
        outs: List[DetectionOutput] = []
        paths = [Path(p) for p in image_paths]
        batch = 8

        with torch.no_grad():
            for i in range(0, len(paths), batch):
                chunk = paths[i : i + batch]
                tensors = []
                for p in chunk:
                    arr = load_image(p).astype(np.float32) / 255.0
                    t = torch.from_numpy(arr).unsqueeze(0).repeat(3, 1, 1)
                    tensors.append(t.to(device))
                preds = self.model(tensors)
                for p, pr in zip(chunk, preds):
                    boxes = pr["boxes"].cpu().numpy().astype(np.float32)
                    scores = pr["scores"].cpu().numpy().astype(np.float32)
                    keep = scores >= conf
                    outs.append(DetectionOutput(p.stem, boxes[keep], scores[keep]))
        return outs

    def predict_sharded(
        self, image_paths: Sequence[Path], conf: float = 0.25
    ) -> List[DetectionOutput]:
        return self.predict(image_paths, conf)
