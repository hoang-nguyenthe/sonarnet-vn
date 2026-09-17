import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from scan_assets import validate_tile, _validate_image


class ScanValidationCacheTests(unittest.TestCase):
    def setUp(self):
        _validate_image.cache_clear()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.directory = self.root / 'assets/real_scan/example'
        self.directory.mkdir(parents=True)
        for name in ('sar.png', 'detections.jpg'):
            Image.new('RGB', (16, 16)).save(self.directory / name)
        self.tile = dict(asset_dir='assets/real_scan/example', bbox=[108, 10, 109, 11],
                         image_size=[16, 16], detections=[],
                         image_sha256=hashlib.sha256((self.directory / 'sar.png').read_bytes()).hexdigest())

    def test_unchanged_images_are_not_read_again(self):
        validate_tile(self.root, self.tile)
        with patch('scan_assets.Image.open', side_effect=AssertionError('Read unchanged image')):
            validate_tile(self.root, self.tile)

    def test_changed_image_is_rejected(self):
        validate_tile(self.root, self.tile)
        Image.new('RGB', (16, 16), 'white').save(self.directory / 'sar.png')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            validate_tile(self.root, self.tile)

    def test_changed_manifest_and_missing_file_are_rejected(self):
        validate_tile(self.root, self.tile)
        with self.assertRaisesRegex(ValueError, 'dimensions'):
            validate_tile(self.root, dict(self.tile, image_size=[32, 32]))
        (self.directory / 'sar.png').unlink()
        with self.assertRaises(OSError):
            validate_tile(self.root, self.tile)

    def test_invalid_detection_still_checked_on_cache_hit(self):
        validate_tile(self.root, self.tile)
        bad = dict(id=1, bbox_px=[0, 0, 17, 16], latitude=10.5, longitude=108.5, confidence=.5)
        with self.assertRaisesRegex(ValueError, 'outside image'):
            validate_tile(self.root, dict(self.tile, detections=[bad]))
