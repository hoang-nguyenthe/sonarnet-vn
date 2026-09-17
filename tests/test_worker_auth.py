import sys
from pathlib import Path
import unittest
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from worker_auth import RefreshingToken


class WorkerAuthTests(unittest.TestCase):
    def test_refresh_before_expiry_and_reuse_until_then(self):
        clock = Mock(return_value=0)
        acquire = Mock(side_effect=[('first', 600), ('second', 600)])
        provider = RefreshingToken(acquire, clock)
        self.assertEqual(provider.get(), 'first')
        clock.return_value = 449
        self.assertEqual(provider.get(), 'first')
        acquire.assert_called_once()
        clock.return_value = 450
        self.assertEqual(provider.get(), 'second')

    def test_short_lifetime_and_failed_refresh(self):
        clock = Mock(return_value=0)
        acquire = Mock(side_effect=[('first', 60), RuntimeError('unavailable'), ('second', 60)])
        provider = RefreshingToken(acquire, clock)
        self.assertEqual(provider.get(), 'first')
        clock.return_value = 30
        with self.assertRaises(RuntimeError):
            provider.get()
        self.assertEqual(provider.get(), 'second')
