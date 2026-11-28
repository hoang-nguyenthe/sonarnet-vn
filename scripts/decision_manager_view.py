"""Manage decisions on the same observed points that appear on the public map."""
from hashlib import sha256
import json
import sqlite3

import pandas as pd
import streamlit as st

from decision_access import manager_is_signed_in, require_manager, sign_out
from manager_decisions import (
    DecisionConflict, PENDING, database_path, decision_history, point_decisions,
    read_snapshot, save_decision,
)
from observation_labels import coordinates, observation_time
from observation_view import candidate_crop, local_time, published_layers, published_yolo_result
from review_workspace import OPERATIONAL_DECISIONS, tile_identity
from scan_assets import resolve_scan_directory, validate_tile


def verified_source(root, tile):
    validate_tile(root, tile)
    source = (resolve_scan_directory(root, tile) / 'sar.png').read_bytes()
    if sha256(source).hexdigest() != tile['image_sha256']:
        raise ValueError('Ảnh nguồn đã thay đổi.')
    return source


def render(root, open_observation):
    st.subheader('Quản lý quyết định')
    st.write('Xem ảnh nguồn của điểm cần rà, ghi hướng xử lý và cập nhật tab Quan sát.')
    if not require_manager():
        return
    st.button('Thoát quyền quản lý', on_click=sign_out)
    regions = {area['key']: area for area in published_layers(root)}
    if not regions:
        st.info('Chưa có khu vực với ảnh công bố để rà soát.')
        return
    region = st.selectbox('Khu vực', list(regions), key='manager_region',
                          format_func=lambda key: regions[key]['label'])
    result = published_yolo_result(root, regions[region])
    if not result or not result['detections']:
        st.info('Khu vực này chưa có điểm trên ảnh chi tiết đã công bố.')
        return
    path = database_path(root)
    try:
        _, published = read_snapshot(path)
    except (OSError, sqlite3.Error):
        st.error('Kho quyết định chưa đọc được. Thử lại trước khi ghi hướng xử lý.')
        return
    decisions = point_decisions(result, published)
    available = result['detections']
    pending_count = len(available) - len(decisions)
    first, second = st.columns(2)
    first.metric('Chưa có quyết định', pending_count)
    second.metric('Đã có quyết định', len(decisions))
    filter_mode = st.radio('Lọc hàng rà', ('Tất cả', 'Chưa có quyết định', 'Đã có quyết định'),
                           horizontal=True, key='manager_filter')
    candidates = {point['id']: point for point in available if
                  filter_mode == 'Tất cả' or (point['id'] in decisions) == (filter_mode == 'Đã có quyết định')}
    if not candidates:
        st.info('Không có điểm trong nhóm này.')
        return
    point_id = st.selectbox(
        'Điểm cần rà', list(candidates), key='manager_point',
        format_func=lambda key: f"{key} · {coordinates(candidates[key]['latitude'], candidates[key]['longitude'])} · "
                                f"{observation_time(candidates[key])}",
    )
    point = candidates[point_id]
    tile = next(item for item in result['tiles'] if item['key'] == point['tile_key'])
    identity = tile_identity(tile)
    decision = decisions.get(point_id)
    try:
        source = verified_source(root, tile)
        crop = candidate_crop(root, point, image_bytes=source, outline=True)
    except (OSError, ValueError, KeyError, TypeError):
        st.warning('Ảnh nguồn chưa xác minh được. Chọn điểm khác hoặc mở lại sau khi đồng bộ ảnh.')
        return
    preview, form = st.columns([1, 2])
    with preview:
        st.image(crop, width='stretch', caption='Ảnh SAR · khung xanh là vùng mô hình đánh dấu')
        st.caption(f"{point_id} · {observation_time(point)} · Điểm phát hiện SAR {point['confidence']:.2f}/1")
        st.code(tile['image_sha256'], wrap_lines=True)
        st.button('Mở điểm này trên Quan sát', on_click=open_observation,
                  args=(regions[region]['label'], point_id))
    with form:
        st.markdown('#### Hướng xử lý')
        st.write(decision['outcome'] if decision else PENDING)
        if decision:
            st.text(decision['basis'])
            st.caption(local_time(decision['decided_at']))
        notice = st.session_state.pop('decision_saved', None)
        if notice:
            st.success(f'Đã cập nhật {notice} trên tab Quan sát.')
        revision = decision['revision'] if decision else 0
        with st.form(f'manager-decision-{identity}-{point_id}-{revision}'):
            outcome = st.selectbox('Chọn hướng xử lý', OPERATIONAL_DECISIONS,
                                   index=OPERATIONAL_DECISIONS.index(decision['outcome']) if decision else None,
                                   placeholder='Chọn một hướng xử lý')
            basis = st.text_area('Căn cứ hiển thị trên Quan sát', max_chars=1200,
                                 placeholder='Ghi dấu hiệu nhìn thấy trên ảnh hoặc dữ liệu cần bổ sung.')
            st.caption('Bản đồ công khai hiển thị hướng xử lý, căn cứ và thời điểm ghi nhận.')
            confirmed = st.checkbox('Tôi đã kiểm tra đúng điểm và ảnh nguồn.')
            saved = st.form_submit_button('Lưu và cập nhật bản đồ', type='primary')
        if saved:
            if not manager_is_signed_in():
                st.error('Phiên quản lý đã hết. Mở lại bằng mã truy cập.')
            elif not confirmed:
                st.error('Xác nhận đã xem ảnh nguồn trước khi lưu.')
            else:
                try:
                    save_decision(path, tile, point_id, outcome, basis, revision)
                except DecisionConflict as error:
                    st.warning(str(error))
                except ValueError as error:
                    st.error(str(error))
                except (OSError, sqlite3.Error):
                    st.error('Chưa ghi được vào kho quyết định. Thử lưu lại.')
                else:
                    st.session_state['decision_saved'] = point_id
                    st.rerun()
    with st.expander('Lịch sử quyết định của điểm này'):
        rows = [{'Hướng xử lý': item['outcome'], 'Căn cứ': item['basis'],
                 'Thời điểm': local_time(item['decided_at'])}
                for item in decision_history(path, point_id, identity)]
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')
            archive = json.dumps({'point_id': point_id, 'evidence_id': identity, 'history': rows}, ensure_ascii=False, indent=2)
            st.download_button('Tải lịch sử điểm', archive, 'sonarnet-lich-su-diem.json', 'application/json')
        else:
            st.caption('Chưa ghi nhận quyết định cho ảnh nguồn này.')
