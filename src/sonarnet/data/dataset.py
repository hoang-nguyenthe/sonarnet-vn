"""Ghi các cảnh mô phỏng ra đĩa theo định dạng chuẩn cho huấn luyện và đánh giá.

Bố cục thư mục tuân theo quy ước của Ultralytics YOLO để có thể huấn luyện trực
tiếp, đồng thời lưu kèm siêu dữ liệu địa lý và dòng AIS phục vụ tầng hợp nhất::

    data/yolo/
      ├── images/{train,val,test}/*.png
      ├── labels/{train,val,test}/*.txt
      ├── scenes/{train,val,test}.jsonl     ← siêu dữ liệu phương tiện
      ├── ais/{train,val,test}.jsonl        ← dòng bản ghi AIS
      └── data.yaml
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import numpy as np

from ..utils import get_logger
from .geo import SceneGeoReference
from .simulator import Scene, Vessel

LOG = get_logger("data.dataset")

# Một lớp đối tượng duy nhất: phương tiện trên biển
CLASS_NAMES = ["phuong_tien"]


def _save_image(img: np.ndarray, path: Path) -> None:
    """Ghi ảnh xám 8 bit, ưu tiên OpenCV rồi tới Pillow."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import cv2

        cv2.imwrite(str(path), img)
        return
    except Exception:
        pass
    from PIL import Image

    Image.fromarray(img).save(path)


def load_image(path: Path) -> np.ndarray:
    try:
        import cv2

        arr = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if arr is not None:
            return arr
    except Exception:
        pass
    from PIL import Image

    return np.array(Image.open(path).convert("L"))


def boxes_to_yolo(boxes: np.ndarray, size: int) -> List[str]:
    """Chuyển khung bao (x1, y1, x2, y2) sang dòng nhãn YOLO đã chuẩn hoá."""
    lines: List[str] = []
    for x1, y1, x2, y2 in boxes:
        x1 = max(0.0, min(float(x1), size - 1.0))
        y1 = max(0.0, min(float(y1), size - 1.0))
        x2 = max(0.0, min(float(x2), size - 1.0))
        y2 = max(0.0, min(float(y2), size - 1.0))
        w, h = x2 - x1, y2 - y1
        if w <= 1.0 or h <= 1.0:
            continue
        xc = (x1 + x2) / 2.0 / size
        yc = (y1 + y2) / 2.0 / size
        lines.append(f"0 {xc:.6f} {yc:.6f} {w / size:.6f} {h / size:.6f}")
    return lines


def _georef_to_dict(g: SceneGeoReference) -> Dict:
    return {
        "lat_top": g.lat_top,
        "lon_left": g.lon_left,
        "width": g.width,
        "height": g.height,
        "pixel_spacing_m": g.pixel_spacing_m,
    }


def georef_from_dict(d: Dict) -> SceneGeoReference:
    return SceneGeoReference(
        lat_top=d["lat_top"], lon_left=d["lon_left"],
        width=d["width"], height=d["height"],
        pixel_spacing_m=d["pixel_spacing_m"],
    )


def write_split(
    scenes: Iterable[Scene], split: str, root: Path, size: int
) -> Dict[str, int]:
    """Ghi một tập cảnh ra đĩa, trả về thống kê tóm tắt."""
    root = Path(root)
    img_dir = root / "images" / split
    lbl_dir = root / "labels" / split
    img_dir.mkdir(parents=True, exist_ok=True)
    lbl_dir.mkdir(parents=True, exist_ok=True)
    (root / "scenes").mkdir(parents=True, exist_ok=True)
    (root / "ais").mkdir(parents=True, exist_ok=True)

    scene_meta_path = root / "scenes" / f"{split}.jsonl"
    ais_path = root / "ais" / f"{split}.jsonl"

    n_scene = n_vessel = n_box = n_ais = 0
    state_counts: Dict[str, int] = {}

    with scene_meta_path.open("w", encoding="utf-8") as f_scene, \
         ais_path.open("w", encoding="utf-8") as f_ais:

        for sc in scenes:
            _save_image(sc.image, img_dir / f"{sc.scene_id}.png")

            lines = boxes_to_yolo(sc.boxes, size)
            (lbl_dir / f"{sc.scene_id}.txt").write_text(
                "\n".join(lines), encoding="utf-8"
            )
            n_box += len(lines)

            f_scene.write(
                json.dumps(
                    {
                        "scene_id": sc.scene_id,
                        "capture_time_s": sc.capture_time_s,
                        "georef": _georef_to_dict(sc.georef),
                        "meta": sc.meta,
                        "vessels": [asdict(v) for v in sc.vessels],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

            for rec in sc.ais_records:
                rec = dict(rec)
                rec["scene_id"] = sc.scene_id
                f_ais.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n_ais += len(sc.ais_records)

            for v in sc.vessels:
                state_counts[v.identity_state] = state_counts.get(v.identity_state, 0) + 1
            n_vessel += len(sc.vessels)
            n_scene += 1

    LOG.info(
        "Tập %-5s: %d cảnh | %d phương tiện | %d khung bao | %d bản ghi AIS",
        split, n_scene, n_vessel, n_box, n_ais,
    )
    return {
        "split": split,
        "n_scenes": n_scene,
        "n_vessels": n_vessel,
        "n_boxes": n_box,
        "n_ais_records": n_ais,
        **{f"n_{k}": v for k, v in state_counts.items()},
    }


def write_data_yaml(root: Path) -> Path:
    """Sinh tệp mô tả dữ liệu cho Ultralytics."""
    root = Path(root).resolve()
    content = (
        f"# Bộ dữ liệu phát hiện phương tiện trên ảnh SAR — SonarNet-VN\n"
        f"path: {root}\n"
        f"train: images/train\n"
        f"val: images/val\n"
        f"test: images/test\n"
        f"nc: {len(CLASS_NAMES)}\n"
        f"names:\n"
        + "".join(f"  {i}: {n}\n" for i, n in enumerate(CLASS_NAMES))
    )
    path = root / "data.yaml"
    path.write_text(content, encoding="utf-8")
    LOG.info("Đã ghi mô tả dữ liệu: %s", path)
    return path


def read_scene_meta(root: Path, split: str) -> List[Dict]:
    """Đọc lại siêu dữ liệu phương tiện của một tập."""
    path = Path(root) / "scenes" / f"{split}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_ais(root: Path, split: str) -> Dict[str, List[Dict]]:
    """Đọc dòng AIS, nhóm theo định danh cảnh."""
    path = Path(root) / "ais" / f"{split}.jsonl"
    out: Dict[str, List[Dict]] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        out.setdefault(rec["scene_id"], []).append(rec)
    return out


def build_dataset(cfg, rng: np.random.Generator) -> Dict:
    """Sinh và ghi toàn bộ ba tập dữ liệu. Trả về bản tóm tắt."""
    from .simulator import SceneSimulator

    sim = SceneSimulator(cfg)
    root = cfg.dir_yolo
    root.mkdir(parents=True, exist_ok=True)

    summary = {"splits": []}
    plan = [
        ("train", cfg.data.n_train_scenes),
        ("val", cfg.data.n_val_scenes),
        ("test", cfg.data.n_test_scenes),
    ]
    for split, n in plan:
        scenes = sim.generate_split(n, split, rng)
        summary["splits"].append(
            write_split(scenes, split, root, cfg.data.scene_size)
        )

    summary["data_yaml"] = str(write_data_yaml(root))
    summary["root"] = str(root)
    return summary
