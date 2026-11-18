"""Open a pinned, previously published SAR observation without the map or API."""
from functools import lru_cache
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from PIL import Image
import streamlit as st

ARCHIVE_SHA256 = '09a64b8c0e2fe5a86b4496c1abf9901ba3cede8bab6bdc5f11f12c85ad87c1bc'
MAX_BUNDLE = 8 * 1024**2
MEMBERS = {'evidence.json', 'source.png', 'candidates.jpg', 'raw-model-candidates.jpg', 'review.html', 'checksums.json'}


@lru_cache(maxsize=4)
def _read(path, fingerprint):
    payload = path.read_bytes()
    if len(payload) > MAX_BUNDLE or sha256(payload).hexdigest() != ARCHIVE_SHA256:
        raise ValueError('Mã băm tệp mẫu không khớp')
    with ZipFile(BytesIO(payload)) as archive:
        members = archive.infolist()
        if {m.filename for m in members} != MEMBERS or len(members) != len(MEMBERS):
            raise ValueError('Danh sách thành viên ZIP không đúng')
        if any(m.file_size > MAX_BUNDLE or m.is_dir() for m in members) or sum(m.file_size for m in members) > MAX_BUNDLE:
            raise ValueError('Tệp mẫu vượt giới hạn bộ nhớ')
        items = {m.filename: archive.read(m) for m in members}
    checksum = json.loads(items['checksums.json'])
    if checksum != {k:sha256(v).hexdigest() for k,v in items.items() if k!='checksums.json'}:
        raise ValueError('Một thành phần không khớp mã băm')
    evidence = json.loads(items['evidence.json'])
    if (evidence['key'] != 'cell_0_1' or evidence['image_sha256'] != checksum['source.png'] or
        evidence['data_status'] != 'MISSING_DATA' or evidence['operational_assessment'].get('status') != 'pending' or
        evidence['operational_assessment'].get('conclusion') is not None):
        raise ValueError('Bản sao không phải hồ sơ chưa xác minh đã khóa')
    for k in ('source.png','candidates.jpg'):
        with Image.open(BytesIO(items[k])) as im:
            if list(im.size) != evidence['image_size']:
                raise ValueError('Kích thước ảnh không khớp')
            im.verify()
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
