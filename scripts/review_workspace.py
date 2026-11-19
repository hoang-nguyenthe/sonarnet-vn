"""Portable review state bound to exact processed images, with no server storage."""
import hashlib
import html
import json
from io import BytesIO
import zipfile
from copy import deepcopy
from datetime import date, datetime, timezone

STATUSES = ['Chưa xem xét', 'Cần kiểm tra tiếp', 'Đã xem, chưa thấy mục tiêu rõ']
CANDIDATE_STATUSES = ['Chưa đánh giá', 'Có khả năng là tàu', 'Nhiễu / không phải tàu']
OPERATIONAL_DECISIONS = ['Cần bổ sung dữ liệu', 'Chuyển chuyên viên xác minh', 'Khép lại lượt rà soát này']


def confirm_operational_review(tile, reviewer, conclusion, basis, confirmed):
    """Record an explicit human assessment tied to exact evidence, not a legal verdict."""
    if confirmed is not True or not isinstance(reviewer, str) or not reviewer.strip():
        raise ValueError('Cần tên chuyên viên và xác nhận trực tiếp.')
    if conclusion not in OPERATIONAL_DECISIONS or not isinstance(basis, str) or not basis.strip():
        raise ValueError('Cần quyết định hợp lệ và căn cứ kiểm tra.')
    return dict(status='confirmed', reviewer=reviewer.strip()[:200], conclusion=conclusion,
                basis=basis.strip()[:5000], confirmed_at=datetime.now(timezone.utc).isoformat(),
                evidence_identity=tile_identity(tile), evidence_identity_version=3,
                authentication='self_declared')


def operational_assessment(tile, review):
    value = review.get('operational_review')
    if value is None:
        return {'status': 'pending', 'conclusion': None, 'reviewer': None}
    if (not isinstance(value, dict) or value.get('status') != 'confirmed'
        or value.get('conclusion') not in OPERATIONAL_DECISIONS
        or not all(isinstance(value.get(k), str) and value[k].strip()
                   for k in ('reviewer', 'basis', 'confirmed_at'))
        or value.get('evidence_identity_version', 2) not in (2, 3)
        or value.get('evidence_identity') != tile_identity(
            tile, version=value.get('evidence_identity_version', 2))):
        raise ValueError('Xác nhận chuyên viên thiếu căn cứ hoặc không khớp bằng chứng.')
    return dict(value, authentication='self_declared')


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
        legacy = state.get('workspace_' + report_id(report, version=2), {})
        for key, review in legacy.items():
            if key in current:
                bank[(key, current[key])] = deepcopy(review)
    if current == previous and 'review_active_notes' in state:
        return state['review_active_notes']
    for key in set(previous) | set(current):
        if previous.get(key) != current.get(key):
            # Streamlit widgets otherwise retain the previous image's verdict.
            for widget in list(state):
                if widget in (f'verdict_{key}', f'note_{key}') or widget.startswith((f'candidate_status_{key}_', f'operational_{key}_')):
                    del state[widget]
    notes = {}
    for tile in report['tiles']:
        key = tile['key']
        stored = bank.get((key, current.get(key)))
        if stored is not None:
            try:
                notes[key] = validate_note(stored, tile)
            except ValueError:
                # An archived record with invalid candidate IDs remains inactive.
                continue
    state['review_active_identities'] = current
    state['review_active_notes'] = notes
    return notes


def report_id(report, *, version=3):
    identity = sorted((t['key'], tile_identity(t, version=version)) for t in report['tiles'])
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def tile_identity(tile, *, version=3):
    fields = ('image_sha256', 'weights_sha256', 'land_mask_version',
              'inference_policy_sha256', 'bbox', 'observation_day_utc', 'detections')
    if version == 3:
        fields += ('key', 'image_size', 'source', 'source_provider', 'source_item_url',
                   'source_asset_url', 'source_acquired_at', 'reference_product',
                   'band', 'time_scope', 'inference_pipeline', 'excluded_detections')
    payload = {key: tile.get(key) for key in fields}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def export_workspace(report, reviews, *, archived=None):
    identities = {t['key']: tile_identity(t) for t in report['tiles']
                  if t['status'] == 'processed' and t['key'] in reviews}
    if archived is None:
        return json.dumps({'schema_version': 3, 'tile_identities': identities, 'reviews': reviews},
                          ensure_ascii=False, indent=2)
    entries = dict(archived)
    entries.update({(key, identity):reviews[key] for key,identity in identities.items()})
    records = [{'tile_key': key, 'evidence_identity': identity, 'review': note}
               for (key,identity),note in sorted(entries.items())]
    return json.dumps({'schema_version': 4, 'records': records}, ensure_ascii=False, indent=2)


def import_workspace(raw, report):
    restored, unavailable = restore_workspace(raw, report)
    if unavailable:
        raise ValueError('Có ghi chú không khớp ảnh hoặc kết quả hiện tại.')
    return restored


def restore_workspace(raw, report):
    restored, unavailable, _ = read_workspace(raw, report)
    return restored, unavailable


def validate_note(item, tile=None):
    if not isinstance(item, dict):
        raise ValueError('Hồ sơ chứa ghi chú không hợp lệ.')
    if item.get('status') not in STATUSES or not isinstance(item.get('note'), str) or len(item['note']) > 5000:
        raise ValueError('Trạng thái hoặc ghi chú không hợp lệ.')
    labels = item.get('candidate_labels', {})
    if not isinstance(labels, dict) or any(label not in CANDIDATE_STATUSES for label in labels.values()):
        raise ValueError('Đánh giá ứng viên không hợp lệ.')
    review = {'status': item['status'], 'note': item['note']}
    if labels:
        review['candidate_labels'] = labels
    if tile is None:
        if item.get('operational_review') is not None:
            if not isinstance(item['operational_review'], dict):
                raise ValueError('Xác nhận chuyên viên không hợp lệ.')
            # A saved assessment stays inactive until its evidence is available.
            review['operational_review'] = dict(item['operational_review'], authentication='self_declared')
    else:
        candidate_ids = {str(candidate['id']) for candidate in tile.get('detections', [])}
        if not labels.keys() <= candidate_ids:
            raise ValueError('Đánh giá ứng viên không hợp lệ.')
        assessment = operational_assessment(tile, item)
        if assessment['status'] == 'confirmed':
            review['operational_review'] = assessment
    return review


def read_workspace(raw, report):
    """Open existing workspace formats, retaining v3/v4 notes for absent evidence."""
    if len(raw) > 50 * 1024**2:
        raise ValueError('Hồ sơ quá lớn (giới hạn 50 MB).')
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError('Tệp không phải JSON hợp lệ.') from None
    if not isinstance(data, dict):
        raise ValueError('Hồ sơ không thuộc đúng bộ ảnh và mô hình này.')
    version = data.get('schema_version')
    if version == 1:
        legacy_identity = [(t['key'], t.get('image_sha256'), t.get('weights_sha256'),
                            t.get('land_mask_version')) for t in report['tiles']]
        old_id = hashlib.sha256(json.dumps(legacy_identity, sort_keys=True).encode()).hexdigest()
        if data.get('report_id') != old_id:
            raise ValueError('Hồ sơ cũ cần đúng bộ ảnh ban đầu để mở lại.')
    if version == 4:
        records = data.get('records')
        if not isinstance(records, list) or not all(isinstance(r, dict) for r in records):
            raise ValueError('Danh sách ghi chú không hợp lệ.')
    elif version in (1, 2, 3):
        notes = data.get('reviews')
        if not isinstance(notes, dict):
            raise ValueError('Danh sách ghi chú không hợp lệ.')
        ids = data.get('tile_identities', {})
        if version in (2, 3) and (not isinstance(ids, dict) or not notes.keys() <= ids.keys()):
            raise ValueError('Ghi chú thiếu mã kiểm chứng ảnh tương ứng.')
        records = [{'tile_key': key, 'evidence_identity': ids.get(key) if version != 1 else None, 'review': note}
                   for key,note in notes.items()]
    else:
        raise ValueError('Phiên bản hồ sơ chưa được hỗ trợ.')
    tiles = {t['key']: t for t in report['tiles'] if t['status'] == 'processed'}
    seen, result, unavailable, archive = set(), {}, [], {}
    for record in records:
        key, identity = record.get('tile_key'), record.get('evidence_identity')
        if not isinstance(key, str) or not key:
            raise ValueError('Ghi chú thiếu định danh ô ảnh.')
        if version != 1 and (not isinstance(identity, str) or len(identity) != 64
                             or any(ch not in '0123456789abcdef' for ch in identity)):
            raise ValueError('Ghi chú thiếu mã kiểm chứng ảnh tương ứng.')
        ident = (key,identity)
        if ident in seen:
            raise ValueError('Một ảnh có nhiều ghi chú trùng trong tệp.')
        seen.add(ident)
        tile = tiles.get(key)
        item = record.get('review')
        matches = tile is not None and (version == 1 or identity == tile_identity(tile,version=min(3,version)))
        if matches:
            result[key] = validate_note(item, tile)
        else:
            unavailable.append(key)
            if version >= 3:
                archive[ident] = validate_note(item)
    return result, unavailable, archive


def source_time_caption(tile):
    acquired = tile.get('source_acquired_at')
    if isinstance(acquired, str):
        try:
            timestamp = datetime.fromisoformat(acquired.replace('Z', '+00:00'))
            if timestamp.tzinfo is not None:
                utc = timestamp.astimezone(timezone.utc).strftime('%d/%m/%Y %H:%M:%S')
                return f'Giờ chụp theo nguồn {utc} UTC.'
        except ValueError:
            pass
    return 'Có ngày quan sát theo nguồn. Thời điểm riêng từng điểm ảnh chưa được xác định.'


def printable_review(tile, review, day):
    # A refresh can leave neighbouring cells at different acquisition dates.
    # The evidence packet must always describe its own source image.
    if tile.get('observation_day_utc'):
        day = date.fromisoformat(tile['observation_day_utc']).strftime('%d/%m/%Y')
    esc = lambda value: html.escape(str(value))
    assessment = operational_assessment(tile, review)
    decision = ('Đang xác minh; chưa có kết luận nghiệp vụ' if assessment['status'] == 'pending' else
                f"{assessment['conclusion']} — chuyên viên: {assessment['reviewer']}; căn cứ: {assessment['basis']}; UTC: {assessment['confirmed_at']}")
    masking = 'Phiên bản mặt nạ đất và dải ven bờ chưa có trong hồ sơ ảnh này. Mở ảnh nguồn và bản dự đoán gốc để đối chiếu.'
    if tile.get('land_mask_version'):
        masking = (f"Bộ lọc đất {tile['land_mask_version']}. Đã loại "
                   f"{len(tile.get('excluded_detections', []))} ứng viên chạm đất hoặc vùng 500 m từ bờ. "
                   'Kết quả gốc được giữ riêng trong gói bằng chứng.')
    labels = review.get('candidate_labels', {})
    rows = ''.join(f'<tr><td>{esc(d["id"])}</td><td>{d["confidence"]:.3f}</td>'
                   f'<td>{d["latitude"]:.5f}</td><td>{d["longitude"]:.5f}</td>'
                   f'<td>{esc(labels.get(str(d["id"]), CANDIDATE_STATUSES[0]))}</td></tr>'
                   for d in tile['detections'])
    return f'''<!doctype html><html lang="vi"><meta charset="utf-8"><title>SonarNet — hồ sơ kiểm tra</title>
<style>body{{font:16px system-ui;max-width:850px;margin:40px auto;padding:20px;color:#193249}}table{{width:100%;border-collapse:collapse}}td,th{{text-align:left;padding:10px;border-bottom:1px solid #ddd}}.note{{white-space:pre-wrap}}small{{overflow-wrap:anywhere}}@media print{{body{{margin:0}}}}</style>
<h1>Hồ sơ kiểm tra ảnh SAR</h1><p>{esc(tile['key'])} · Ngày ảnh UTC: {esc(day)}</p>
<p>Nguồn: {esc(tile['source'])}<br>{esc(source_time_caption(tile))}<br>Phạm vi WGS84: {esc(tile['bbox'])}</p>
<p>{esc(masking)}</p>
<p><b>Đánh dấu của người xem:</b> {esc(review['status'])}</p><p class="note">{esc(review['note'])}</p>
<p><b>Đối chiếu AIS:</b> Thiếu dữ liệu. Chưa có nguồn AIS cùng thời điểm để ghép.</p>
<p><b>Xác nhận nghiệp vụ:</b> {esc(decision)}</p>
<p>Người xác nhận tự khai danh tính trong phiên; đây không phải chữ ký số hay kết luận pháp lý.</p>
<h2>Ứng viên mô hình — chưa xác minh</h2><table><tr><th>ID</th><th>Điểm mô hình</th><th>Vĩ độ</th><th>Kinh độ</th><th>Đánh giá của người rà</th></tr>{rows}</table>
<p>Không phải xác nhận tàu, tàu cá hay vi phạm. Các vùng không có điểm phát hiện vẫn có thể có tàu.</p>
<small>Mã ảnh: {esc(tile['image_sha256'])}<br>Mã mô hình: {esc(tile['weights_sha256'])}</small></html>'''


def read_review_images(root, tile):
    """Read the chosen image once and reuse its verified bytes for display and export."""
    from land_mask import annotated_image
    from scan_assets import resolve_scan_directory
    directory = resolve_scan_directory(root, tile)
    source = (directory/'sar.png').read_bytes()
    if hashlib.sha256(source).hexdigest() != tile['image_sha256']:
        raise ValueError('Ảnh nguồn đã thay đổi. Mở lại ô ảnh để kiểm tra phiên bản mới.')
    marked = BytesIO()
    annotated_image(root, tile, source=BytesIO(source)).save(marked, format='JPEG', quality=95)
    return {'source.png': source, 'candidates.jpg': marked.getvalue(),
            'raw-model-candidates.jpg': (directory/'detections.jpg').read_bytes()}


def evidence_bundle(root, tile, review, day, *, fixed_images=None):
    """An offline packet with exact image files, notes and integrity hashes."""
    sources = read_review_images(root, tile) if fixed_images is None else fixed_images
    images = {name: sources[name] for name in ('source.png', 'candidates.jpg', 'raw-model-candidates.jpg')}
    if hashlib.sha256(images['source.png']).hexdigest() != tile['image_sha256']:
        raise ValueError('Ảnh nguồn không khớp mã kiểm chứng của ô ảnh.')
    payloads = {
        **images,
        'review.html': printable_review(tile, review, day).encode('utf-8'),
        'evidence.json': json.dumps(dict(tile, review=review, data_status='MISSING_DATA',
            operational_assessment=operational_assessment(tile, review)), ensure_ascii=False, indent=2).encode('utf-8'),
    }
    payloads['checksums.json'] = json.dumps({name:hashlib.sha256(data).hexdigest() for name,data in payloads.items()},indent=2).encode()
    buffer = BytesIO()
    with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,data in payloads.items():
            archive.writestr(name,data)
    return buffer.getvalue()
