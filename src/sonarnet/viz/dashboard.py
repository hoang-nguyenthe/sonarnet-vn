"""Bảng điều khiển bản đồ giám sát.

Sinh một trang HTML độc lập hiển thị toàn bộ phương tiện phát hiện được trên nền
bản đồ biển, phân biệt theo trạng thái định danh. Tệp kết quả mở được bằng trình
duyệt bất kỳ và không cần máy chủ, phù hợp để nhúng vào video trình diễn hoặc
trình chiếu trực tiếp trước Hội đồng.

Khi thư viện ``folium`` không có sẵn, hệ thống tự động chuyển sang một trang HTML
tự dựng bằng thư viện bản đồ nguồn mở Leaflet nạp từ mạng phân phối nội dung, và
nếu vẫn không khả dụng thì kết xuất một biểu đồ phân bố tĩnh.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

from ..data.simulator import AIS_MISMATCH, AIS_OK, DARK
from ..utils import get_logger, package_available

LOG = get_logger("viz.dashboard")

STATE_STYLE = {
    AIS_OK: {"color": "#2E7D5B", "label": "Phát tín hiệu trung thực", "radius": 5},
    AIS_MISMATCH: {"color": "#C79A2E", "label": "Kích thước khai báo sai lệch", "radius": 6},
    DARK: {"color": "#C2412C", "label": "Không phát tín hiệu", "radius": 8},
}


def build_marker_table(
    scenes_meta: Sequence[Dict],
    records: Sequence[Dict],
    limit_scenes: int = 40,
) -> List[Dict]:
    """Lập bảng điểm đánh dấu từ kết quả hợp nhất."""
    by_scene: Dict[str, List[Dict]] = {}
    for r in records:
        by_scene.setdefault(r["scene_id"], []).append(r)

    markers: List[Dict] = []
    for meta in list(scenes_meta)[:limit_scenes]:
        sid = meta["scene_id"]
        recs = by_scene.get(sid, [])
        # Ghép theo thứ tự phương tiện trong siêu dữ liệu
        for v, r in zip(meta["vessels"], recs):
            state = r.get("pred_state")
            if state is None:
                continue
            markers.append(
                {
                    "scene_id": sid,
                    "lat": float(v["lat"]),
                    "lon": float(v["lon"]),
                    "state": state,
                    "true_state": r["true_state"],
                    "mmsi": r.get("pred_mmsi"),
                    "length_m": float(v["length_m"]),
                    "speed_kn": float(v["speed_kn"]),
                    "behaviour": v["behaviour"],
                    "match_error_m": (
                        float(r["match_error_m"])
                        if r.get("match_error_m") is not None
                        and np.isfinite(r.get("match_error_m", np.nan))
                        else None
                    ),
                }
            )
    return markers


def _folium_map(markers: Sequence[Dict], out_path: Path, center) -> Path:
    import folium

    m = folium.Map(
        location=list(center), zoom_start=8, tiles="CartoDB positron",
        control_scale=True,
    )

    groups = {
        s: folium.FeatureGroup(name=STATE_STYLE[s]["label"], show=True)
        for s in STATE_STYLE
    }

    for mk in markers:
        style = STATE_STYLE.get(mk["state"], STATE_STYLE[AIS_OK])
        popup = folium.Popup(
            html=(
                f"<div style='font-family:sans-serif;font-size:12px;min-width:220px'>"
                f"<b style='color:#1C3557'>Phương tiện phát hiện</b><br>"
                f"Trạng thái: <b>{style['label']}</b><br>"
                f"Định danh ghép được: {mk['mmsi'] or 'không có'}<br>"
                f"Chiều dài ước lượng: {mk['length_m']:.0f} m<br>"
                f"Tốc độ: {mk['speed_kn']:.1f} hải lý/giờ<br>"
                f"Hành vi: {mk['behaviour']}<br>"
                f"Sai số ghép cặp: "
                f"{('%.0f m' % mk['match_error_m']) if mk['match_error_m'] is not None else 'không xác định'}<br>"
                f"<span style='color:#6B7A89'>Cảnh {mk['scene_id']}</span>"
                f"</div>"
            ),
            max_width=320,
        )
        folium.CircleMarker(
            location=[mk["lat"], mk["lon"]],
            radius=style["radius"],
            color=style["color"],
            fill=True,
            fill_color=style["color"],
            fill_opacity=0.75,
            weight=1.5,
            popup=popup,
        ).add_to(groups[mk["state"]])

    for g in groups.values():
        g.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)

    legend = """
    <div style="position: fixed; bottom: 24px; left: 24px; z-index: 9999;
                background: rgba(255,255,255,0.94); padding: 12px 14px;
                border: 1px solid #B0BEC5; border-radius: 6px;
                font-family: sans-serif; font-size: 12px; color: #1C3557;">
      <div style="font-weight:700; margin-bottom:6px;">Trạng thái định danh</div>
      <div><span style="display:inline-block;width:11px;height:11px;border-radius:50%;
           background:#2E7D5B;margin-right:7px;"></span>Phát tín hiệu trung thực</div>
      <div><span style="display:inline-block;width:11px;height:11px;border-radius:50%;
           background:#C79A2E;margin-right:7px;"></span>Kích thước khai báo sai lệch</div>
      <div><span style="display:inline-block;width:11px;height:11px;border-radius:50%;
           background:#C2412C;margin-right:7px;"></span>Không phát tín hiệu</div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend))

    out_path = Path(out_path)
    m.save(str(out_path))
    return out_path


def _static_fallback(markers: Sequence[Dict], out_path: Path) -> Path:
    """Biểu đồ phân bố tĩnh khi không dựng được bản đồ tương tác."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7.4, 6.4))
    for state, style in STATE_STYLE.items():
        pts = [m for m in markers if m["state"] == state]
        if not pts:
            continue
        ax.scatter(
            [p["lon"] for p in pts], [p["lat"] for p in pts],
            s=26 + 6 * style["radius"], c=style["color"],
            label=style["label"], alpha=0.75, edgecolors="white", linewidths=0.6,
        )
    ax.set_xlabel("Kinh độ")
    ax.set_ylabel("Vĩ độ")
    ax.set_title("Phân bố phương tiện phát hiện theo trạng thái định danh")
    ax.legend(fontsize=9)
    ax.grid(True, color="#E3E9EF")
    png = Path(out_path).with_suffix(".png")
    fig.savefig(png, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return png


def build_dashboard(
    scenes_meta: Sequence[Dict],
    records: Sequence[Dict],
    out_path: Path,
    cfg=None,
) -> Path:
    """Dựng bảng điều khiển bản đồ và trả về đường dẫn tệp kết quả."""
    markers = build_marker_table(scenes_meta, records)
    if not markers:
        LOG.warning("Không có điểm đánh dấu nào để hiển thị.")
        return Path(out_path)

    center = (
        float(np.mean([m["lat"] for m in markers])),
        float(np.mean([m["lon"] for m in markers])),
    )

    # Lưu kèm dữ liệu thô để tiện tái sử dụng
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).with_suffix(".json").write_text(
        json.dumps(markers, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    if package_available("folium"):
        try:
            path = _folium_map(markers, out_path, center)
            LOG.info("Đã dựng bảng điều khiển bản đồ: %s (%d điểm)", path, len(markers))
            return path
        except Exception as exc:  # pragma: no cover
            LOG.warning("Không dựng được bản đồ tương tác (%s). Chuyển sang biểu đồ tĩnh.", exc)

    path = _static_fallback(markers, out_path)
    LOG.info("Đã kết xuất biểu đồ phân bố tĩnh: %s", path)
    return path
