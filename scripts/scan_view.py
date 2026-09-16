"""Evidence-first review of real SAR processing, including negative results."""
import json
from datetime import date
from pathlib import Path

import folium
import streamlit as st
from PIL import Image
from streamlit.components.v1 import html
from review_workspace import STATUSES, report_id, export_workspace, import_workspace, printable_review, evidence_bundle
from scan_assets import validated_report


def render_scan(root: Path):
    path = root / 'assets/real_scan/report.json'
    if not path.exists():
        st.info('Chưa có hồ sơ xử lý ảnh thật được công bố.')
        return
    try:
        report = validated_report(root)
    except (ValueError, KeyError, TypeError, OSError):
        st.warning('Hồ sơ quan sát đang được kiểm tra. Chuyển sang Xem ảnh toàn cảnh; không sử dụng kết quả chưa xác thực.')
        return
    workspace_key = 'workspace_' + report_id(report)
    reviews = st.session_state.setdefault(workspace_key, {})
    day = report['observation_day_utc']
    day_label = date.fromisoformat(day).strftime('%d/%m/%Y')
    tiles = report['tiles']
    ready = [r for r in tiles if r['status'] == 'processed']
    if len(ready) < len(tiles):
        st.warning(f'{len(tiles)-len(ready)} ô chưa có bằng chứng hợp lệ và không được đưa vào danh sách kiểm tra. Không coi các ô này là không có tàu.')
    count = sum(len(r['detections']) for r in ready)
    st.subheader('Kiểm tra ảnh radar thật')
    st.caption('Chọn ảnh → xem ứng viên → lưu ghi chú và bằng chứng.')
    reviewed = sum(1 for value in reviews.values() if value.get('status') != STATUSES[0])
    follow_up = sum(1 for value in reviews.values() if value.get('status') == STATUSES[1])
    st.markdown(f'<div class="observation-meta"><span>Vùng thử nghiệm<strong>Bình Thuận</strong></span><span>Ngày ảnh (UTC)<strong>{day_label}</strong></span><span>Đã xử lý<strong>{len(ready)} / {len(tiles)} ô</strong></span><span>Ứng viên baseline<strong>{count}</strong></span><span>Đã xem<strong>{reviewed} ô</strong></span><span>Cần xem tiếp<strong>{follow_up} ô</strong></span></div>', unsafe_allow_html=True)
    model_hash = next((t.get('weights_sha256') for t in ready if t.get('weights_sha256')), '')
    st.caption(f"Mô hình: YOLO baseline học từ ảnh mô phỏng · mã {model_hash[:12] if model_hash else 'chưa có'}. Đây là ứng viên để người xem rà soát, không phải kết quả đã xác minh.")
    st.caption('Ảnh lưu trữ · Ứng viên chưa xác minh, không phải số tàu.')
    with st.expander('Lưu / mở lại phiên kiểm tra'):
        st.write('Tải hồ sơ phiên trước khi đóng trang. Có thể mở lại trên máy khác với đúng bộ ảnh; ghi chú không lưu vào cơ sở dữ liệu máy chủ.')
        upload = st.file_uploader('Mở hồ sơ phiên (.json)', type=['json'], key='restore_reviews')
        if st.button('Nạp ghi chú từ hồ sơ', disabled=upload is None):
            try:
                imported = import_workspace(upload.getvalue(), report)
                conflicts = set(imported) & set(reviews)
                if conflicts:
                    st.error('Có ô đã ghi chú trong phiên này. Để tránh ghi đè, chỉ nạp hồ sơ vào một phiên mới.')
                else:
                    reviews.update(imported)
                    for key, value in imported.items():
                        st.session_state[f'verdict_{key}'] = value['status']
                        st.session_state[f'note_{key}'] = value['note']
                    st.success(f'Đã nạp {len(imported)} ghi chú.')
            except ValueError as error:
                st.error(str(error))
        st.download_button('Lưu toàn bộ phiên kiểm tra', export_workspace(report, reviews), 'sonarnet-review-session.json', 'application/json')
    with st.expander('Cần biết trước khi dùng kết quả'):
        st.write('Mô hình công bố học trên ảnh mô phỏng, chưa kiểm chứng độ chính xác trên ảnh thật. Có ứng viên trên đất/bờ biển; chưa có mặt nạ loại đất hay nhãn xác minh. Không dùng kết quả để kết luận tàu cá hoặc vi phạm.')
        st.write('Đây là ảnh lưu trữ của một ngày quan sát, không phải ảnh mới nhất. Ảnh ghép trong ngày chưa có thời điểm riêng từng pixel. Không phát hiện không chứng minh không có tàu.')
    chart = folium.Map(tiles=None, zoom_snap=.25)
    folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', attr='Esri, Maxar, Earthstar Geographics').add_to(chart)
    for tile in tiles:
        w,s,e,n = tile['bbox']
        processed = tile['status'] == 'processed'
        summary = f"{len(tile['detections'])} ứng viên" if processed else 'Chưa xử lý được'
        review_status = reviews.get(tile['key'], {}).get('status', STATUSES[0])
        border = '#43c6b7' if review_status == STATUSES[2] else '#ff9f43' if review_status == STATUSES[1] else '#74869a'
        folium.Rectangle([[s,w],[n,e]], color=border if processed else '#efad48', weight=3 if review_status != STATUSES[0] else 2, fill=True, fill_opacity=.18,
                         tooltip=f"{tile['key']} · {review_status}", popup=f"{tile['key']} · {summary} · {day_label} UTC · {review_status}").add_to(chart)
        for d in tile.get('detections', []):
            folium.CircleMarker([d['latitude'],d['longitude']],radius=5,color='#ffb85c',fill=True,
                popup=f"{tile['key']} / #{d['id']} · điểm mô hình {d['confidence']:.2f} · chưa xác minh").add_to(chart)
    chart.fit_bounds([[6,102],[24,115]])
    with st.expander('Phạm vi đã quét trên Việt Nam', expanded=True):
        html(chart.get_root().render(), height=420)
        st.caption('Viền xám: chưa xem · cam: cần kiểm tra tiếp · xanh: đã xem, chưa thấy mục tiêu rõ.')
    if not ready:
        return
    by_key = {t['key']:t for t in sorted(ready, key=lambda t: -len(t['detections']))}
    chosen = st.selectbox('Ô ảnh cần kiểm tra', list(by_key), format_func=lambda key: f"{key.replace('cell_', 'Ô ')} · {len(by_key[key]['detections'])} ứng viên", key='review_tile')
    tile = by_key[chosen]
    original = st.toggle('Xem ảnh gốc không khung đánh dấu', value=False)
    st.image(str(root / tile['asset_dir'] / ('sar.png' if original else 'detections.jpg')), use_container_width=True,
             caption=f"{chosen} · Sentinel-1 VV · {tile['image_size'][0]} × {tile['image_size'][1]} px · ngưỡng {tile['confidence_threshold']}")
    if tile['detections']:
        detection = st.selectbox('Mở bằng chứng ứng viên', tile['detections'], format_func=lambda d: f"#{d['id']} · điểm mô hình {d['confidence']:.2f}")
        with Image.open(root / tile['asset_dir'] / 'sar.png') as image:
            x1,y1,x2,y2 = detection['bbox_px']
            crop = image.crop((max(0,int(x1)-24),max(0,int(y1)-24),min(image.width,int(x2)+24),min(image.height,int(y2)+24)))
            st.image(crop, caption='Ảnh cắt để kiểm tra trực quan — không phải xác nhận tàu cá', width=256)
        st.write(f"Tọa độ xấp xỉ: {detection['latitude']:.5f}, {detection['longitude']:.5f}. Chưa đối chiếu AIS.")
    else:
        st.info('YOLO không đề xuất ứng viên trong ô này ở ngưỡng 0,35. Vẫn cần kiểm tra ảnh; không được suy ra rằng vùng này không có tàu.')
    st.caption(f"Nguồn: {tile['source']} · WGS84: {tile['bbox']}. Ảnh ghép trong ngày, không có thời điểm riêng từng pixel.")
    saved = reviews.get(chosen, {'status': STATUSES[0], 'note': ''})
    with st.form(f'review_form_{chosen}'):
        verdict = st.radio('Đánh dấu của người xem', STATUSES, index=STATUSES.index(saved['status']), key=f'verdict_{chosen}')
        note = st.text_area('Ghi chú kiểm tra', value=saved['note'], max_chars=5000, key=f'note_{chosen}', placeholder='Ví dụ: có điểm sáng cần đối chiếu với ảnh độ phân giải cao hơn…')
        if st.form_submit_button('Lưu ghi chú ô ảnh'):
            reviews[chosen] = {'status': verdict, 'note': note}
            st.rerun()
    saved = reviews.get(chosen, {'status': STATUSES[0], 'note': ''})
    st.caption(f"Đã lưu trong phiên: {saved['status']}. Bấm lưu trước khi đổi ô. Tải hồ sơ để giữ lại sau khi đóng trang.")
    evidence = dict(tile, reviewer_status=saved['status'], reviewer_note=saved['note'], scan_report_date=report['generated_at'])
    st.download_button('Tải hồ sơ ô ảnh & ghi chú', json.dumps(evidence,ensure_ascii=False,indent=2), f'{chosen}-review.json', 'application/json')
    st.download_button('Tải bản đọc / in hồ sơ', printable_review(tile, saved, day_label), f'{chosen}-review.html', 'text/html')
    st.download_button('Tải gói bằng chứng kèm ảnh', evidence_bundle(root, tile, saved, day_label), f'{chosen}-evidence.zip', 'application/zip')
    st.caption('Gói ZIP gồm ảnh gốc, ảnh đánh dấu, hồ sơ đọc/in, dữ liệu JSON và mã kiểm tra SHA‑256. Ghi chú chỉ phản ánh đánh giá của người xem.')
    with st.expander('Thông tin toàn bộ lần quét'):
        st.write(f"Tất cả {len(tiles)} ô được chọn theo lưới cố định, không chọn lọc theo số phát hiện. Ô lỗi được ghi riêng, không tính là 0 tàu.")
        st.download_button('Tải báo cáo quét', path.read_bytes(), 'sonarnet-real-scan.json', 'application/json')
