"""Regression cases for BTC: missing/conflicting data cannot assert identity or intent."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
sys.path[:0] = [str(Path(__file__).resolve().parents[1] / name) for name in ('src', 'scripts')]
from sonarnet.fusion.matching import Detection, SARAISFusion
from sonarnet.config import RunConfig as Config
from sonarnet.evaluation.fusion_metrics import evaluate_fusion
from review_workspace import (confirm_operational_review, operational_assessment,
                              export_workspace, import_workspace, printable_review)


class SafeConclusionsTests(unittest.TestCase):
    def test_all_missed_classes_remain_in_evaluation(self):
        from sonarnet.evaluation.ablation import _metrics_from_records
        from sonarnet.fusion.status import EVALUATION_STATES
        records=[dict(true_state=s,pred_state=None,true_mmsi=i,pred_mmsi=None)
                 for i,s in enumerate(['AIS_OK','AIS_MISMATCH','DARK'])]
        result=_metrics_from_records(records)
        self.assertEqual(result.n_evaluated,3)
        self.assertEqual(result.state_accuracy,0.)
        self.assertEqual(result.confusion_matrix[:,EVALUATION_STATES.index('MISSING_DATA')].sum(),3)

    def test_invalid_records_and_missing_declared_length_do_not_crash(self):
        fusion=SARAISFusion(Config())
        det=Detection(0,16.,108.,30.,8.,(0,0,3,1))
        records=[{'mmsi':None},{'mmsi':1,'timestamp':0,'lat':float('nan'),'lon':108.}]
        result=fusion.run('bad',[det],records,0.)
        self.assertEqual(result.states,['MISSING_DATA'])
        records=[dict(mmsi=1,timestamp=0,lat=16.,lon=108.,declared_length_m=None)]
        result=fusion.run('missing_size',[det],records,0.)
        self.assertEqual(result.states,['MISSING_DATA'])

    def test_missing_ais_is_missing_data(self):
        fusion = SARAISFusion(Config())
        det = Detection(0, 16., 108., 30., 8., (0, 0, 3, 1))
        self.assertEqual(fusion.classify_states([det], {}, {}), ['MISSING_DATA'])
        self.assertEqual(fusion.classify_states([det], {}, {1: object()}, ['out_of_range']), ['DARK'])
        self.assertEqual(fusion.classify_states([det], {}, {1: object()}, ['stale_ais']), ['MISSING_DATA'])
        self.assertEqual(fusion.classify_states([det], {0: 1}, {1: SimpleNamespace()}), ['MISSING_DATA'])
        self.assertEqual(fusion.classify_states([det], {0: 1}, {1: SimpleNamespace(declared_length_m=120)}), ['AIS_MISMATCH'])

    def test_abstention_not_dropped_from_metrics(self):
        result = evaluate_fusion(['AIS_OK', 'AIS_OK'], ['AIS_OK', 'MISSING_DATA'], [1,2], [1,None], [0,float('nan')])
        self.assertEqual(result.state_accuracy, .5)
        self.assertEqual(result.confusion_matrix.sum(), 2)
        self.assertLess(result.per_state_f1['AIS_OK'], 1)

    def test_confirm_requires_human_and_evidence(self):
        tile = dict(key='t',status='processed',image_sha256='a',weights_sha256='b',source='SAR',bbox=[1,2,3,4],detections=[])
        review = {'status':'Cần kiểm tra tiếp','note':'Kiểm tra AIS'}
        self.assertIsNone(operational_assessment(tile,review)['conclusion'])
        for who, basis, checked in [('', 'căn cứ', True), ('A', '', True), ('A','căn cứ', False)]:
            with self.assertRaises(ValueError):
                confirm_operational_review(tile, who, 'Chuyển chuyên viên xác minh', basis, checked)
        review['operational_review'] = confirm_operational_review(tile, 'Chuyên viên A', 'Cần bổ sung dữ liệu', 'Thiếu AIS cùng thời điểm', True)
        report = {'tiles':[tile]}
        restored = import_workspace(export_workspace(report, {'t':review}), report)
        self.assertEqual(restored['t'], review)
        self.assertIn('Chuyên viên A', printable_review(tile, review, '01/01/2026'))
        with self.assertRaises(ValueError):
            operational_assessment(dict(tile,image_sha256='changed'), review)


if __name__ == '__main__':
    unittest.main()
