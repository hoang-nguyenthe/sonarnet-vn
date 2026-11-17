"""Moving the published root to SSD must preserve exports and path boundaries."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import pytest
from scan_assets import resolve_scan_directory


def test_external_root_and_child_escape(tmp_path):
    root=tmp_path/'repo';scan=root/'assets/real_scan';scan.mkdir(parents=True)
    ssd=tmp_path/'ssd';(ssd/'cell').mkdir(parents=True)
    (scan/'published').symlink_to(ssd,target_is_directory=True)
    assert resolve_scan_directory(root,{'asset_dir':'assets/real_scan/published/cell'})==ssd/'cell'
    private=tmp_path/'private';private.mkdir()
    (ssd/'escape').symlink_to(private,target_is_directory=True)
    with pytest.raises(ValueError):
        resolve_scan_directory(root,{'asset_dir':'assets/real_scan/published/escape'})
    with pytest.raises(ValueError):
        resolve_scan_directory(root,{'asset_dir':'../private'})
