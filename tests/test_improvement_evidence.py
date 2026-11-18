import importlib
from unittest.mock import patch
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

    def test_home_shows_benchmark_and_opens_evidence(self):
        app = AppTest.from_file(str(ROOT/'scripts/demo_app.py'), default_timeout=60).run()
        self.assertFalse(app.exception)
        self.assertIn('Kết quả trước và sau cải tiến', [item.value for item in app.subheader])
        summary = next(item.value for item in app.markdown if 'chang1-results' in item.value)
        for value in ('3/147', '51/147', '36 lên 211', '898 xuống 879', '3.722'):
            self.assertIn(value, summary)
        proceed = next(button for button in app.button if button.label == 'Mở minh chứng và tải báo cáo')
        proceed.click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.radio(key='main_section').value, 'Minh chứng cải tiến')
        self.assertEqual(app.query_params['trang'], 'minh-chung')
        self.assertIn('Kết quả trước và sau cải tiến', [item.value for item in app.subheader])
        self.assertIn('51/147 → 60/147', [item.value for item in app.metric])
        self.assertIn('69/146 → 87/146', [item.value for item in app.metric])
        app.radio(key='recall_retest_mode').set_value('fixed_budget').run()
        self.assertFalse(app.exception)
        self.assertIn('36/147 → 38/147', [item.value for item in app.metric])
        self.assertIn('20/146 → 22/146', [item.value for item in app.metric])
        tables = [item.value for item in app.dataframe if 'Nhãn khớp' in item.value.columns]
        self.assertTrue(any('22/146 → 28/146' in table['Nhãn khớp'].values for table in tables))

    def test_vietnam_point_reference_counts_are_separate(self):
        app = AppTest.from_file(str(ROOT/'scripts/demo_app.py'), default_timeout=60)
        app.query_params['trang'] = 'minh-chung'
        app.run()
        self.assertFalse(app.exception)
        self.assertIn('Kiểm tra trên ảnh ven biển Việt Nam', [item.value for item in app.subheader])
        metrics = {item.label: item.value for item in app.metric}
        self.assertEqual(metrics['Nhãn điểm trong vùng chấm'], '224')
        self.assertEqual(metrics['Nhãn điểm khớp · cùng giới hạn rà'], '98 → 101')
        self.assertTrue(any('128/224' in item.value for item in app.caption))
        app.select_slider(key='vn_rtc_distance').set_value(50).run()
        self.assertFalse(app.exception)
        self.assertIn('Recall trên 12 lượt chụp mới', [item.value for item in app.subheader])
        app.radio(key='fresh_rtc_review_mode').set_value('matched_review_count').run()
        self.assertFalse(app.exception)
        table = next(item.value for item in app.dataframe if 'Ứng viên phải rà' in item.value
                     and 'Bản đồ · ngưỡng 0,35' in item.value.get('Phương án', []).values)
        self.assertEqual(table.iloc[0]['Nhãn khớp'], '80/152')
        self.assertEqual(table.iloc[1]['Nhãn khớp'], '80/152')
        expected = {'Xem ảnh radar thật và các điểm được tìm thêm',
                    'Thử xếp hạng bằng hai kênh radar VV và VH'}
        self.assertTrue(expected <= {item.label for item in app.expander})

    def test_direct_link_opens_observation_sample(self):
        app = AppTest.from_file(str(ROOT/'scripts/demo_app.py'), default_timeout=60)
        app.query_params['trang'] = 'quan-sat'
        app.query_params['che-do'] = 'ho-so-mau'
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.radio(key='observation_workflow').value, 'Hồ sơ mẫu')
        self.assertTrue(any(item.proto.label == 'Tải ZIP ảnh và hồ sơ mẫu'
                            for item in app.get('download_button')))
        app.radio(key='main_section').set_value('Minh chứng cải tiến').run()
        self.assertFalse(app.exception)
        self.assertNotIn('che-do', app.query_params)

    def test_view_import_recovers_if_hot_reload_removes_module_once(self):
        app = AppTest.from_file(str(ROOT/'scripts/demo_app.py'), default_timeout=60)
        app.query_params['trang'] = 'minh-chung'
        attempts = []
        load = importlib.import_module

        def fail_once(name, package=None):
            if name == 'improvement_view':
                attempts.append(name)
                if len(attempts) == 1:
                    raise KeyError(name)
            return load(name, package)

        with patch('importlib.import_module', side_effect=fail_once):
            app.run()

        self.assertEqual(attempts, ['improvement_view', 'improvement_view'])
        self.assertFalse(app.exception)
        self.assertIn('Recall trên 12 lượt chụp mới', [item.value for item in app.subheader])

    def test_repeatability_failure_is_visible_not_silently_aggregated(self):
        app=AppTest.from_file(str(ROOT/'scripts/demo_app.py'),default_timeout=60).run()
        app.radio[0].set_value('Minh chứng cải tiến').run()
        self.assertFalse(app.exception)
        self.assertTrue(any('Kiểm tra lại trên các cảnh mới' in item.value for item in app.subheader))
        self.assertTrue(any('3/147' in i.value and '1/35' in i.value for i in app.warning))


if __name__=='__main__': unittest.main()
