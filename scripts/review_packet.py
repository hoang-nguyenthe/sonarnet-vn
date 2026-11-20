"""Check a SonarNet review packet without extracting files or opening its HTML."""

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from PIL import Image

from review_workspace import operational_assessment, read_review_json

MAX_PACKET_BYTES = 50 * 1024**2
IMAGES = {'source.png': 'PNG', 'candidates.jpg': 'JPEG', 'raw-model-candidates.jpg': 'JPEG'}
MEMBERS = set(IMAGES) | {'review.html', 'evidence.json', 'checksums.json'}


def read_evidence_packet(payload, *, expected_sha256=None, max_bytes=MAX_PACKET_BYTES):
    """Validate ZIP integrity, image identity and the operational evidence binding."""
    if len(payload) > max_bytes:
        raise ValueError('Hồ sơ vượt giới hạn bộ nhớ.')
    if expected_sha256 is not None and sha256(payload).hexdigest() != expected_sha256:
        raise ValueError('Mã băm tệp ZIP không khớp.')
    with ZipFile(BytesIO(payload)) as archive:
        entries = archive.infolist()
        if len(entries) != len(MEMBERS) or {entry.filename for entry in entries} != MEMBERS:
            raise ValueError('Danh sách thành phần ZIP không đúng.')
        if sum(entry.file_size for entry in entries) > max_bytes:
            raise ValueError('Dung lượng giải nén vượt giới hạn.')
        if any(entry.flag_bits & 1 for entry in entries):
            raise ValueError('Tệp ZIP mã hóa không được hỗ trợ.')
        files = {entry.filename: archive.read(entry) for entry in entries}
    hashes = {name: sha256(contents).hexdigest() for name, contents in files.items()
              if name != 'checksums.json'}
    if read_review_json(files['checksums.json']) != hashes:
        raise ValueError('Một thành phần không khớp mã băm.')

    evidence = read_review_json(files['evidence.json'])
    if not isinstance(evidence, dict) or evidence.get('image_sha256') != hashes['source.png']:
        raise ValueError('Ảnh nguồn không khớp mã trong hồ sơ.')
    review = evidence.get('review')
    if (evidence.get('data_status') != 'MISSING_DATA' or not isinstance(review, dict)
            or evidence.get('operational_assessment') != operational_assessment(evidence, review)):
        raise ValueError('Trạng thái hoặc xác nhận nghiệp vụ không khớp hồ sơ.')
    for name, image_format in IMAGES.items():
        try:
            with Image.open(BytesIO(files[name])) as image:
                if image.format != image_format or list(image.size) != evidence.get('image_size'):
                    raise ValueError('Định dạng hoặc kích thước ảnh không khớp hồ sơ.')
                image.verify()
        except Image.DecompressionBombError:
            raise ValueError('Kích thước ảnh vượt giới hạn.') from None
    return evidence, files, hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('packet', type=Path)
    parser.add_argument('--sha256', help='SHA-256 obtained independently from the release or sender.')
    options = parser.parse_args()
    try:
        if options.packet.stat().st_size > MAX_PACKET_BYTES:
            raise ValueError('Hồ sơ vượt giới hạn bộ nhớ.')
        payload = options.packet.read_bytes()
        evidence, _, hashes = read_evidence_packet(payload, expected_sha256=options.sha256)
    except (BadZipFile, OSError, ValueError, RuntimeError, NotImplementedError) as error:
        parser.exit(1, f'Kiểm tra thất bại. {error}\n')
    print(json.dumps({
        'zip_sha256': sha256(payload).hexdigest(),
        'independent_sha256_checked': options.sha256 is not None,
        'files_verified': len(hashes),
        'data_status': evidence['data_status'],
        'operational_status': evidence['operational_assessment']['status'],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
