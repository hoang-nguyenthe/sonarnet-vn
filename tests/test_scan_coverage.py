import sys
import unittest
from pathlib import Path
from unittest.mock import Mock
import numpy as np
from PIL import Image
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from scan_coverage import cells, image_has_observation, cell_state, distributed_queue
from refresh_detailed_scan import infer_tile, allowed_pixels


class CoverageTests(unittest.TestCase):
    def test_queue_reaches_north_and_south_without_dropping_cells(self):
        pending = [{'key':str(i), 'bbox':[108, lat, 108.1, lat+.1]} for i,lat in enumerate([6,6.1,6.2,12,12.1,21,21.1])]
        result = distributed_queue(pending)
        self.assertEqual([int(c['bbox'][1]) for c in result[:3]], [21,12,6])
        self.assertEqual({c['key'] for c in result}, {c['key'] for c in pending})
    def test_grid_includes_fractional_edge(self):
        result = list(cells([108, 10, 108.25, 10.15]))
        self.assertEqual(len(result), 6)
        self.assertEqual(result[-1]['bbox'], [108.2, 10.1, 108.25, 10.15])
        self.assertEqual(len({c['key'] for c in result}), 6)

    def test_unknown_and_empty_are_not_processed(self):
        cell = next(cells([108, 10, 108.1, 10.1]))
        record = {'bbox': cell['bbox']}
        alpha = np.ones((10, 10), dtype=bool)
        self.assertEqual(cell_state(cell, record, alpha, None, None, set()), 'blocked_missing_mask')
        self.assertEqual(cell_state(cell, record, ~alpha, None, None, set()), 'no_observation')
        self.assertEqual(cell_state(cell, record, alpha, box(100, 0, 120, 30), box(108, 10, 109, 11), set()), 'excluded_land_coast')

    def test_model_receives_only_allowed_pixels(self):
        bounds = [108, 10, 108.1, 10.1]
        mask = ({'coverage_bbox': [100, 0, 120, 30], 'version': 'test', 'coastal_buffer_m': 500},
                {'land': box(108, 10, 108.05, 10.1), 'coast': box(108.05, 10, 108.06, 10.1)})
        image = Image.new('RGBA', (512, 512), (100, 100, 100, 255))
        model = Mock()
        model.predict.return_value = [Mock(boxes=[])]
        audit = {}
        infer_tile(model, image, bounds, mask=mask, audit=audit)
        pixels = np.asarray(model.predict.call_args.args[0])
        self.assertEqual(pixels[:, :307, :].max(), 0)
        self.assertEqual(pixels[:, 308:, :].min(), 100)
        self.assertEqual(image.getpixel((0, 0)), (100, 100, 100, 255))
        self.assertAlmostEqual(audit['allowed_pixel_fraction'], .4, places=2)

    def test_fully_excluded_never_invokes_model(self):
        mask = ({'coverage_bbox': [100, 0, 120, 30], 'version': 'test', 'coastal_buffer_m': 500},
                {'land': box(107, 9, 110, 12), 'coast': box(106, 8, 107, 9)})
        model = Mock()
        result, _ = infer_tile(model, Image.new('RGB', (512, 512)), [108, 10, 108.1, 10.1], mask=mask)
        self.assertEqual(result, [])
        model.predict.assert_not_called()

    def test_missing_mask_does_not_claim_ocean(self):
        mask = ({'coverage_bbox': [100, 0, 120, 30]}, {'land': box(101, 1, 102, 2), 'coast': box(102, 1, 103, 2)})
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            allowed_pixels(Image.new('RGB', (512, 512)), [-10, 10, -9.9, 10.1], mask)
