import sys
from pathlib import Path
import unittest
from shapely.geometry import box

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from land_mask import add_map_layer, classify, get_mask
from scan_assets import validated_report


class LandMaskTests(unittest.TestCase):
    def test_buffer_is_seaward_only_and_500_metres(self):
        from build_land_mask import offshore_buffer
        from shapely.geometry import Point
        land = box(0, 0, 2000, 2000)
        sea_band = offshore_buffer(land)
        self.assertEqual(sea_band.intersection(land).area, 0)
        self.assertTrue(sea_band.covers(Point(2250, 1000)))
        self.assertTrue(sea_band.covers(Point(2500, 1000)))
        self.assertFalse(sea_band.covers(Point(2501, 1000)))
        self.assertFalse(sea_band.covers(Point(1999, 1000)))

    def test_conservative_bbox_classification(self):
        tile = {'bbox': [0, 0, 10, 10], 'image_size': [100, 100]}
        metadata = {'coverage_bbox': [0, 0, 10, 10]}
        geometries = {'land': box(0, 0, 5, 10), 'core': box(0, 0, 4, 10), 'coast': box(4, 0, 6, 10)}
        def result(bounds):
            return classify(tile, {'bbox_px': bounds}, metadata, geometries)
        self.assertEqual(result([10, 10, 20, 20]), 'excluded_land')
        self.assertEqual(result([45, 10, 55, 20]), 'excluded_land')
        self.assertEqual(result([35, 10, 65, 20]), 'excluded_land')
        self.assertEqual(result([51, 10, 59, 20]), 'excluded_coast')
        self.assertEqual(result([70, 10, 80, 20]), 'water')
        self.assertEqual(result([95, 10, 105, 20]), 'unknown')

    def test_real_geography_and_audit(self):
        from shapely.geometry import Point
        data, geometries = get_mask(ROOT)
        self.assertTrue(geometries['core'].covers(Point(105.84, 21.03)))
        self.assertFalse(geometries['land'].covers(Point(110, 15)))
        # The exclusion overlay cannot paint the inland half of a symmetric
        # shoreline buffer, or trace the artificial regional crop rectangle.
        self.assertLess(geometries['coast'].intersection(geometries['land']).area, 1e-7)
        self.assertIn('shoreline', geometries)
        extent_boundary = box(*data['coverage_bbox']).boundary
        overlap = geometries['shoreline'].intersection(extent_boundary)
        self.assertLess(overlap.length, 1e-8)
        report = validated_report(ROOT)
        for tile in report['tiles']:
            if tile['status'] != 'processed':
                continue
            self.assertEqual(tile['raw_detection_count'], len(tile['detections']) + len(tile['excluded_detections']))
            self.assertFalse(any(d['surface'].startswith('excluded_') for d in tile['detections']))
            self.assertTrue(all(d['surface'].startswith('excluded_') for d in tile['excluded_detections']))

    def test_map_overlay_is_zoom_aware_and_not_an_opaque_land_fill(self):
        import folium
        chart = folium.Map(location=[16, 108], zoom_start=5)
        add_map_layer(chart, ROOT)
        markup = chart.get_root().render()
        self.assertTrue('map.getZoom() >= 9' in markup)
        self.assertTrue("map.on('zoomend', update)" in markup)
        self.assertFalse('#ff9f0a' in markup)
        self.assertTrue("style.pointerEvents = 'none'" in markup)
        self.assertFalse('AIS minh' in markup)
        self.assertFalse('YOLO' in markup)
        self.assertLess(markup.index('.createPane('), markup.index('L.geoJson('))


if __name__ == '__main__':
    unittest.main()
