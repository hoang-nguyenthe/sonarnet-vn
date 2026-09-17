import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from coverage_status import coverage_rows, waiting_cells


class CoverageStatusTests(unittest.TestCase):
    def test_retries_count_as_outstanding_work(self):
        self.assertEqual(waiting_cells({'states': {'pending': 5498, 'retry_later': 2}}), 5500)

    def test_missing_data_and_exclusions_are_not_completed(self):
        plan = {'states': {'processed': 37, 'no_observation': 8283, 'excluded_land_coast': 6720}}
        rows = coverage_rows(plan)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]['Số ô'], 37)
        self.assertEqual(sum(r['Số ô'] for r in rows), sum(plan['states'].values()))

    def test_empty_plan_has_no_fabricated_coverage(self):
        self.assertEqual(coverage_rows({}), [])
        self.assertEqual(waiting_cells({}), 0)
