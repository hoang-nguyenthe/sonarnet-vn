#!/usr/bin/env python
"""Khảo sát nhanh một bộ dữ liệu thô chưa biết cấu trúc.

Tệp lệnh này được viết cho tình huống tại Vòng Khu vực, khi Ban Tổ chức cung cấp
một bộ dữ liệu thô và đội thi cần nắm được cấu trúc của nó trong thời gian ngắn
nhất. Chương trình duyệt cây thư mục, thống kê định dạng tệp, đọc thử ảnh và dữ
liệu bảng, rồi đề xuất cách ánh xạ sang cấu trúc mà SonarNet-VN sử dụng.

Ví dụ::

    python scripts/inspect_dataset.py --path /kaggle/input/bo-du-lieu-btc
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
TABLE_EXT = {".csv", ".tsv", ".json", ".jsonl", ".parquet", ".xlsx"}
GEO_EXT = {".geojson", ".shp", ".gpkg", ".kml"}

# Các tên trường thường gặp, dùng để gợi ý ánh xạ
FIELD_HINTS = {
    "mmsi": ["mmsi", "vessel_id", "ship_id", "id_tau", "imo"],
    "timestamp": ["timestamp", "time", "datetime", "date_time", "t", "epoch",
                  "thoi_gian", "acquisition_time"],
    "lat": ["lat", "latitude", "y", "vi_do"],
    "lon": ["lon", "lng", "longitude", "x", "kinh_do"],
    "speed": ["sog", "speed", "speed_kn", "toc_do", "velocity"],
    "course": ["cog", "course", "heading", "huong", "bearing"],
    "length": ["length", "length_m", "chieu_dai", "vessel_length", "loa"],
}


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024.0
    return f"{n:.1f} TB"


def scan_tree(root: Path, max_depth: int = 4) -> Dict:
    """Duyệt cây thư mục và thống kê theo phần mở rộng."""
    ext_count: Counter = Counter()
    ext_bytes: Counter = Counter()
    ext_sample: Dict[str, Path] = {}
    dirs: List[str] = []

    for p in sorted(root.rglob("*")):
        try:
            rel = p.relative_to(root)
        except ValueError:
            continue
        if len(rel.parts) > max_depth:
            continue
        if p.is_dir():
            dirs.append(str(rel))
            continue
        ext = p.suffix.lower()
        ext_count[ext] += 1
        try:
            ext_bytes[ext] += p.stat().st_size
        except OSError:
            pass
        ext_sample.setdefault(ext, p)

    return {
        "dirs": dirs,
        "ext_count": ext_count,
        "ext_bytes": ext_bytes,
        "ext_sample": ext_sample,
    }


def probe_image(path: Path) -> Optional[Dict]:
    """Đọc thử một ảnh và trả về thông tin cơ bản."""
    try:
        import numpy as np
        from PIL import Image

        Image.MAX_IMAGE_PIXELS = None
        with Image.open(path) as im:
            info = {
                "kích thước": f"{im.width} × {im.height}",
                "chế độ màu": im.mode,
                "định dạng": im.format,
            }
            arr = np.asarray(im.convert("L"))
        info["giá trị"] = (
            f"nhỏ nhất {arr.min()}, lớn nhất {arr.max()}, "
            f"trung bình {arr.mean():.1f}, độ lệch chuẩn {arr.std():.1f}"
        )
        return info
    except Exception as exc:
        return {"lỗi": str(exc)}


def probe_table(path: Path, n_rows: int = 3) -> Optional[Dict]:
    """Đọc thử một tệp dữ liệu bảng và trả về danh sách trường."""
    ext = path.suffix.lower()
    try:
        if ext in {".csv", ".tsv"}:
            import csv

            delim = "\t" if ext == ".tsv" else ","
            with path.open("r", encoding="utf-8", errors="replace") as f:
                reader = csv.reader(f, delimiter=delim)
                header = next(reader, [])
                rows = [next(reader, []) for _ in range(n_rows)]
            return {"trường": header, "dòng mẫu": [r for r in rows if r]}

        if ext == ".jsonl":
            lines = []
            with path.open("r", encoding="utf-8", errors="replace") as f:
                for _ in range(n_rows):
                    line = f.readline()
                    if not line:
                        break
                    lines.append(json.loads(line))
            keys = sorted({k for d in lines for k in d}) if lines else []
            return {"trường": keys, "dòng mẫu": lines}

        if ext == ".json":
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            if isinstance(data, list) and data and isinstance(data[0], dict):
                return {"trường": sorted(data[0].keys()),
                        "dòng mẫu": data[:n_rows],
                        "số phần tử": len(data)}
            if isinstance(data, dict):
                return {"trường": sorted(data.keys())[:40], "kiểu": "đối tượng"}
            return {"kiểu": type(data).__name__}

        if ext == ".parquet":
            import pandas as pd

            df = pd.read_parquet(path)
            return {"trường": list(df.columns), "số dòng": len(df),
                    "dòng mẫu": df.head(n_rows).to_dict("records")}

        if ext == ".xlsx":
            import pandas as pd

            df = pd.read_excel(path, nrows=n_rows)
            return {"trường": list(df.columns),
                    "dòng mẫu": df.to_dict("records")}
    except Exception as exc:
        return {"lỗi": str(exc)}
    return None


def suggest_mapping(fields: List[str]) -> Dict[str, List[str]]:
    """Gợi ý ánh xạ tên trường sang cấu trúc của hệ thống."""
    lowered = {f.lower().strip(): f for f in fields}
    out: Dict[str, List[str]] = defaultdict(list)
    for target, hints in FIELD_HINTS.items():
        for h in hints:
            for low, orig in lowered.items():
                if low == h or h in low:
                    if orig not in out[target]:
                        out[target].append(orig)
    return dict(out)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Khảo sát nhanh cấu trúc một bộ dữ liệu thô."
    )
    ap.add_argument("--path", required=True, help="Thư mục chứa dữ liệu")
    ap.add_argument("--max-depth", type=int, default=4)
    args = ap.parse_args()

    root = Path(args.path).expanduser()
    if not root.exists():
        print(f"Không tìm thấy thư mục: {root}")
        return 1

    print("=" * 74)
    print(f"KHẢO SÁT BỘ DỮ LIỆU: {root}")
    print("=" * 74)

    tree = scan_tree(root, args.max_depth)

    # ---- Cây thư mục -----------------------------------------------------
    print("\n1. CÂY THƯ MỤC")
    if tree["dirs"]:
        for d in tree["dirs"][:40]:
            depth = d.count("/")
            print(f"   {'  ' * depth}{Path(d).name}/")
        if len(tree["dirs"]) > 40:
            print(f"   ... và {len(tree['dirs']) - 40} thư mục khác")
    else:
        print("   (không có thư mục con)")

    # ---- Thống kê định dạng ---------------------------------------------
    print("\n2. THỐNG KÊ THEO ĐỊNH DẠNG")
    if not tree["ext_count"]:
        print("   (không tìm thấy tệp nào)")
        return 0
    width = max(len(e or "(không đuôi)") for e in tree["ext_count"])
    for ext, cnt in tree["ext_count"].most_common(20):
        label = ext or "(không đuôi)"
        size = human_size(tree["ext_bytes"][ext])
        print(f"   {label:<{width}}  {cnt:>7} tệp   {size:>12}")

    # ---- Ảnh -------------------------------------------------------------
    img_exts = [e for e in tree["ext_count"] if e in IMAGE_EXT]
    if img_exts:
        print("\n3. ẢNH")
        for ext in img_exts:
            sample = tree["ext_sample"][ext]
            print(f"   Mẫu {ext}: {sample.relative_to(root)}")
            info = probe_image(sample)
            if info:
                for k, v in info.items():
                    print(f"      {k}: {v}")
    else:
        print("\n3. ẢNH\n   (không tìm thấy tệp ảnh)")

    # ---- Dữ liệu bảng ----------------------------------------------------
    tab_exts = [e for e in tree["ext_count"] if e in TABLE_EXT]
    all_fields: List[str] = []
    if tab_exts:
        print("\n4. DỮ LIỆU BẢNG")
        for ext in tab_exts:
            sample = tree["ext_sample"][ext]
            print(f"   Mẫu {ext}: {sample.relative_to(root)}")
            info = probe_table(sample)
            if not info:
                continue
            if "lỗi" in info:
                print(f"      không đọc được: {info['lỗi']}")
                continue
            fields = info.get("trường", [])
            all_fields.extend(str(f) for f in fields)
            print(f"      trường ({len(fields)}): {', '.join(map(str, fields[:18]))}"
                  + (" ..." if len(fields) > 18 else ""))
            for key in ("số dòng", "số phần tử"):
                if key in info:
                    print(f"      {key}: {info[key]}")
            rows = info.get("dòng mẫu") or []
            if rows:
                first = rows[0]
                text = json.dumps(first, ensure_ascii=False, default=str)
                print(f"      dòng đầu: {text[:180]}"
                      + (" ..." if len(text) > 180 else ""))
    else:
        print("\n4. DỮ LIỆU BẢNG\n   (không tìm thấy)")

    # ---- Dữ liệu địa lý --------------------------------------------------
    geo_exts = [e for e in tree["ext_count"] if e in GEO_EXT]
    if geo_exts:
        print("\n5. DỮ LIỆU ĐỊA LÝ")
        for ext in geo_exts:
            print(f"   {ext}: {tree['ext_count'][ext]} tệp — "
                  f"{tree['ext_sample'][ext].relative_to(root)}")

    # ---- Gợi ý ánh xạ ----------------------------------------------------
    print("\n6. GỢI Ý ÁNH XẠ SANG CẤU TRÚC SONARNET-VN")
    if all_fields:
        mapping = suggest_mapping(all_fields)
        if mapping:
            for target, found in mapping.items():
                print(f"   {target:<12} ← {', '.join(found)}")
        else:
            print("   Không nhận ra trường nào quen thuộc.")
        missing = [k for k in ("mmsi", "timestamp", "lat", "lon")
                   if k not in mapping]
        if missing:
            print(f"\n   Thiếu trường bắt buộc: {', '.join(missing)}")
            print("   Cần xác định thủ công trường tương ứng trong dữ liệu.")
    else:
        print("   (chưa đọc được trường nào)")

    print("\n7. BƯỚC TIẾP THEO")
    print("   Viết src/sonarnet/data/loader_btc.py với hàm")
    print("   build_dataset_from_btc(cfg, raw_dir) sinh ra đúng cấu trúc")
    print("   mô tả trong docs/ADAPT_NEW_DATA.md mục 1, sau đó thay lời gọi")
    print("   trong pipeline.step_build_data và chạy:")
    print("       python scripts/run_pipeline.py --quick")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
