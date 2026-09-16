import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from observation_view import local_time, date_label, points_in_region, published_layers, provenance


class ObservationTests(unittest.TestCase):
    def test_timezone(self):
        self.assertEqual(local_time('2026-09-16T00:00:00Z'), '16/09/2026 · 07:00 GMT+7')
        self.assertEqual(date_label('2026-09-16'), '16/09/2026')

    def test_filter(self):
        points = [{'longitude': 108, 'latitude': 16}, {'longitude': 20, 'latitude': 40}]
        self.assertEqual(points_in_region(points, [102, 6, 115, 24]), points[:1])

    def test_assets_and_provenance(self):
        records = published_layers(Path(__file__).resolve().parents[1])
        self.assertGreater(len(records), 0)
        self.assertEqual(records[0]['key'], 'vietnam')
        for record in records:
            self.assertIn('không phải ngày chụp của mọi điểm ảnh', provenance(record))


if __name__ == '__main__':
    unittest.main()
