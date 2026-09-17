"""A single observation workspace backed only by published assets."""
from __future__ import annotations

import base64
from io import BytesIO
import html
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import folium
from folium.plugins import MarkerCluster
import pandas as pd
import streamlit as st
from PIL import Image
from branca.element import Element, MacroElement, Template
from streamlit.components.v1 import html as embed
from map_raster import overlay_source, static_overlay_source, ViewportRadar
from coverage_status import coverage_rows, waiting_cells
from observation_labels import candidate_label, coordinates

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
    workflow = st.radio('Bạn muốn làm gì?', ['Xem toàn cảnh', 'Kiểm tra chi tiết'], horizontal=True, key='observation_workflow')
    if workflow == 'Kiểm tra chi tiết':
        render_scan(root)
        return
    records = published_layers(root)
    detection = read_json(root / "assets/gfw_global_ship_detections_latest.json")
    if not records:
        st.info("Chưa có ảnh được xuất bản. Dữ liệu sẽ xuất hiện sau lần đồng bộ thành công.")
        return
    choices = {record["label"]: record for record in records}
    selected = st.selectbox("Khu vực có ảnh sẵn", list(choices), key="observation_region")
    record = choices[selected]
    region_points = points_in_region(detection.get("points", []), record["bbox"])
    updated = record.get("refreshed_at")
    st.markdown(f'<div class="observation-meta"><span>Khu vực<strong>{html.escape(selected)}</strong></span><span>Thời gian ảnh<strong>{date_label(record.get("window_start"))} – {date_label(record.get("window_end"))}</strong></span></div>', unsafe_allow_html=True)
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
        "Hiện vùng nghi là tàu",
        value=True,
        key="panorama_yolo_enabled",
        help="Các vùng ảnh được hệ thống đánh dấu để bạn kiểm tra; chưa xác nhận là tàu.",
    )
    yolo_result = None
    illustrative = st.toggle('Xem tình huống có dữ liệu tàu', value=False,
                             help='Hồ sơ minh hoạ để trải nghiệm đối chiếu; không phải AIS thật hoặc danh tính của mục tiêu trong ảnh.')
    if illustrative:
        st.info('Đang xem hồ sơ minh hoạ, không phải dữ liệu tàu thật. Xanh ngọc: tình huống có bản tin phù hợp · xám: chưa có bản tin. Loại tàu và thông số là giả định.')
    yolo_result = published_yolo_result(root, record)
    if yolo_enabled:
        if yolo_result and yolo_result['tiles']:
            days = sorted({tile['observation_day_utc'] for tile in yolo_result['tiles']})
            st.caption(f"{len(yolo_result['detections'])} điểm cần kiểm tra · {len(yolo_result['tiles'])} ô ảnh đã xử lý · "
                       f"ngày ảnh {', '.join(date_label(day) for day in days)} (UTC). Chạm điểm sáng để xem ảnh bằng chứng.")
        else:
            st.info("Khu vực này chưa được kiểm tra tự động trên ảnh chi tiết. Bạn vẫn có thể xem ảnh; chưa có kết quả không có nghĩa là không có tàu.")
    coverage = read_json(root/'assets/real_scan/coverage.json')
    area_plan = next((area for area in coverage.get('regions', []) if area['key'] == record['key']), None)
    if area_plan and waiting_cells(area_plan):
        st.caption(f"Đang mở rộng vùng kiểm tra: còn {waiting_cells(area_plan):,} ô ảnh chờ xử lý hoặc tải lại. Kết quả được bổ sung sau mỗi lượt đồng bộ, chưa phủ kín khu vực.")
    chart = folium.Map(location=[16, 108], zoom_start=5, zoom_snap=.25, tiles=None, control_scale=True, prefer_canvas=True)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri, Maxar, Earthstar Geographics", name="Nền ảnh vệ tinh", show=True, control=False,
    ).add_to(chart)
    radar = folium.FeatureGroup(name="Ảnh radar", show=True).add_to(chart)
    yolo_layer = folium.FeatureGroup(name="Vùng nghi là tàu", show=bool(yolo_enabled)).add_to(chart)
    # Load only the chosen area's radar raster. Do not send all global images
    # into a phone's map iframe on every rerun.
    for item in [record]:
        w, s, e, n = item["bbox"]
        layer = folium.raster_layers.ImageOverlay(
            image=overlay_source(root / 'assets' / item['asset'], item['bbox']),
            bounds=[[s, w], [n, e]], opacity=.82, interactive=True, alt=f"Ảnh Sentinel-1 · {item['label']}",
        ).add_to(radar)
        layer.add_child(folium.Popup(provenance(item), max_width=320))
    if yolo_result:
        radar_records = []
        for tile in yolo_result['tiles']:
            w, s, e, n = tile['bbox']
            radar_records.append(dict(
                url=static_overlay_source(root / tile['asset_dir'] / 'sar.png', tile['bbox'], root/'scripts/static'),
                bounds=[[s,w],[n,e]], label=f"Ô radar chi tiết {tile['key']}",
                popup=f"Sentinel-1 VV · Copernicus · {date_label(tile['observation_day_utc'])} UTC · Ảnh ghép trong ngày.",
            ))
        ViewportRadar(chart, radar, radar_records).add_to(chart)
        st.caption("Phóng to vùng đã xử lý để xem ảnh radar chi tiết. Ảnh tự tải theo vị trí đang xem; mỗi ô có ngày quan sát riêng.")
    from place_labels import add_place_labels
    add_place_labels(chart)
    dots = folium.FeatureGroup(name="Quan sát từ nguồn khác", show=False).add_to(chart)
    for point in region_points:
        details = (
            "<b>Quan sát tham khảo · Global Fishing Watch</b><br>"
            f"Tâm ô: {point['latitude']:.2f}°, {point['longitude']:.2f}°<br>"
            f"Lượt phát hiện cộng dồn: {point['detections']}<br>"
            f"Mốc mới nhất: {html.escape(local_time(point['acquired_at']))}<br>"
            f"Khoảng thống kê: {detection.get('window_start')} → {detection.get('window_end')}<br><br>"
            "Ô lưới 0,25° (~28 km theo vĩ độ). Một ô có thể chứa nhiều lượt quan sát cùng tàu; "
            "vị trí này không phải tọa độ chính xác của một tàu."
        )
        folium.CircleMarker(
            [point['latitude'], point['longitude']], radius=4,
            color="#ffecad", weight=1.5, fill=False,
            popup=folium.Popup(details, max_width=320), tooltip="Mở thông tin ô phát hiện",
        ).add_to(dots)
    if yolo_result:
        cluster = MarkerCluster(name='Các điểm quan sát', control=False,
            options={'maxClusterRadius': 34, 'disableClusteringAtZoom': 10,
                     'showCoverageOnHover': False, 'spiderfyOnMaxZoom': True},
            icon_create_function="""function(cluster) {
                return L.divIcon({html: '<div style="width:30px;height:30px;border-radius:50%;background:rgba(20,39,49,.88);border:1px solid rgba(173,220,229,.65);color:#eefcff;display:flex;align-items:center;justify-content:center;font:600 11px system-ui;box-shadow:0 2px 8px #0004">'+cluster.getChildCount()+'</div>',className:'observation-cluster',iconSize:[30,30]});
            }""").add_to(yolo_layer)
        from illustrative_vessels import profile, popup as illustrative_popup
        for candidate in yolo_result["detections"]:
            crop_b64 = base64.b64encode(candidate_crop(root, candidate)).decode()
            color = ('#64d8c6' if profile(candidate)['matched'] else '#c1ccd4') if illustrative else '#bde8ee'
            folium.CircleMarker(
                [candidate["latitude"], candidate["longitude"]], radius=4,
                color=color, weight=1.2, fill=False,
                popup=folium.Popup(
                    f"<b>Điểm cần kiểm tra · {candidate['id']}</b><br>"
                    f"<img src='data:image/jpeg;base64,{crop_b64}' width='180' alt='Ảnh radar gốc tại ứng viên'><br>"
                    f"Sentinel-1 · Copernicus · {date_label(candidate['observation_day_utc'])} UTC<br>"
                    "Ngoài vùng bỏ qua trên đất và sát bờ.<br>"
                    f"Tọa độ xấp xỉ: {candidate['latitude']:.5f}°, {candidate['longitude']:.5f}°<br>"
                    "Chưa xác minh là tàu<br>Thông tin tàu: chưa có dữ liệu đối chiếu cùng thời điểm."
                    + (illustrative_popup(candidate) if illustrative else ''),
                    max_width=320,
                ),
                tooltip=f"Mở ảnh kiểm tra · {candidate['id']}",
            ).add_to(cluster)
    from land_mask import add_map_layer
    add_map_layer(chart, root, detail_bounds=[t['bbox'] for t in yolo_result['tiles']] if yolo_result else [])
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
        scanButton.textContent = 'Vùng đã kiểm tra';
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
      .leaflet-popup-content-wrapper{border-radius:18px;background:rgba(250,253,255,.97);color:#20313c;box-shadow:0 12px 36px #08182740;border:1px solid #ffffffb3}
      .leaflet-popup-content{margin:18px 20px;max-width:calc(100vw - 100px)}
      .leaflet-popup-content img{display:block;width:100%;max-width:240px;border-radius:10px;margin:10px 0}
      .leaflet-popup-content strong,.leaflet-popup-content b{font-weight:600}
      .leaflet-popup-content hr{border:0;border-top:1px solid #dce5eb;margin:14px 0}
      .observation-cluster{background:transparent;border:0}
      .observation-cluster>div{transition:transform .18s ease,box-shadow .18s ease}
      .observation-cluster:hover>div{transform:scale(1.12);box-shadow:0 4px 18px #0005!important}
      @media(prefers-reduced-motion:reduce){.observation-cluster>div{transition:none}}
      @media(max-width:600px){.leaflet-control-layers{font-size:11px;max-width:165px;padding:5px!important}}
    </style>"""))
    embed(chart.get_root().render(), height=540)
    if yolo_result and yolo_result['tiles']:
        st.caption('Điểm sáng: vùng nghi là tàu, cần xác minh. Ảnh nền toàn cảnh không đồng nghĩa đã kiểm tra toàn bộ. Xem tiến độ và độ phủ bên dưới. Dải bỏ qua sát bờ 500 m hiện quanh ảnh chi tiết khi phóng gần.')
    st.caption('Kéo để di chuyển · Chạm ảnh để xem nguồn và ngày quan sát · Chạm tên quần đảo để xem nguồn địa danh.')
    if yolo_result and yolo_result['detections']:
        options = {item['id']: item for item in yolo_result['detections']}
        point_numbers = {key: index+1 for index, key in enumerate(options)}
        chosen = st.selectbox('Chọn điểm cần kiểm tra', list(options), key='panorama_candidate',
                              format_func=lambda key: candidate_label(options[key], point_numbers[key]))
        candidate = options[chosen]
        with st.expander('Ảnh bằng chứng & thông tin đối chiếu', expanded=True):
            photo, details = st.columns([1, 2])
            with photo:
                st.image(candidate_crop(root, candidate), width=220, caption='Ảnh radar gốc · vùng quanh ứng viên')
            with details:
                st.write(f"**Điểm cần kiểm tra {point_numbers[chosen]}**")
                st.write(f"Ngày ảnh: {date_label(candidate['observation_day_utc'])} UTC · Copernicus")
                st.caption(f"{coordinates(candidate['latitude'], candidate['longitude'])} · ảnh ghép trong ngày")
                st.write('**Thông tin tàu: chưa xác định.**')
                st.caption('Chưa có tên tàu, số đăng ký và tín hiệu vị trí cùng thời điểm để đối chiếu.')
                def open_evidence():
                    st.session_state['observation_workflow'] = 'Kiểm tra chi tiết'
                    st.session_state['review_tile'] = candidate['tile_key']
                    st.session_state['review_target_id'] = str(candidate['id']).split('/')[-1]
                st.button('Kiểm tra điểm này', on_click=open_evidence, type='primary')
        with st.expander("Danh sách điểm cần kiểm tra"):
            rows = [
                {
                    "Điểm": point_numbers[item['id']],
                    "Ngày ảnh (UTC)": date_label(item['observation_day_utc']),
                    "Vĩ độ xấp xỉ": round(item["latitude"], 5),
                    "Kinh độ xấp xỉ": round(item["longitude"], 5),
                }
                for item in yolo_result["detections"]
            ]
            if rows:
                st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
            else:
                st.info("Chưa thấy điểm cần kiểm tra. Điều này không chứng minh vùng này không có tàu.")
    st.caption(f"Ảnh radar được tạo: {local_time(updated)}. Ảnh ghép nhiều lượt bay, không phải luồng trực tiếp.")
    with st.expander("Quan sát từ nguồn khác"):
        st.caption('Lớp tham khảo Global Fishing Watch: thống kê theo vùng, không phải vị trí từng tàu. Danh sách theo khu vực đã chọn.')
        st.write("Các ô đã công bố trong khu vực; số lượt phát hiện không phải số tàu duy nhất.")
        rows = [{"Vĩ độ tâm ô": p['latitude'], "Kinh độ tâm ô": p['longitude'], "Lượt phát hiện": p['detections'], "Quan sát mới nhất (GMT+7)": local_time(p['acquired_at'])} for p in region_points]
        if rows:
            frame = pd.DataFrame(rows)
            st.dataframe(frame, hide_index=True, use_container_width=True)
            st.download_button("Tải bảng CSV", frame.to_csv(index=False).encode('utf-8-sig'), "sonarnet-observations.csv", "text/csv")
        else:
            st.info("Bộ dữ liệu đang công bố chưa có ô phát hiện tại khu vực này. Điều này không chứng minh khu vực không có tàu.")
    with st.expander("Nguồn, thời gian & độ phủ", expanded=False):
        from land_mask import summary
        if yolo_result:
            st.caption(summary(yolo_result['tiles']))
        coverage = read_json(root / 'assets/real_scan/coverage.json')
        plan = next((r for r in coverage.get('regions', []) if r['key'] == record['key']), None)
        if plan:
            states = plan['states']
            pending = waiting_cells(plan)
            st.write(f"Đã công bố {plan['published_detail_cells']} ô ảnh chi tiết. Còn {pending:,} ô trong kế hoạch cần xử lý; đây không phải vùng đã tìm xong tàu.")
            st.dataframe(pd.DataFrame(coverage_rows(plan)), hide_index=True, width='stretch')
            st.caption('Số ô trên lưới kế hoạch có thể khác số ảnh công bố: các ảnh thử nghiệm ban đầu không cùng lưới. Không cộng hai số này để tính độ phủ.')
            if states.get('blocked_missing_mask'):
                st.caption('Một phần khu vực chưa có đường bờ được kiểm tra để loại đất và vùng ven bờ, nên chưa chạy nhận diện ở đó.')
        st.write("Hệ thống tìm vùng giống tàu trong từng ảnh chi tiết, rồi đánh dấu đúng vị trí lên toàn cảnh. Ảnh nền không đồng nghĩa toàn bộ khu vực đã được kiểm tra; xem số ô đã xử lý và còn chờ trong mục độ phủ. Chưa có dữ liệu định danh và vị trí trực tiếp từ tàu.")
        st.caption(f"GFW được tải: {local_time(detection.get('refreshed_at'))}")
        st.markdown("**Ảnh radar:** [Copernicus Data Space](https://dataspace.copernicus.eu/) · Sentinel‑1 GRD. **Ô phát hiện:** [Global Fishing Watch](https://globalfishingwatch.org/our-apis/). **Nền ảnh:** Esri. Địa danh Việt Nam là lớp nhãn riêng; không sử dụng lớp đường biên của nhà cung cấp bản đồ.")
        st.write("Ảnh ghép dùng nhiều lượt bay trong khoảng ngày công bố. Nơi chưa có ảnh radar sẽ hiện nền ảnh màu bên dưới. Ngày chụp của ảnh nền và ngày riêng từng điểm ảnh radar chưa được cung cấp ở đây.")
        st.write("Nguồn Global Fishing Watch dùng để tham khảo, chưa đối chiếu với thông tin phát từ tàu hoặc xác minh thành cảnh báo vi phạm. Bộ hiện tại giới hạn 1.800 ô có nhiều lượt phát hiện nhất trên các vùng đã tải; không phải toàn bộ tàu trên thế giới.")
        st.write("Lịch kiểm tra dữ liệu: mỗi 6 giờ. Ngày tạo ảnh và ngày quan sát là hai mốc khác nhau; lịch chạy có thể trễ khi dịch vụ không sẵn sàng.")
        st.dataframe(pd.DataFrame([{
            "Khu vực": r['label'], "Từ": r['window_start'], "Đến": r['window_end'],
            "Mốc catalog đã truy vấn": local_time(r.get('newest_catalog_acquired_at')),
            "Tạo ảnh": local_time(r.get('refreshed_at')),
        } for r in records]), hide_index=True, use_container_width=True)
        st.caption(f"Đang có {len(records)} vùng ảnh lưu sẵn. Phạm vi bản đồ toàn cầu không đồng nghĩa Sentinel‑1 phủ kín toàn cầu. Các truy vấn catalog cũ giới hạn tối đa 50 kết quả.")
        evaluation = read_json(root / 'assets/real_model_evaluation.json')
        if evaluation:
            st.markdown('**Độ tin cậy của nhận diện tự động**')
            st.warning('Phiên bản đang hiển thị còn báo nhầm nhiều và bỏ sót tàu khi kiểm tra trên bộ ảnh thật. Chưa đủ chất lượng để dùng cho quyết định nghiệp vụ; cần kiểm tra từng ảnh bằng chứng.')
            st.download_button('Tải báo cáo đánh giá đầy đủ', json.dumps(evaluation,ensure_ascii=False,indent=2), 'sonarnet-quality-report.json', 'application/json')
