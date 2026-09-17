import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from illustrative_vessels import FILTERS, STATES, filter_vessels, profile


class VesselFilterTests(unittest.TestCase):
    def test_status_filters_partition_all_vessels(self):
        candidates = [{'id': f'tile/{i}'} for i in range(100)]
        groups = [filter_vessels(candidates, label) for label in list(FILTERS)[1:]]
        self.assertEqual(sum(map(len, groups)), len(candidates))
        self.assertTrue(all(groups))
        self.assertEqual(filter_vessels(candidates, 'Tất cả'), candidates)
        for label, status in list(FILTERS.items())[1:]:
            self.assertTrue(all(profile(c)['status'] == status for c in filter_vessels(candidates, label)))

    def test_three_explicit_colors(self):
        self.assertEqual([v[1] for v in STATES.values()], ['#30d158', '#ffd60a', '#ff453a'])

    def test_empty_filter(self):
        self.assertEqual(filter_vessels([], 'Đỏ · Chưa có AIS'), [])
