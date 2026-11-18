"""The pinned case remains available without the scan archive or external map."""
from hashlib import sha256
from pathlib import Path
import shutil
import sys

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from demo_snapshot import ARCHIVE_SHA256, load_snapshot


def test_snapshot_integrity_and_pending(tmp_path):
    dest = tmp_path/'reports/final/export_verification'
    dest.mkdir(parents=True)
    path = dest/'sample_evidence.zip'
    shutil.copyfile(ROOT/'reports/final/export_verification/sample_evidence.zip', path)
    evidence, files, payload = load_snapshot(tmp_path)
    assert sha256(payload).hexdigest()==ARCHIVE_SHA256
    assert sha256(files['source.png']).hexdigest()==evidence['image_sha256']
    assert evidence['data_status']=='MISSING_DATA'
    assert evidence['operational_assessment']['conclusion'] is None
    path.write_bytes(payload[:-1]+b'0')
    with pytest.raises(ValueError, match='Mã băm'):
        load_snapshot(tmp_path)


def test_snapshot_view_does_not_require_scan_assets(tmp_path):
    dest = tmp_path/'reports/final/export_verification'
    dest.mkdir(parents=True)
    shutil.copyfile(ROOT/'reports/final/export_verification/sample_evidence.zip',dest/'sample_evidence.zip')
    app=AppTest.from_string(f'from pathlib import Path\nfrom demo_snapshot import render_snapshot\nrender_snapshot(Path({str(tmp_path)!r}))').run()
    assert not app.exception
    assert any('Thiếu dữ liệu AIS' in item.value for item in app.info)
    app.toggle(key='snapshot_highlight').set_value(True).run()
    assert not app.exception
    assert app.toggle(key='snapshot_highlight').value is True
    assert any('Chưa có kết luận nghiệp vụ' in item.value for item in app.info)
    assert len(app.get('download_button'))==1
