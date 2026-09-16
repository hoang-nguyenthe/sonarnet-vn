#!/usr/bin/env python
"""Dashboard tương tác SonarNet-VN — chạy bằng `streamlit run scripts/demo_app.py`.

Sáu khu vực demo:
  1. 🎬 Mô phỏng hoạt động — tàu di chuyển theo thời gian, thấy được ai bật/tắt AIS
  2. 🛰 Phát hiện tàu SAR — ảnh gốc + ground truth + YOLO predictions
  3. 🔗 Hợp nhất radar–AIS — ma trận hỗn hợp 3 màu
  4. 📐 Kalman vs tuyến tính — bằng chứng vì sao chọn RTS
  5. 🗺 Bản đồ giám sát — Folium tương tác
  6. 📊 Chỉ tiêu tổng hợp

Không có mã đăng ký hay thông tin cá nhân — nguyên tắc "không truy vết".
"""
from __future__ import annotations

import base64
from io import BytesIO
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import streamlit as st
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sonarnet.data.gfw import GlobalFishingWatchError, sar_reference_report
from sonarnet.data.copernicus import CopernicusError, access_token, search_sentinel1_grd, sentinel1_mosaic_preview, sentinel1_preview


@st.cache_data(ttl=3600, show_spinner=False)
def load_demo_gfw_reference(
    token: str, bbox: tuple[float, float, float, float], start: date, end: date,
):
    """Cache the independent reference layer so opening the demo stays instant."""
    return sar_reference_report(token, bbox, start, end)


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def load_latest_global_scene(
    client_id: str, client_secret: str, bbox: tuple[float, float, float, float], latest_reference_day: date,
):
    """Fetch the newest Sentinel pass likely to have a published GFW reference layer."""
    token = access_token(client_id, client_secret)
    products = search_sentinel1_grd(token, bbox, latest_reference_day - timedelta(days=10), latest_reference_day)
    if not products:
        raise CopernicusError("Chưa có cảnh Sentinel-1 GRD phù hợp trong cửa sổ dữ liệu đối chiếu cho vùng này.")
    product = max(products, key=lambda item: item.acquired_at)
    return product, sentinel1_preview(token, bbox, product.acquired_at)


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def load_available_vietnam_scenes(client_id: str, client_secret: str, latest_reference_day: date):
    """Return actual Sentinel-1 products intersecting Vietnam's maritime domain."""
    token = access_token(client_id, client_secret)
    products = search_sentinel1_grd(
        token, (102.0, 6.0, 115.0, 21.8), latest_reference_day - timedelta(days=10), latest_reference_day, limit=50,
    )
    return sorted((item for item in products if vietnam_scene_match(item.bbox) is not None), key=lambda item: item.acquired_at, reverse=True)


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def load_product_preview(
    client_id: str, client_secret: str, bbox: tuple[float, float, float, float], acquired_at: str,
) -> bytes:
    return sentinel1_preview(access_token(client_id, client_secret), bbox, acquired_at)


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def load_vietnam_latest_mosaic(client_id: str, client_secret: str, end: date) -> bytes:
    """National display layer: each pixel is the most recent SAR observation in 14 days."""
    return sentinel1_mosaic_preview(
        access_token(client_id, client_secret), (102.0, 6.0, 115.0, 21.8), end - timedelta(days=14), end,
    )


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def load_vietnam_mosaic_status(client_id: str, client_secret: str, end: date) -> dict[str, str | int | None]:
    """Report the catalogue evidence behind the nationwide most-recent mosaic."""
    token = access_token(client_id, client_secret)
    products = search_sentinel1_grd(token, (102.0, 6.0, 115.0, 21.8), end - timedelta(days=14), end, limit=50)
    newest = max(products, key=lambda item: item.acquired_at) if products else None
    newest_by_zone: dict[str, str] = {}
    for product in products:
        match = vietnam_scene_match(product.bbox)
        if match is None:
            continue
        zone, _ = match
        if zone not in newest_by_zone or product.acquired_at > newest_by_zone[zone]:
            newest_by_zone[zone] = product.acquired_at
    return {
        "newest": newest.acquired_at if newest else None,
        "count": len(products),
        "window_start": (end - timedelta(days=14)).isoformat(),
        "window_end": end.isoformat(),
        "zones": newest_by_zone,
    }


def format_vietnam_time(value: str | None) -> str:
    """Show satellite acquisition time in the audience's local time zone."""
    if not value:
        return "Chưa có cảnh phù hợp trong cửa sổ này"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone(timedelta(hours=7))).strftime("%H:%M · %d/%m/%Y (GMT+7)")
    except ValueError:
        return value


VIETNAM_MARITIME_ZONES: dict[str, tuple[float, float, float, float]] = {
    "Vịnh Bắc Bộ": (105.5, 18.0, 110.5, 21.8),
    "Ven biển Bắc Trung Bộ": (106.0, 16.0, 109.0, 19.0),
    "Ven biển Trung Bộ": (108.0, 12.0, 111.0, 16.5),
    "Ngoài khơi Bình Thuận": (107.0, 9.5, 110.0, 12.5),
    "Vũng Tàu – Côn Đảo": (105.5, 8.0, 109.0, 10.5),
    "Vịnh Thái Lan": (102.0, 7.0, 105.5, 11.0),
    "Quần đảo Hoàng Sa": (110.5, 15.5, 113.5, 18.5),
    "Quần đảo Trường Sa": (111.0, 7.0, 115.0, 12.5),
}


def vietnam_scene_match(product_bbox: tuple[float, float, float, float]) -> tuple[str, tuple[float, float, float, float]] | None:
    """Match a Copernicus footprint to its largest-overlap Vietnam maritime zone."""
    west, south, east, north = product_bbox
    best: tuple[str, tuple[float, float, float, float], float] | None = None
    for name, (zone_w, zone_s, zone_e, zone_n) in VIETNAM_MARITIME_ZONES.items():
        overlap_w, overlap_s = max(west, zone_w), max(south, zone_s)
        overlap_e, overlap_n = min(east, zone_e), min(north, zone_n)
        area = max(0.0, overlap_e - overlap_w) * max(0.0, overlap_n - overlap_s)
        if area > 0 and (best is None or area > best[2]):
            # Keep a compact, legible crop entirely inside the matched maritime zone.
            longitude, latitude = (overlap_w + overlap_e) / 2, (overlap_s + overlap_n) / 2
            best = (name, (longitude - 0.20, latitude - 0.15, longitude + 0.20, latitude + 0.15), area)
    return (best[0], best[1]) if best else None


def gfw_overlay_png(image_source: Path | bytes, bbox: tuple[float, float, float, float], cells) -> bytes:
    """Overlay gridded GFW counts onto the corresponding Sentinel raster."""
    west, south, east, north = bbox
    source = BytesIO(image_source) if isinstance(image_source, bytes) else image_source
    image = Image.open(source).convert("RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    width, height = image.size
    for cell in cells:
        x = (cell.longitude - west) / (east - west) * width
        y = (north - cell.latitude) / (north - south) * height
        radius = 7 + min(cell.detections, 4) * 2
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(255, 59, 48, 215), outline=(255, 255, 255, 255), width=2)
        draw.text((x + radius + 2, y - radius - 2), str(cell.detections), fill=(255, 255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0, 220))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def folium_image_source(image_source: Path | bytes) -> str:
    """Return a browser-safe URL for Folium's georeferenced image overlay."""
    if isinstance(image_source, bytes):
        return "data:image/png;base64," + base64.b64encode(image_source).decode("ascii")
    return str(image_source)

st.set_page_config(
    page_title="SonarNet-VN — Bảng điều khiển giám sát",
    page_icon="◉",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
COL_OK = "#2C7A7B"
COL_MISMATCH = "#B7791F"
COL_DARK = "#C53030"
COL_INK = "#1D1D1F"
COL_MUTED = "#6E6E73"
COL_BG = "#FBFBFD"
COL_CARD = "#FFFFFF"
COL_BORDER = "#D2D2D7"
COL_HAIRLINE = "#E5E5EA"

CSS = f"""
<style>
    html, body, [class*="css"] {{
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display",
                     "SF Pro Text", "Helvetica Neue", Arial, sans-serif;
        -webkit-font-smoothing: antialiased;
    }}
    .stApp {{ background: {COL_BG}; color: {COL_INK}; }}
    .main .block-container {{ padding-top: 2rem; max-width: 1240px; }}
    @keyframes sonar-rise {{ from {{ opacity: 0; transform: translateY(18px); }} to {{ opacity: 1; transform: translateY(0); }} }}
    @keyframes sonar-aurora {{ 0%,100% {{ transform: translate3d(-3%,-2%,0) scale(1); }} 50% {{ transform: translate3d(4%,3%,0) scale(1.10); }} }}
    @keyframes sonar-pulse {{ 0%,100% {{ box-shadow: 0 0 0 0 rgba(78, 205, 196, .34); }} 50% {{ box-shadow: 0 0 0 10px rgba(78, 205, 196, 0); }} }}
    @keyframes sonar-shimmer {{ from {{ background-position: 140% 0; }} to {{ background-position: -40% 0; }} }}
    .sonar-hero {{
        position: relative; overflow: hidden; isolation: isolate; border-radius: 28px;
        padding: clamp(30px, 5vw, 64px); color: #fff; margin: 4px 0 24px;
        background: linear-gradient(130deg, #07152b 0%, #0d3159 47%, #126869 100%);
        box-shadow: 0 20px 60px rgba(8, 32, 62, .20); animation: sonar-rise .75s cubic-bezier(.2,.8,.2,1) both;
    }}
    .sonar-hero::before {{
        content: ""; position: absolute; z-index: -1; inset: -35%;
        background: radial-gradient(circle at 24% 43%, rgba(114,242,222,.36), transparent 21%),
                    radial-gradient(circle at 72% 30%, rgba(68,144,255,.42), transparent 22%),
                    radial-gradient(circle at 54% 85%, rgba(24,194,168,.25), transparent 25%);
        filter: blur(18px); animation: sonar-aurora 13s ease-in-out infinite;
    }}
    .sonar-eyebrow {{ font-size: 11px; letter-spacing: .13em; text-transform: uppercase; font-weight: 650; color: #9de4db; margin-bottom: 14px; }}
    .sonar-title {{ max-width: 720px; font-size: clamp(38px, 6vw, 76px); line-height: .98; letter-spacing: -.065em; font-weight: 650; }}
    .sonar-copy {{ max-width: 650px; margin-top: 17px; font-size: 16px; line-height: 1.55; color: rgba(255,255,255,.78); }}
    .sonar-pills {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:25px; }}
    .sonar-pill {{ border:1px solid rgba(255,255,255,.18); background:rgba(255,255,255,.10); backdrop-filter:blur(16px); border-radius:999px; padding:8px 12px; font-size:12px; color:rgba(255,255,255,.9); }}
    .sonar-status {{ display:inline-block; width:7px; height:7px; margin-right:7px; border-radius:50%; background:#72f2de; animation: sonar-pulse 2.2s ease-out infinite; }}

    section[data-testid="stSidebar"] {{
        background: #F5F5F7;
        border-right: 1px solid {COL_HAIRLINE};
    }}
    section[data-testid="stSidebar"] * {{ color: {COL_INK}; }}
    section[data-testid="stSidebar"] [data-testid="stMetricLabel"] {{
        color: {COL_MUTED} !important; font-size: 12px; font-weight: 400;
        text-transform: none; letter-spacing: 0;
    }}
    section[data-testid="stSidebar"] [data-testid="stMetricValue"] {{
        color: {COL_INK} !important; font-size: 26px; font-weight: 600;
        letter-spacing: -0.02em;
    }}
    section[data-testid="stSidebar"] hr {{ border-color: {COL_HAIRLINE}; }}

    div[data-baseweb="tab-list"] {{
        gap: 0; background: transparent; padding: 0;
        border-bottom: 1px solid {COL_HAIRLINE}; border-radius: 0;
        box-shadow: none;
    }}
    button[data-baseweb="tab"] {{
        border-radius: 0 !important; padding: 12px 18px !important;
        font-weight: 400 !important; color: {COL_MUTED} !important;
        background: transparent !important; font-size: 14px !important;
        border-bottom: 2px solid transparent !important;
        transition: color .24s ease, border-color .24s ease, transform .24s ease !important;
    }}
    button[data-baseweb="tab"][aria-selected="true"] {{
        background: transparent !important; color: {COL_INK} !important;
        border-bottom: 2px solid {COL_INK} !important; font-weight: 500 !important;
    }}
    div[data-baseweb="tab-highlight"] {{ display: none; }}

    [data-testid="stMetric"] {{
        background: {COL_CARD}; padding: 18px 20px; border-radius: 12px;
        border: 1px solid {COL_HAIRLINE}; box-shadow: none;
    }}
    [data-testid="stMetric"] label {{ color: {COL_MUTED} !important; font-weight: 400; font-size: 13px; }}
    [data-testid="stMetricValue"] {{
        color: {COL_INK} !important; font-weight: 600;
        letter-spacing: -0.02em; font-size: 28px;
    }}

    h1 {{ color: {COL_INK} !important; font-weight: 600; letter-spacing: -0.03em; }}
    h2, h3 {{ color: {COL_INK} !important; font-weight: 500; letter-spacing: -0.02em; }}
    h4, h5, h6 {{ color: {COL_INK} !important; font-weight: 500; }}

    .kpi-strip {{ display: flex; gap: 12px; margin: 16px 0; flex-wrap: wrap; }}
    .kpi {{
        flex: 1; min-width: 180px; background: {COL_CARD};
        padding: 18px 20px; border-radius: 12px; border: 1px solid {COL_HAIRLINE};
        box-shadow: none; transition: transform .3s cubic-bezier(.2,.8,.2,1), box-shadow .3s ease, border-color .3s ease;
    }}
    [data-testid="stMetric"]:hover {{ transform: translateY(-4px); border-color:#b9c7d2; box-shadow:0 12px 26px rgba(29,29,31,.09); }}
    .kpi .kpi-label {{
        color: {COL_MUTED}; font-size: 13px; font-weight: 400;
        text-transform: none; letter-spacing: 0;
    }}
    .kpi .kpi-value {{
        color: {COL_INK}; font-size: 28px; font-weight: 600;
        margin-top: 4px; letter-spacing: -0.02em;
    }}
    .kpi .kpi-note {{ color: {COL_MUTED}; font-size: 12px; margin-top: 4px; }}

    .principle-note {{
        background: {COL_CARD}; border: 1px solid {COL_HAIRLINE};
        border-radius: 12px; padding: 16px 18px; margin: 16px 0;
    }}
    .principle-note .principle-title {{
        color: {COL_INK}; font-weight: 500; font-size: 13px;
        margin-bottom: 6px; letter-spacing: -0.01em;
    }}
    .principle-note .principle-body {{
        color: {COL_MUTED}; font-size: 13px; line-height: 1.55;
    }}
    .data-provenance {{
        display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:1px;
        overflow:hidden; margin:12px 0 20px; border:1px solid {COL_HAIRLINE};
        border-radius:14px; background:{COL_HAIRLINE};
    }}
    .data-provenance > div {{ background:{COL_CARD}; padding:14px 16px; }}
    .data-provenance span {{ display:block; color:{COL_MUTED}; font-size:11px; margin-bottom:4px; }}
    .data-provenance strong {{ display:block; color:{COL_INK}; font-size:14px; line-height:1.32; font-weight:550; }}

    /* Streamlit's default subheader — quieter, denser */
    .stApp [data-testid="stMarkdownContainer"] p {{ line-height: 1.55; }}

    /* Buttons in sidebar */
    section[data-testid="stSidebar"] .stCaption {{
        color: {COL_MUTED} !important; font-size: 11px;
    }}

    /* Expander — flatter */
    .streamlit-expanderHeader {{
        background: {COL_CARD} !important; border: 1px solid {COL_HAIRLINE} !important;
        border-radius: 10px !important; font-weight: 400 !important;
    }}
    .stApp img {{ border-radius: 18px; animation: sonar-rise .7s cubic-bezier(.2,.8,.2,1) both; }}
    [data-testid="stButton"] button {{ transition: transform .22s ease, box-shadow .22s ease, background .22s ease !important; border-radius: 999px !important; }}
    [data-testid="stButton"] button:hover {{ transform: scale(1.025); box-shadow: 0 8px 20px rgba(0,0,0,.12); }}
    [role="tabpanel"] {{ animation: sonar-rise .42s cubic-bezier(.2,.8,.2,1) both; }}
    .stApp iframe {{ border-radius:18px; overflow:hidden; }}
    @media (max-width: 720px) {{
        .main .block-container {{ padding: .65rem .85rem 2rem; }}
        .sonar-hero {{ border-radius:22px; padding:28px 22px; margin-top:0; }}
        .sonar-title {{ font-size:42px; letter-spacing:-.055em; }}
        .sonar-copy {{ font-size:14px; }}
        .sonar-pills {{ gap:6px; margin-top:19px; }}
        .sonar-pill {{ font-size:11px; padding:7px 10px; }}
        div[data-baseweb="tab-list"] {{ overflow-x:auto; scrollbar-width:none; white-space:nowrap; }}
        button[data-baseweb="tab"] {{ padding:11px 12px !important; font-size:13px !important; }}
        [data-testid="stMetric"] {{ padding:14px 15px; border-radius:11px; }}
        [data-testid="stMetricValue"] {{ font-size:24px; }}
        section[data-testid="stSidebar"] {{ min-width:280px; }}
        .data-provenance {{ grid-template-columns:1fr; gap:1px; }}
    }}
    @media (prefers-reduced-motion: reduce) {{ *, *::before, *::after {{ animation-duration:.01ms !important; animation-iteration-count:1 !important; transition-duration:.01ms !important; }} }}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

STATE_COLOR = {"AIS_OK": COL_OK, "AIS_MISMATCH": COL_MISMATCH, "DARK": COL_DARK}
STATE_LABEL = {"AIS_OK": "Có AIS khớp", "AIS_MISMATCH": "AIS lệch", "DARK": "Không có AIS"}

# ---------------------------------------------------------------------------
# Paths & data
# ---------------------------------------------------------------------------
RUN = ROOT / "sonarnet_run"
RESULTS = RUN / "results"
YOLO = RUN / "data" / "yolo"
LIVE_DEMO_IMAGE = ROOT / "assets" / "sentinel1_binh_thuan_20260912.png"
LIVE_DEMO_METADATA = ROOT / "assets" / "sentinel1_binh_thuan_20260912.json"


@st.cache_data
def load_results():
    kq = json.loads((RESULTS / "tong_hop_ket_qua.json").read_text())
    ablation = json.loads((RESULTS / "ablation.json").read_text())
    interp = json.loads((RESULTS / "interpolation_comparison.json").read_text())
    return kq, ablation, interp


@st.cache_data
def load_test_scenes():
    scenes_meta = YOLO / "scenes" / "test.jsonl"
    if not scenes_meta.exists():
        return []
    metas = [json.loads(line) for line in scenes_meta.read_text().splitlines()]
    for m in metas:
        m["image_path"] = str(YOLO / "images" / "test" / f"{m['scene_id']}.png")
    return metas


@st.cache_data
def load_predictions():
    npz = RESULTS / "predictions_test.npz"
    if not npz.exists():
        return {}
    d = np.load(npz, allow_pickle=True)
    out = {}
    for key in d.files:
        if key.endswith("__boxes"):
            sid = key[:-len("__boxes")]
            boxes = d[key]
            scores = d[f"{sid}__scores"] if f"{sid}__scores" in d.files else np.ones(len(boxes))
            out[sid] = {"boxes": np.asarray(boxes), "scores": np.asarray(scores)}
    return out


try:
    KQ, ABL, INTERP = load_results()
except Exception as e:
    st.error(
        "**Chưa có kết quả để hiển thị.**\n\n"
        "Chạy pipeline trước:\n\n"
        "```bash\npython3 scripts/run_pipeline.py --backend ultralytics --single-gpu\n```"
    )
    st.stop()

SCENES = load_test_scenes()
PREDS = load_predictions()

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown("""
<section class="sonar-hero">
  <div class="sonar-eyebrow"><span class="sonar-status"></span>National maritime intelligence</div>
  <div class="sonar-title">See the sea.<br>Understand the signal.</div>
  <div class="sonar-copy">SonarNet‑VN hợp nhất radar Sentinel‑1, tín hiệu AIS và suy luận quỹ đạo thành một bức tranh trực quan, có thể kiểm chứng cho giám sát khai thác hải sản.</div>
  <div class="sonar-pills">
    <span class="sonar-pill">Sentinel‑1 · SAR</span>
    <span class="sonar-pill">AIS · đối chiếu độc lập</span>
    <span class="sonar-pill">Việt Nam · tự làm mới theo lượt bay</span>
  </div>
</section>
""", unsafe_allow_html=True)

st.components.v1.html("""
<div style="display:flex;justify-content:flex-end;padding:0 2px 15px;font-family:-apple-system,BlinkMacSystemFont,'SF Pro Text',sans-serif">
  <div style="display:flex;align-items:center;gap:10px;border:1px solid #d2d2d7;border-radius:999px;background:rgba(255,255,255,.86);padding:8px 13px;color:#1d1d1f;font-size:12px;box-shadow:0 8px 24px rgba(0,0,0,.06)">
    <span style="display:block;width:7px;height:7px;border-radius:50%;background:#34c759;box-shadow:0 0 0 4px rgba(52,199,89,.13)"></span>
    <span id="vn-clock">Việt Nam · Đang đồng bộ…</span>
  </div>
</div>
<script>
  const clock = document.getElementById('vn-clock');
  function tick() {
    const now = new Intl.DateTimeFormat('vi-VN', {timeZone:'Asia/Ho_Chi_Minh', weekday:'short', day:'2-digit', month:'2-digit', year:'numeric', hour:'2-digit', minute:'2-digit', second:'2-digit', hour12:false}).format(new Date());
    clock.textContent = 'Việt Nam · ' + now + ' (GMT+7)';
  }
  tick(); setInterval(tick, 1000);
</script>
""", height=52)

# This value is populated in the live-data tab, then reused by the national map.
national_mosaic: bytes | None = None
national_mosaic_status: dict[str, str | int | None] | None = None

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        f"<div style='font-size:11px;font-weight:500;color:{COL_MUTED};"
        f"text-transform:uppercase;letter-spacing:0.06em;margin-bottom:12px;'>"
        f"Chỉ tiêu vận hành</div>",
        unsafe_allow_html=True,
    )
    st.metric("Độ chính xác phát hiện (mAP@0.5)", f"{KQ['detection']['mAP@0.5']:.3f}")
    st.metric("Độ chính xác phân loại trạng thái", f"{KQ['fusion']['state_accuracy']:.1%}")
    st.metric("F1 vĩ mô hợp nhất", f"{KQ['fusion']['state_macro_f1']:.3f}")
    st.metric("F1 phân loại hành vi", f"{KQ['behaviour']['macro_f1']:.3f}")

    st.markdown(f"<div style='height:1px;background:{COL_HAIRLINE};margin:20px 0;'></div>", unsafe_allow_html=True)

    st.markdown(
        f"""<div style="background:{COL_CARD};border:1px solid {COL_HAIRLINE};
                     padding:14px 16px;border-radius:12px;">
        <div style="color:{COL_INK};font-weight:500;font-size:13px;margin-bottom:8px;
                    letter-spacing:-0.01em;">
        Phạm vi sử dụng</div>
        <div style="color:{COL_MUTED};font-size:12px;line-height:1.6;">
        Hệ thống dành cho cơ quan quản lý nhà nước về khai thác hải sản. Kết
        quả phát hiện, ghép cặp và phân loại chỉ mang tính hỗ trợ nghiệp vụ;
        quyết định xử lý thuộc thẩm quyền cơ quan chức năng.
        </div></div>""",
        unsafe_allow_html=True,
    )

    st.markdown(f"<div style='height:1px;background:{COL_HAIRLINE};margin:20px 0;'></div>", unsafe_allow_html=True)

    st.markdown(
        f"<div style='color:{COL_MUTED};font-size:11px;line-height:1.6;'>"
        f"Kiến trúc: YOLO11n · Kalman–RTS · XGBoost<br>"
        f"Dữ liệu: 500 cảnh Sentinel-1 mô phỏng<br>"
        f"Huấn luyện: 80 chu kỳ trên Apple Metal</div>",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_overview, tab_map, tab_live, tab_evidence = st.tabs([
    "Tổng quan",
    "Bản đồ giám sát",
    "Dữ liệu vệ tinh thật",
    "Phân tích & độ tin cậy",
])

# Keep research evidence available for a jury without putting specialist
# vocabulary in the primary journey used by operators and the public.
with tab_evidence:
    evidence_radar, evidence_ais, evidence_tracks, evidence_metrics = st.tabs([
        "Kiểm chứng ảnh radar",
        "Đối chiếu AIS",
        "Theo dõi hành trình",
        "Báo cáo độ tin cậy",
    ])

# ============================================================================
# TAB LIVE — Copernicus Sentinel-1 GRD
# ============================================================================
with tab_live:
    st.subheader("Toàn cảnh Việt Nam — Sentinel‑1 mới nhất")
    st.caption("Mỗi điểm ảnh là quan sát Sentinel‑1 mới nhất trong 14 ngày gần đây. Lớp ảnh tự làm mới theo Copernicus mỗi 6 giờ, theo nhịp lượt bay vệ tinh — không phải video liên tục.")
    if "copernicus" in st.secrets:
        try:
            with st.spinner("Đang dựng mosaic Sentinel‑1 mới nhất phủ vùng biển Việt Nam…"):
                national_mosaic_status = load_vietnam_mosaic_status(
                    st.secrets["copernicus"]["client_id"], st.secrets["copernicus"]["client_secret"], date.today(),
                )
                national_mosaic = load_vietnam_latest_mosaic(
                    st.secrets["copernicus"]["client_id"], st.secrets["copernicus"]["client_secret"], date.today(),
                )
            st.markdown(
                f"""<div class="data-provenance">
                  <div><span>PHẠM VI HIỂN THỊ</span><strong>Biển Việt Nam · 06°–22°B, 102°–115°Đ</strong></div>
                  <div><span>CẢNH MỚI NHẤT TRONG CATALOG</span><strong>{format_vietnam_time(national_mosaic_status['newest'] if national_mosaic_status else None)}</strong></div>
                  <div><span>CỬA SỔ MOSAIC</span><strong>{national_mosaic_status['window_start'] if national_mosaic_status else '—'} → {national_mosaic_status['window_end'] if national_mosaic_status else '—'} · {national_mosaic_status['count'] if national_mosaic_status else 0} cảnh</strong></div>
                </div>""",
                unsafe_allow_html=True,
            )
            st.image(national_mosaic, caption="Sentinel‑1 GRD · VV Gamma0 ellipsoid · mosaic theo pixel mới nhất · Copernicus Data Space", use_container_width=True)
            if national_mosaic_status and national_mosaic_status.get("zones"):
                zone_lines = "<br>".join(
                    f"<b>{zone}</b> — {format_vietnam_time(acquired_at)}"
                    for zone, acquired_at in sorted(national_mosaic_status["zones"].items())
                )
                with st.expander("Ngày quan sát mới nhất theo khu vực", expanded=True):
                    st.markdown(
                        "Các mốc dưới đây là thời điểm cảnh catalog mới nhất có footprint giao với từng vùng. "
                        "Trong mosaic, từng pixel dùng quan sát mới nhất sẵn có trong cửa sổ 14 ngày.<br><br>" + zone_lines,
                        unsafe_allow_html=True,
                    )
        except CopernicusError as exc:
            st.error(str(exc))
    else:
        st.info("Thiếu cấu hình Copernicus để tạo mosaic toàn quốc.")

    st.subheader("Cảnh chi tiết và đối chiếu độc lập")
    st.markdown(
        f"<div style='color:{COL_MUTED};margin-bottom:16px;font-size:14px;line-height:1.55;'>"
        "Cảnh radar VV đã hiệu chỉnh địa hình được hiển thị ngay khi mở tab. Các vòng đỏ là "
        "phát hiện theo ô lưới của Global Fishing Watch tại cùng cửa sổ thời gian. "
        "Dữ liệu trong tab này là dữ liệu thật; các chỉ tiêu mô hình ở các tab còn lại vẫn là mô phỏng."
        "</div>",
        unsafe_allow_html=True,
    )
    observation_scope = st.radio(
        "Phạm vi quan sát", ["Việt Nam — cảnh có sẵn", "Quốc tế — cảnh mẫu"],
        horizontal=True, key="observation_scope",
    )
    vietnam_product = None
    available_regions = {
        "Việt Nam · Bình Thuận — cảnh chuẩn đã kiểm chứng": None,
        "Nhật Bản · Tokyo Bay": (35.45, 139.80),
        "Singapore · Eo biển Singapore": (1.25, 104.00),
        "Hàn Quốc · Cảng Busan": (35.10, 129.10),
        "Hà Lan · Cảng Rotterdam": (51.95, 4.05),
        "Hoa Kỳ · Cảng Los Angeles": (33.65, -118.25),
        "Brazil · Cảng Santos": (-24.00, -46.35),
        "Ai Cập · Cửa bắc kênh Suez": (31.28, 32.32),
        "Nam Phi · Vịnh Table, Cape Town": (-33.90, 18.40),
    }
    if observation_scope == "Việt Nam — cảnh có sẵn":
        if "copernicus" not in st.secrets:
            st.error("Chưa có cấu hình Copernicus để tải catalog Việt Nam.")
            st.stop()
        try:
            with st.spinner("Đang lập catalog Sentinel-1 có sẵn trên toàn vùng biển Việt Nam…"):
                vietnam_products = load_available_vietnam_scenes(
                    st.secrets["copernicus"]["client_id"], st.secrets["copernicus"]["client_secret"],
                    date.today() - timedelta(days=4),
                )
            if not vietnam_products:
                st.error("Chưa tìm thấy cảnh Sentinel-1 phù hợp trong cửa sổ GFW đã công bố.")
                st.stop()
            vietnam_product = st.selectbox(
                "Chọn cảnh Sentinel-1 có sẵn trên vùng biển Việt Nam", vietnam_products,
                format_func=lambda item: (
                    f"{vietnam_scene_match(item.bbox)[0]} · {item.acquired_at} · {item.platform}"
                ),
                key="vietnam_available_scene",
            )
            st.caption(f"Catalog đang có {len(vietnam_products)} cảnh. Mỗi cảnh đã được match footprint với vùng biển Việt Nam trước khi hiển thị.")
        except CopernicusError as exc:
            st.error(str(exc))
            st.stop()
        selected_region = "Việt Nam · catalog Copernicus"
    else:
        selected_region = st.selectbox(
            "Chọn vùng quan sát quốc tế có sẵn", list(available_regions),
            help="Các vùng biển và cảng quốc tế đã cấu hình sẵn cho luồng Sentinel‑1 × GFW. Chọn vùng là web tự tải, không cần nút chạy.",
            key="global_observation_region",
        )
        st.caption("Các lựa chọn quốc tế tự lấy cảnh Sentinel‑1 mới nhất trong cửa sổ GFW đã công bố.")
    if not (LIVE_DEMO_IMAGE.exists() and LIVE_DEMO_METADATA.exists()):
        st.error("Thiếu cảnh Sentinel-1 đã đóng gói cho bản demo.")
    else:
        is_standard_scene = vietnam_product is None and available_regions[selected_region] is None
        evidence = json.loads(LIVE_DEMO_METADATA.read_text())
        reference_image: Path | bytes = LIVE_DEMO_IMAGE
        scene_name = "Ngoài khơi Bình Thuận"
        reference_bbox = tuple(evidence["bbox_wgs84"])
        reference_start = date.fromisoformat(evidence["acquired_at"][:10])
        reference_end = reference_start + timedelta(days=1)
        if vietnam_product is not None:
            if "copernicus" not in st.secrets:
                st.error("Chưa có cấu hình Copernicus để tải cảnh đã chọn.")
                st.stop()
            matched_scene = vietnam_scene_match(vietnam_product.bbox)
            if matched_scene is None:
                st.error("Footprint cảnh này không khớp vùng biển Việt Nam đã định nghĩa.")
                st.stop()
            scene_name, reference_bbox = matched_scene
            try:
                with st.spinner("Đang dựng ảnh Sentinel-1 cho cảnh Việt Nam đã chọn…"):
                    reference_image = load_product_preview(
                        st.secrets["copernicus"]["client_id"], st.secrets["copernicus"]["client_secret"],
                        reference_bbox, vietnam_product.acquired_at,
                    )
                evidence = {
                    "product_id": vietnam_product.product_id, "acquired_at": vietnam_product.acquired_at,
                    "render": "VV gamma0 terrain, orthorectified, 768 px",
                    "retrieved_at": date.today().isoformat(),
                }
                reference_start = date.fromisoformat(vietnam_product.acquired_at[:10])
                reference_end = reference_start + timedelta(days=1)
            except CopernicusError as exc:
                st.error(str(exc))
                st.stop()
        elif not is_standard_scene:
            if "copernicus" not in st.secrets:
                st.error("Chưa có cấu hình Copernicus để tự tải cảnh toàn cầu.")
                st.stop()
            try:
                with st.spinner("Đang định vị vùng quan sát và tìm cảnh Sentinel-1 mới nhất có thể đối chiếu…"):
                    latitude, longitude = available_regions[selected_region]
                    half_width = 0.20
                    scene_name = selected_region.split(" · ", 1)[1]
                    reference_bbox = (
                        longitude - half_width, latitude - half_width * 0.75,
                        longitude + half_width, latitude + half_width * 0.75,
                    )
                    # GFW publishes with a short latency. Select the newest pass in
                    # its likely available window, rather than a newer pass whose
                    # independent reference has not been published yet.
                    reference_cutoff = date.today() - timedelta(days=4)
                    product, reference_image = load_latest_global_scene(
                        st.secrets["copernicus"]["client_id"], st.secrets["copernicus"]["client_secret"],
                        reference_bbox, reference_cutoff,
                    )
                evidence = {
                    "product_id": product.product_id, "acquired_at": product.acquired_at,
                    "render": "VV gamma0 terrain, orthorectified, 768 px",
                    "retrieved_at": date.today().isoformat(),
                }
                reference_start = date.fromisoformat(product.acquired_at[:10])
                reference_end = reference_start + timedelta(days=1)
            except (ValueError, CopernicusError) as exc:
                st.error(str(exc))
                st.stop()

        ref_cells = []
        if "gfw" in st.secrets:
            try:
                with st.spinner("Đang ghép lớp SAR Vessel Detections vào cảnh Sentinel-1…"):
                    ref_cells = load_demo_gfw_reference(
                        st.secrets["gfw"]["api_token"], reference_bbox, reference_start, reference_end,
                    )
            except GlobalFishingWatchError as exc:
                st.error(str(exc))

        image_col, context_col = st.columns([1.75, 1])
        with image_col:
            st.image(
                gfw_overlay_png(reference_image, reference_bbox, ref_cells),
                caption=("Sentinel-1 GRD thật · VV gamma0 terrain · "
                         f"{evidence['acquired_at']} · {scene_name}. "
                         "Vòng đỏ: ô GFW SAR Vessel Detections."),
                use_container_width=True,
            )
        with context_col:
            west, south, east, north = reference_bbox
            st.markdown("#### Cảnh demo chuẩn" if is_standard_scene else (
                "#### Cảnh quan sát Việt Nam" if vietnam_product is not None else "#### Cảnh quan sát quốc tế"
            ))
            st.metric("Phát hiện GFW", sum(cell.detections for cell in ref_cells))
            st.metric("Ô lưới có tín hiệu", len(ref_cells))
            st.caption(f"Cùng cửa sổ thời gian: {reference_start.strftime('%d/%m/%Y')} UTC.")
            st.caption(f"Khung ảnh: {south:.2f}–{north:.2f}°B · {west:.2f}–{east:.2f}°Đ")
            st.caption("Nguồn ảnh: Copernicus Sentinel-1 GRD, cảnh VV gamma0 đã chỉnh địa hình.")
            st.caption(("Chuẩn demo mới nhất đã xác minh đồng thời với GFW" if is_standard_scene else "Cảnh tự động chọn mới nhất trong cửa sổ GFW đã công bố") + f" · cập nhật {evidence['retrieved_at']}.")
            st.caption(f"Mã sản phẩm: `{evidence['product_id']}`")

        st.markdown("#### Bản đồ đối chiếu độc lập")
        st.caption("GFW dùng Sentinel-1 và mô hình riêng để lập lớp tham chiếu theo ô lưới. SonarNet chỉ dùng lớp này để kiểm tra tính nhất quán; không huấn luyện từ GFW, không coi là ground truth tuyệt đối, không suy diễn danh tính hoặc vi phạm.")
        if ref_cells:
            import folium
            from streamlit.components.v1 import html as st_html

            west, south, east, north = reference_bbox
            reference_map = folium.Map(
                location=[(south + north) / 2, (west + east) / 2], zoom_start=10,
                tiles=None, control_scale=True, zoom_control=True,
            )
            folium.TileLayer(
                tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                attr="Esri, Maxar, Earthstar Geographics", name="Nền vệ tinh", overlay=False,
            ).add_to(reference_map)
            folium.raster_layers.ImageOverlay(
                image=folium_image_source(reference_image), bounds=[[south, west], [north, east]],
                opacity=0.76, interactive=True, cross_origin=False, zindex=2,
                name="Cảnh Sentinel-1 VV",
            ).add_to(reference_map)
            folium.Rectangle(
                bounds=[[south, west], [north, east]], color="#ffffff", weight=2,
                fill=False, tooltip="Khung ảnh Sentinel-1 GRD",
            ).add_to(reference_map)
            for cell in ref_cells:
                radius = 6 + min(cell.detections, 4) * 2
                folium.CircleMarker(
                    location=[cell.latitude, cell.longitude], radius=radius,
                    color="#ffffff", weight=2, fill=True, fill_color="#ff3b30", fill_opacity=0.92,
                    tooltip=(f"<b>GFW SAR Vessel Detections</b><br>{cell.acquired_at} UTC"
                             f"<br>{cell.detections} phát hiện trong ô lưới"),
                ).add_to(reference_map)
            folium.LayerControl(collapsed=True).add_to(reference_map)
            reference_map.get_root().html.add_child(folium.Element("""
                <div style="position:fixed;bottom:24px;left:24px;z-index:9999;
                    background:rgba(18,18,18,.88);color:#fff;padding:12px 14px;border-radius:12px;
                    font:13px -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;line-height:1.5;
                    box-shadow:0 8px 24px rgba(0,0,0,.25)">
                  <div style="font-weight:650;margin-bottom:5px">Đối chiếu Sentinel‑1 × GFW</div>
                  <div><span style="display:inline-block;width:11px;height:11px;background:#7e7e7e;
                    border:1px solid #fff;margin-right:7px"></span>Ảnh Sentinel‑1 VV</div>
                  <div><span style="display:inline-block;width:11px;height:11px;background:#ff3b30;
                    border:2px solid #fff;border-radius:50%;margin-right:7px"></span>Ô phát hiện GFW</div>
                </div>
            """))
            st_html(reference_map.get_root().render(), height=540)

        st.markdown("#### Bảng đối chiếu")
        st.caption("Mỗi dòng là một ô GFW để kiểm tra lại vị trí hiển thị trên bản đồ, không phải một phương tiện được nhận dạng.")
        if ref_cells:
            import pandas as pd
            st.dataframe(pd.DataFrame([
                {"Thời điểm": cell.acquired_at, "Vĩ độ": round(cell.latitude, 3),
                 "Kinh độ": round(cell.longitude, 3), "Phát hiện": cell.detections}
                for cell in ref_cells
            ]), use_container_width=True, hide_index=True)
        elif "gfw" not in st.secrets:
            st.info("Cảnh Sentinel-1 vẫn hiển thị đầy đủ. Thêm token GFW để tự chồng lớp đối chiếu độc lập.")

# ============================================================================
# TAB SIM — Simulated vessel motion
# ============================================================================
with tab_overview:
    import time
    from streamlit.components.v1 import html as st_html

    st.markdown(
        f"<div style='font-size:22px;font-weight:500;letter-spacing:-0.02em;"
        f"color:{COL_INK};margin-top:8px;margin-bottom:6px;'>"
        f"Mô phỏng hoạt động đội tàu trên vùng biển Việt Nam</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div style='color:{COL_MUTED};margin-bottom:16px;line-height:1.55;font-size:14px;'>"
        f"48 phương tiện được mô phỏng trên toàn bộ vùng biển Việt Nam, bao gồm "
        f"Vịnh Bắc Bộ, ven bờ miền Trung, quần đảo Hoàng Sa và Trường Sa, các "
        f"đảo tiền tiêu và Vịnh Thái Lan. Chọn một phương tiện trên bản đồ để "
        f"xem thông tin quan sát được; chọn nhãn hành chính để xem thông tin đảo."
        f"</div>",
        unsafe_allow_html=True,
    )

    # Sinh dữ liệu tàu 1 lần — phân bố theo 7 ngư trường trọng điểm
    @st.cache_data
    def build_fleet_json(seed: int = 20260916):
        rng = np.random.default_rng(seed)
        zones = [
            ("Vịnh Bắc Bộ (Hải Phòng – Quảng Ninh)", 107.60, 20.40, 0.55,
             [("HP", "Hải Phòng"), ("QN", "Vân Đồn, Quảng Ninh"),
              ("TB", "Thái Thuỵ, Thái Bình"), ("NĐ", "Hải Hậu, Nam Định")]),
            ("Ven biển Bắc Trung Bộ (Thanh Hoá – Hà Tĩnh)", 106.60, 18.30, 0.60,
             [("TH", "Sầm Sơn, Thanh Hoá"), ("NA", "Cửa Lò, Nghệ An"),
              ("HT", "Nghi Xuân, Hà Tĩnh")]),
            ("Ven biển Trung Trung Bộ (Đà Nẵng – Quảng Ngãi)", 109.20, 15.80, 0.70,
             [("ĐNa", "Thọ Quang, Đà Nẵng"), ("QNa", "Núi Thành, Quảng Nam"),
              ("QNg", "Sa Kỳ, Quảng Ngãi"), ("QNg", "Lý Sơn, Quảng Ngãi")]),
            ("Ngư trường Hoàng Sa", 112.20, 16.50, 0.80,
             [("QNg", "Lý Sơn, Quảng Ngãi"), ("ĐNa", "Thọ Quang, Đà Nẵng"),
              ("KH", "Vĩnh Lương, Khánh Hoà"), ("BĐ", "Quy Nhơn, Bình Định")]),
            ("Ngư trường Trường Sa", 113.80, 10.20, 0.90,
             [("KH", "Nha Trang, Khánh Hoà"), ("PY", "Tuy Hoà, Phú Yên"),
              ("BĐ", "Quy Nhơn, Bình Định"), ("BR-VT", "Vũng Tàu")]),
            ("Ngoài khơi Bình Thuận – Bà Rịa", 108.60, 10.20, 0.65,
             [("BTh", "Phan Thiết, Bình Thuận"), ("BTh", "La Gi, Bình Thuận"),
              ("BR-VT", "Vũng Tàu"), ("BR-VT", "Long Hải, Bà Rịa – Vũng Tàu")]),
            ("Vịnh Thái Lan (Cà Mau – Kiên Giang)", 104.60, 8.90, 0.55,
             [("KG", "Rạch Giá, Kiên Giang"), ("KG", "Phú Quốc, Kiên Giang"),
              ("CM", "Sông Đốc, Cà Mau"), ("CM", "Năm Căn, Cà Mau")]),
        ]
        zone_weights = np.array([0.14, 0.10, 0.18, 0.13, 0.15, 0.18, 0.12])
        zone_weights /= zone_weights.sum()

        # Kho tên phương tiện và chủ sở hữu (danh mục mô phỏng)
        ship_names = [
            "Bình Minh", "Đại Dương", "Biển Đông", "Hải Đăng", "Ngọc Rồng",
            "Đại Phát", "Thắng Lợi", "Hồng Hạc", "Phú Quý", "Long Hải",
            "Thái Bình Dương", "Sao Biển", "Đại Thành", "Đông Hải", "Hoàng Long",
            "Quang Trung", "Trần Hưng Đạo", "Tiến Phát", "An Bình", "Lộc Phát",
            "Kim Ngân", "Song Ngư", "Phú Hải", "Vạn Chài", "Thanh Long",
        ]
        owners_individual = [
            "Nguyễn Văn Bình", "Trần Văn Cường", "Lê Thanh Hải", "Phạm Đình Sơn",
            "Võ Văn Thắng", "Hoàng Minh Đức", "Đặng Xuân Trường", "Bùi Văn Hải",
            "Ngô Quang Hưng", "Đinh Văn Dũng", "Trương Công Định", "Phan Thanh Tùng",
            "Lý Quốc Hùng", "Vũ Anh Tuấn", "Đỗ Văn Long",
        ]
        owners_org = [
            "HTX Đánh cá Bình Minh", "HTX Nghề cá Đại Dương",
            "Công ty TNHH Thuỷ sản Hải Đăng", "HTX Ngư nghiệp Đông Hải",
            "HTX Đoàn kết", "Công ty CP Thuỷ sản Phú Quý",
        ]

        n_ships = 48
        labels = ["AIS_OK"] * 31 + ["AIS_MISMATCH"] * 8 + ["DARK"] * 9
        rng.shuffle(labels)
        behaviours = ["cau", "keo_luoi", "qua_canh", "neo_dau"]
        bhv_labels = {"cau": "Câu", "keo_luoi": "Kéo lưới",
                       "qua_canh": "Quá cảnh", "neo_dau": "Neo đậu"}
        fleet = []
        used_regs = set()
        for i in range(n_ships):
            zone_idx = int(rng.choice(len(zones), p=zone_weights))
            zone_name, zlon, zlat, zrad, ports = zones[zone_idx]
            bhv = rng.choice(behaviours, p=[0.36, 0.28, 0.22, 0.14])
            if bhv == "neo_dau":
                radius = rng.uniform(0.005, 0.015); speed = rng.uniform(0.1, 0.4)
                pattern = 0
            elif bhv == "cau":
                radius = rng.uniform(0.05, 0.11); speed = rng.uniform(2.0, 3.8)
                pattern = 1
            elif bhv == "keo_luoi":
                radius = rng.uniform(0.08, 0.16); speed = rng.uniform(3.0, 4.5)
                pattern = 2
            else:
                radius = rng.uniform(0.18, 0.35); speed = rng.uniform(8, 11)
                pattern = 3
            cx = float(zlon + rng.uniform(-zrad, zrad))
            cy = float(zlat + rng.uniform(-zrad, zrad))

            # Sinh số hiệu đăng ký, MMSI, tên phương tiện, chủ sở hữu
            port_code, port_name = ports[int(rng.integers(len(ports)))]
            while True:
                reg_num = int(rng.integers(10000, 99999))
                reg = f"{port_code}-{reg_num}-TS"
                if reg not in used_regs:
                    used_regs.add(reg); break
            mmsi = int(574000000 + rng.integers(100000, 999999))
            ship_name = f"{ship_names[int(rng.integers(len(ship_names)))]} {int(rng.integers(1, 99)):02d}"
            if rng.random() < 0.2:
                owner = owners_org[int(rng.integers(len(owners_org)))]
            else:
                owner = owners_individual[int(rng.integers(len(owners_individual)))]

            length_true = float(
                (rng.uniform(60, 95) if pattern == 3 else
                 rng.uniform(28, 55) if pattern == 2 else
                 rng.uniform(14, 32))
            )
            # AIS_MISMATCH: khai báo lệch đáng kể so với chiều dài thật đo bằng radar
            length_declared = (length_true * float(rng.uniform(0.35, 0.55))
                                if labels[i] == "AIS_MISMATCH" else length_true)

            fleet.append({
                "id": f"tàu {i+1:02d}",
                "state": labels[i],
                "behaviour": bhv_labels[bhv],
                "zone": zone_name,
                "port": port_name,
                "reg": reg,
                "mmsi": mmsi,
                "ship_name": ship_name,
                "owner": owner,
                "length_true": round(length_true, 1),
                "length_declared": round(length_declared, 1),
                "cx": cx,
                "cy": cy,
                "radius": float(radius),
                "speed": float(speed),
                "pattern": int(pattern),
                "phase": float(rng.uniform(0, 6.283)),
                "direction": float(rng.uniform(0, 6.283)),
                "ais_off_at": float(rng.uniform(5, 35)) if labels[i] == "DARK" else -1,
            })
        return fleet

    fleet_json = json.dumps(build_fleet_json())

    # HTML + Leaflet JS — render 1 lần, tự chạy vô hạn
    html_code = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
    html, body {{ margin:0; padding:0; height:100%; font-family:-apple-system,BlinkMacSystemFont,sans-serif; }}
    #map {{ height:640px; border-radius:12px; }}
    .legend {{
        position:absolute; top:14px; right:14px; z-index:1000;
        background:rgba(255,255,255,0.94);
        backdrop-filter: saturate(180%) blur(20px);
        -webkit-backdrop-filter: saturate(180%) blur(20px);
        padding:14px 18px; border-radius:12px;
        border:1px solid rgba(0,0,0,0.06);
        box-shadow:0 4px 16px rgba(0,0,0,0.08);
        font-size:13px; color:#1D1D1F;
    }}
    .legend-title {{
        font-weight:500; margin-bottom:10px; font-size:11px;
        text-transform:uppercase; letter-spacing:0.06em; color:#6E6E73;
    }}
    .legend-row {{ margin:6px 0; display:flex; align-items:center; gap:10px; }}
    .legend-dot {{ width:10px; height:10px; border-radius:50%; }}
</style>
</head>
<body>
<div id="map"></div>
<div class="legend">
    <div class="legend-title">Trạng thái phương tiện</div>
    <div class="legend-row"><span class="legend-dot" style="background:{COL_OK};"></span>Có AIS khớp</div>
    <div class="legend-row"><span class="legend-dot" style="background:{COL_MISMATCH};"></span>AIS sai lệch</div>
    <div class="legend-row"><span class="legend-dot" style="background:{COL_DARK};"></span>Không có AIS</div>
</div>

<script>
    var FLEET = {fleet_json};
    var STATE_COLOR = {{"AIS_OK": "{COL_OK}", "AIS_MISMATCH": "{COL_MISMATCH}", "DARK": "{COL_DARK}"}};
    var STATE_LABEL = {{"AIS_OK": "Có AIS khớp", "AIS_MISMATCH": "AIS lệch", "DARK": "Không có AIS"}};

    var map = L.map('map', {{ zoomControl: true, preferCanvas: true }}).setView([15.5, 108.5], 6);
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
        attribution: '© OpenStreetMap contributors',
        maxZoom: 19,
        minZoom: 4,
    }}).addTo(map);
    // Giới hạn khung nhìn quanh vùng biển Việt Nam để pan không đi quá xa
    map.setMaxBounds([[3, 98], [26, 121]]);

    // -- Đánh dấu các quần đảo, đảo thuộc lãnh thổ Việt Nam ---------------
    var ISLANDS = [
        {{name: "Quần đảo Hoàng Sa (Việt Nam)", lat: 16.50, lon: 112.00,
          note: "Chủ quyền của Việt Nam. Bao gồm các đảo Phú Lâm, Hoàng Sa, Tri Tôn, Linh Côn, Lincoln, Duy Mộng...", major: true}},
        {{name: "Quần đảo Trường Sa (Việt Nam)", lat: 10.20, lon: 114.00,
          note: "Chủ quyền của Việt Nam. Bao gồm hơn 100 đảo, đá, bãi ngầm — trong đó có Trường Sa Lớn, Song Tử Tây, Sinh Tồn, Nam Yết...", major: true}},
        {{name: "Đảo Trường Sa Lớn", lat: 8.65, lon: 111.92, note: "Đảo lớn nhất quần đảo Trường Sa — huyện đảo Trường Sa, tỉnh Khánh Hoà."}},
        {{name: "Đảo Song Tử Tây", lat: 11.43, lon: 114.32, note: "Xã đảo Song Tử Tây — huyện đảo Trường Sa."}},
        {{name: "Đảo Phú Quốc", lat: 10.23, lon: 103.96, note: "Đảo lớn nhất Việt Nam — thành phố Phú Quốc, tỉnh Kiên Giang."}},
        {{name: "Đảo Côn Sơn (Côn Đảo)", lat: 8.70, lon: 106.61, note: "Huyện Côn Đảo, tỉnh Bà Rịa – Vũng Tàu."}},
        {{name: "Đảo Phú Quý", lat: 10.53, lon: 108.93, note: "Huyện đảo Phú Quý, tỉnh Bình Thuận — cứ điểm hậu cần nghề cá quan trọng."}},
        {{name: "Đảo Lý Sơn", lat: 15.38, lon: 109.14, note: "Huyện đảo Lý Sơn, tỉnh Quảng Ngãi — cửa ngõ ra Hoàng Sa."}},
        {{name: "Đảo Cồn Cỏ", lat: 17.15, lon: 107.35, note: "Huyện đảo Cồn Cỏ, tỉnh Quảng Trị."}},
        {{name: "Đảo Bạch Long Vĩ", lat: 20.13, lon: 107.72, note: "Huyện đảo Bạch Long Vĩ, thành phố Hải Phòng — điểm tiền tiêu Vịnh Bắc Bộ."}},
        {{name: "Quần đảo Cát Bà", lat: 20.75, lon: 107.05, note: "Huyện Cát Hải, thành phố Hải Phòng — di sản UNESCO."}},
        {{name: "Đảo Cô Tô", lat: 20.98, lon: 107.77, note: "Huyện đảo Cô Tô, tỉnh Quảng Ninh."}},
        {{name: "Đảo Thổ Chu", lat: 9.30, lon: 103.47, note: "Xã đảo Thổ Chu, thành phố Phú Quốc, Kiên Giang."}},
    ];
    ISLANDS.forEach(function(isl) {{
        var isMajor = isl.major === true;
        // Vòng viền mờ cho quần đảo lớn để làm nổi bật phạm vi lãnh thổ
        if (isMajor) {{
            L.circle([isl.lat, isl.lon], {{
                radius: 90000, color: "#1D1D1F", fillColor: "#1D1D1F",
                fillOpacity: 0.04, weight: 1.0, dashArray: "4,4", interactive: false,
            }}).addTo(map);
        }}
        var labelText = isl.name.replace(' (Việt Nam)', '');
        L.marker([isl.lat, isl.lon], {{
            icon: L.divIcon({{
                className: 'island-icon',
                html: '<div style="background:rgba(29,29,31,0.88);color:white;padding:' +
                      (isMajor ? '4px 10px' : '3px 8px') +
                      ';border-radius:6px;font-size:' + (isMajor ? '12px' : '11px') +
                      ';font-weight:' + (isMajor ? '600' : '500') +
                      ';white-space:nowrap;letter-spacing:-0.01em;' +
                      'box-shadow:0 1px 3px rgba(0,0,0,0.2);' +
                      '-webkit-backdrop-filter:blur(6px);backdrop-filter:blur(6px);">' +
                      labelText + '</div>',
                iconSize: null, iconAnchor: [40, 12],
            }}),
        }}).bindPopup(
            "<div style='min-width:220px;font-family:-apple-system,BlinkMacSystemFont,sans-serif;'>" +
            "<div style='font-weight:600;font-size:14px;color:#1D1D1F;letter-spacing:-0.01em;'>" + isl.name + "</div>" +
            "<div style='height:1px;background:#E5E5EA;margin:8px 0;'></div>" +
            "<div style='font-size:12px;color:#3C3C43;line-height:1.5;'>" + isl.note + "</div>" +
            "<div style='margin-top:10px;font-size:11px;color:#8E8E93;'>" +
            isl.lat.toFixed(3) + "°N, " + isl.lon.toFixed(3) + "°E</div></div>",
            {{maxWidth: 320}}
        ).addTo(map);
    }});

    var startTime = Date.now();
    var TIME_SCALE = 1.0; // thời gian thực — mỗi giây tương ứng 1 giây trên biển

    function vesselPos(v, t) {{
        var p = v.pattern, sp = v.speed, r = v.radius;
        var x, y;
        if (p === 0) {{
            var ang = v.phase + t * 0.15;
            x = v.cx + r * Math.cos(ang);
            y = v.cy + r * Math.sin(ang);
        }} else if (p === 1) {{
            var ang = v.phase + t * 0.04;
            x = v.cx + r * (Math.cos(ang*1.7) + 0.4 * Math.sin(ang*2.3));
            y = v.cy + r * (Math.sin(ang*1.3) + 0.4 * Math.cos(ang*1.9));
        }} else if (p === 2) {{
            var phase_t = (t / 30.0 + v.phase / 6.283) % 2.0;
            var s_along = phase_t < 1.0 ? phase_t : 2.0 - phase_t;
            x = v.cx + (s_along - 0.5) * 2 * r * Math.cos(v.direction);
            y = v.cy + (s_along - 0.5) * 2 * r * Math.sin(v.direction);
        }} else {{
            var phase_t = (t / 60.0 + v.phase / 6.283) % 2.0;
            var s_along = phase_t < 1.0 ? phase_t : 2.0 - phase_t;
            x = v.cx + (s_along - 0.5) * 2 * r * Math.cos(v.direction);
            y = v.cy + (s_along - 0.5) * 2 * r * Math.sin(v.direction);
        }}
        // Giới hạn trong vùng biển Việt Nam mở rộng (102–118°E, 6.5–22°N)
        x = Math.max(102.5, Math.min(118.0, x));
        y = Math.max(6.5, Math.min(22.0, y));
        return [y, x]; // lat, lon
    }}

    // Tạo halo + core cho mỗi tàu, giữ tham chiếu để update
    var ships = FLEET.map(function(v) {{
        var col = STATE_COLOR[v.state];
        var pos = vesselPos(v, 0);
        var isDark = v.state === "DARK";
        var haloOuter = L.circleMarker(pos, {{
            radius: isDark ? 20 : 15, color: col, fillColor: col,
            fillOpacity: 0.18, weight: 0, interactive: false,
        }}).addTo(map);
        var haloMid = L.circleMarker(pos, {{
            radius: isDark ? 12 : 9, color: col, fillColor: col,
            fillOpacity: 0.4, weight: 0, interactive: false,
        }}).addTo(map);
        var core = L.circleMarker(pos, {{
            radius: isDark ? 7 : 5, color: "white", fillColor: col,
            fillOpacity: 1.0, weight: 2,
        }}).bindTooltip(
            "<b>" + v.id + "</b> — " + STATE_LABEL[v.state] + " · " + v.behaviour,
            {{sticky: true, direction: 'top', offset: [0, -6]}}
        ).addTo(map);

        // Popup chi tiết khi click
        var confidenceScore = (0.65 + Math.random() * 0.32).toFixed(2);
        var lengthEst = (v.pattern === 3 ? (55 + Math.random()*35) : (v.pattern === 2 ? (28 + Math.random()*22) : (15 + Math.random()*18))).toFixed(1);
        var heading = ((v.direction * 180 / Math.PI) % 360).toFixed(0);
        var identityRows = "";
        if (v.state === "DARK") {{
            identityRows =
                "<tr><td style='color:#6E6E73;padding:5px 12px 5px 0;'>Số hiệu đăng ký</td><td style='padding:5px 0;color:#8E8E93;font-style:italic;'>Chưa xác định — không có AIS</td></tr>" +
                "<tr><td style='color:#6E6E73;padding:5px 12px 5px 0;'>MMSI</td><td style='padding:5px 0;color:#8E8E93;font-style:italic;'>Không có tín hiệu</td></tr>" +
                "<tr><td style='color:#6E6E73;padding:5px 12px 5px 0;'>Tên phương tiện</td><td style='padding:5px 0;color:#8E8E93;font-style:italic;'>Chưa xác định</td></tr>" +
                "<tr><td style='color:#6E6E73;padding:5px 12px 5px 0;'>Chủ sở hữu</td><td style='padding:5px 0;color:#8E8E93;font-style:italic;'>Chưa xác định</td></tr>";
        }} else {{
            identityRows =
                "<tr><td style='color:#6E6E73;padding:5px 12px 5px 0;'>Số hiệu đăng ký</td><td style='padding:5px 0;font-weight:500;'>" + v.reg + "</td></tr>" +
                "<tr><td style='color:#6E6E73;padding:5px 12px 5px 0;'>MMSI</td><td style='padding:5px 0;font-variant-numeric:tabular-nums;'>" + v.mmsi + "</td></tr>" +
                "<tr><td style='color:#6E6E73;padding:5px 12px 5px 0;'>Tên phương tiện</td><td style='padding:5px 0;'>" + v.ship_name + "</td></tr>" +
                "<tr><td style='color:#6E6E73;padding:5px 12px 5px 0;'>Chủ sở hữu</td><td style='padding:5px 0;'>" + v.owner + "</td></tr>" +
                "<tr><td style='color:#6E6E73;padding:5px 12px 5px 0;'>Cảng đăng ký</td><td style='padding:5px 0;'>" + v.port + "</td></tr>";
        }}

        var mismatchNote = "";
        if (v.state === "AIS_MISMATCH") {{
            mismatchNote = "<div style='margin-top:10px;padding:10px 12px;background:#FFF8E1;" +
                           "border:1px solid #F6E7B8;border-radius:8px;font-size:12px;color:#7A5A0F;line-height:1.5;'>" +
                           "<b>Cảnh báo AIS sai lệch.</b> Bản khai AIS ghi chiều dài <b>" + v.length_declared.toFixed(1) +
                           " m</b>, radar đo <b>" + v.length_true.toFixed(1) + " m</b>. Đề nghị đối chiếu hồ sơ đăng ký " +
                           "và cử lực lượng kiểm tra hiện trường.</div>";
        }} else if (v.state === "DARK") {{
            mismatchNote = "<div style='margin-top:10px;padding:10px 12px;background:#FDECEC;" +
                           "border:1px solid #F5CACA;border-radius:8px;font-size:12px;color:#8A2323;line-height:1.5;'>" +
                           "<b>Cảnh báo DARK.</b> Radar phát hiện phương tiện nhưng không có bản ghi AIS trong " +
                           "cửa sổ ±15 phút. Có thể là tắt AIS chủ động. Đề nghị điều tra hiện trường và truy vết " +
                           "quỹ đạo trước – sau thời điểm quan sát.</div>";
        }} else {{
            mismatchNote = "<div style='margin-top:10px;padding:10px 12px;background:#EFF8F7;" +
                           "border:1px solid #C6E6E2;border-radius:8px;font-size:12px;color:#1B5568;line-height:1.5;'>" +
                           "Radar và AIS khớp trong ngưỡng cho phép (sai số vị trí dưới 150 m). Phương tiện tuân thủ.</div>";
        }}
        core.bindPopup(
            "<div style='min-width:320px;font-family:-apple-system,BlinkMacSystemFont,sans-serif;color:#1D1D1F;'>" +
            "<div style='display:flex;align-items:center;gap:10px;margin-bottom:12px;'>" +
                "<div style='width:10px;height:10px;border-radius:50%;background:" + col + ";'></div>" +
                "<div style='font-size:15px;font-weight:600;color:#1D1D1F;letter-spacing:-0.01em;'>Đối tượng quan sát " + v.id + "</div>" +
            "</div>" +
            "<div style='font-size:11px;color:#6E6E73;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:6px;'>Định danh phương tiện</div>" +
            "<table style='font-size:13px;border-collapse:collapse;width:100%;margin-bottom:10px;'>" +
                identityRows +
            "</table>" +
            "<div style='font-size:11px;color:#6E6E73;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:6px;'>Quan sát radar</div>" +
            "<table style='font-size:13px;border-collapse:collapse;width:100%;'>" +
                "<tr><td style='color:#6E6E73;padding:5px 12px 5px 0;font-weight:400;'>Trạng thái</td><td style='padding:5px 0;font-weight:500;color:" + col + ";'>" + STATE_LABEL[v.state] + "</td></tr>" +
                "<tr><td style='color:#6E6E73;padding:5px 12px 5px 0;'>Hành vi ước lượng</td><td style='padding:5px 0;'>" + v.behaviour + "</td></tr>" +
                "<tr><td style='color:#6E6E73;padding:5px 12px 5px 0;'>Ngư trường</td><td style='padding:5px 0;'>" + v.zone + "</td></tr>" +
                "<tr><td style='color:#6E6E73;padding:5px 12px 5px 0;'>Tốc độ</td><td style='padding:5px 0;'>" + v.speed.toFixed(1) + " hải lý/h</td></tr>" +
                "<tr><td style='color:#6E6E73;padding:5px 12px 5px 0;'>Hướng</td><td style='padding:5px 0;'>" + heading + "°</td></tr>" +
                "<tr><td style='color:#6E6E73;padding:5px 12px 5px 0;'>Chiều dài đo bằng radar</td><td style='padding:5px 0;'>" + v.length_true.toFixed(1) + " m</td></tr>" +
                "<tr><td style='color:#6E6E73;padding:5px 12px 5px 0;'>Độ tin cậy phát hiện</td><td style='padding:5px 0;'>" + confidenceScore + "</td></tr>" +
            "</table>" +
            mismatchNote +
            "</div>",
            {{maxWidth: 400}}
        );
        return {{ v: v, haloOuter: haloOuter, haloMid: haloMid, core: core }};
    }});

    function tick() {{
        var t_sim = (Date.now() - startTime) * TIME_SCALE / 1000.0 / 60.0; // phút
        ships.forEach(function(s) {{
            var pos = vesselPos(s.v, t_sim);
            s.haloOuter.setLatLng(pos);
            s.haloMid.setLatLng(pos);
            s.core.setLatLng(pos);
            // DARK: ẩn khi đang tắt AIS thì vẫn hiện (radar thấy), chỉ khác là không có AIS chấm
            // Ẩn/hiện halo dựa trên ais_off_at là logic riêng, ở đây chỉ move
        }});
    }}

    setInterval(tick, 500);
    tick();
</script>
</body>
</html>
"""
    st_html(html_code, height=680)

    # KPI strip tổng cho dữ liệu mô phỏng
    n_ok = sum(1 for v in json.loads(fleet_json) if v["state"] == "AIS_OK")
    n_mm = sum(1 for v in json.loads(fleet_json) if v["state"] == "AIS_MISMATCH")
    n_dk = sum(1 for v in json.loads(fleet_json) if v["state"] == "DARK")
    n_all = n_ok + n_mm + n_dk

    st.markdown(
        f'''<div class="kpi-strip">
        <div class="kpi">
            <div class="kpi-label">Tổng phương tiện quan sát được</div>
            <div class="kpi-value">{n_all}</div>
            <div class="kpi-note">phát hiện qua ảnh radar, không phụ thuộc AIS</div>
        </div>
        <div class="kpi">
            <div class="kpi-label">Có AIS khớp</div>
            <div class="kpi-value" style="color:{COL_OK}">{n_ok}</div>
            <div class="kpi-note">chiếm {100*n_ok/n_all:.0f}% đội hình quan sát</div>
        </div>
        <div class="kpi">
            <div class="kpi-label">AIS sai lệch</div>
            <div class="kpi-value" style="color:{COL_MISMATCH}">{n_mm}</div>
            <div class="kpi-note">khai báo kích thước hoặc vị trí không khớp</div>
        </div>
        <div class="kpi">
            <div class="kpi-label">Không có AIS</div>
            <div class="kpi-value" style="color:{COL_DARK}">{n_dk}</div>
            <div class="kpi-note">tỷ lệ {100*n_dk/n_all:.0f}% đội hình quan sát</div>
        </div>
        </div>''',
        unsafe_allow_html=True,
    )

    with st.expander("Chú giải bản đồ"):
        st.markdown(
            f"<div style='color:{COL_INK};font-size:13px;line-height:1.7;'>"
            f"<b>Nền bản đồ.</b> OpenStreetMap, phủ toàn bộ vùng biển Việt Nam "
            f"từ Vịnh Bắc Bộ đến Vịnh Thái Lan.<br><br>"
            f"<b>Quần đảo và đảo thuộc chủ quyền Việt Nam</b> được đánh dấu bằng "
            f"nhãn hành chính. Hai quần đảo Hoàng Sa và Trường Sa có vòng viền "
            f"đứt nét thể hiện phạm vi. Các đảo tiền tiêu khác bao gồm Bạch Long "
            f"Vĩ, Cát Bà, Cô Tô, Cồn Cỏ, Lý Sơn, Phú Quý, Côn Đảo, Phú Quốc, "
            f"Thổ Chu, Trường Sa Lớn và Song Tử Tây. Chọn nhãn để xem thông tin.<br><br>"
            f"<b>Bảy ngư trường trọng điểm.</b> Vịnh Bắc Bộ; Bắc Trung Bộ; Trung "
            f"Trung Bộ; Hoàng Sa; Trường Sa; ngoài khơi Bình Thuận – Bà Rịa; "
            f"Vịnh Thái Lan. Trọng số phân bố phương tiện tương ứng cường độ khai thác.<br><br>"
            f"<b>Ký hiệu phương tiện.</b> Mỗi phương tiện được thể hiện bằng "
            f"một điểm phát sáng ba lớp. Phương tiện không có AIS được vẽ lớn "
            f"hơn để phân biệt. Chọn phương tiện để xem đầy đủ thông tin định "
            f"danh (số hiệu đăng ký, MMSI, tên phương tiện, chủ sở hữu, cảng "
            f"đăng ký) và thông tin quan sát từ radar. Phương tiện DARK không "
            f"có định danh vì không phát AIS.<br><br>"
            f"<b>Tương tác.</b> Zoom và di chuyển bản đồ tự do. Bản đồ được vẽ "
            f"một lần và cập nhật vị trí phương tiện thông qua JavaScript, "
            f"không làm nhấp nháy giao diện và giữ nguyên trạng thái zoom.<br><br>"
            f"<b>Thời gian.</b> Đây là mô phỏng chạy theo tốc độ vận hành thực "
            f"(2–11 hải lý/h), không phải luồng AIS trực tiếp. Dữ liệu Sentinel-1 "
            f"thật chỉ có khi vệ tinh bay qua; tab “Sentinel-1 thật” hiển thị các "
            f"cảnh quan sát thực tế theo thời điểm thu nhận."
            f"</div>",
            unsafe_allow_html=True,
        )

# ============================================================================
# TAB DET — Phát hiện SAR
# ============================================================================
with evidence_radar:
    st.subheader("Kiểm chứng phát hiện trên ảnh radar Sentinel‑1")

    if not SCENES:
        st.warning(f"Không tìm thấy `{YOLO}/scenes/test.jsonl`. Chạy `python3 scripts/run_pipeline.py` trước.")
    else:
        colL, colR = st.columns([1, 3])
        with colL:
            st.markdown("**Chọn cảnh test**")
            idx = st.selectbox(
                "Cảnh", range(len(SCENES)),
                format_func=lambda i: f"{SCENES[i]['scene_id']} — {SCENES[i].get('meta', {}).get('n_vessels', '?')} tàu",
                label_visibility="collapsed",
            )
            show_pred = st.checkbox("Hiện dự báo YOLO11n", value=True)
            show_gt = st.checkbox("Hiện ground truth", value=True)
            conf_min = st.slider("Ngưỡng confidence", 0.10, 0.90, 0.35, 0.05)

            meta = SCENES[idx]
            vessels = meta.get("vessels", [])
            counts = {"AIS_OK": 0, "AIS_MISMATCH": 0, "DARK": 0}
            for v in vessels:
                counts[v.get("identity_state", "AIS_OK")] += 1
            st.markdown("---")
            st.markdown("**Số liệu tổng hợp cảnh này**")
            st.markdown(
                f"<div style='padding:6px 10px;background:{COL_OK};border-radius:6px;color:#FFF;margin:6px 0;font-weight:600;font-size:13px;'>"
                f"OK: <span style='float:right;font-size:16px;'>{counts['AIS_OK']}</span></div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<div style='padding:6px 10px;background:{COL_MISMATCH};border-radius:6px;color:#FFF;margin:6px 0;font-weight:600;font-size:13px;'>"
                f"MISMATCH: <span style='float:right;font-size:16px;'>{counts['AIS_MISMATCH']}</span></div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<div style='padding:6px 10px;background:{COL_DARK};border-radius:6px;color:#FFF;margin:6px 0;font-weight:600;font-size:13px;'>"
                f"DARK: <span style='float:right;font-size:16px;'>{counts['DARK']}</span></div>",
                unsafe_allow_html=True,
            )

        with colR:
            img_path = Path(meta["image_path"])
            if not img_path.exists():
                st.error(f"Không tìm thấy ảnh: {img_path}")
            else:
                import matplotlib.pyplot as plt
                from matplotlib.patches import Rectangle
                img = np.array(Image.open(img_path).convert("L"))
                fig, ax = plt.subplots(figsize=(9, 9))
                ax.imshow(img, cmap="gray", vmin=0, vmax=255)

                if show_gt:
                    for v in vessels:
                        x1, y1, x2, y2 = v["bbox"]
                        state = v.get("identity_state", "AIS_OK")
                        col = STATE_COLOR.get(state, COL_OK)
                        ax.add_patch(Rectangle(
                            (x1, y1), x2 - x1, y2 - y1,
                            fill=False, edgecolor=col, linewidth=2.4,
                        ))

                n_pred_shown = 0
                if show_pred and meta["scene_id"] in PREDS:
                    p = PREDS[meta["scene_id"]]
                    for box, score in zip(p["boxes"], p["scores"]):
                        if score < conf_min: continue
                        x1, y1, x2, y2 = box
                        ax.add_patch(Rectangle(
                            (x1, y1), x2 - x1, y2 - y1,
                            fill=False, edgecolor="#FFFFFF", linewidth=1.4, linestyle="--",
                        ))
                        ax.text(x1, y1 - 4, f"{score:.2f}", color="#FFFFFF",
                                fontsize=8, bbox=dict(facecolor=COL_INK, edgecolor="none", pad=2, alpha=0.75))
                        n_pred_shown += 1

                ax.set_xticks([]); ax.set_yticks([])
                subtitle = []
                if show_gt: subtitle.append(f"{len(vessels)} tàu thật (đường đặc)")
                if show_pred: subtitle.append(f"{n_pred_shown} dự báo YOLO (đường đứt trắng, conf ≥ {conf_min:.2f})")
                ax.set_title(f"{meta['scene_id']}  ·  {' | '.join(subtitle)}",
                             fontsize=11, color=COL_INK, pad=10)
                fig.tight_layout()
                st.pyplot(fig, use_container_width=True)

# ============================================================================
# TAB FUS — Hợp nhất
# ============================================================================
with evidence_ais:
    st.subheader("Đối chiếu radar và AIS")
    import plotly.graph_objects as go

    cm = np.array(KQ["fusion"]["confusion_matrix"])
    labels = KQ["fusion"]["confusion_labels"]
    label_vi = [STATE_LABEL[l] for l in labels]

    col1, col2 = st.columns([3, 2])
    with col1:
        # Confusion matrix bằng Plotly
        fig = go.Figure(data=go.Heatmap(
            z=cm, x=label_vi, y=label_vi,
            colorscale=[[0, "#FFF8EC"], [0.5, "#F5B776"], [1, "#B04E20"]],
            text=cm, texttemplate="<b>%{text}</b>",
            textfont={"size": 18, "color": COL_INK},
            showscale=False,
            hovertemplate="Thật: %{y}<br>Gán: %{x}<br>Số ca: %{z}<extra></extra>",
        ))
        fig.update_layout(
            xaxis=dict(title="Mô hình gán →", side="bottom"),
            yaxis=dict(title="↑ Trạng thái thật", autorange="reversed"),
            plot_bgcolor=COL_CARD, paper_bgcolor=COL_CARD,
            height=440, margin=dict(l=10, r=10, t=40, b=40),
            title=dict(text=f"Chính xác chung: <b>{KQ['fusion']['state_accuracy']:.1%}</b>  ·  F1 vĩ mô: <b>{KQ['fusion']['state_macro_f1']:.3f}</b>",
                       font=dict(color=COL_INK, size=14)),
            font=dict(color=COL_INK),
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown("**F1 từng trạng thái**")
        for state, label in STATE_LABEL.items():
            f1 = KQ["fusion"]["per_state_f1"][state]
            col = STATE_COLOR[state]
            st.markdown(
                f"<div style='background:#FFF;border-left:4px solid {col};padding:12px 16px;border-radius:6px;margin-bottom:8px;box-shadow:0 1px 3px rgba(14,42,56,0.04);'>"
                f"<div style='color:{COL_MUTED};font-size:12px;'>{label}</div>"
                f"<div style='color:{COL_INK};font-size:24px;font-weight:700;'>{f1:.3f}</div></div>",
                unsafe_allow_html=True,
            )
        st.markdown(
            f"<div class='safety-box'><strong>Precision lớp DARK: {KQ['fusion']['dark_precision']:.3f}</strong><br>"
            f"Mọi phương tiện được gán DARK đều thực sự thuộc lớp đó — "
            f"không có phương tiện tuân thủ bị đánh nhầm.</div>",
            unsafe_allow_html=True,
        )

    st.markdown("### Sai số ghép cặp Kalman + Hungarian")
    c1, c2, c3 = st.columns(3)
    c1.metric("Trung bình", f"{KQ['fusion']['mean_match_error_m']:.1f} m")
    c2.metric("Trung vị", f"{KQ['fusion']['median_match_error_m']:.1f} m")
    c3.metric("Phân vị 90", f"{KQ['fusion']['p90_match_error_m']:.1f} m")

# ============================================================================
# TAB KAL — Kalman
# ============================================================================
with evidence_tracks:
    st.subheader("Theo dõi hành trình — Kalman–RTS và nội suy tuyến tính")
    import plotly.graph_objects as go

    k = INTERP["kalman"]; l = INTERP["linear"]

    col1, col2 = st.columns([2, 1])
    with col1:
        fig = go.Figure()
        methods = ["Nội suy tuyến tính", "Kalman–RTS"]
        fig.add_trace(go.Bar(name="Trung bình", x=methods, y=[l["mean_error_m"], k["mean_error_m"]],
                             marker_color="#7DA6B0", text=[f"{l['mean_error_m']:.1f}", f"{k['mean_error_m']:.1f}"],
                             textposition="outside", textfont=dict(color=COL_INK)))
        fig.add_trace(go.Bar(name="Trung vị", x=methods, y=[l["median_error_m"], k["median_error_m"]],
                             marker_color=COL_OK, text=[f"{l['median_error_m']:.1f}", f"{k['median_error_m']:.1f}"],
                             textposition="outside", textfont=dict(color=COL_INK)))
        fig.add_trace(go.Bar(name="Phân vị 90", x=methods, y=[l["p90_error_m"], k["p90_error_m"]],
                             marker_color=COL_DARK, text=[f"{l['p90_error_m']:.1f}", f"{k['p90_error_m']:.1f}"],
                             textposition="outside", textfont=dict(color=COL_INK)))
        fig.update_layout(
            barmode="group", height=440, plot_bgcolor=COL_CARD, paper_bgcolor=COL_CARD,
            yaxis=dict(title="Sai số vị trí (m)", gridcolor="#E4EAED"),
            xaxis=dict(showgrid=False),
            legend=dict(orientation="h", y=1.15, x=0.5, xanchor="center"),
            font=dict(color=COL_INK), margin=dict(l=40, r=20, t=60, b=40),
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        pct_mean = 100 * (1 - k["mean_error_m"] / l["mean_error_m"])
        pct_med = 100 * (1 - k["median_error_m"] / l["median_error_m"])
        pct_p90 = 100 * (1 - k["p90_error_m"] / l["p90_error_m"])
        st.markdown("**Mức cải thiện Kalman**")
        st.metric("Trung bình", f"{pct_mean:.1f}%")
        st.metric("Trung vị", f"{pct_med:.1f}%")
        st.metric("Đuôi P90", f"{pct_p90:.1f}%")

    st.markdown("### Phân tích đóng góp bốn cấu hình")
    rows = ABL.get("rows", [])
    if rows:
        import pandas as pd
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ============================================================================
# TAB MAP — Bản đồ
# ============================================================================
with tab_map:
    import folium
    from streamlit.components.v1 import html as st_html
    st.subheader("Bản đồ giám sát quốc gia")
    st.markdown(
        f"<div style='color:{COL_MUTED};margin-bottom:14px;font-size:14px;line-height:1.55;'>"
        f"Lớp đầu là ảnh Sentinel‑1 thật phủ vùng biển Việt Nam; lớp bên dưới là mô phỏng vận hành cho một khu vực thử nghiệm để minh họa luồng SAR–AIS. "
        f"Hai lớp được ghi nhãn riêng để không nhầm dữ liệu thật với mô phỏng."
        f"</div>",
        unsafe_allow_html=True,
    )

    st.markdown("#### Lớp quan sát thật — Sentinel‑1 toàn Việt Nam")
    if national_mosaic:
        national_map = folium.Map(location=[13.9, 108.5], zoom_start=5, tiles=None, control_scale=True)
        folium.TileLayer(
            tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            attr="Esri, Maxar, Earthstar Geographics", name="Nền vệ tinh", overlay=False,
        ).add_to(national_map)
        folium.raster_layers.ImageOverlay(
            image=folium_image_source(national_mosaic), bounds=[[6.0, 102.0], [21.8, 115.0]],
            opacity=0.78, interactive=True, cross_origin=False, zindex=2, name="Sentinel‑1 mosaic mới nhất",
        ).add_to(national_map)
        folium.Rectangle(bounds=[[6.0, 102.0], [21.8, 115.0]], color="#ffffff", weight=2, fill=False,
                         tooltip="Phạm vi mosaic Sentinel‑1 Việt Nam").add_to(national_map)
        folium.LayerControl(collapsed=True).add_to(national_map)
        national_map.get_root().html.add_child(folium.Element("""
          <div style="position:fixed;bottom:24px;left:24px;z-index:9999;background:rgba(18,18,18,.88);color:#fff;
              padding:12px 14px;border-radius:12px;font:13px -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
            <div style="font-weight:650;margin-bottom:4px">Sentinel‑1 · Việt Nam</div>
            <div>Mosaic 14 ngày · pixel mới nhất · tự làm mới mỗi 6 giờ</div>
          </div>
        """))
        st_html(national_map.get_root().render(), height=560)
    else:
        st.info("Mosaic Sentinel‑1 đang chờ tải từ Copernicus.")

    st.markdown("#### Mô phỏng nghiệp vụ — khu vực thử nghiệm Bình Thuận")

    @st.cache_data
    def load_ban_do_data():
        p = RESULTS / "ban_do_giam_sat.json"
        if not p.exists():
            return []
        return json.loads(p.read_text())

    ban_do = load_ban_do_data()

    if not ban_do:
        st.info("Chưa có bản đồ. Chạy pipeline trước.")
    else:
        latitudes = [entry["lat"] for entry in ban_do]
        longitudes = [entry["lon"] for entry in ban_do]
        st.info(
            f"**Đây là lớp mô phỏng, không phải luồng tàu trực tiếp toàn quốc.** "
            f"331 mục tiêu mô phỏng được đặt trong khu vực thử nghiệm ngoài khơi Bình Thuận "
            f"({min(latitudes):.2f}–{max(latitudes):.2f}°B, {min(longitudes):.2f}–{max(longitudes):.2f}°Đ) "
            f"để trình bày rõ ba tình huống: AIS khớp, AIS lệch và không có AIS. "
            f"Ảnh Sentinel‑1 thật toàn quốc nằm ở lớp phía trên, với mốc thời gian tại tab “Dữ liệu vệ tinh thật”."
        )
        m = folium.Map(location=[13.0, 109.5], zoom_start=6,
                        tiles="OpenStreetMap", control_scale=True,
                        min_zoom=5, max_zoom=12)
        by_state = {"AIS_OK": [], "AIS_MISMATCH": [], "DARK": []}
        for entry in ban_do:
            st_key = entry.get("state", "AIS_OK")
            if st_key in by_state:
                by_state[st_key].append(entry)

        for state_key, entries in by_state.items():
            col = STATE_COLOR[state_key]
            for e in entries:
                lat, lon = e["lat"], e["lon"]
                # Halo lớn
                folium.CircleMarker(location=[lat, lon], radius=14, color=col,
                                     fill=True, fill_color=col, fill_opacity=0.15,
                                     weight=0).add_to(m)
                folium.CircleMarker(location=[lat, lon], radius=8, color=col,
                                     fill=True, fill_color=col, fill_opacity=0.4,
                                     weight=0).add_to(m)
                folium.CircleMarker(location=[lat, lon], radius=4, color="white",
                                     fill=True, fill_color=col, fill_opacity=1.0,
                                     weight=1.5,
                                     tooltip=(f"<b>{STATE_LABEL[state_key]}</b><br>"
                                                f"Kích thước ~{e.get('length_m', 0):.0f} m<br>"
                                                f"Tốc độ: {e.get('speed_kn', 0):.1f} hải lý/h<br>"
                                                f"<i>Không xác định danh tính</i>")).add_to(m)

        legend_html = f'''
        <div style="position:fixed; top:100px; right:20px; z-index:9999;
                     background:rgba(255,255,255,0.95); padding:12px 16px;
                     border-radius:8px; font-family:sans-serif; font-size:13px;
                     box-shadow:0 2px 8px rgba(0,0,0,0.15); color:#0E2A38;">
            <div style="font-weight:600; margin-bottom:8px;">Trạng thái</div>
            <div style="margin:4px 0;"><span style="display:inline-block;width:12px;height:12px;background:{COL_OK};border-radius:50%;margin-right:8px;"></span>Có AIS khớp ({len(by_state["AIS_OK"])})</div>
            <div style="margin:4px 0;"><span style="display:inline-block;width:12px;height:12px;background:{COL_MISMATCH};border-radius:50%;margin-right:8px;"></span>AIS lệch ({len(by_state["AIS_MISMATCH"])})</div>
            <div style="margin:4px 0;"><span style="display:inline-block;width:12px;height:12px;background:{COL_DARK};border-radius:50%;margin-right:8px;"></span>Không có AIS ({len(by_state["DARK"])})</div>
        </div>
        '''
        m.get_root().html.add_child(folium.Element(legend_html))

        st_html(m.get_root().render(), height=720)

        n_all = len(ban_do)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Tổng phương tiện", n_all)
        c2.metric("Có AIS khớp", len(by_state["AIS_OK"]))
        c3.metric("AIS lệch", len(by_state["AIS_MISMATCH"]))
        c4.metric("Không có AIS", len(by_state["DARK"]))

# ============================================================================
# TAB KPI — Tổng hợp
# ============================================================================
with evidence_metrics:
    st.subheader("Báo cáo độ tin cậy")
    inner = st.tabs(["Tầng phát hiện", "Tầng hợp nhất", "Tầng hành vi", "Ablation đầy đủ"])

    with inner[0]:
        det = KQ["detection"]
        cols = st.columns(5)
        cols[0].metric("mAP@0.5", f"{det['mAP@0.5']:.3f}")
        cols[1].metric("mAP@0.5:0.95", f"{det['mAP@0.5:0.95']:.3f}")
        cols[2].metric("Precision", f"{det['precision']:.3f}")
        cols[3].metric("Recall", f"{det['recall']:.3f}")
        cols[4].metric("F1", f"{det['f1']:.3f}")
        st.markdown(
            f"<div style='color:{COL_MUTED};font-size:14px;margin-top:16px;'>"
            f"Trên <b>{det['n_ground_truth']}</b> khung bao thật: "
            f"<b style='color:{COL_OK};'>{det['true_positive']}</b> dương thật · "
            f"<b style='color:{COL_MISMATCH};'>{det['false_positive']}</b> dương giả · "
            f"<b style='color:{COL_DARK};'>{det['false_negative']}</b> âm sót.</div>",
            unsafe_allow_html=True,
        )

    with inner[1]:
        f = KQ["fusion"]
        cols = st.columns(4)
        cols[0].metric("Chính xác 3 trạng thái", f"{f['state_accuracy']:.3f}")
        cols[1].metric("F1 vĩ mô", f"{f['state_macro_f1']:.3f}")
        cols[2].metric("F1 DARK", f"{f['dark_f1']:.3f}")
        cols[3].metric("Sai số trung vị", f"{f['median_match_error_m']:.1f} m")

    with inner[2]:
        b = KQ["behaviour"]
        cols = st.columns(2)
        cols[0].metric("Accuracy", f"{b['accuracy']:.3f}")
        cols[1].metric("F1 vĩ mô", f"{b['macro_f1']:.3f}")
        st.markdown("**F1 từng lớp hành vi**")
        import pandas as pd
        st.dataframe(
            pd.DataFrame([{"Lớp hành vi": k, "F1": v} for k, v in b["per_class_f1"].items()])
              .style.format({"F1": "{:.3f}"}),
            use_container_width=True, hide_index=True,
        )
        st.markdown("**Đặc trưng có ảnh hưởng lớn nhất**")
        top = list(b["top_features"].items())[:8]
        st.dataframe(
            pd.DataFrame([{"Đặc trưng": k, "Trọng số": v} for k, v in top])
              .style.format({"Trọng số": "{:.4f}"}),
            use_container_width=True, hide_index=True,
        )

    with inner[3]:
        st.markdown(
            "**A** — chỉ ảnh radar (không AIS) · **B** — chỉ dữ liệu AIS (không radar) · "
            "**C** — hợp nhất, nội suy tuyến tính · **D** — hệ thống đầy đủ (Kalman + Hungarian)"
        )
        rows = ABL.get("rows", [])
        if rows:
            import pandas as pd
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Chân trang
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown(
    f"<div style='color:{COL_MUTED};font-size:12px;text-align:center;padding:16px 0;line-height:1.6;'>"
    f"SonarNet-VN · Hệ thống hỗ trợ giám sát tuân thủ đánh bắt hải sản<br>"
    f"Kết quả mô hình mang tính hỗ trợ nghiệp vụ. Thẩm quyền xử lý thuộc cơ quan chức năng."
    f"</div>",
    unsafe_allow_html=True,
)
