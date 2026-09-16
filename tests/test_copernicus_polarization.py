from datetime import date
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from sonarnet.data.copernicus import sentinel1_mosaic_preview


class PolarizationTests(unittest.TestCase):
    def test_requested_band_matches_filtered_products(self):
        for polarization, band in [('DV','VV'), ('SV','VV'), ('DH','HH'), ('SH','HH')]:
            with self.subTest(polarization=polarization), patch('sonarnet.data.copernicus.urlopen') as request:
                response = MagicMock()
                response.__enter__.return_value.read.return_value = b'\x89PNGpayload'
                request.return_value = response
                sentinel1_mosaic_preview('test-token', (10, 20, 18, 28), date(2026,9,1), date(2026,9,16), polarization=polarization)
                payload = json.loads(request.call_args.args[0].data)
                self.assertEqual(payload['input']['data'][0]['dataFilter']['polarization'], polarization)
                self.assertIn(f'sample.{band}', payload['evalscript'])
                self.assertNotIn('sample.' + ('HH' if band == 'VV' else 'VV'), payload['evalscript'])

    def test_invalid_polarization_rejected_before_request(self):
        with patch('sonarnet.data.copernicus.urlopen') as request:
            with self.assertRaises(ValueError):
                sentinel1_mosaic_preview('test-token', (10,20,18,28), date.today(), date.today(), polarization='unknown')
            request.assert_not_called()


if __name__ == '__main__':
    unittest.main()
