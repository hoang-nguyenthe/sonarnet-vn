"""Cấu hình tập trung cho toàn bộ pipeline SonarNet-VN.

Mọi tham số điều khiển hành vi của hệ thống đều nằm ở đây. Notebook trên Kaggle
chỉ cần sửa các trường trong ``CFG`` là thay đổi được toàn bộ quy trình.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional


def _default_root() -> Path:
    """Thư mục làm việc: ưu tiên /kaggle/working khi chạy trên Kaggle."""
    if Path("/kaggle/working").exists():
        return Path("/kaggle/working/sonarnet_run")
    return Path.cwd() / "sonarnet_run"


@dataclass
class GeoConfig:
    """Khung địa lý của vùng biển thí điểm.

    Mặc định là một ô biển ngoài khơi Nam Trung Bộ. Toạ độ chỉ dùng để gắn
    hệ quy chiếu cho ảnh mô phỏng và cho bản đồ trình diễn.
    """

    lat_min: float = 9.20
    lat_max: float = 10.10
    lon_min: float = 108.40
    lon_max: float = 109.40
    # Độ phân giải mặt đất của Sentinel-1 GRD (mét trên mỗi điểm ảnh)
    pixel_spacing_m: float = 10.0


@dataclass
class DataConfig:
    """Tham số sinh và nạp dữ liệu."""

    # Kích thước một cảnh ảnh (điểm ảnh)
    scene_size: int = 640
    # Số cảnh cho từng tập
    n_train_scenes: int = 500
    n_val_scenes: int = 80
    n_test_scenes: int = 80
    # Số tàu trên mỗi cảnh
    ships_per_scene: tuple = (3, 14)
    # Tỉ lệ tàu chủ động ngắt AIS
    dark_vessel_ratio: float = 0.28
    # Tỉ lệ cảnh có vùng đất liền / đảo
    land_probability: float = 0.22
    # Bật bóng ma phương vị (azimuth ambiguity) - một giả tượng đặc trưng của SAR
    azimuth_ambiguity: bool = True
    # Nhiễu vị trí của bản ghi AIS (mét)
    ais_position_noise_m: float = 45.0
    # Khoảng thời gian giữa hai bản ghi AIS liên tiếp (giây)
    ais_interval_s: tuple = (12, 180)
    # Nửa cửa sổ thời gian lấy AIS quanh thời điểm chụp (giây)
    ais_window_s: int = 900
    # Thư mục dữ liệu Kaggle nếu người dùng có gắn bộ dữ liệu thật
    kaggle_input_dir: str = "/kaggle/input"


@dataclass
class DetectConfig:
    """Tham số huấn luyện mô hình phát hiện tàu."""

    # "ultralytics" | "torchvision" | "auto"
    backend: str = "auto"
    # Mô hình YOLO dùng khi backend là ultralytics
    yolo_model: str = "yolo11n.pt"
    imgsz: int = 640
    epochs: int = 80
    batch_size: int = 32
    workers: int = 4
    # Giảm từ 0,01 xuống 0,005 kết hợp với AdamW mặc định của Ultralytics — hội tụ
    # ổn định hơn ở cuối và giảm dao động chỉ tiêu chính xác trên tập kiểm định.
    lr0: float = 0.005
    patience: int = 30
    # Bật tăng cường suy luận (test-time augmentation) — mAP thường cao hơn ~1–2 %
    # TTA thử nghiệm: tăng recall nhưng làm giảm precision đáng kể (0,88 → 0,50),
    # vì tổng hợp nhiều biến thể ảnh dễ tạo dương giả. Tắt mặc định.
    tta_inference: bool = False
    # Số epoch cuối tắt mosaic để tinh chỉnh độ khớp hộp bao (theo khuyến nghị ultralytics)
    close_mosaic_epochs: int = 20
    # Danh sách GPU sử dụng. [0, 1] khai thác đủ hai card T4 trên Kaggle.
    devices: List[int] = field(default_factory=lambda: [0, 1])
    # Ngưỡng độ tin cậy khi suy luận. 0,35 cân bằng precision-recall tốt cho ảnh SAR
    # đơn kênh, tránh dương giả từ vệt sóng và bóng ma phương vị còn lại.
    conf_threshold: float = 0.35
    iou_threshold: float = 0.50


@dataclass
class FusionConfig:
    """Tham số hợp nhất ảnh radar và tín hiệu AIS."""

    # Ngưỡng khoảng cách tối đa để chấp nhận một cặp ghép (mét)
    max_match_distance_m: float = 500.0
    # Độ lệch chuẩn gia tốc nhiễu của mô hình động học, mét trên giây bình phương.
    # Giá trị được chọn theo quán tính thực tế của phương tiện đường thuỷ: trong
    # một khoảng mười lăm phút, tàu biển gần như giữ nguyên hướng và tốc độ, biến
    # động chủ yếu đến từ sóng, dòng chảy và thao tác bánh lái. Đặt tham số này
    # quá lớn sẽ khiến mô hình động học mất tác dụng ràng buộc và bộ làm trơn
    # thoái hoá về mức của phép nội suy hai điểm.
    kalman_process_noise: float = 0.01
    # Độ lệch chuẩn sai số vị trí của bản ghi AIS, mét
    kalman_measurement_noise: float = 45.0
    # Ngưỡng sai lệch kích thước để gán nhãn "AIS không phù hợp" (tỉ lệ).
    # Giảm từ 0,55 xuống 0,42 sau khi phân tích ma trận nhầm: ước lượng độ dài
    # phương tiện từ hộp bao có sai số ~10-15%, cộng với biên độ khai báo sai của
    # MISMATCH (tỉ số 0,22-0,42 hoặc 2,1-3,4) đôi khi vượt ngưỡng 0,55 chỉ khi
    # ước lượng ngả cùng chiều — kéo tụt recall lớp MISMATCH.
    size_mismatch_ratio: float = 0.42


@dataclass
class BehaviorConfig:
    """Tham số phân loại hành vi hoạt động của phương tiện."""

    classes: List[str] = field(
        default_factory=lambda: ["qua_canh", "cau", "keo_luoi", "neo_dau"]
    )
    # Độ dài chuỗi quỹ đạo dùng để trích đặc trưng (giờ)
    track_hours: float = 18.0
    # Bước thời gian lấy mẫu quỹ đạo (phút)
    track_step_min: float = 10.0
    n_tracks_per_class: int = 320
    test_size: float = 0.25
    # "xgboost" | "sklearn" | "auto"
    backend: str = "auto"


@dataclass
class RunConfig:
    """Cấu hình tổng thể của một lần chạy."""

    root: Path = field(default_factory=_default_root)
    seed: int = 20260914
    # Chế độ nhanh: giảm quy mô để chạy thử toàn tuyến trong vài phút
    quick_mode: bool = False
    # Cho phép dùng nhiều GPU
    multi_gpu: bool = True

    geo: GeoConfig = field(default_factory=GeoConfig)
    data: DataConfig = field(default_factory=DataConfig)
    detect: DetectConfig = field(default_factory=DetectConfig)
    fusion: FusionConfig = field(default_factory=FusionConfig)
    behavior: BehaviorConfig = field(default_factory=BehaviorConfig)

    # ---- Đường dẫn dẫn xuất -------------------------------------------------
    @property
    def dir_data(self) -> Path:
        return self.root / "data"

    @property
    def dir_yolo(self) -> Path:
        return self.root / "data" / "yolo"

    @property
    def dir_runs(self) -> Path:
        return self.root / "runs"

    @property
    def dir_results(self) -> Path:
        return self.root / "results"

    @property
    def dir_figures(self) -> Path:
        return self.root / "results" / "figures"

    def make_dirs(self) -> None:
        for d in (
            self.root,
            self.dir_data,
            self.dir_yolo,
            self.dir_runs,
            self.dir_results,
            self.dir_figures,
        ):
            d.mkdir(parents=True, exist_ok=True)

    def apply_quick_mode(self) -> None:
        """Thu nhỏ quy mô để kiểm tra toàn tuyến nhanh."""
        self.quick_mode = True
        self.data.n_train_scenes = 60
        self.data.n_val_scenes = 20
        self.data.n_test_scenes = 20
        self.detect.epochs = 8
        self.detect.batch_size = 16
        self.behavior.n_tracks_per_class = 120

    def to_json(self, path: Optional[Path] = None) -> str:
        payload = asdict(self)
        payload["root"] = str(self.root)
        text = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
        if path is not None:
            Path(path).write_text(text, encoding="utf-8")
        return text


# Đối tượng cấu hình dùng chung cho toàn pipeline
CFG = RunConfig()


def describe(cfg: RunConfig = CFG) -> str:
    """Tóm tắt cấu hình dưới dạng văn bản ngắn để in ra notebook."""
    lines = [
        f"Thư mục làm việc      : {cfg.root}",
        f"Hạt giống ngẫu nhiên  : {cfg.seed}",
        f"Chế độ nhanh          : {'CÓ' if cfg.quick_mode else 'KHÔNG'}",
        f"Số cảnh huấn luyện    : {cfg.data.n_train_scenes}",
        f"Số cảnh kiểm định     : {cfg.data.n_val_scenes}",
        f"Số cảnh kiểm tra      : {cfg.data.n_test_scenes}",
        f"Kích thước cảnh       : {cfg.data.scene_size} x {cfg.data.scene_size} điểm ảnh",
        f"Tỉ lệ tàu ngắt AIS    : {cfg.data.dark_vessel_ratio:.0%}",
        f"Số chu kỳ huấn luyện  : {cfg.detect.epochs}",
        f"GPU sử dụng           : {cfg.detect.devices}",
        f"Ngưỡng ghép cặp       : {cfg.fusion.max_match_distance_m:.0f} m",
    ]
    return "\n".join(lines)
