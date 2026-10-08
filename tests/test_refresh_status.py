from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from run_satellite_refresh import still_cooling, read_state, write_state
import run_satellite_refresh as runner
from sonarnet.data.copernicus import CopernicusQuotaError
from sonarnet.data.planetary import PlanetaryAccessError


class RefreshStateTests(unittest.TestCase):
    def test_cooldown_requires_a_valid_future_timestamp(self):
        now=datetime(2026,10,8,tzinfo=timezone.utc)
        self.assertTrue(still_cooling('2026-10-09T00:00:00Z',now))
        for value in [None,'wrong','2026-10-07T00:00:00Z','2026-10-09T00:00:00']:
            self.assertFalse(still_cooling(value,now))

    def test_status_round_trip_does_not_touch_report(self):
        with TemporaryDirectory() as d:
            path=Path(d)/'status.json'
            self.assertEqual(read_state(path),{})
            write_state(path,{'state':'blocked','reason':'CopernicusQuotaError'})
            self.assertEqual(read_state(path)['reason'],'CopernicusQuotaError')
            self.assertEqual(list(Path(d).iterdir()),[path])

    def test_quota_switches_once_without_repeating_copernicus(self):
        with TemporaryDirectory() as d:
            mosaic=Mock(side_effect=CopernicusQuotaError('quota'))
            scan=Mock()
            modules={'refresh_sentinel_mosaic':SimpleNamespace(main=mosaic),
                     'refresh_detailed_scan':SimpleNamespace(main=scan)}
            with patch.object(runner,'ROOT',Path(d)),patch.dict(sys.modules,modules):
                runner.main(['--max-updates','3'])
                self.assertEqual(mosaic.call_count,1)
                self.assertEqual(scan.call_args.args[0][-2:],['--source','planetary'])
                runner.main(['--max-updates','3'])
                self.assertEqual(mosaic.call_count,1)
                self.assertEqual(scan.call_count,2)

    def test_source_block_does_not_claim_success_or_loop(self):
        with TemporaryDirectory() as d:
            mosaic=Mock(side_effect=CopernicusQuotaError('quota'))
            scan=Mock(side_effect=PlanetaryAccessError('access unavailable'))
            modules={'refresh_sentinel_mosaic':SimpleNamespace(main=mosaic),
                     'refresh_detailed_scan':SimpleNamespace(main=scan)}
            with patch.object(runner,'ROOT',Path(d)),patch.dict(sys.modules,modules):
                with self.assertRaises(SystemExit): runner.main([])
                state=read_state(Path(d)/'assets/real_scan/refresh_status.json')
                self.assertEqual(state['state'],'blocked')
                self.assertEqual(state['updated_this_run'],0)
                runner.main([])
                self.assertEqual(scan.call_count,1)


if __name__ == '__main__':unittest.main()
