import sys
from pathlib import Path
import unittest
import tempfile
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from map_raster import project_rgba, static_overlay_source, ViewportRadar


class ProjectionTests(unittest.TestCase):
    def test_static_display_cache_preserves_input(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root/'source.png'
            Image.new('RGBA', (8, 12), (80, 90, 100, 255)).save(source)
            original = source.read_bytes()
            url = static_overlay_source(source, [102, 6, 103, 7], root/'static')
            self.assertTrue(url.startswith('/app/static/radar/'))
            self.assertNotIn('base64', url)
            self.assertEqual(source.read_bytes(), original)
            self.assertTrue((root/'static/radar'/url.split('/')[-1]).exists())
            self.assertEqual(url, static_overlay_source(source, [102, 6, 103, 7], root/'static'))

    def test_latitude_stripe_follows_mercator(self):
        south, north, lat, height = 6, 24, 16, 1800
        data = np.zeros((height, 2, 4), dtype='uint8')
        data[:, :, 3] = 255
        row = int((north-lat)/(north-south)*height)
        data[row-1:row+2, :, :3] = 255
        result = np.asarray(project_rgba(Image.fromarray(data), south, north))
        merc = lambda x: np.arcsinh(np.tan(np.radians(x)))
        expected = (merc(north)-merc(lat))/(merc(north)-merc(south))*height
        actual = result[:, 0, 0].argmax()
        self.assertLess(abs(actual-expected), 2)
        self.assertGreater(abs(actual-row), 10)

    def test_alpha_and_extent_preserved(self):
        image = Image.new('RGBA', (8, 12), (200, 100, 50, 0))
        result = np.asarray(project_rgba(image, 6, 24))
        self.assertEqual(result.shape, (12, 8, 4))
        self.assertEqual(result.max(), 0)
