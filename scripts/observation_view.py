"""A single observation workspace backed only by published assets."""
from __future__ import annotations

import base64
from io import BytesIO
import hashlib
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
    # Per-tile manifests may explicitly contain ``null``.  Treat that as
    # missing and fall back to the manifest refresh time so every published
    # image can show a trustworthy “created” timestamp in its provenance.
    records.extend(
        dict(item, refreshed_at=item.get("refreshed_at") or manifest.get("refreshed_at"))
        for item in manifest.get("tiles", [])
    )
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


def published_yolo_result(root: Path, record: dict):
    """Project only validated, detailed SAR evidence onto the overview map."""
    from scan_assets import validated_report
    try:
        report = validated_report(root)
    except (OSError, ValueError, TypeError, KeyError):
        return None
    west, south, east, north = record['bbox']
    tiles = []
    candidates = []
    for tile in report['tiles']:
        w, s, e, n = tile['bbox']
        # Overviews are never detector inputs: individual vessels disappear
        # at kilometre-scale overview resolution.
        metres_per_pixel = 111320 * (n - s) / tile['image_size'][1] if tile.get('image_size') else float('inf')
        if tile['status'] != 'processed' or metres_per_pixel > 25 or e < west or w > east or n < south or s > north:
            continue
        tiles.append(tile)
        for candidate in tile['detections']:
            if not (west <= candidate['longitude'] <= east and south <= candidate['latitude'] <= north):
                continue
            candidates.append(dict(candidate, id=f"{tile['key']}/{candidate['id']}",
                                   tile_key=tile['key'], asset_dir=tile['asset_dir'],
                                   observation_day_utc=tile['observation_day_utc'],
                                   weights_sha256=tile['weights_sha256']))
    return dict(detections=candidates, tiles=tiles, generated_at=report['generated_at'])


def candidate_crop(root, candidate):
    """Small source-image evidence that remains legible on a phone."""
    with Image.open(root / candidate['asset_dir'] / 'sar.png') as image:
        x1, y1, x2, y2 = candidate['bbox_px']
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        half = max(48, (x2-x1)/2 + 20, (y2-y1)/2 + 20)
        crop = image.crop((max(0, int(cx-half)), max(0, int(cy-half)),
                           min(image.width, int(cx+half)), min(image.height, int(cy+half))))
        buffer = BytesIO()
        crop.convert('RGB').save(buffer, 'JPEG', quality=88)
        return buffer.getvalue()


def points_in_region(points, bounds):
    west, south, east, north = bounds
    return [point for point in points if west <= point["longitude"] <= east and south <= point["latitude"] <= north]


def demo_ais_record(record: dict, candidate: dict) -> dict:
    """Create a deterministic, explicitly synthetic AIS record for demos.

    The public app has no live VMS/AIS feed.  This helper mirrors the fields a
    future authorized feed would provide so the review flow can be presented
    end-to-end without fabricating real identities or implying a live match.
    """
    token = int(hashlib.sha256(str(candidate['id']).encode()).hexdigest()[:8], 16)
    statuses = ["AIS khớp", "AIS lệch", "Không có AIS"]
    status = statuses[token % len(statuses)]
    lat, lon = candidate["latitude"], candidate["longitude"]
    # Deliberate offsets make the three states visible on the map: close for a
    # plausible match, farther away for a mismatch, and no point for dark.
    if status == "AIS khớp":
        ais_lat, ais_lon = lat + 0.012, lon + 0.010
    elif status == "AIS lệch":
        ais_lat, ais_lon = lat + 0.16, lon + 0.18
    else:
        ais_lat, ais_lon = None, None
    mmsi = f"DEMO-{token % 1_000_000:06d}" if ais_lat is not None else "Chưa xác định"
    registration = f"DEMO-{token % 100000:05d}-TS"
    return {
        "status": status,
        "mmsi": mmsi,
        "registration": registration if ais_lat is not None else "Chưa xác định",
        "vessel_name": f"SONARNET DEMO {token % 100:02d}" if ais_lat is not None else "Chưa xác định",
        "owner": "Chủ sở hữu minh hoạ" if ais_lat is not None else "Chưa xác định",
        "port": "Cảng minh hoạ" if ais_lat is not None else "Chưa xác định",
        "latitude": ais_lat,
        "longitude": ais_lon,
        "timestamp": candidate.get("observation_day_utc"),
    }


def provenance(record):
    esc = html.escape
    return (
        f"<b>{esc(record['label'])} · Sentinel‑1 GRD</b><br>"
        f"Nguồn: Copernicus Data Space · kênh {esc(record.get('band', 'VV'))}<br>"
        f"Khoảng ghép ảnh: {esc(record.get('window_start', '—'))} → {esc(record.get('window_end', '—'))}<br>"
        f"Mốc mới nhất trong catalog đã truy vấn: {esc(local_time(record.get('newest_catalog_acquired_at')))}<br>"
        f"Ảnh được tạo: {esc(local_time(record.get('refreshed_at')))}<br><br>"
        "Ảnh ghép nhiều lượt bay. Mốc catalog không phải ngày chụp của mọi điểm ảnh. "
        "Chưa có ngày chụp riêng cho vị trí được bấm."
    )


def render(root):
    from scan_view import render_scan
    # Start with the nationwide context so a first-time visitor immediately
    # sees the published Sentinel‑1 coverage.  The focused YOLO review remains
    # one deliberate step away and is clearly labelled as a test workspace.
    workflow = st.radio('Bạn muốn làm gì?', ['Xem ảnh toàn cảnh', 'Kiểm tra ảnh thật'], horizontal=True)
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
    yolo_enabled = st.toggle(
        "Hiện ứng viên YOLO",
        value=True,
        key="panorama_yolo_enabled",
        help="Khoanh các vùng ảnh giống tàu để rà soát. Đây là ứng viên mô hình, không phải tàu đã xác minh.",
    )
    yolo_result = None
    if yolo_enabled:
        yolo_result = published_yolo_result(root, record)
        if yolo_result and yolo_result['tiles']:
            days = sorted({tile['observation_day_utc'] for tile in yolo_result['tiles']})
            from land_mask import summary
            st.caption(summary(yolo_result['tiles']))
            st.caption(f"{len(yolo_result['detections'])} ứng viên thử nghiệm · {len(yolo_result['tiles'])} ô ảnh chi tiết đã quét · "
                       f"ngày ảnh {', '.join(date_label(day) for day in days)} (UTC). Chạm điểm sáng để xem ảnh bằng chứng.")
        else:
            st.info("Khu vực này chưa có kết quả YOLO trên ảnh chi tiết được công bố. Ảnh toàn cảnh vẫn có thể xem; không coi vùng chưa quét là không có tàu.")
    ais_demo = []
    ais_enabled = False
    if yolo_result and yolo_result['detections']:
        ais_enabled = st.toggle(
            "Hiện đối chiếu AIS minh hoạ",
            value=True,
            key="panorama_ais_demo_enabled",
            help="Dữ liệu giả lập để trình bày luồng nghiệp vụ; không phải tín hiệu AIS/VMS thật.",
        )
        if ais_enabled:
            ais_demo = [demo_ais_record(record, candidate) for candidate in yolo_result["detections"]]
            status_counts = {status: sum(item["status"] == status for item in ais_demo) for status in ["AIS khớp", "AIS lệch", "Không có AIS"]}
            st.info(f"AIS minh hoạ · {status_counts['AIS khớp']} khớp · {status_counts['AIS lệch']} lệch · {status_counts['Không có AIS']} không có tín hiệu. "
                    "Định danh và trạng thái là dữ liệu giả lập để trình bày quy trình.")
    chart = folium.Map(location=[16, 108], zoom_start=5, zoom_snap=.25, tiles=None, control_scale=True, prefer_canvas=True)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri, Maxar, Earthstar Geographics", name="Nền ảnh vệ tinh", show=True, control=False,
    ).add_to(chart)
    radar = folium.FeatureGroup(name="Ảnh radar Sentinel‑1", show=True).add_to(chart)
    yolo_layer = folium.FeatureGroup(name="Ứng viên YOLO · chưa xác minh", show=bool(yolo_enabled)).add_to(chart)
    ais_layer = folium.FeatureGroup(name="AIS minh hoạ · DEMO", show=bool(ais_enabled)).add_to(chart)
    # All published regions are available when panning; the selected region controls the summary.
    for item in records:
        w, s, e, n = item["bbox"]
        raw = (root / "assets" / item["asset"]).read_bytes()
        layer = folium.raster_layers.ImageOverlay(
            image="data:image/png;base64," + base64.b64encode(raw).decode(),
            bounds=[[s, w], [n, e]], opacity=.82, interactive=True, alt=f"Ảnh Sentinel-1 · {item['label']}",
        ).add_to(radar)
        layer.add_child(folium.Popup(provenance(item), max_width=320))
    if yolo_result:
        for tile in yolo_result['tiles']:
            w, s, e, n = tile['bbox']
            raw = (root / tile['asset_dir'] / 'sar.png').read_bytes()
            folium.raster_layers.ImageOverlay(
                image='data:image/png;base64,' + base64.b64encode(raw).decode(),
                bounds=[[s,w],[n,e]], opacity=1, alt=f"Ô radar chi tiết {tile['key']}",
            ).add_to(radar)
            folium.Rectangle([[s,w],[n,e]], weight=1, color='#64d2ff', fill=False,
                tooltip=f"Đã quét YOLO · {tile['key']} · {date_label(tile['observation_day_utc'])} UTC",
                popup=f"Sentinel-1 VV · Copernicus · {date_label(tile['observation_day_utc'])} UTC · "
                      f"{len(tile['detections'])} ứng viên thử nghiệm. Ảnh ghép trong ngày.").add_to(yolo_layer)
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
    if yolo_result:
        for index, candidate in enumerate(yolo_result["detections"]):
            ais = ais_demo[index] if ais_enabled else None
            ais_text = ""
            if ais:
                ais_text = (
                    f"<br><b>AIS minh hoạ:</b> {ais['status']}<br>"
                    f"MMSI {ais['mmsi']} · {ais['registration']}<br>"
                    f"Tên: {ais['vessel_name']} · Cảng: {ais['port']}"
                )
            crop_b64 = base64.b64encode(candidate_crop(root, candidate)).decode()
            folium.CircleMarker(
                [candidate["latitude"], candidate["longitude"]], radius=7,
                color="#ff9f0a" if candidate.get('surface') == 'near_coast' else "#ffd166", weight=2, fill=True,
                fill_color="#ff9f0a" if candidate.get('surface') == 'near_coast' else "#ffd166", fill_opacity=.9,
                popup=folium.Popup(
                    f"<b>Ứng viên YOLO · {candidate['id']}</b><br>"
                    f"<img src='data:image/jpeg;base64,{crop_b64}' width='180' alt='Ảnh radar gốc tại ứng viên'><br>"
                    f"Sentinel-1 · Copernicus · {date_label(candidate['observation_day_utc'])} UTC<br>"
                    f"Điểm mô hình: {candidate['confidence']:.2f}<br>"
                    f"Bề mặt: {'Sát bờ · cần kiểm tra' if candidate.get('surface') == 'near_coast' else 'Ngoài vùng đất loại trừ · chưa xác minh'}<br>"
                    f"Tọa độ xấp xỉ: {candidate['latitude']:.5f}°, {candidate['longitude']:.5f}°<br>"
                    f"Chưa xác minh là tàu{ais_text}",
                    max_width=320,
                ),
                tooltip=f"YOLO #{candidate['id']} · {candidate['confidence']:.2f}",
            ).add_to(yolo_layer)
        if ais_enabled:
            for candidate, ais in zip(yolo_result["detections"], ais_demo):
                if ais["latitude"] is None:
                    continue
                status_color = {"AIS khớp": "#32d74b", "AIS lệch": "#ff9f0a"}.get(ais["status"], "#ff453a")
                folium.PolyLine(
                    [[candidate["latitude"], candidate["longitude"]], [ais["latitude"], ais["longitude"]]],
                    color=status_color, weight=2, opacity=.75, dash_array="5,6",
                ).add_to(ais_layer)
                folium.CircleMarker(
                    [ais["latitude"], ais["longitude"]], radius=6, color=status_color,
                    fill=True, fill_color=status_color, fill_opacity=.88,
                    popup=folium.Popup(
                        f"<b>Bản ghi AIS minh hoạ · {ais['status']}</b><br>"
                        f"MMSI: {ais['mmsi']}<br>Số đăng ký: {ais['registration']}<br>"
                        f"Tên phương tiện: {ais['vessel_name']}<br>Chủ sở hữu: {ais['owner']}<br>"
                        f"Cảng đăng ký: {ais['port']}<br>Ngày kịch bản: {date_label(ais['timestamp'])} UTC<br><br>"
                        "Dữ liệu giả lập để trình bày — không phải định danh thật.", max_width=320,
                    ),
                    tooltip=f"AIS minh hoạ · {ais['status']}",
                ).add_to(ais_layer)
    from land_mask import add_map_layer
    add_map_layer(chart, root)
    folium.LayerControl(collapsed=True, position="topright").add_to(chart)
    chart.fit_bounds(bounds)
    name = chart.get_name()
    scan_bounds = None
    if yolo_result and yolo_result['tiles']:
        boxes = [tile['bbox'] for tile in yolo_result['tiles']]
        scan_bounds = [[min(b[1] for b in boxes), min(b[0] for b in boxes)],
                       [max(b[3] for b in boxes), max(b[2] for b in boxes)]]
    scan_button_js = '' if scan_bounds is None else f"""
        const scanButton = L.DomUtil.create('button', '', group);
        scanButton.textContent = 'Vùng đã quét YOLO';
        scanButton.style.cssText = button.style.cssText + ';margin-top:5px';
        scanButton.onclick = () => {name}.fitBounds({json.dumps(scan_bounds)}, {{padding:[24,24]}});
    """
    home_control = MacroElement()
    home_control._template = Template("{% macro script(this, kwargs) %}" + f"""
        const home = L.control({{position:'topleft'}});
        home.onAdd = function() {{
            const group = L.DomUtil.create('div');
            const button = L.DomUtil.create('button', '', group);
            button.textContent = 'Về Việt Nam';
            button.style.cssText = 'display:block;background:white;border:0;border-radius:6px;padding:10px;cursor:pointer;font:13px system-ui;box-shadow:0 1px 6px #0003';
            L.DomEvent.disableClickPropagation(group);
            button.onclick = () => {name}.fitBounds({json.dumps(VN_VIEW)});
            {scan_button_js}
            return group;
        }}; home.addTo({name});
        let previousWidth = {name}.getContainer().clientWidth;
        let resizeTimer;
        new ResizeObserver(() => {{
            const width = {name}.getContainer().clientWidth;
            if (!width || width === previousWidth) return;
            previousWidth = width;
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(() => {{
                {name}.invalidateSize({{pan:false}});
                {name}.fitBounds({json.dumps(bounds)}, {{animate:false}});
            }}, 120);
        }}).observe({name}.getContainer());
    """ + "{% endmacro %}")
    chart.add_child(home_control)
    chart.get_root().header.add_child(Element("""<style>
      .leaflet-container{font-family:-apple-system,BlinkMacSystemFont,sans-serif}
      .leaflet-control-layers{border:0!important;border-radius:12px!important;padding:10px!important;box-shadow:0 4px 20px #0002!important}
      .leaflet-popup-content{font-size:13px;line-height:1.6}
      @media(max-width:600px){.leaflet-control-layers{font-size:11px;max-width:165px;padding:5px!important}}
    </style>"""))
    embed(chart.get_root().render(), height=540)
    if yolo_result and yolo_result['tiles']:
        st.caption('YOLO thử nghiệm học từ ảnh mô phỏng; có thể nhầm nhiễu hoặc bờ đất. Viền xanh là vùng đã quét; điểm sáng chưa được xác minh là tàu.')
    if yolo_result and yolo_result['detections']:
        options = {item['id']: item for item in yolo_result['detections']}
        chosen = st.selectbox('Xem bằng chứng của ứng viên', list(options), key='panorama_candidate')
        candidate = options[chosen]
        with st.expander('Ảnh bằng chứng & thông tin đối chiếu', expanded=True):
            photo, details = st.columns([1, 2])
            with photo:
                st.image(candidate_crop(root, candidate), width=220, caption='Ảnh radar gốc · vùng quanh ứng viên')
            with details:
                st.write(f"**{chosen}** · điểm mô hình {candidate['confidence']:.2f}")
                st.write(f"Copernicus · Sentinel-1 VV · {date_label(candidate['observation_day_utc'])} UTC")
                st.caption(f"{candidate['latitude']:.5f}°B, {candidate['longitude']:.5f}°Đ · ảnh ghép trong ngày")
                if ais_enabled:
                    ais = demo_ais_record(record, candidate)
                    st.write(f"**AIS minh hoạ: {ais['status']}**")
                    st.write(f"{ais['vessel_name']} · {ais['registration']}")
                    st.caption(f"Định danh demo: {ais['mmsi']} · {ais['port']}")
                st.caption('Để đánh giá ứng viên và xuất ảnh bằng chứng, mở Kiểm tra ảnh thật.')
        with st.expander("Danh sách ứng viên YOLO trên ảnh này"):
            rows = [
                {
                    "ID": item["id"],
                    "Điểm mô hình": round(item["confidence"], 3),
                    "Vĩ độ xấp xỉ": round(item["latitude"], 5),
                    "Kinh độ xấp xỉ": round(item["longitude"], 5),
                }
                for item in yolo_result["detections"]
            ]
            if rows:
                st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
            else:
                st.info("YOLO không đề xuất ứng viên ở ngưỡng 0,35. Điều này không chứng minh vùng này không có tàu.")
        if ais_demo:
            with st.expander("Bản ghi AIS minh hoạ & đối chiếu"):
                st.caption("Các trường nhận dạng dưới đây chỉ là dữ liệu demo có cấu trúc, chờ thay bằng nguồn VMS/AIS được cấp quyền.")
                ais_rows = []
                for candidate, ais in zip(yolo_result["detections"], ais_demo):
                    ais_rows.append({
                        "Ứng viên YOLO": f"#{candidate['id']} · {candidate['confidence']:.2f}",
                        "Trạng thái AIS": ais["status"],
                        "MMSI minh hoạ": ais["mmsi"],
                        "Số đăng ký": ais["registration"],
                        "Tên phương tiện": ais["vessel_name"],
                        "Cảng đăng ký": ais["port"],
                        "Ngày kịch bản (UTC)": date_label(ais["timestamp"]),
                    })
                st.dataframe(pd.DataFrame(ais_rows), hide_index=True, use_container_width=True)
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
        st.write("YOLO chạy trên ô ảnh chi tiết; các ứng viên được đưa lên ảnh toàn cảnh bằng tọa độ. Viền xanh thể hiện phạm vi đã quét. Hiện bộ bằng chứng công bố gồm 12 ô Bình Thuận, chưa phủ toàn quốc. Định danh và trạng thái AIS trong chế độ minh hoạ là kịch bản giả lập.")
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
        evaluation = read_json(root / 'assets/real_model_evaluation.json')
        if evaluation:
            st.markdown('**Trạng thái mô hình YOLO**')
            baseline = evaluation.get('baseline_comparison', {})
            st.write(f"Baseline đang hiển thị: precision {baseline.get('precision', 0):.4f} · recall {baseline.get('recall', 0):.4f} trên bộ test SAR thật. Chất lượng này chưa đủ cho giám sát nghiệp vụ; cần xem từng ảnh bằng chứng.")
            benchmark = evaluation.get('benchmark', {})
            st.write(f"Mô hình thử nghiệm huấn luyện lại (chưa thay baseline trên bản đồ): precision {benchmark.get('precision', 0):.3f} · recall {benchmark.get('recall', 0):.3f} · mAP50 {benchmark.get('map50', 0):.3f}. Đây là benchmark giữ riêng từ bộ SAR công khai, chưa chứng minh chất lượng trên Việt Nam.")
            st.warning(evaluation.get('promotion_decision', 'Chưa có quyết định phát hành mô hình.'))
