"""Portable review state bound to exact processed images, with no server storage."""
import hashlib
import html
import json
from io import BytesIO
import zipfile
from copy import deepcopy
from datetime import date

STATUSES = ['Chưa xem xét', 'Cần kiểm tra tiếp', 'Đã xem, chưa thấy mục tiêu rõ']
CANDIDATE_STATUSES = ['Chưa đánh giá', 'Có khả năng là tàu', 'Nhiễu / không phải tàu']


def session_reviews(state, report):
    """Keep reviews across appended observations, isolated by exact evidence.

    Older evidence stays in session memory and becomes available again if
    that exact observation is restored. Never copy verdicts to changed pixels.
    """
    bank = state.setdefault('review_evidence_bank', {})
    previous = state.get('review_active_identities', {})
    for key, review in state.get('review_active_notes', {}).items():
        if key in previous:
            bank[(key, previous[key])] = deepcopy(review)
    current = {t['key']: tile_identity(t) for t in report['tiles']
               if t['status'] == 'processed'}
    if not previous:
        legacy = state.get('workspace_' + report_id(report), {})
        for key, review in legacy.items():
            if key in current:
                bank[(key, current[key])] = deepcopy(review)
    if current == previous and 'review_active_notes' in state:
        return state['review_active_notes']
    for key in set(previous) | set(current):
        if previous.get(key) != current.get(key):
            # Streamlit widgets otherwise retain the previous image's verdict.
            for widget in list(state):
                if widget in (f'verdict_{key}', f'note_{key}') or widget.startswith(f'candidate_status_{key}_'):
                    del state[widget]
    notes = {key: deepcopy(bank[(key, identity)]) for key, identity in current.items()
             if (key, identity) in bank}
    state['review_active_identities'] = current
    state['review_active_notes'] = notes
    return notes


def report_id(report):
    identity = sorted((t['key'], tile_identity(t)) for t in report['tiles'])
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def tile_identity(tile):
    fields = ('image_sha256', 'weights_sha256', 'land_mask_version',
              'inference_policy_sha256', 'bbox', 'observation_day_utc', 'detections')
    payload = {key: tile.get(key) for key in fields}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def export_workspace(report, reviews):
    return json.dumps({'schema_version': 2, 'report_id': report_id(report),
                       'tile_identities': {t['key']: tile_identity(t) for t in report['tiles']},
                       'reviews': reviews}, ensure_ascii=False, indent=2)


def import_workspace(raw, report):
    if len(raw) > 1_000_000:
        raise ValueError('Hồ sơ quá lớn (giới hạn 1 MB).')
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError):
        raise ValueError('Tệp không phải JSON hợp lệ.') from None
    if not isinstance(data, dict):
        raise ValueError('Hồ sơ không thuộc đúng bộ ảnh và mô hình này.')
    if data.get('schema_version') == 1:
        old_identity = [(t['key'], t.get('image_sha256'), t.get('weights_sha256'), t.get('land_mask_version')) for t in report['tiles']]
        old_id = hashlib.sha256(json.dumps(old_identity, sort_keys=True).encode()).hexdigest()
        if data.get('report_id') != old_id:
            raise ValueError('Hồ sơ cũ cần đúng bộ ảnh ban đầu để mở lại.')
    elif data.get('schema_version') == 2:
        identities = data.get('tile_identities')
        current = {t['key']: tile_identity(t) for t in report['tiles']}
        if not isinstance(identities, dict) or not identities:
            raise ValueError('Hồ sơ thiếu mã kiểm chứng ảnh.')
        # Appending observations must not invalidate the user's old notes.
        # Changing an existing image, policy, bounds or candidates must.
        if any(current.get(key) != digest for key, digest in identities.items()):
            raise ValueError('Ảnh hoặc kết quả trong hồ sơ đã thay đổi; không gắn ghi chú cũ vào bằng chứng mới.')
    else:
        raise ValueError('Phiên bản hồ sơ chưa được hỗ trợ.')
    reviews = data.get('reviews')
    if not isinstance(reviews, dict):
        raise ValueError('Danh sách ghi chú không hợp lệ.')
    allowed = {t['key'] for t in report['tiles'] if t['status']=='processed'}
    for key, item in reviews.items():
        if key not in allowed or not isinstance(item, dict):
            raise ValueError('Hồ sơ chứa ô ảnh không hợp lệ.')
        if data['schema_version'] == 2 and key not in data['tile_identities']:
            raise ValueError('Ghi chú thiếu mã kiểm chứng ảnh tương ứng.')
        if item.get('status') not in STATUSES or not isinstance(item.get('note'), str) or len(item['note']) > 5000:
            raise ValueError('Trạng thái hoặc ghi chú không hợp lệ.')
        labels = item.get('candidate_labels', {})
        if not isinstance(labels, dict):
            raise ValueError('Đánh giá ứng viên không hợp lệ.')
        tile = next(tile for tile in report['tiles'] if tile['key'] == key)
        candidate_ids = {str(candidate['id']) for candidate in tile.get('detections', [])}
        for candidate_id, label in labels.items():
            if str(candidate_id) not in candidate_ids or label not in CANDIDATE_STATUSES:
                raise ValueError('Đánh giá ứng viên không hợp lệ.')
    # Keep the original session shape for older workspaces.  Candidate-level
    # labels are optional and are only added when the reviewer has actually
    # recorded one, so importing an old tile review never creates noisy empty
    # fields or breaks round-trip compatibility.
    result = {}
    for key, value in reviews.items():
        review = {'status': value['status'], 'note': value['note']}
        if value.get('candidate_labels'):
            review['candidate_labels'] = value['candidate_labels']
        result[key] = review
    return result


def printable_review(tile, review, day):
    # A refresh can leave neighbouring cells at different acquisition dates.
    # The evidence packet must always describe its own source image.
    if tile.get('observation_day_utc'):
        day = date.fromisoformat(tile['observation_day_utc']).strftime('%d/%m/%Y')
    esc = lambda value: html.escape(str(value))
    rows = ''.join(f'<tr><td>{d["id"]}</td><td>{d["confidence"]:.3f}</td><td>{d["latitude"]:.5f}</td><td>{d["longitude"]:.5f}</td></tr>' for d in tile['detections'])
    return f'''<!doctype html><html lang="vi"><meta charset="utf-8"><title>SonarNet — hồ sơ kiểm tra</title>
<style>body{{font:16px system-ui;max-width:850px;margin:40px auto;padding:20px;color:#193249}}table{{width:100%;border-collapse:collapse}}td,th{{text-align:left;padding:10px;border-bottom:1px solid #ddd}}.note{{white-space:pre-wrap}}small{{overflow-wrap:anywhere}}@media print{{body{{margin:0}}}}</style>
<h1>Hồ sơ kiểm tra ảnh SAR</h1><p>{esc(tile['key'])} · Ngày ảnh UTC: {esc(day)}</p>
<p>Nguồn: {esc(tile['source'])}<br>Phạm vi WGS84: {esc(tile['bbox'])}</p>
<p>Bộ lọc đất: {esc(tile.get('land_mask_version', 'Chưa áp dụng'))} · Loại {len(tile.get('excluded_detections', []))} ứng viên chạm đất hoặc vùng 500 m từ bờ ra biển. Tàu trong cảng/sát bờ cũng bị bỏ qua. Kết quả gốc được giữ riêng trong gói bằng chứng.</p>
<p><b>Đánh dấu của người xem:</b> {esc(review['status'])}</p><p class="note">{esc(review['note'])}</p>
<h2>Ứng viên mô hình — chưa xác minh</h2><table><tr><th>ID</th><th>Điểm mô hình</th><th>Vĩ độ</th><th>Kinh độ</th></tr>{rows}</table>
<p>Không phải xác nhận tàu, tàu cá hay vi phạm. Không phát hiện không chứng minh không có tàu. Ảnh ghép trong ngày; chưa có thời điểm riêng từng pixel.</p>
<small>Mã ảnh: {esc(tile['image_sha256'])}<br>Mã mô hình: {esc(tile['weights_sha256'])}</small></html>'''


def evidence_bundle(root, tile, review, day):
    """An offline packet with exact image files, notes and integrity hashes."""
    directory = (root / tile['asset_dir']).resolve()
    if not directory.is_relative_to((root / 'assets/real_scan').resolve()):
        raise ValueError('Evidence must belong to the published scan directory')
    from land_mask import annotated_image
    marked = BytesIO()
    annotated_image(root, tile).save(marked, format='JPEG', quality=95)
    payloads = {
        'source.png': (directory / 'sar.png').read_bytes(),
        'candidates.jpg': marked.getvalue(),
        'raw-model-candidates.jpg': (directory / 'detections.jpg').read_bytes(),
        'review.html': printable_review(tile, review, day).encode('utf-8'),
        'evidence.json': json.dumps(dict(tile, review=review), ensure_ascii=False, indent=2).encode('utf-8'),
    }
    payloads['checksums.json'] = json.dumps({name:hashlib.sha256(data).hexdigest() for name,data in payloads.items()},indent=2).encode()
    buffer = BytesIO()
    with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,data in payloads.items():
            archive.writestr(name,data)
    return buffer.getvalue()
