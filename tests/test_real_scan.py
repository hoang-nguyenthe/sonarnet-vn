import json
from pathlib import Path
import unittest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


class ScanTests(unittest.TestCase):
    def test_published_grid(self):
        report = json.loads((ROOT / 'assets/real_scan/report.json').read_text())
        self.assertEqual(len(report['tiles']), 12)
        self.assertEqual(len({t['key'] for t in report['tiles']}), 12)
        for tile in report['tiles']:
            if tile['status'] != 'processed':
                continue
            with Image.open(ROOT / tile['asset_dir'] / 'sar.png') as image:
                self.assertEqual(list(image.size), tile['image_size'])
                image.verify()
            w,s,e,n = tile['bbox']
            for d in tile['detections']:
                self.assertTrue(w <= d['longitude'] <= e)
                self.assertTrue(s <= d['latitude'] <= n)
                self.assertGreaterEqual(d['confidence'], tile['confidence_threshold'])
            self.assertEqual(len(tile['weights_sha256']), 64)


if __name__ == '__main__':
    unittest.main()
