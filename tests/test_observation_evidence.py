"""Check that overview detections keep their detailed-image provenance."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from observation_view import published_yolo_result, demo_ais_record, candidate_crop
from refresh_detailed_scan import infer_tile, resolution_m


class ObservationEvidenceTests(unittest.TestCase):
    def test_overview_cannot_be_detector_input(self):
        model = Mock()
        with self.assertRaisesRegex(ValueError, 'too coarse'):
            infer_tile(model, Image.new('RGB', (1280, 1600)), [102, 6, 115, 21.8])
        model.predict.assert_not_called()

    def test_detailed_cell_has_usable_pixel_spacing(self):
        self.assertLess(resolution_m([107.7, 10.35, 107.8, 10.45], [1024, 1024]), 12)

    def test_candidates_retain_individual_evidence_and_day(self):
        result = published_yolo_result(ROOT, {'bbox': [102, 6, 115, 24]})
        self.assertTrue(result['tiles'])
        self.assertEqual(len({c['id'] for c in result['detections']}), len(result['detections']))
        sources = {tile['key']: tile for tile in result['tiles']}
        for candidate in result['detections']:
            source = sources[candidate['tile_key']]
            self.assertEqual(candidate['observation_day_utc'], source['observation_day_utc'])
            self.assertEqual(candidate['weights_sha256'], source['weights_sha256'])
            self.assertTrue(candidate_crop(ROOT, candidate).startswith(b'\xff\xd8'))

    def test_other_region_does_not_inherit_vietnam_candidates(self):
        result = published_yolo_result(ROOT, {'bbox': [-82, 25, -74, 33]})
        self.assertEqual(result['detections'], [])
        self.assertEqual(result['tiles'], [])

    def test_missing_ais_has_no_invented_identity(self):
        rows = [demo_ais_record({}, dict(id=f'cell/{i}', latitude=10, longitude=108,
                                       observation_day_utc='2026-09-12')) for i in range(50)]
        dark = [row for row in rows if row['status'] == 'Không có AIS']
        self.assertTrue(dark)
        for row in dark:
            self.assertIsNone(row['latitude'])
            self.assertEqual(row['mmsi'], 'Chưa xác định')
            self.assertEqual(row['vessel_name'], 'Chưa xác định')


if __name__ == '__main__':
    unittest.main()
