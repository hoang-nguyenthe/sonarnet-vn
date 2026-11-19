"""Evidence-first review of real SAR processing, including negative results."""
import json
from datetime import date
from pathlib import Path
from io import BytesIO
from zipfile import BadZipFile

import folium
import streamlit as st
from PIL import Image
from streamlit.components.v1 import html
from demo_snapshot import load_snapshot
from review_workspace import (
    STATUSES, CANDIDATE_STATUSES, OPERATIONAL_DECISIONS, session_reviews, export_workspace,
    read_workspace, printable_review, evidence_bundle, read_review_images,
    confirm_operational_review, operational_assessment, source_time_caption,
)
from scan_assets import validated_report
from land_mask import add_map_layer, summary as land_summary
from observation_labels import tile_label


def render_scan(root: Path, *, fixed_sample=False):
    path = root / 'assets/real_scan/report.json'
    report, snapshot = None, None
    if not fixed_sample:
        try:
            with st.spinner('Đang kiểm chứng ảnh nguồn và mã băm. Lần mở đầu có thể lâu hơn.'):
                report = validated_report(root)
        except (ValueError, KeyError, TypeError, OSError):
            pass
    if report is None or not any(tile['status'] == 'processed' for tile in report['tiles']):
        try:
            fixed, snapshot, _ = load_snapshot(root)
        except (ValueError, KeyError, TypeError, OSError, BadZipFile):
            st.warning('Chưa có ảnh kiểm tra vượt qua xác minh tệp. Hãy mở trang Minh chứng cải tiến để thử các tình huống đối chứng.')
            return
        report = {'tiles':[fixed], 'observation_day_utc':fixed['observation_day_utc'],
                  'generated_at':fixed['generated_at']}
        info = 'Đang rà soát hồ sơ mẫu từ ảnh thật đã lưu.'
        if not fixed_sample:
            info += ' Kho ảnh chi tiết chưa sẵn sàng trong bản này.'
        st.info(info)
    reviews = session_reviews(st.session_state, report)
    current = st.session_state['review_active_identities']
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
    candidate_reviewed = sum(label != CANDIDATE_STATUSES[0] for review in reviews.values()
                             for label in review.get('candidate_labels', {}).values())
    st.subheader('Kiểm tra chi tiết')
    st.caption('Chọn ảnh → xem điểm nghi vấn → lưu ghi chú và bằng chứng.')
    st.markdown(f'<div class="observation-meta"><span>Ngày ảnh (UTC)<strong>{day_label}</strong></span><span>Ảnh có sẵn<strong>{len(ready)} ô</strong></span><span>Điểm cần kiểm tra<strong>{count}</strong></span><span>Đã đánh giá<strong>{candidate_reviewed}/{count} điểm</strong></span></div>', unsafe_allow_html=True)
    st.caption('Điểm nghi vấn chưa được xác minh, không phải số tàu.')
    with st.expander('Lưu / mở lại phiên kiểm tra'):
        bank = st.session_state['review_evidence_bank']
        st.write('Tệp phiên giữ cả ghi chú của ảnh đã thay đổi. Khi mở lại, hệ thống '
                 'phục hồi ghi chú còn khớp với đúng ảnh và kết quả.')
        archived_count = sum(key not in reviews or current.get(key) != identity
                             for key,identity in bank)
        if archived_count:
            st.caption(f'{archived_count} ghi chú của ảnh cũ được giữ trong tệp phiên.')
        upload = st.file_uploader('Mở hồ sơ phiên (.json)', type=['json'], key='restore_reviews')
        if st.button('Nạp ghi chú từ hồ sơ', disabled=upload is None):
            try:
                imported, unavailable, archived = read_workspace(upload.getvalue(), report)
            except ValueError as error:
                st.error(str(error))
            else:
                conflicts = set(imported) & reviews.keys()
                for identity, saved_note in archived.items():
                    bank.setdefault(identity, saved_note)
                for key, value in imported.items():
                    if key in conflicts:
                        continue
                    reviews[key] = value
                    context = f'{key}_{current[key]}'
                    st.session_state[f'verdict_{context}'] = value['status']
                    st.session_state[f'note_{context}'] = value['note']
                    notes = value.get('candidate_labels', {})
                    for widget in list(st.session_state):
                        if widget.startswith(f'candidate_status_{context}_'):
                            candidate_id = widget.removeprefix(f'candidate_status_{context}_')
                            st.session_state[widget] = notes.get(candidate_id, CANDIDATE_STATUSES[0])
                st.session_state['review_restore_notice'] = (len(imported)-len(conflicts),
                    len(unavailable), len(archived), len(conflicts))
                st.rerun()
        st.download_button('Lưu toàn bộ phiên kiểm tra', export_workspace(report, reviews, archived=bank),
                           'sonarnet-review-session.json', 'application/json')
    notice = st.session_state.pop('review_restore_notice', None)
    if notice is not None:
        restored, unavailable, saved_old, conflicts = notice
        st.info(f'Đã nạp {restored} ghi chú. Có {unavailable} ghi chú của ảnh hiện không khớp, '
                f'trong đó {saved_old} được giữ để phục hồi sau. '
                f'{conflicts} ô giữ ghi chú đang có trong phiên.')
        if unavailable > saved_old:
            st.caption('Các ghi chú chưa có mã kiểm chứng đầy đủ vẫn nằm trong tệp đã chọn.')
    with st.expander('Cần biết trước khi dùng kết quả'):
        st.write('Hệ thống nhận diện chưa được kiểm chứng đủ để dùng cho quyết định nghiệp vụ. Đất liền và vùng 500 m từ bờ ra biển được bỏ qua, bao gồm tàu trong cảng và sát bờ. Đường bờ phiên bản 2017 có thể khác thực địa hiện tại, nhất là khu lấn biển. Không dùng kết quả để kết luận tàu cá hoặc vi phạm.')
        st.caption(land_summary(ready))
        st.write('Mỗi ô giữ ngày quan sát của chính ảnh đó. Lịch kiểm tra 6 giờ giữ lại ảnh cũ nếu chưa có ảnh mới hợp lệ. Ảnh ghép trong ngày chưa có thời điểm riêng từng pixel. Không phát hiện không chứng minh không có tàu.')
    if snapshot is None and st.toggle('Hiện bản đồ các ảnh đã kiểm tra', key='review_show_map'):
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
                folium.CircleMarker([d['latitude'],d['longitude']],radius=5,color=dot_color,weight=1.5,fill=False,
                    popup=f"{tile['key']} / #{d['id']} · {label}").add_to(chart)
        add_map_layer(chart, root, detail_bounds=[t['bbox'] for t in ready])
        chart.fit_bounds([[6,102],[24,115]])
        from place_labels import add_place_labels
        add_place_labels(chart)
        folium.LayerControl(collapsed=True).add_to(chart)
        html(chart.get_root().render(), height=420)
        st.caption('Viền xám: chưa xem · cam: cần kiểm tra tiếp · xanh: đã xem, chưa thấy mục tiêu rõ.')
    if not ready:
        return
    by_key = {t['key']:t for t in sorted(ready, key=lambda t: -len(t['detections']))}
    chosen = st.selectbox('Chọn ảnh', list(by_key), format_func=lambda key: tile_label(by_key[key]), key='review_tile')
    tile = by_key[chosen]
    context = f'{chosen}_{current[chosen]}'
    st.caption(f"Ngày ảnh đã chọn: {date.fromisoformat(tile['observation_day_utc']).strftime('%d/%m/%Y')} UTC · Copernicus")
    try:
        images = snapshot if snapshot is not None else read_review_images(root,tile)
    except (OSError, ValueError):
        st.warning('Ảnh đang cập nhật hoặc không đọc được. Mở lại ô ảnh để kiểm tra lại bằng chứng.')
        return
    image_views = ('Ảnh có khung trong hồ sơ' if snapshot else 'Trong phạm vi bản đồ',
                   'Ảnh radar nguồn', 'Dự đoán gốc')
    view = st.radio('Lớp hiển thị', image_views, horizontal=True, key='review_image_view')
    image_names = ('candidates.jpg','source.png','raw-model-candidates.jpg')
    displayed = images[image_names[image_views.index(view)]]
    st.image(displayed, width=704, caption=f'{tile_label(tile)} · {view}')
    if view == image_views[2] and snapshot is None:
        excluded = tile.get('excluded_detections', [])
        coast = sum(d.get('surface') == 'excluded_coast' for d in excluded)
        st.warning(f'Dự đoán trước lọc. Bản đồ đã loại {len(excluded)} ứng viên, gồm {coast} điểm trong dải ven bờ. Mọi ứng viên đều cần rà soát.')
    if tile['detections']:
        target = st.session_state.pop('review_target_id', None)
        target_index = next((i for i, d in enumerate(tile['detections']) if str(d['id']) == target), 0)
        candidate_key = f'review_candidate_{context}'
        if target is not None:
            st.session_state[candidate_key] = tile['detections'][target_index]
        detection = st.selectbox('Mở điểm cần kiểm tra', tile['detections'],
                                 format_func=lambda d: f"Điểm {d['id']}", key=candidate_key)
        original = BytesIO(images['source.png'])
        with Image.open(original) as image:
            x1,y1,x2,y2 = detection['bbox_px']
            crop = image.crop((max(0,int(x1)-24),max(0,int(y1)-24),min(image.width,int(x2)+24),min(image.height,int(y2)+24)))
            st.image(crop, caption='Ảnh cắt để kiểm tra trực quan — không phải xác nhận tàu cá', width=256)
        st.write(f"Tọa độ xấp xỉ: {detection['latitude']:.5f}, {detection['longitude']:.5f}. Thông tin tàu chưa xác định.")
        candidate_labels = reviews.get(chosen, {}).get('candidate_labels', {})
        selected_label = candidate_labels.get(str(detection['id']), CANDIDATE_STATUSES[0])
        with st.form(f'candidate_form_{context}_{detection["id"]}'):
            candidate_status = st.radio('Bạn thấy gì trong ảnh?', CANDIDATE_STATUSES, index=CANDIDATE_STATUSES.index(selected_label), key=f'candidate_status_{context}_{detection["id"]}')
            if st.form_submit_button('Lưu đánh giá'):
                if candidate_status == CANDIDATE_STATUSES[0]:
                    candidate_labels.pop(str(detection['id']), None)
                else:
                    review = reviews.setdefault(chosen, {'status': STATUSES[0], 'note': ''})
                    review.setdefault('candidate_labels', {})[str(detection['id'])] = candidate_status
                st.rerun()
        st.caption('Đây là đánh giá thủ công để tạo dữ liệu kiểm chứng, không phải nhãn sự thật hay kết luận tàu cá.')
    else:
        st.info('Chưa có điểm cần kiểm tra ngoài vùng bỏ qua trên đất và sát bờ. Không được suy ra rằng vùng này không có tàu.')
    st.caption(f"Nguồn {tile['source']}. {source_time_caption(tile)}")
    saved = reviews.get(chosen, {'status': STATUSES[0], 'note': ''})
    with st.form(f'review_form_{context}'):
        verdict = st.radio('Đánh dấu của người xem', STATUSES, index=STATUSES.index(saved['status']), key=f'verdict_{context}')
        note = st.text_area('Ghi chú kiểm tra', value=saved['note'], max_chars=5000, key=f'note_{context}', placeholder='Ví dụ: có điểm sáng cần đối chiếu với ảnh độ phân giải cao hơn…')
        if st.form_submit_button('Lưu ghi chú ô ảnh'):
            # Preserve candidate-level decisions when the tile-level verdict
            # is saved afterwards.  Without this, a normal workflow of
            # labelling a candidate then saving the tile would silently erase
            # the candidate review from the map and exported session.
            candidate_labels = reviews.get(chosen, {}).get('candidate_labels', {})
            previous_operational = reviews.get(chosen, {}).get('operational_review')
            reviews[chosen] = {'status': verdict, 'note': note}
            if candidate_labels:
                reviews[chosen]['candidate_labels'] = candidate_labels
            if previous_operational:
                reviews[chosen]['operational_review'] = previous_operational
            st.rerun()
    saved = reviews.get(chosen, {'status': STATUSES[0], 'note': ''})
    with st.expander('Xác nhận của chuyên viên'):
        st.caption('Thiếu dữ liệu AIS cùng thời điểm. Đánh giá ảnh không xác nhận danh tính hay hành vi. Danh tính chuyên viên tự khai; ứng dụng chưa xác thực tài khoản hoặc ký số.')
        current = operational_assessment(tile, saved)
        st.write('Đang xác minh; chưa có kết luận nghiệp vụ' if current['status'] == 'pending' else
                 f"Đã ghi nhận: {current['conclusion']} · {current['reviewer']}")
        with st.form(f'operational_{context}_form'):
            reviewer = st.text_input('Tên chuyên viên xác nhận', max_chars=200, key=f'operational_{context}_name')
            decision = st.selectbox('Hướng xử lý sau rà soát', OPERATIONAL_DECISIONS, key=f'operational_{context}_decision')
            basis = st.text_area('Căn cứ kiểm tra / tài liệu đối chiếu', max_chars=5000, key=f'operational_{context}_basis')
            checked = st.checkbox('Tôi đã xem bằng chứng và chịu trách nhiệm về đánh giá này', key=f'operational_{context}_confirm')
            if st.form_submit_button('Xác nhận hướng xử lý'):
                try:
                    assessment = confirm_operational_review(tile, reviewer, decision, basis, checked)
                    reviews.setdefault(chosen, {'status': STATUSES[0], 'note': ''})['operational_review'] = assessment
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))
    saved = reviews.get(chosen, {'status': STATUSES[0], 'note': ''})
    st.caption(f"Đã lưu trong phiên: {saved['status']}. Bấm lưu trước khi đổi ô. Tải hồ sơ để giữ lại sau khi đóng trang.")
    evidence = dict(tile, reviewer_status=saved['status'], reviewer_note=saved['note'], scan_report_date=report['generated_at'],
                    data_status='MISSING_DATA', operational_assessment=operational_assessment(tile, saved),
                    candidate_labels=saved.get('candidate_labels', {}))
    st.download_button('Tải hồ sơ kèm ảnh', evidence_bundle(root,tile,saved,day_label,fixed_images=images),
                       f'{chosen}-evidence.zip', 'application/zip', type='primary')
    st.caption('Gồm ảnh gốc, ảnh đánh dấu và ghi chú của bạn. Tải xuống để giữ hồ sơ sau khi đóng trang.')
    with st.expander('Thông tin ảnh và lần quét'):
        st.download_button('Tải dữ liệu ô ảnh', json.dumps(evidence,ensure_ascii=False,indent=2), f'{chosen}-review.json', 'application/json')
        st.download_button('Tải bản đọc / in hồ sơ', printable_review(tile, saved, day_label), f'{chosen}-review.html', 'text/html')
        if snapshot is None:
            st.write(f"Tất cả {len(tiles)} ô được chọn theo lưới cố định, không chọn lọc theo số phát hiện. Ô lỗi được ghi riêng, không tính là 0 tàu.")
            st.download_button('Tải báo cáo quét', path.read_bytes(), 'sonarnet-real-scan.json', 'application/json')
