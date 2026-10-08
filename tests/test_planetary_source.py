from datetime import date
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from sonarnet.data.planetary import gray_rgba, search_rtc, validate_asset_url, PlanetaryError, RTCProduct, provenance

HREF = 'https://sentinel1euwestrtc.blob.core.windows.net/sentinel1-grd-rtc/test/iw-vv.rtc.tiff'


class PlanetarySourceTests(unittest.TestCase):
    def test_linear_gamma_conversion_and_nodata(self):
        values = np.ma.array([[.01, 1, 0, -32768, float('nan')]], mask=[[0,0,0,0,0]])
        rgba = gray_rgba(values)
        self.assertEqual(rgba[0,:,3].tolist(), [255,255,0,0,0])
        self.assertEqual(rgba[0,0,0], 42)
        self.assertEqual(rgba[0,1,0], 212)
        self.assertTrue(np.all(rgba[:,:,:3] == rgba[:,:,:1]))

    def test_masked_positive_pixels_stay_transparent(self):
        self.assertEqual(gray_rgba(np.ma.array([[1.]],mask=[[True]]))[0,0,3], 0)

    def test_no_other_asset_hosts_or_protocols(self):
        for url in ['http://example.org/a.tiff', 'file:///tmp/a.tiff', HREF.replace('sentinel1euwestrtc', 'wrong')]:
            with self.assertRaises(PlanetaryError): validate_asset_url(url)
        validate_asset_url(HREF)

    def test_catalog_requires_vv_and_usable_resolution(self):
        item = {'id':'scene','properties':{'datetime':'2026-10-01T01:00:00Z','sar:instrument_mode':'IW',
                   'sar:pixel_spacing_range':10},'assets':{'vv':{'href':HREF}}}
        with patch('sonarnet.data.planetary.get_json', return_value={'features':[item]}):
            self.assertEqual(search_rtc([109,13,109.1,13.1],date(2026,9,1),date(2026,10,8))[0].product_id,'scene')
            item['properties']['sar:pixel_spacing_range']=40
            self.assertEqual(search_rtc([109,13,109.1,13.1],date(2026,9,1),date(2026,10,8)),[])

    def test_provenance_preserves_acquisition_and_unsigned_url(self):
        record=provenance(RTCProduct('test_rtc','2026-10-01T01:00:00Z',HREF,10))
        self.assertEqual(record['source_asset_url'],HREF)
        self.assertEqual(record['source_acquired_at'],'2026-10-01T01:00:00Z')
        self.assertIn('terrain-corrected',record['radiometry'])


if __name__ == '__main__': unittest.main()
