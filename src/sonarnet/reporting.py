"""Kết xuất hình minh hoạ và báo cáo tổng hợp cho một lần chạy."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

from .data.dataset import load_image
from .data.simulator import AIS_MISMATCH, AIS_OK, DARK, IDENTITY_STATES
from .utils import get_logger, save_json, timed
from .viz import dashboard as dash
from .viz import figures as fig

LOG = get_logger("reporting")

BEHAVIOUR_LABELS = {
    "qua_canh": "Quá cảnh",
    "cau": "Câu",
    "keo_luoi": "Kéo lưới",
    "neo_dau": "Neo đậu",
}
STATE_SHORT = {
    AIS_OK: "Trung thực",
    AIS_MISMATCH: "Sai kích thước",
    DARK: "Không phát AIS",
}


def make_figures(
    cfg,
    eval_out: Dict,
    fusion_out: Dict,
    behaviour_out: Dict,
    ablation_out: Dict,
    split: str = "test",
) -> Dict[str, str]:
    """Sinh toàn bộ hình minh hoạ và trả về đường dẫn từng tệp."""
    out: Dict[str, str] = {}
    figs = cfg.dir_figures
    figs.mkdir(parents=True, exist_ok=True)

    # 1. Một cảnh ảnh tiêu biểu, ưu tiên cảnh có phương tiện ngắt định danh
    meta_list = eval_out["scene_meta"]
    chosen = None
    for m in meta_list:
        if any(v["identity_state"] == DARK for v in m["vessels"]) and len(m["vessels"]) >= 5:
            chosen = m
            break
    chosen = chosen or (meta_list[0] if meta_list else None)

    if chosen is not None:
        img_path = cfg.dir_yolo / "images" / split / f"{chosen['scene_id']}.png"
        if img_path.exists():
            image = load_image(img_path)
            gt_boxes = np.array([v["bbox"] for v in chosen["vessels"]], dtype=np.float32)
            gt_states = [v["identity_state"] for v in chosen["vessels"]]
            pred = eval_out["predictions"].get(chosen["scene_id"])
            out["scene"] = str(
                fig.plot_scene_with_boxes(
                    image, gt_boxes, gt_states,
                    pred[0] if pred is not None else None,
                    figs / "01_canh_anh_radar.png",
                    title=f"Cảnh {chosen['scene_id']} — đối chứng và phát hiện",
                )
            )

    # 2. Đường cong chính xác – độ nhạy
    dm = eval_out["metrics"]
    recall, precision = dm.pr_curve
    if recall.size:
        out["pr_curve"] = str(
            fig.plot_pr_curve(recall, precision, dm.ap50, figs / "02_duong_cong_pr.png")
        )

    # 3. Ma trận nhầm lẫn của tầng hợp nhất
    fm = fusion_out["metrics"]
    out["fusion_confusion"] = str(
        fig.plot_confusion(
            fm.confusion_matrix, list(IDENTITY_STATES),
            figs / "03_ma_tran_hop_nhat.png",
            title="Phân loại ba trạng thái định danh",
            display_labels=[STATE_SHORT[s] for s in IDENTITY_STATES],
        )
    )

    # 4. Phân bố sai số ghép cặp
    out["match_errors"] = str(
        fig.plot_match_errors(
            fusion_out["records"], figs / "04_sai_so_ghep_cap.png",
            threshold_m=cfg.fusion.max_match_distance_m,
        )
    )

    # 5. So sánh hai phương pháp nội suy
    out["interpolation"] = str(
        fig.plot_interpolation_comparison(
            fusion_out["interpolation"], figs / "05_so_sanh_noi_suy.png"
        )
    )

    # 6. Ma trận nhầm lẫn của bộ phân loại hành vi
    br = behaviour_out["report"]
    out["behaviour_confusion"] = str(
        fig.plot_confusion(
            br.confusion_matrix, br.classes,
            figs / "06_ma_tran_hanh_vi.png",
            title="Phân loại bốn nhóm hành vi hoạt động",
            display_labels=[BEHAVIOUR_LABELS.get(c, c) for c in br.classes],
        )
    )

    # 7. Quỹ đạo tiêu biểu
    out["tracks"] = str(
        fig.plot_behaviour_tracks(behaviour_out["tracks"], figs / "07_quy_dao_hanh_vi.png")
    )

    # 8. Độ quan trọng đặc trưng
    p = fig.plot_feature_importance(br.feature_importance, figs / "08_dac_trung_quan_trong.png")
    if p:
        out["feature_importance"] = str(p)

    # 9. Bảng phân tích đóng góp thành phần
    out["ablation"] = str(
        fig.plot_ablation(
            [r.to_dict() for r in ablation_out["rows"]], figs / "09_dong_gop_thanh_phan.png"
        )
    )

    LOG.info("Đã kết xuất %d hình minh hoạ vào %s", len(out), figs)
    return out


def make_dashboard(cfg, eval_out: Dict, fusion_out: Dict) -> str:
    """Dựng bảng điều khiển bản đồ giám sát."""
    path = dash.build_dashboard(
        eval_out["scene_meta"], fusion_out["records"],
        cfg.dir_results / "ban_do_giam_sat.html", cfg,
    )
    return str(path)


def _fmt(v, nd: int = 4) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        if not np.isfinite(v):
            return "—"
        return f"{v:.{nd}f}"
    return str(v)


def write_report(
    cfg,
    dataset_summary: Dict,
    eval_out: Dict,
    fusion_out: Dict,
    behaviour_out: Dict,
    ablation_out: Dict,
    figure_paths: Dict[str, str],
    dashboard_path: str,
    train_info: Optional[Dict] = None,
) -> Path:
    """Ghi báo cáo tổng hợp dạng Markdown."""
    dm = eval_out["metrics"].to_dict()
    fm = fusion_out["metrics"].to_dict()
    br = behaviour_out["report"].to_dict()
    interp = fusion_out["interpolation"]

    lines: List[str] = []
    A = lines.append

    A("# SonarNet-VN — Báo cáo kết quả thực nghiệm")
    A("")
    A(f"*Thời điểm kết xuất: {datetime.now().strftime('%d/%m/%Y %H:%M')}*")
    A("")
    A("Hệ thống giám sát tuân thủ quy định chống khai thác thuỷ sản bất hợp pháp, "
      "không khai báo và không theo quy định, trên cơ sở hợp nhất ảnh vệ tinh radar "
      "khẩu độ tổng hợp với tín hiệu giám sát hành trình tàu cá.")
    A("")

    # ---- Cấu hình --------------------------------------------------------
    A("## 1. Cấu hình lần chạy")
    A("")
    A("| Tham số | Giá trị |")
    A("|---|---|")
    A(f"| Chế độ | {'Rút gọn' if cfg.quick_mode else 'Đầy đủ'} |")
    A(f"| Hạt giống ngẫu nhiên | {cfg.seed} |")
    A(f"| Kích thước cảnh | {cfg.data.scene_size} × {cfg.data.scene_size} điểm ảnh |")
    A(f"| Độ phân giải mặt đất | {cfg.geo.pixel_spacing_m:.0f} m/điểm ảnh |")
    A(f"| Tỉ lệ phương tiện ngắt định danh | {cfg.data.dark_vessel_ratio:.0%} |")
    A(f"| Số chu kỳ huấn luyện | {cfg.detect.epochs} |")
    if train_info:
        A(f"| Phương án phát hiện | {train_info.get('backend', 'không rõ')} |")
        A(f"| Huấn luyện phân tán | {'có' if train_info.get('distributed') else 'không'} |")
    A(f"| Ngưỡng ghép cặp | {cfg.fusion.max_match_distance_m:.0f} m |")
    A("")

    # ---- Dữ liệu ---------------------------------------------------------
    A("## 2. Bộ dữ liệu")
    A("")
    A("| Tập | Số cảnh | Số phương tiện | Số khung bao | Số bản ghi AIS |")
    A("|---|---:|---:|---:|---:|")
    for s in dataset_summary["splits"]:
        A(f"| {s['split']} | {s['n_scenes']} | {s['n_vessels']} | "
          f"{s['n_boxes']} | {s['n_ais_records']} |")
    A("")

    # ---- Phát hiện -------------------------------------------------------
    A("## 3. Tầng phát hiện phương tiện")
    A("")
    A("| Chỉ tiêu | Giá trị | Mục tiêu đề ra |")
    A("|---|---:|---:|")
    A(f"| mAP@0.5 | {dm['mAP@0.5']:.4f} | ≥ 0,70 |")
    A(f"| mAP@0.5:0.95 | {dm['mAP@0.5:0.95']:.4f} | — |")
    A(f"| Độ chính xác | {dm['precision']:.4f} | — |")
    A(f"| Độ nhạy | {dm['recall']:.4f} | ≥ 0,80 |")
    A(f"| F1 | {dm['f1']:.4f} | — |")
    A(f"| Dương tính thật / giả / bỏ sót | {dm['true_positive']} / "
      f"{dm['false_positive']} / {dm['false_negative']} | — |")
    A("")
    if "pr_curve" in figure_paths:
        A(f"![Đường cong chính xác – độ nhạy]({Path(figure_paths['pr_curve']).name})")
        A("")

    # ---- Hợp nhất --------------------------------------------------------
    A("## 4. Tầng hợp nhất ảnh radar và AIS")
    A("")
    A("| Chỉ tiêu | Giá trị | Mục tiêu đề ra |")
    A("|---|---:|---:|")
    A(f"| Tỉ lệ ghép cặp chính xác | {fm['match_accuracy']:.4f} | ≥ 0,85 |")
    A(f"| Sai số ghép cặp trung bình | {_fmt(fm['mean_match_error_m'], 1)} m | ≤ 200 m |")
    A(f"| Sai số ghép cặp trung vị | {_fmt(fm['median_match_error_m'], 1)} m | — |")
    A(f"| Độ chính xác lớp không phát AIS | {fm['dark_precision']:.4f} | ≥ 0,75 |")
    A(f"| Độ nhạy lớp không phát AIS | {fm['dark_recall']:.4f} | ≥ 0,70 |")
    A(f"| F1 lớp không phát AIS | {fm['dark_f1']:.4f} | — |")
    A(f"| Độ chính xác ba trạng thái | {fm['state_accuracy']:.4f} | — |")
    A(f"| F1 vĩ mô ba trạng thái | {fm['state_macro_f1']:.4f} | — |")
    A("")
    A("### So sánh phương pháp nội suy quỹ đạo")
    A("")
    A("| Phương pháp | Sai số trung bình | Sai số trung vị | Bách phân vị 90 |")
    A("|---|---:|---:|---:|")
    for key, name in (("kalman", "Bộ lọc Kalman"), ("linear", "Nội suy tuyến tính")):
        if key in interp:
            d = interp[key]
            A(f"| {name} | {_fmt(d['mean_error_m'], 1)} m | "
              f"{_fmt(d['median_error_m'], 1)} m | {_fmt(d['p90_error_m'], 1)} m |")
    A("")

    # ---- Hành vi ---------------------------------------------------------
    A("## 5. Tầng phân loại hành vi hoạt động")
    A("")
    A(f"Thuật toán sử dụng: **{br['backend']}**. "
      f"Huấn luyện trên {br['n_train']} quỹ đạo, kiểm tra trên {br['n_test']} quỹ đạo.")
    A("")
    A("| Chỉ tiêu | Giá trị | Mục tiêu đề ra |")
    A("|---|---:|---:|")
    A(f"| Độ chính xác | {br['accuracy']:.4f} | — |")
    A(f"| F1 vĩ mô | {br['macro_f1']:.4f} | ≥ 0,70 |")
    A("")
    A("| Nhóm hành vi | F1 |")
    A("|---|---:|")
    for k, v in br["per_class_f1"].items():
        A(f"| {BEHAVIOUR_LABELS.get(k, k)} | {v:.4f} |")
    A("")

    # ---- Ablation --------------------------------------------------------
    A("## 6. Phân tích đóng góp của từng thành phần")
    A("")
    rows = [r.to_dict() for r in ablation_out["rows"]]
    if rows:
        headers = list(rows[0].keys())
        A("| " + " | ".join(headers) + " |")
        A("|" + "|".join(["---"] * len(headers)) + "|")
        for r in rows:
            A("| " + " | ".join(_fmt(r[h]) if isinstance(r[h], float) else str(r[h] if r[h] is not None else "—")
                                for h in headers) + " |")
    A("")
    A("Bảng trên cho thấy giá trị cốt lõi của việc hợp nhất hai nguồn dữ liệu. "
      "Cấu hình chỉ dùng ảnh radar phát hiện được phương tiện nhưng không có căn cứ "
      "để xác định trạng thái định danh. Cấu hình chỉ dùng AIS bỏ sót hoàn toàn các "
      "phương tiện chủ động ngắt tín hiệu — đúng những trường hợp cần phát hiện nhất. "
      "Chỉ khi hợp nhất cả hai nguồn, hệ thống mới đồng thời đạt độ nhạy phát hiện cao "
      "và khả năng nhận diện phương tiện ngắt định danh.")
    A("")

    # ---- Hình và sản phẩm ------------------------------------------------
    A("## 7. Sản phẩm kết xuất")
    A("")
    A("| Tệp | Nội dung |")
    A("|---|---|")
    names = {
        "scene": "Cảnh ảnh radar kèm đối chứng và phát hiện",
        "pr_curve": "Đường cong chính xác – độ nhạy",
        "fusion_confusion": "Ma trận nhầm lẫn ba trạng thái định danh",
        "match_errors": "Phân bố sai số ghép cặp",
        "interpolation": "So sánh hai phương pháp nội suy",
        "behaviour_confusion": "Ma trận nhầm lẫn bốn nhóm hành vi",
        "tracks": "Quỹ đạo tiêu biểu của từng nhóm hành vi",
        "feature_importance": "Đặc trưng động học quan trọng nhất",
        "ablation": "Biểu đồ đóng góp của từng thành phần",
    }
    for key, desc in names.items():
        if key in figure_paths:
            A(f"| `{Path(figure_paths[key]).name}` | {desc} |")
    A(f"| `{Path(dashboard_path).name}` | Bảng điều khiển bản đồ giám sát |")
    A("")

    A("## 8. Ghi chú về dữ liệu")
    A("")
    A("Kết quả trong báo cáo này được tạo trên bộ dữ liệu mô phỏng có nhãn đối chứng "
      "đầy đủ. Bộ mô phỏng tái tạo các đặc trưng vật lý chính của ảnh radar khẩu độ "
      "tổng hợp trên biển: tán xạ nền Rayleigh, nhiễu đốm nhân tính, điều biến do gió, "
      "vệt nước sau tàu và bóng ma phương vị. Mục đích là kiểm chứng tính đúng đắn của "
      "toàn bộ kiến trúc xử lý và thiết lập mức tham chiếu cho từng tầng.")
    A("")
    A("Để chuyển sang dữ liệu thật, thay thế bước sinh dữ liệu bằng ảnh Sentinel-1 tải "
      "từ Copernicus Data Space và dòng AIS từ Global Fishing Watch; toàn bộ các tầng "
      "phía sau giữ nguyên không đổi. Hướng dẫn chi tiết nằm trong tệp `README.md`.")
    A("")

    path = cfg.dir_results / "BAO_CAO_KET_QUA.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    LOG.info("Đã ghi báo cáo tổng hợp: %s", path)

    # Đồng thời lưu bản tổng hợp dạng máy đọc được
    save_json(
        {
            "detection": dm,
            "fusion": fm,
            "behaviour": br,
            "interpolation": interp,
            "ablation": rows,
            "figures": figure_paths,
            "dashboard": dashboard_path,
        },
        cfg.dir_results / "tong_hop_ket_qua.json",
    )
    return path


def step_report(
    cfg,
    dataset_summary: Dict,
    eval_out: Dict,
    fusion_out: Dict,
    behaviour_out: Dict,
    ablation_out: Dict,
    train_info: Optional[Dict] = None,
    split: str = "test",
) -> Dict:
    """Bước cuối: sinh hình, bảng điều khiển và báo cáo."""
    with timed("Kết xuất hình minh hoạ"):
        figure_paths = make_figures(
            cfg, eval_out, fusion_out, behaviour_out, ablation_out, split
        )
    with timed("Dựng bảng điều khiển bản đồ"):
        dashboard_path = make_dashboard(cfg, eval_out, fusion_out)
    with timed("Ghi báo cáo tổng hợp"):
        report_path = write_report(
            cfg, dataset_summary, eval_out, fusion_out, behaviour_out,
            ablation_out, figure_paths, dashboard_path, train_info,
        )
    return {
        "figures": figure_paths,
        "dashboard": dashboard_path,
        "report": str(report_path),
    }
