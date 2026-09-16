"""Tiện ích dùng chung: hạt giống ngẫu nhiên, thiết bị tính toán, ghi nhật ký."""

from __future__ import annotations

import json
import logging
import os
import random
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-22s | %(message)s"
_CONFIGURED = False


def get_logger(name: str = "sonarnet") -> logging.Logger:
    """Trả về logger đã cấu hình sẵn, an toàn khi gọi nhiều lần."""
    global _CONFIGURED
    if not _CONFIGURED:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt="%H:%M:%S"))
        root = logging.getLogger("sonarnet")
        root.setLevel(logging.INFO)
        root.handlers.clear()
        root.addHandler(handler)
        root.propagate = False
        _CONFIGURED = True
    return logging.getLogger(name if name.startswith("sonarnet") else f"sonarnet.{name}")


LOG = get_logger()


# ---------------------------------------------------------------------------
# Tính tái lập
# ---------------------------------------------------------------------------
def set_seed(seed: int) -> np.random.Generator:
    """Đặt hạt giống cho toàn bộ thư viện và trả về bộ sinh số của NumPy."""
    random.seed(seed)
    np.random.seed(seed % (2**32 - 1))
    os.environ["PYTHONHASHSEED"] = str(seed)
    try:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.deterministic = False
        torch.backends.cudnn.benchmark = True
    except Exception:  # pragma: no cover - torch luôn có trên Kaggle
        pass
    return np.random.default_rng(seed)


# ---------------------------------------------------------------------------
# Thiết bị tính toán
# ---------------------------------------------------------------------------
@dataclass
class DeviceInfo:
    n_gpu: int
    names: List[str]
    total_memory_gb: List[float]
    cuda_available: bool
    torch_version: str
    kind: str = "cpu"   # "cuda" | "mps" | "cpu"

    @property
    def summary(self) -> str:
        if self.kind == "cpu" or self.n_gpu == 0:
            return "Không phát hiện GPU. Pipeline sẽ chạy trên CPU (chậm hơn nhiều)."
        rows = [f"PyTorch {self.torch_version} | Loại thiết bị: {self.kind} | Số GPU khả dụng: {self.n_gpu}"]
        for i, (nm, mem) in enumerate(zip(self.names, self.total_memory_gb)):
            rows.append(f"  GPU {i}: {nm} — {mem:.1f} GB" if mem > 0 else f"  GPU {i}: {nm}")
        if self.kind == "cuda" and self.n_gpu >= 2:
            rows.append("  Cấu hình hai GPU hợp lệ: sẽ huấn luyện phân tán trên cả hai card.")
        if self.kind == "mps":
            rows.append("  Apple Metal Performance Shaders — huấn luyện chạy trên GPU tích hợp của máy.")
        return "\n".join(rows)


def probe_devices() -> DeviceInfo:
    """Kiểm tra GPU khả dụng: CUDA, MPS (Apple Metal), rồi mới đến CPU."""
    try:
        import torch
    except Exception:
        return DeviceInfo(0, [], [], False, "không rõ", "cpu")

    if torch.cuda.is_available():
        n = torch.cuda.device_count()
        names, mems = [], []
        for i in range(n):
            props = torch.cuda.get_device_properties(i)
            names.append(props.name)
            mems.append(props.total_memory / (1024**3))
        return DeviceInfo(n, names, mems, True, torch.__version__, "cuda")

    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return DeviceInfo(1, ["Apple Metal (MPS)"], [0.0], False, torch.__version__, "mps")

    return DeviceInfo(0, [], [], False, torch.__version__, "cpu")


def torch_device(index: int = 0):
    """Trả về torch.device dựa trên phần cứng thực có."""
    import torch
    info = probe_devices()
    if info.kind == "cuda":
        return torch.device(f"cuda:{index}")
    if info.kind == "mps":
        return torch.device("mps")
    return torch.device("cpu")


def resolve_devices(requested: List[int], allow_multi: bool = True) -> List[int]:
    """Lọc danh sách GPU yêu cầu theo số card thực có."""
    info = probe_devices()
    if info.n_gpu == 0:
        return []
    usable = [d for d in requested if d < info.n_gpu]
    if not usable:
        usable = [0]
    if not allow_multi:
        usable = usable[:1]
    return usable


def gpu_utilisation() -> Optional[str]:
    """Đọc mức sử dụng GPU qua nvidia-smi, trả về None nếu không có."""
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if out.returncode != 0:
            return None
        rows = []
        for line in out.stdout.strip().splitlines():
            idx, name, util, used, total = [x.strip() for x in line.split(",")]
            rows.append(
                f"  GPU {idx} ({name}): tải {util}% | bộ nhớ {used}/{total} MiB"
            )
        return "\n".join(rows) if rows else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Đo thời gian
# ---------------------------------------------------------------------------
@contextmanager
def timed(label: str, logger: Optional[logging.Logger] = None):
    """Đo thời gian một khối lệnh và ghi nhật ký."""
    log = logger or LOG
    log.info("▶ %s ...", label)
    t0 = time.perf_counter()
    try:
        yield
    finally:
        dt = time.perf_counter() - t0
        if dt < 90:
            log.info("✔ %s — hoàn tất trong %.1f giây", label, dt)
        else:
            log.info("✔ %s — hoàn tất trong %.1f phút", label, dt / 60.0)


# ---------------------------------------------------------------------------
# Vào ra
# ---------------------------------------------------------------------------
def save_json(obj: Any, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    def _default(o):
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, Path):
            return str(o)
        return str(o)

    path.write_text(
        json.dumps(obj, indent=2, ensure_ascii=False, default=_default), encoding="utf-8"
    )
    return path


def load_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def package_available(name: str) -> bool:
    """Kiểm tra một gói Python có nạp được hay không."""
    import importlib.util

    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def format_table(rows: List[Dict[str, Any]], headers: Optional[List[str]] = None) -> str:
    """Định dạng danh sách bản ghi thành bảng văn bản căn cột."""
    if not rows:
        return "(không có dữ liệu)"
    headers = headers or list(rows[0].keys())
    widths = {h: len(str(h)) for h in headers}
    str_rows = []
    for r in rows:
        sr = {}
        for h in headers:
            v = r.get(h, "")
            s = f"{v:.4f}" if isinstance(v, float) else str(v)
            sr[h] = s
            widths[h] = max(widths[h], len(s))
        str_rows.append(sr)

    sep = "-+-".join("-" * widths[h] for h in headers)
    out = [" | ".join(str(h).ljust(widths[h]) for h in headers), sep]
    for sr in str_rows:
        out.append(" | ".join(sr[h].ljust(widths[h]) for h in headers))
    return "\n".join(out)
