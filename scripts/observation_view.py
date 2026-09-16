"""A single observation workspace backed only by published assets."""
from __future__ import annotations

import base64
import html
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import folium
import pandas as pd
import streamlit as st
from PIL import Image
from branca.element import Element, MacroElement, Template
from streamlit.components.v1 import html as embed

VN_VIEW = [[6, 102], [24, 115]]


def local_time(value):
    if not value:
        return "Chưa có thông tin"
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return moment.astimezone(timezone(timedelta(hours=7))).strftime("%d/%m/%Y · %H:%M GMT+7")
    except ValueError:
        return str(value)


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def date_label(value):
    try:
        return datetime.fromisoformat(value).strftime('%d/%m/%Y')
    except (ValueError, TypeError):
        return 'Chưa rõ'


def published_layers(root):
    assets = root / "assets"
    records = []
    national = read_json(assets / "sentinel1_vietnam_latest.json")
    if national:
        records.append(dict(national, key="vietnam", label="Việt Nam", asset="sentinel1_vietnam_latest.png"))
    manifest = read_json(assets / "sentinel1_global/latest.json")
    records.extend(dict(item, refreshed_at=item.get("refreshed_at", manifest.get("refreshed_at"))) for item in manifest.get("tiles", []))
    valid = []
    for record in records:
        path = assets / record["asset"]
        try:
            with Image.open(path) as picture:
                picture.verify()
            valid.append(record)
        except (OSError, ValueError):
            continue
    return valid


def points_in_region(points, bounds):
    west, south, east, north = bounds
    return [point for point in points if west <= point["longitude"] <= east and south <= point["latitude"] <= north]


def provenance(record):
    esc = html.escape
    return (
        f"<b>{esc(record['label'])} · Sentinel‑1 GRD</b><br>"
        "Nguồn: Copernicus Data Space<br>"
        f"Khoảng ghép ảnh: {esc(record.get('window_start', '—'))} → {esc(record.get('window_end', '—'))}<br>"
        f"Mốc mới nhất trong catalog đã truy vấn: {esc(local_time(record.get('newest_catalog_acquired_at')))}<br>"
        f"Ảnh được tạo: {esc(local_time(record.get('refreshed_at')))}<br><br>"
        "Ảnh ghép nhiều lượt bay. Mốc catalog không phải ngày chụp của mọi điểm ảnh. "
        "Chưa có ngày chụp riêng cho vị trí được bấm."
    )


def render(root):
    from scan_view import render_scan
    workflow = st.radio('Bạn muốn làm gì?', ['Kiểm tra ảnh thật', 'Xem ảnh toàn cảnh'], horizontal=True)
    if workflow == 'Kiểm tra ảnh thật':
        render_scan(root)
        return
    records = published_layers(root)
    detection = read_json(root / "assets/gfw_global_ship_detections_latest.json")
    st.caption("Kéo để khám phá · Phóng to để xem gần · Chạm ảnh radar để xem nguồn")
    if not records:
        st.info("Chưa có ảnh được xuất bản. Dữ liệu sẽ xuất hiện sau lần đồng bộ thành công.")
        return
    choices = {record["label"]: record for record in records}
    selected = st.selectbox("Khu vực có ảnh sẵn", list(choices), key="observation_region")
    record = choices[selected]
    region_points = points_in_region(detection.get("points", []), record["bbox"])
    updated = record.get("refreshed_at")
    st.markdown(f'<div class="observation-meta"><span>Ảnh radar<strong>Sentinel‑1 GRD</strong></span><span>Khoảng ghép ảnh<strong>{date_label(record.get("window_start"))} – {date_label(record.get("window_end"))}</strong></span></div>', unsafe_allow_html=True)
    if updated:
        try:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(updated.replace('Z', '+00:00'))
            if age.total_seconds() > 12 * 3600:
                st.warning("Ảnh lưu sẵn đã hơn 12 giờ chưa cập nhật. Ngày quan sát và ngày tải được giữ nguyên bên dưới.")
        except ValueError:
            pass
    west, south, east, north = record["bbox"]
    bounds = VN_VIEW if record["key"] == "vietnam" else [[south, west], [north, east]]
    chart = folium.Map(location=[16, 108], zoom_start=5, zoom_snap=.25, tiles=None, control_scale=True, prefer_canvas=True)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri, Maxar, Earthstar Geographics", name="Nền ảnh vệ tinh", show=True, control=False,
    ).add_to(chart)
    radar = folium.FeatureGroup(name="Ảnh radar Sentinel‑1", show=True).add_to(chart)
    # All published regions are available when panning; the selected region controls the summary.
    for item in records:
        w, s, e, n = item["bbox"]
        raw = (root / "assets" / item["asset"]).read_bytes()
        layer = folium.raster_layers.ImageOverlay(
            image="data:image/png;base64," + base64.b64encode(raw).decode(),
            bounds=[[s, w], [n, e]], opacity=.82, interactive=True,
        ).add_to(radar)
        layer.add_child(folium.Popup(provenance(item), max_width=320))
    folium.map.CustomPane("place_labels", z_index=650, pointer_events=False).add_to(chart)
    folium.TileLayer(
        tiles="https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
        attr="Esri", name="Tên địa danh", overlay=True, pane="place_labels",
    ).add_to(chart)
    dots = folium.FeatureGroup(name="Tham khảo GFW · không phải YOLO", show=False).add_to(chart)
    for point in region_points:
        details = (
            "<b>Ô phát hiện SAR · GFW</b><br>"
            f"Tâm ô: {point['latitude']:.2f}°, {point['longitude']:.2f}°<br>"
            f"Lượt phát hiện cộng dồn: {point['detections']}<br>"
            f"Mốc mới nhất: {html.escape(local_time(point['acquired_at']))}<br>"
            f"Khoảng thống kê: {detection.get('window_start')} → {detection.get('window_end')}<br><br>"
            "Ô lưới 0,25° (~28 km theo vĩ độ). Một ô có thể chứa nhiều lượt quan sát cùng tàu; "
            "vị trí này không phải tọa độ chính xác của một tàu."
        )
        folium.CircleMarker(
            [point['latitude'], point['longitude']], radius=4,
            color="#ffecad", weight=1, fill=True, fill_color="#ef993c", fill_opacity=.85,
            popup=folium.Popup(details, max_width=320), tooltip="Mở thông tin ô phát hiện",
        ).add_to(dots)
    folium.LayerControl(collapsed=True, position="topright").add_to(chart)
    chart.fit_bounds(bounds)
    name = chart.get_name()
    home_control = MacroElement()
    home_control._template = Template("{% macro script(this, kwargs) %}" + f"""
        const home = L.control({{position:'topleft'}});
        home.onAdd = function() {{
            const button = L.DomUtil.create('button');
            button.textContent = 'Về Việt Nam';
            button.style.cssText = 'background:white;border:0;border-radius:6px;padding:10px;cursor:pointer;font:13px system-ui;box-shadow:0 1px 6px #0003';
            L.DomEvent.disableClickPropagation(button);
            button.onclick = () => {name}.fitBounds({json.dumps(VN_VIEW)});
            return button;
        }}; home.addTo({name});
    """ + "{% endmacro %}")
    chart.add_child(home_control)
    chart.get_root().header.add_child(Element("""<style>
      .leaflet-container{font-family:-apple-system,BlinkMacSystemFont,sans-serif}
      .leaflet-control-layers{border:0!important;border-radius:12px!important;padding:10px!important;box-shadow:0 4px 20px #0002!important}
      .leaflet-popup-content{font-size:13px;line-height:1.6}
      @media(max-width:600px){.leaflet-control-layers{font-size:11px;max-width:165px;padding:5px!important}}
    </style>"""))
    embed(chart.get_root().render(), height=540)
    st.caption(f"Ảnh radar được tạo: {local_time(updated)}. Ảnh ghép nhiều lượt bay, không phải luồng trực tiếp.")
    st.caption("Thang xám: ảnh radar. Bật ‘Tham khảo GFW’ để xem các ô màu vàng do nguồn bên ngoài cung cấp — không phải kết quả YOLO của SonarNet.")
    st.caption("Danh sách và số ô bên dưới theo khu vực đã chọn. Kéo bản đồ không thay đổi bộ lọc khu vực.")
    with st.expander("Danh sách phát hiện & xuất dữ liệu"):
        st.write("Các ô đã công bố trong khu vực; số lượt phát hiện không phải số tàu duy nhất.")
        rows = [{"Vĩ độ tâm ô": p['latitude'], "Kinh độ tâm ô": p['longitude'], "Lượt phát hiện": p['detections'], "Quan sát mới nhất (GMT+7)": local_time(p['acquired_at'])} for p in region_points]
        if rows:
            frame = pd.DataFrame(rows)
            st.dataframe(frame, hide_index=True, use_container_width=True)
            st.download_button("Tải bảng CSV", frame.to_csv(index=False).encode('utf-8-sig'), "sonarnet-observations.csv", "text/csv")
        else:
            st.info("Bộ dữ liệu đang công bố chưa có ô phát hiện tại khu vực này. Điều này không chứng minh khu vực không có tàu.")
    with st.expander("Nguồn, thời gian & độ phủ", expanded=False):
        st.write("Ảnh toàn quốc dùng để quan sát, không phải lớp YOLO toàn quốc. Thử nghiệm YOLO ảnh thật bên trên chỉ xử lý một vùng nhỏ; chưa định danh tàu hay kết luận vi phạm. GFW là lớp tham khảo bên ngoài, không phải kết quả YOLO.")
        st.caption(f"GFW được tải: {local_time(detection.get('refreshed_at'))}")
        st.markdown("**Ảnh radar:** [Copernicus Data Space](https://dataspace.copernicus.eu/) · Sentinel‑1 GRD. **Ô phát hiện:** [Global Fishing Watch](https://globalfishingwatch.org/our-apis/). **Nền và địa danh:** Esri.")
        st.write("Ảnh ghép dùng nhiều lượt bay trong khoảng ngày công bố. Nơi trong suốt chưa có pixel SAR trong bản ghép; nền tham chiếu vẫn hiện ở dưới. Ngày chụp của nền Esri và ngày riêng từng pixel SAR chưa được cung cấp ở giao diện này.")
        st.write("Các ô GFW là lớp tham chiếu độc lập, chưa được SonarNet ghép với AIS hoặc xác minh thành cảnh báo vi phạm. Bộ hiện tại giới hạn 1.800 ô có nhiều lượt phát hiện nhất trên các vùng đã tải; không phải toàn bộ tàu trên thế giới.")
        st.write("Lịch kiểm tra dữ liệu: mỗi 6 giờ. Ngày tạo ảnh và ngày quan sát là hai mốc khác nhau; lịch chạy có thể trễ khi dịch vụ không sẵn sàng.")
        st.dataframe(pd.DataFrame([{
            "Khu vực": r['label'], "Từ": r['window_start'], "Đến": r['window_end'],
            "Mốc catalog đã truy vấn": local_time(r.get('newest_catalog_acquired_at')),
            "Tạo ảnh": local_time(r.get('refreshed_at')),
        } for r in records]), hide_index=True, use_container_width=True)
        st.caption(f"Đang có {len(records)} vùng ảnh lưu sẵn. Phạm vi bản đồ toàn cầu không đồng nghĩa Sentinel‑1 phủ kín toàn cầu. Các truy vấn catalog cũ giới hạn tối đa 50 kết quả.")
