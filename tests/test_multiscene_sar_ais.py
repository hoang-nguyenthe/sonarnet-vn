import json
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts'),str(ROOT/'src')]
from evaluate_multiscene_sar_ais import fixed_references, stable_window
from sonarnet.fusion.matching import Detection

RULE=dict(holdout_s=120,max_median_displacement_m=35,minimum_fixes=2,minimum_span_s=30,
          max_nearest_offset_s=65,unique_match_m=100,competitor_m=250)


def fixes(ship, positions):
    return [dict(MMSI=ship,second=t,LAT=lat,LON=lon) for t,lat,lon in positions]


class MultisceneSarAisTest(unittest.TestCase):
    def test_stationary_anchor_is_bracketed_and_withheld_from_matching_input(self):
        frame=pd.DataFrame(
            fixes(100000001,[(900,40.,-74.),(955,40.,-74.),(1045,40.0001,-74.),(1180,40.,-74.)]) +
            fixes(100000002,[(935,40.02,-74.),(1045,40.025,-74.),(1180,40.03,-74.)]) +
            fixes(100000003,[(945,40.04,-74.),(970,40.04,-74.)])
        )
        points,ids,history,eligible=stable_window(frame,1000,RULE,lambda p:True)
        self.assertEqual([ids[i] for i in np.flatnonzero(eligible)],[100000001])
        self.assertTrue(all(abs(r['timestamp']-1000)>120 for r in history))
        detections=[Detection(0,points[0].lat,points[0].lon,np.nan,np.nan,(0,0,1,1))]
        reference=fixed_references(detections,points,ids,eligible,RULE)
        self.assertEqual(reference[0][0],100000001)

    def test_close_moving_observation_prevents_stationary_reference(self):
        frame=pd.DataFrame(
            fixes(100000001,[(955,40.,-74.),(1045,40.,-74.)]) +
            fixes(100000002,[(930,40.001,-74.),(1045,40.008,-74.)])
        )
        _,_,_,eligible=stable_window(frame,1000,RULE,lambda p:True)
        self.assertFalse(eligible.any())


if __name__=='__main__':
    unittest.main()
