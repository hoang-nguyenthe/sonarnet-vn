import hashlib
import sys
from pathlib import Path
import tempfile
import unittest
import numpy as np
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from sonarnet.evaluation.independent_sar import audit_manifest,operational_metrics
from sonarnet.evaluation.detection_metrics import evaluate_detections


class IndependentSARTests(unittest.TestCase):
    def test_false_alarms_and_geometric_error_have_real_denominators(self):
        rows=[dict(id='a',boxes_xyxy=[[0,0,10,10]],nearshore_gt=[True],valid_area_km2=2.,gsd_x_m=2.,gsd_y_m=3.),
              dict(id='background',boxes_xyxy=[],nearshore_gt=[],valid_area_km2=2.)]
        predictions={'a':(np.array([[1,0,11,10]]),np.array([.9])),
                     'background':(np.array([[2,2,3,3]]),np.array([.9]))}
        for row in rows:row['image_pixel_area']=1000000
        m,_=operational_metrics(rows,predictions)
        self.assertEqual(m['false_positive'],1)
        self.assertEqual(m['false_alarms_per_km2'],.25)
        self.assertEqual(m['nearshore_recall'],1.)
        self.assertEqual(m['center_error_m_median'],2.)
        self.assertEqual(m['box_width_error_m_median'],0.)
        self.assertEqual(m['center_error_px_median'],1.)
        self.assertEqual(m['false_alarms_per_megapixel'],.5)
        for row in rows:
            row.pop('valid_area_km2')
            row.pop('nearshore_gt')
        m,_=operational_metrics(rows,predictions)
        self.assertIsNone(m['false_alarms_per_km2'])
        self.assertIsNone(m['nearshore_recall'])

    def test_background_only_does_not_hide_false_alarms(self):
        m,_=operational_metrics([dict(id='a',boxes_xyxy=[])],{'a':(np.array([[0,0,1,1]]),np.array([.9]))})
        self.assertEqual(m['false_positive'],1)
        self.assertIsNone(m['recall'])
        with self.assertRaises(ValueError):
            evaluate_detections({'unknown':(np.array([[0,0,1,1]]),np.array([.9]))},{'a':np.empty((0,4))})
        with self.assertRaises(ValueError):
            evaluate_detections({'a':(np.array([[0,0,1,1]]),np.array([]))},{'a':np.empty((0,4))})

    def test_holdout_rejects_pixel_and_scene_leakage(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);rows=[]
            rng=np.random.default_rng(5)
            for i,split in enumerate(['train','val','test']):
                path=base/f'{i}.png'
                Image.fromarray(rng.integers(0,256,(32,32),dtype=np.uint8)).save(path)
                rows.append(dict(id=str(i),split=split,scene_id=str(i),region_id=str(i),
                    acquired_date_utc=f'2020-01-0{i+1}',annotation_status='reviewed',
                    image=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),boxes_xyxy=[]))
            manifest={'metadata_source':'unit fixture','images':rows}
            self.assertTrue(audit_manifest(manifest,base)['passed'])
            rows[2]['scene_id']='0'
            self.assertFalse(audit_manifest(manifest,base)['passed'])
            rows[2]['scene_id']='2';rows[2]['image']=rows[0]['image'];rows[2]['sha256']=rows[0]['sha256']
            result=audit_manifest(manifest,base)
            self.assertTrue(any('identical pixels' in e for e in result['errors']))
            self.assertTrue(result['review_required'])


if __name__=='__main__':unittest.main()
