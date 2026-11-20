"""Open a pinned, previously published SAR observation without the map or API."""
from functools import lru_cache
from pathlib import Path
from zipfile import BadZipFile

import streamlit as st

from review_packet import read_evidence_packet

ARCHIVE_SHA256 = '09a64b8c0e2fe5a86b4496c1abf9901ba3cede8bab6bdc5f11f12c85ad87c1bc'
MAX_BUNDLE = 8 * 1024**2


@lru_cache(maxsize=4)
def _read(path, fingerprint):
    payload = path.read_bytes()
    evidence, items, _ = read_evidence_packet(
        payload, expected_sha256=ARCHIVE_SHA256, max_bytes=MAX_BUNDLE
    )
    if evidence.get('key') != 'cell_0_1' or evidence['operational_assessment']['status'] != 'pending':
        raise ValueError('Bản sao không phải hồ sơ chưa xác minh đã khóa')
    return evidence, items, payload


def load_snapshot(root: Path):
    path = root / 'reports/final/export_verification/sample_evidence.zip'
    s = path.stat()
    if s.st_size > MAX_BUNDLE:
        raise ValueError('Tệp mẫu vượt giới hạn bộ nhớ')
    return _read(path, (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns))


def render_snapshot(root: Path):
    st.subheader('Mở nhanh một hồ sơ ảnh thật')
    st.caption('Bản sao cố định của một ô đã công bố. Không tải dữ liệu trực tiếp và không thay cho rà soát từng ảnh.')
    try:
        evidence, files, payload = load_snapshot(root)
    except (OSError, TypeError, KeyError, ValueError, BadZipFile):
        st.warning('Ảnh mẫu không có sẵn hoặc không vượt qua kiểm tra tệp. Không hiển thị ảnh thay thế.')
        return
    st.write(f"**Ảnh {evidence['key']} · {evidence['observation_day_utc']} UTC**")
    st.caption(f"Nguồn: {evidence['source']}. Ảnh ghép trong ngày, chưa có thời điểm riêng cho từng điểm ảnh.")
    highlighted = st.toggle('Xem ảnh có đánh dấu ứng viên', value=False, key='snapshot_highlight')
    st.image(files['candidates.jpg' if highlighted else 'source.png'], width=520,
             caption='Ảnh có khung ứng viên · chưa xác minh' if highlighted else 'Ảnh radar gốc dùng trong hồ sơ mẫu')
    st.info('Thiếu dữ liệu AIS · Đang xác minh · Chưa có kết luận nghiệp vụ.')
    st.download_button('Tải ZIP ảnh và hồ sơ mẫu',payload,'sonarnet-ho-so-mau-cell-0-1.zip','application/zip',key='snapshot_zip')
    with st.expander('Nguồn và mã kiểm chứng'):
        st.code(f"Ảnh SHA-256: {evidence['image_sha256']}\nMô hình SHA-256: {evidence['weights_sha256']}\nZIP SHA-256: {ARCHIVE_SHA256}")
