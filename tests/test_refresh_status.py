from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
from tempfile import TemporaryDirectory
from contextlib import redirect_stdout
from io import StringIO
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

    def test_preflight_reports_cooldown_without_modifying_last_attempt(self):
        with TemporaryDirectory() as d:
            root=Path(d)
            path=root/'assets/real_scan/refresh_status.json'
            write_state(path,{'state':'blocked','retry_after':'2099-01-01T00:00:00Z'})
            before=path.read_bytes()
            with patch.object(runner,'ROOT',root),patch.dict('os.environ',{'GITHUB_STEP_SUMMARY':str(root/'summary.md')}):
                with redirect_stdout(StringIO()) as out: runner.main(['--check-cooldown'])
                self.assertEqual(out.getvalue().strip(),'deferred')
                self.assertIn('no catalog check', (root/'summary.md').read_text())
                with redirect_stdout(StringIO()) as out: runner.main(['--check-cooldown','--force-probe'])
                self.assertEqual(out.getvalue().strip(),'due')
            self.assertEqual(path.read_bytes(),before)

    def test_zero_updates_are_not_ready(self):
        with TemporaryDirectory() as d:
            root=Path(d)
            modules={'refresh_sentinel_mosaic':SimpleNamespace(main=Mock()),
                     'refresh_detailed_scan':SimpleNamespace(main=Mock())}
            with patch.object(runner,'ROOT',root),patch.dict(sys.modules,modules): runner.main([])
            state=read_state(root/'assets/real_scan/refresh_status.json')
            self.assertEqual(state['state'],'checked_no_updates')
            self.assertIs(state['overview_updated'],False)

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
