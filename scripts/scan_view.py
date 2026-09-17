"""Evidence-first review of real SAR processing, including negative results."""
import json
from datetime import date
from pathlib import Path

import folium
import streamlit as st
from PIL import Image
from streamlit.components.v1 import html
from review_workspace import STATUSES, CANDIDATE_STATUSES, report_id, export_workspace, import_workspace, printable_review, evidence_bundle
from scan_assets import validated_report
from land_mask import add_map_layer, annotated_image, summary as land_summary


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
    observation_days = sorted({r['observation_day_utc'] for r in ready})
    if observation_days:
        day_label = ' → '.join(date.fromisoformat(d).strftime('%d/%m/%Y') for d in sorted({observation_days[0], observation_days[-1]}))
    if len(ready) < len(tiles):
        st.warning(f'{len(tiles)-len(ready)} ô chưa có bằng chứng hợp lệ và không được đưa vào danh sách kiểm tra. Không coi các ô này là không có tàu.')
    count = sum(len(r['detections']) for r in ready)
    candidate_reviewed = sum(len(v.get('candidate_labels', {})) for v in reviews.values())
    st.subheader('Kiểm tra chi tiết')
    st.caption('Chọn ảnh → xem điểm nghi vấn → lưu ghi chú và bằng chứng.')
    reviewed = sum(1 for value in reviews.values() if value.get('status') != STATUSES[0])
    follow_up = sum(1 for value in reviews.values() if value.get('status') == STATUSES[1])
    st.markdown(f'<div class="observation-meta"><span>Ngày ảnh (UTC)<strong>{day_label}</strong></span><span>Ảnh có sẵn<strong>{len(ready)} ô</strong></span><span>Điểm cần kiểm tra<strong>{count}</strong></span><span>Đã đánh giá<strong>{candidate_reviewed}/{count} điểm</strong></span></div>', unsafe_allow_html=True)
    model_hash = next((t.get('weights_sha256') for t in ready if t.get('weights_sha256')), '')
    st.caption('Điểm nghi vấn chưa được xác minh, không phải số tàu.')
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
        st.write('Hệ thống nhận diện chưa được kiểm chứng đủ để dùng cho quyết định nghiệp vụ. Đất liền và vùng 500 m từ bờ ra biển được bỏ qua, bao gồm tàu trong cảng và sát bờ. Đường bờ phiên bản 2017 có thể khác thực địa hiện tại, nhất là khu lấn biển. Không dùng kết quả để kết luận tàu cá hoặc vi phạm.')
        st.caption(land_summary(ready))
        st.write('Mỗi ô giữ ngày quan sát của chính ảnh đó. Lịch kiểm tra 6 giờ giữ lại ảnh cũ nếu chưa có ảnh mới hợp lệ. Ảnh ghép trong ngày chưa có thời điểm riêng từng pixel. Không phát hiện không chứng minh không có tàu.')
    chart = folium.Map(tiles=None, zoom_snap=.25)
    folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', attr='Esri, Maxar, Earthstar Geographics').add_to(chart)
    for tile in tiles:
        w,s,e,n = tile['bbox']
        processed = tile['status'] == 'processed'
        summary = f"{len(tile['detections'])} điểm cần kiểm tra" if processed else 'Chưa xử lý được'
        review_status = reviews.get(tile['key'], {}).get('status', STATUSES[0])
        border = '#43c6b7' if review_status == STATUSES[2] else '#ff9f43' if review_status == STATUSES[1] else '#74869a'
        folium.Rectangle([[s,w],[n,e]], color=border if processed else '#efad48', weight=3 if review_status != STATUSES[0] else 2, fill=True, fill_opacity=.18,
                         tooltip=f"{tile['key']} · {review_status}", popup=f"{tile['key']} · {summary} · {tile.get('observation_day_utc', 'Chưa rõ')} UTC · {review_status}").add_to(chart)
        for d in tile.get('detections', []):
            label = reviews.get(tile['key'], {}).get('candidate_labels', {}).get(str(d['id']), CANDIDATE_STATUSES[0])
            dot_color = '#45c9b8' if label == CANDIDATE_STATUSES[1] else '#ea6b61' if label == CANDIDATE_STATUSES[2] else '#ffb85c'
            folium.CircleMarker([d['latitude'],d['longitude']],radius=5,color=dot_color,fill=True,
                popup=f"{tile['key']} / #{d['id']} · {label}").add_to(chart)
    add_map_layer(chart, root)
    chart.fit_bounds([[6,102],[24,115]])
    from maritime_reference import add_reference
    add_reference(chart, root)
    folium.LayerControl(collapsed=True).add_to(chart)
    with st.expander('Vị trí các ảnh đã kiểm tra', expanded=False):
        html(chart.get_root().render(), height=420)
        st.caption('Viền xám: chưa xem · cam: cần kiểm tra tiếp · xanh: đã xem, chưa thấy mục tiêu rõ.')
    if not ready:
        return
    by_key = {t['key']:t for t in sorted(ready, key=lambda t: -len(t['detections']))}
    chosen = st.selectbox('Chọn ảnh', list(by_key), format_func=lambda key: f"{key.replace('cell_', 'Ô ')} · {len(by_key[key]['detections'])} điểm cần kiểm tra", key='review_tile')
    tile = by_key[chosen]
    st.caption(f"Ngày ảnh đã chọn: {date.fromisoformat(tile['observation_day_utc']).strftime('%d/%m/%Y')} UTC · Copernicus")
    original = st.toggle('Xem ảnh gốc không khung đánh dấu', value=False)
    st.image(str(root / tile['asset_dir'] / 'sar.png') if original else annotated_image(root, tile), use_container_width=True,
             caption=f"{chosen} · Ảnh radar gốc và các vùng cần kiểm tra")
    if tile['detections']:
        target = st.session_state.pop('review_target_id', None)
        target_index = next((i for i, d in enumerate(tile['detections']) if str(d['id']) == target), 0)
        detection = st.selectbox('Mở điểm cần kiểm tra', tile['detections'], index=target_index, format_func=lambda d: f"Điểm {d['id']}")
        with Image.open(root / tile['asset_dir'] / 'sar.png') as image:
            x1,y1,x2,y2 = detection['bbox_px']
            crop = image.crop((max(0,int(x1)-24),max(0,int(y1)-24),min(image.width,int(x2)+24),min(image.height,int(y2)+24)))
            st.image(crop, caption='Ảnh cắt để kiểm tra trực quan — không phải xác nhận tàu cá', width=256)
        st.write(f"Tọa độ xấp xỉ: {detection['latitude']:.5f}, {detection['longitude']:.5f}. Thông tin tàu chưa xác định.")
        review_state = reviews.setdefault(chosen, {'status': STATUSES[0], 'note': ''})
        candidate_labels = review_state.setdefault('candidate_labels', {})
        selected_label = candidate_labels.get(str(detection['id']), CANDIDATE_STATUSES[0])
        with st.form(f'candidate_form_{chosen}_{detection["id"]}'):
            candidate_status = st.radio('Bạn thấy gì trong ảnh?', CANDIDATE_STATUSES, index=CANDIDATE_STATUSES.index(selected_label), key=f'candidate_status_{chosen}_{detection["id"]}')
            if st.form_submit_button('Lưu đánh giá'):
                reviews.setdefault(chosen, {}).setdefault('candidate_labels', {})[str(detection['id'])] = candidate_status
                st.rerun()
        st.caption('Đây là đánh giá thủ công để tạo dữ liệu kiểm chứng, không phải nhãn sự thật hay kết luận tàu cá.')
    else:
        st.info('Chưa có điểm cần kiểm tra ngoài vùng bỏ qua trên đất và sát bờ. Không được suy ra rằng vùng này không có tàu.')
    st.caption(f"Nguồn: {tile['source']}. Ảnh ghép trong ngày, chưa có thời điểm riêng từng điểm ảnh.")
    saved = reviews.get(chosen, {'status': STATUSES[0], 'note': ''})
    with st.form(f'review_form_{chosen}'):
        verdict = st.radio('Đánh dấu của người xem', STATUSES, index=STATUSES.index(saved['status']), key=f'verdict_{chosen}')
        note = st.text_area('Ghi chú kiểm tra', value=saved['note'], max_chars=5000, key=f'note_{chosen}', placeholder='Ví dụ: có điểm sáng cần đối chiếu với ảnh độ phân giải cao hơn…')
        if st.form_submit_button('Lưu ghi chú ô ảnh'):
            # Preserve candidate-level decisions when the tile-level verdict
            # is saved afterwards.  Without this, a normal workflow of
            # labelling a candidate then saving the tile would silently erase
            # the candidate review from the map and exported session.
            candidate_labels = reviews.get(chosen, {}).get('candidate_labels', {})
            reviews[chosen] = {'status': verdict, 'note': note}
            if candidate_labels:
                reviews[chosen]['candidate_labels'] = candidate_labels
            st.rerun()
    saved = reviews.get(chosen, {'status': STATUSES[0], 'note': ''})
    st.caption(f"Đã lưu trong phiên: {saved['status']}. Bấm lưu trước khi đổi ô. Tải hồ sơ để giữ lại sau khi đóng trang.")
    evidence = dict(tile, reviewer_status=saved['status'], reviewer_note=saved['note'], scan_report_date=report['generated_at'])
    st.download_button('Tải hồ sơ kèm ảnh', evidence_bundle(root, tile, saved, day_label), f'{chosen}-evidence.zip', 'application/zip', type='primary')
    st.caption('Gồm ảnh gốc, ảnh đánh dấu và ghi chú của bạn. Tải xuống để giữ hồ sơ sau khi đóng trang.')
    with st.expander('Thông tin toàn bộ lần quét'):
        st.download_button('Tải dữ liệu ô ảnh', json.dumps(evidence,ensure_ascii=False,indent=2), f'{chosen}-review.json', 'application/json')
        st.download_button('Tải bản đọc / in hồ sơ', printable_review(tile, saved, day_label), f'{chosen}-review.html', 'text/html')
        st.write(f"Tất cả {len(tiles)} ô được chọn theo lưới cố định, không chọn lọc theo số phát hiện. Ô lỗi được ghi riêng, không tính là 0 tàu.")
        st.download_button('Tải báo cáo quét', path.read_bytes(), 'sonarnet-real-scan.json', 'application/json')
