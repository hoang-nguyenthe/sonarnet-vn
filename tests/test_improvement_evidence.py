import sys
from pathlib import Path
import unittest
from streamlit.testing.v1 import AppTest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from improvement_view import run_scenario


class ImprovementEvidenceTests(unittest.TestCase):
    def test_scenarios_use_conservative_states(self):
        expected={'missing':'MISSING_DATA','distant':'DARK','conflict':'AIS_MISMATCH',
                  'missing_size':'MISSING_DATA','stale':'MISSING_DATA','crossing':'DARK','bias':'DARK','clean':'AIS_OK'}
        for scenario,state in expected.items():
            with self.subTest(scenario=scenario):
                _,payload=run_scenario(scenario)
                self.assertEqual(set(payload['states']),{state})
                self.assertIsNone(payload['operational_assessment']['conclusion'])
        _,payload=run_scenario('clean',age_s=181)
        self.assertFalse(payload['matches'])
        _,payload=run_scenario('clean',age_s=10,sigma_m=151)
        self.assertFalse(payload['matches'])

    def test_interactive_missing_conflicting_crossing_cases(self):
        app=AppTest.from_file(str(ROOT/'scripts/demo_app.py'),default_timeout=60).run()
        app.radio[0].set_value('Minh chứng cải tiến').run()
        self.assertFalse(app.exception)
        for scenario in ['Thiếu AIS','Kích thước mâu thuẫn','Hai quỹ đạo giao nhau','Chuỗi AIS lệch vị trí']:
            app.selectbox(key='evidence_case').set_value(scenario).run()
            self.assertFalse(app.exception)
            self.assertTrue(any('MÔ PHỎNG' in i.value for i in app.info))
            self.assertGreater(len(app.dataframe),0)

    def test_external_benchmark_keeps_field_limits_visible(self):
        app=AppTest.from_file(str(ROOT/'scripts/demo_app.py'),default_timeout=60).run()
        app.radio[0].set_value('Minh chứng cải tiến').run()
        self.assertFalse(app.exception)
        self.assertTrue(any('Đối chứng SAR có tọa độ' in item.value for item in app.subheader))
        summary={metric.label:metric.value for metric in app.metric}
        self.assertEqual(summary['Tìm thấy trong 500 m từ bờ'],'4/14')
        self.assertTrue(any('không phải GPS độc lập' in i.value for i in app.warning))

    def test_direct_evidence_link_opens_real_sample_without_map(self):
        app = AppTest.from_file(str(ROOT/'scripts/demo_app.py'), default_timeout=60)
        app.query_params['trang'] = 'minh-chung'
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.radio(key='main_section').value, 'Minh chứng cải tiến')
        app.toggle(key='evidence_open_snapshot').set_value(True).run()
        self.assertFalse(app.exception)
        self.assertTrue(any('Chưa có kết luận nghiệp vụ' in item.value for item in app.info))
        app.radio(key='main_section').set_value('Hướng dẫn').run()
        self.assertEqual(app.query_params['trang'], 'huong-dan')

    def test_repeatability_failure_is_visible_not_silently_aggregated(self):
        app=AppTest.from_file(str(ROOT/'scripts/demo_app.py'),default_timeout=60).run()
        app.radio[0].set_value('Minh chứng cải tiến').run()
        self.assertFalse(app.exception)
        self.assertTrue(any('Kiểm tra lại trên các cảnh mới' in item.value for item in app.subheader))
        self.assertTrue(any('3/147' in i.value and '1/35' in i.value for i in app.warning))


if __name__=='__main__': unittest.main()
