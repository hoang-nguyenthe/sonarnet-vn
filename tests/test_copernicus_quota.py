from io import BytesIO
from datetime import date
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from sonarnet.data.copernicus import process_error, CopernicusQuotaError, sentinel1_mosaic_preview


class QuotaTests(unittest.TestCase):
    def test_quota_has_distinct_error(self):
        self.assertIsInstance(process_error(403,'Insufficient processing units or requests available in your account.','test'),CopernicusQuotaError)

    def test_generic_forbidden_is_not_called_quota(self):
        self.assertNotIsInstance(process_error(403,'Access denied','test'),CopernicusQuotaError)

    def test_rate_limit_is_not_called_monthly_quota(self):
        self.assertNotIsInstance(process_error(429,'Slow down','test'),CopernicusQuotaError)

    def test_process_client_raises_quota_without_retry(self):
        error=HTTPError('https://example.org',403,'Forbidden',{},BytesIO(b'Insufficient processing units or requests available in your account.'))
        with patch('sonarnet.data.copernicus.urlopen',side_effect=error) as request:
            with self.assertRaises(CopernicusQuotaError):
                sentinel1_mosaic_preview('token',(109,13,109.1,13.1),date.today(),date.today())
            self.assertEqual(request.call_count,1)


if __name__ == '__main__':unittest.main()
