"""Popup images must work inside Cloud's /~/+/ app and local srcdoc maps."""
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from urllib.parse import urljoin

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from popup_evidence import evidence_url


class PopupEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.asset = self.root / 'assets/real_scan/published/test/cell'
        self.asset.mkdir(parents=True)
        Image.new('RGB', (256, 256), (100, 120, 140)).save(self.asset / 'sar.png')
        self.candidate = {
            'asset_dir': 'assets/real_scan/published/test/cell',
            'bbox_px': [112, 110, 132, 136],
        }

    def test_image_exists_and_decodes(self):
        url = evidence_url(self.root, self.candidate)
        path = self.root / 'scripts/static/crops' / url.rsplit('/', 1)[-1]
        with Image.open(path) as image:
            self.assertEqual(image.format, 'JPEG')
            self.assertGreaterEqual(min(image.size), 160)
            self.assertLessEqual(max(image.size), 280)
            image.load()

    def test_url_preserves_streamlit_cloud_prefix(self):
        url = evidence_url(self.root, self.candidate)
        for base in ('https://sonarnet.streamlit.app/~/+/',
                     'http://localhost:8501/', 'https://example.org/myapp/'):
            self.assertEqual(urljoin(base, url), base + url)

    def test_existing_crop_is_reused(self):
        url = evidence_url(self.root, self.candidate)
        path = self.root / 'scripts/static/crops' / url.rsplit('/', 1)[-1]
        timestamp = path.stat().st_mtime_ns
        self.assertEqual(evidence_url(self.root, self.candidate), url)
        self.assertEqual(path.stat().st_mtime_ns, timestamp)

    def test_different_detections_have_different_crops(self):
        other = dict(self.candidate, bbox_px=[12, 10, 32, 36])
        self.assertNotEqual(evidence_url(self.root, self.candidate),
                            evidence_url(self.root, other))

    def test_missing_source_does_not_make_a_broken_url(self):
        self.assertIsNone(evidence_url(self.root, dict(self.candidate, asset_dir='absent')))


if __name__ == '__main__':
    unittest.main()
