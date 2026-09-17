from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from scan_prefetch import prefetched


class PrefetchTests(unittest.TestCase):
    def test_order_and_failure_isolation(self):
        def load(i):
            if i == 2:
                raise OSError('source unavailable')
            return i * 10
        rows = list(prefetched(range(4), load))
        self.assertEqual([r[0] for r in rows], [0, 1, 2, 3])
        self.assertEqual(rows[1], (1, 10, None))
        self.assertIsInstance(rows[2][2], OSError)
        self.assertEqual(rows[3], (3, 30, None))

    def test_next_download_overlaps_consumption(self):
        downloaded = threading.Event()
        def load(i):
            if i == 1:
                downloaded.set()
            return i
        stream = prefetched(range(100), load, depth=2)
        try:
            self.assertEqual(next(stream)[0], 0)
            self.assertTrue(downloaded.wait(2))
        finally:
            stream.close()

    def test_invalid_depth(self):
        with self.assertRaises(ValueError):
            list(prefetched([], lambda x: x, depth=0))
