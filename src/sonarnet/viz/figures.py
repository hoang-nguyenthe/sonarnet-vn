"""Kết xuất hình minh hoạ phục vụ báo cáo kỹ thuật và video trình diễn.

Bảng màu được chọn thống nhất với bộ tài liệu đề xuất: nền trung tính, các mức
nhấn bằng tông pastel, chữ màu mực đậm. Phông chữ mặc định của Matplotlib hỗ trợ
đầy đủ tiếng Việt nên không cần cài đặt thêm.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..utils import get_logger

LOG = get_logger("viz.figures")

# Bảng màu thống nhất toàn dự án
NAVY = "#1C3557"
SLATE = "#3F576F"
BLUE = "#5B8DB8"
BLUE_SOFT = "#D6E5F3"
MINT = "#7FB29A"
MINT_SOFT = "#E4F0EA"
CREAM = "#DFC58A"
BLUSH = "#D98C7A"
GREY = "#8A97A3"

STATE_COLORS = {
    "AIS_OK": MINT,
    "AIS_MISMATCH": CREAM,
    "DARK": BLUSH,
}
STATE_LABELS = {
    "AIS_OK": "Phát tín hiệu trung thực",
    "AIS_MISMATCH": "Kích thước khai báo sai lệch",
    "DARK": "Không phát tín hiệu",
}


def _setup():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "figure.dpi": 130,
            "savefig.dpi": 160,
            "savefig.bbox": "tight",
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.titleweight": "bold",
            "axes.labelcolor": SLATE,
            "axes.edgecolor": GREY,
            "axes.titlecolor": NAVY,
            "xtick.color": SLATE,
            "ytick.color": SLATE,
            "axes.grid": True,
            "grid.color": "#E3E9EF",
            "grid.linewidth": 0.7,
            "axes.axisbelow": True,
        }
    )
    return plt


# ---------------------------------------------------------------------------
def plot_scene_with_boxes(
    image: np.ndarray,
    gt_boxes: np.ndarray,
    gt_states: Sequence[str],
    pred_boxes: Optional[np.ndarray],
    out_path: Path,
    title: str = "Cảnh ảnh radar mô phỏng",
) -> Path:
    """Vẽ một cảnh ảnh kèm khung bao đối chứng và khung bao dự đoán."""
    plt = _setup()
    from matplotlib.patches import Patch, Rectangle

    fig, ax = plt.subplots(figsize=(7.2, 7.2))
    ax.imshow(image, cmap="gray", interpolation="nearest")
    ax.grid(False)

    for box, state in zip(gt_boxes, gt_states):
        x1, y1, x2, y2 = box
        ax.add_patch(
            Rectangle(
                (x1, y1), x2 - x1, y2 - y1,
                fill=False, edgecolor=STATE_COLORS.get(state, MINT),
                linewidth=1.7,
            )
        )

    if pred_boxes is not None and len(pred_boxes):
        for x1, y1, x2, y2 in pred_boxes:
            ax.add_patch(
                Rectangle(
                    (x1, y1), x2 - x1, y2 - y1,
                    fill=False, edgecolor="#FFFFFF",
                    linewidth=0.9, linestyle="--",
                )
            )

    handles = [
        Patch(facecolor="none", edgecolor=STATE_COLORS[s], label=STATE_LABELS[s])
        for s in STATE_COLORS
    ]
    if pred_boxes is not None and len(pred_boxes):
        handles.append(
            Patch(facecolor="none", edgecolor="#FFFFFF", linestyle="--",
                  label="Phát hiện của mô hình")
        )
    ax.legend(handles=handles, loc="upper right", framealpha=0.85, fontsize=8)
    ax.set_title(title)
    ax.set_xlabel("Điểm ảnh theo trục ngang")
    ax.set_ylabel("Điểm ảnh theo trục dọc")

    out_path = Path(out_path)
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


# ---------------------------------------------------------------------------
def plot_pr_curve(recall: np.ndarray, precision: np.ndarray, ap: float, out_path: Path) -> Path:
    """Đường cong chính xác – độ nhạy của tầng phát hiện."""
    plt = _setup()
    fig, ax = plt.subplots(figsize=(5.6, 4.4))
    ax.plot(recall, precision, color=NAVY, linewidth=2.0)
    ax.fill_between(recall, precision, color=BLUE_SOFT, alpha=0.75)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.02)
    ax.set_xlabel("Độ nhạy (Recall)")
    ax.set_ylabel("Độ chính xác (Precision)")
    ax.set_title(f"Đường cong chính xác – độ nhạy   (mAP@0.5 = {ap:.3f})")
    fig.savefig(out_path)
    plt.close(fig)
    return Path(out_path)


# ---------------------------------------------------------------------------
def plot_confusion(
    cm: np.ndarray,
    labels: Sequence[str],
    out_path: Path,
    title: str = "Ma trận nhầm lẫn",
    display_labels: Optional[Sequence[str]] = None,
) -> Path:
    """Ma trận nhầm lẫn dạng bản đồ nhiệt, có ghi số tuyệt đối và tỉ lệ."""
    plt = _setup()
    from matplotlib.colors import LinearSegmentedColormap

    cmap = LinearSegmentedColormap.from_list("pastel_blue", ["#FFFFFF", BLUE_SOFT, BLUE])
    disp = list(display_labels or labels)

    cm = np.asarray(cm, dtype=float)
    row_sum = cm.sum(axis=1, keepdims=True)
    norm = np.divide(cm, np.clip(row_sum, 1e-9, None))

    n = len(disp)
    fig, ax = plt.subplots(figsize=(1.55 * n + 2.4, 1.3 * n + 2.0))
    im = ax.imshow(norm, cmap=cmap, vmin=0, vmax=1)
    ax.grid(False)

    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(disp, rotation=22, ha="right")
    ax.set_yticklabels(disp)
    ax.set_xlabel("Dự đoán")
    ax.set_ylabel("Thực tế")
    ax.set_title(title)

    for i in range(n):
        for j in range(n):
            val = int(cm[i, j])
            pct = norm[i, j]
            ax.text(
                j, i, f"{val}\n{pct:.0%}",
                ha="center", va="center",
                color=NAVY if pct < 0.55 else "#FFFFFF",
                fontsize=9, fontweight="bold" if i == j else "normal",
            )

    fig.colorbar(im, ax=ax, fraction=0.042, pad=0.04, label="Tỉ lệ theo hàng")
    fig.savefig(out_path)
    plt.close(fig)
    return Path(out_path)


# ---------------------------------------------------------------------------
def plot_ablation(rows: Sequence[Dict], out_path: Path) -> Path:
    """Biểu đồ cột so sánh bốn cấu hình của phép phân tích đóng góp."""
    plt = _setup()

    configs = [r["Cấu hình"] for r in rows]
    labels = [f"{r['Cấu hình']}. {r['Nội dung']}" for r in rows]
    metrics = [
        ("Độ nhạy phát hiện", BLUE),
        ("F1 lớp DARK", BLUSH),
        ("F1 vĩ mô 3 trạng thái", MINT),
    ]

    x = np.arange(len(configs))
    width = 0.26
    fig, ax = plt.subplots(figsize=(9.2, 4.8))

    for k, (name, color) in enumerate(metrics):
        vals = [float(r.get(name) or 0.0) for r in rows]
        bars = ax.bar(x + (k - 1) * width, vals, width, label=name, color=color)
        for b, v in zip(bars, vals):
            ax.text(
                b.get_x() + b.get_width() / 2, v + 0.018, f"{v:.2f}",
                ha="center", va="bottom", fontsize=8, color=SLATE,
            )

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylim(0, 1.12)
    ax.set_ylabel("Giá trị chỉ tiêu")
    ax.set_title("Đóng góp của từng thành phần trong hệ thống")
    ax.legend(loc="upper left", fontsize=9, framealpha=0.9)
    fig.savefig(out_path)
    plt.close(fig)
    return Path(out_path)


# ---------------------------------------------------------------------------
def plot_match_errors(records: Sequence[Dict], out_path: Path, threshold_m: float = 500.0) -> Path:
    """Phân bố sai số ghép cặp giữa phát hiện và vị trí AIS nội suy."""
    plt = _setup()

    errs = np.array(
        [
            r["match_error_m"]
            for r in records
            if r.get("match_error_m") is not None and np.isfinite(r.get("match_error_m", np.nan))
        ],
        dtype=float,
    )
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    if errs.size:
        ax.hist(errs, bins=36, color=BLUE_SOFT, edgecolor=BLUE, linewidth=0.9)
        ax.axvline(
            float(np.median(errs)), color=NAVY, linestyle="--", linewidth=1.6,
            label=f"Trung vị {np.median(errs):.0f} m",
        )
        ax.axvline(
            threshold_m, color=BLUSH, linestyle=":", linewidth=1.6,
            label=f"Ngưỡng chấp nhận {threshold_m:.0f} m",
        )
        ax.legend(fontsize=9)
    ax.set_xlabel("Sai số ghép cặp (mét)")
    ax.set_ylabel("Số trường hợp")
    ax.set_title("Phân bố sai số ghép cặp ảnh radar và AIS")
    fig.savefig(out_path)
    plt.close(fig)
    return Path(out_path)


# ---------------------------------------------------------------------------
def plot_interpolation_comparison(interp: Dict[str, Dict[str, float]], out_path: Path) -> Path:
    """So sánh sai số nội suy giữa bộ lọc Kalman và nội suy tuyến tính."""
    plt = _setup()

    names = {"kalman": "Bộ lọc Kalman", "linear": "Nội suy tuyến tính"}
    keys = [k for k in ("kalman", "linear") if k in interp]
    metrics = [
        ("mean_error_m", "Sai số trung bình"),
        ("median_error_m", "Sai số trung vị"),
        ("p90_error_m", "Bách phân vị 90"),
    ]

    x = np.arange(len(metrics))
    width = 0.34
    fig, ax = plt.subplots(figsize=(6.8, 4.3))

    for i, k in enumerate(keys):
        vals = [float(interp[k].get(m[0], np.nan)) for m in metrics]
        color = MINT if k == "kalman" else GREY
        bars = ax.bar(x + (i - 0.5) * width, vals, width, label=names[k], color=color)
        for b, v in zip(bars, vals):
            if np.isfinite(v):
                ax.text(
                    b.get_x() + b.get_width() / 2, v, f"{v:.0f}",
                    ha="center", va="bottom", fontsize=8, color=SLATE,
                )

    ax.set_xticks(x)
    ax.set_xticklabels([m[1] for m in metrics])
    ax.set_ylabel("Sai số vị trí (mét)")
    ax.set_title("Chất lượng nội suy quỹ đạo AIS về thời điểm chụp ảnh")
    ax.legend(fontsize=9)
    fig.savefig(out_path)
    plt.close(fig)
    return Path(out_path)


# ---------------------------------------------------------------------------
def plot_behaviour_tracks(tracks: Sequence, out_path: Path, per_class: int = 2) -> Path:
    """Minh hoạ quỹ đạo tiêu biểu của bốn nhóm hành vi."""
    plt = _setup()

    by_class: Dict[str, List] = {}
    for tr in tracks:
        by_class.setdefault(tr.behaviour, []).append(tr)

    labels = {
        "qua_canh": "Di chuyển quá cảnh",
        "cau": "Câu",
        "keo_luoi": "Kéo lưới",
        "neo_dau": "Neo đậu, tụ tập",
    }
    classes = [c for c in ("qua_canh", "cau", "keo_luoi", "neo_dau") if c in by_class]

    fig, axes = plt.subplots(1, len(classes), figsize=(3.4 * len(classes), 3.6))
    if len(classes) == 1:
        axes = [axes]

    for ax, cls in zip(axes, classes):
        for tr in by_class[cls][:per_class]:
            lon = np.asarray(tr.lons)
            lat = np.asarray(tr.lats)
            ax.plot(lon - lon.mean(), lat - lat.mean(), linewidth=1.3, color=NAVY, alpha=0.8)
            ax.scatter(
                [lon[0] - lon.mean()], [lat[0] - lat.mean()],
                s=22, color=MINT, zorder=3,
            )
        ax.set_title(labels.get(cls, cls), fontsize=10)
        ax.set_xlabel("Δ kinh độ")
        ax.set_ylabel("Δ vĩ độ")
        ax.ticklabel_format(style="sci", scilimits=(-2, 2), axis="both")

    fig.suptitle("Dấu hiệu động học của bốn nhóm hành vi", fontsize=12,
                 color=NAVY, fontweight="bold")
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    return Path(out_path)


# ---------------------------------------------------------------------------
def plot_feature_importance(importance: Optional[Dict[str, float]], out_path: Path) -> Optional[Path]:
    """Xếp hạng mức đóng góp của các đặc trưng động học."""
    if not importance:
        return None
    plt = _setup()

    items = sorted(importance.items(), key=lambda kv: kv[1], reverse=True)[:14]
    names = [k for k, _ in items][::-1]
    vals = [v for _, v in items][::-1]

    fig, ax = plt.subplots(figsize=(7.0, 5.0))
    ax.barh(names, vals, color=BLUE_SOFT, edgecolor=BLUE, linewidth=0.9)
    ax.set_xlabel("Mức đóng góp tương đối")
    ax.set_title("Đặc trưng động học có ảnh hưởng lớn nhất")
    fig.savefig(out_path)
    plt.close(fig)
    return Path(out_path)
