import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from observation_labels import coordinates, candidate_label, tile_label, observation_time


class LabelTests(unittest.TestCase):
    def test_exact_time_is_preserved_for_rtc(self):
        self.assertEqual(observation_time({'source_acquired_at':'2026-10-01T10:55:19.123Z'}),
                         '01/10/2026 10:55:19 UTC')

    def test_daily_mosaic_does_not_invent_an_exact_time(self):
        self.assertEqual(observation_time({'observation_day_utc':'2026-09-20'}),'20/09/2026 UTC')
    def test_hemispheres_are_not_always_vietnam(self):
        self.assertEqual(coordinates(-12, -75), '12.000°N, 75.000°T')
        self.assertEqual(coordinates(12, 109), '12.000°B, 109.000°Đ')

    def test_candidate_uses_own_date_and_location(self):
        value = candidate_label(dict(latitude=12, longitude=109, observation_day_utc='2026-09-09'), 3)
        self.assertEqual(value, 'Điểm 3 · 12.000°B, 109.000°Đ · 09/09/2026')

    def test_tile_label_has_count_instead_of_internal_key(self):
        value = tile_label(dict(key='grid_opaque', bbox=[108, 10, 110, 12], observation_day_utc='2026-09-09', detections=[]))
        self.assertEqual(value, '11.000°B, 109.000°Đ · 09/09/2026 · 0 điểm')
