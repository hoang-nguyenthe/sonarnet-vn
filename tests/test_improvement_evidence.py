import importlib
import json
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

    def test_six_coincident_acquisitions_support_both_reference_rules(self):
        app = AppTest.from_file(str(ROOT/'scripts/demo_app.py'),default_timeout=60)
        app.query_params['trang'] = 'minh-chung'
        app.run()
        self.assertFalse(app.exception)
        self.assertTrue(any('410 ứng viên radar' in x.value and '17 mốc' in x.value for x in app.markdown))
        app.radio(key='multiscene_anchor').set_value('near_stationary').run()
        self.assertFalse(app.exception)
        self.assertTrue(any('410 ứng viên radar' in x.value and '8 mốc' in x.value for x in app.markdown))
        table = next(x.value for x in app.dataframe if 'Giữ mốc để rà' in x.value.columns)
        proposal = table.iloc[-1]
        self.assertEqual(proposal['Đồng thuận'],6)
        self.assertEqual(proposal['Giữ mốc để rà'],2)

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

    def test_rtc_recall_compares_at_exact_review_counts(self):
        app = AppTest.from_file(str(ROOT/'scripts/demo_app.py'), default_timeout=60)
        app.query_params['trang'] = 'minh-chung'
        app.run()
        self.assertFalse(app.exception)
        self.assertIn('Phát hiện thêm với cùng số lượt rà', [item.value for item in app.subheader])
        self.assertTrue(any('**82/152** nhãn khớp' in item.value and '**116** điểm' in item.value
                            for item in app.markdown))
        app.radio(key='close_point_review_mode').set_value('equal_relaxed').run()
        self.assertFalse(app.exception)
        self.assertTrue(any('**102/152** nhãn khớp' in item.value and '**191** điểm' in item.value
                            for item in app.markdown))
        trials = next(item.value for item in app.dataframe if 'Hướng đã thử' in item.value.columns)
        self.assertEqual(trials.iloc[2][['116 lượt rà', '191 lượt rà']].tolist(), ['45/152', '63/152'])
        self.assertTrue(any(item.proto.label == 'Tải bảng đối chứng năm hướng thử'
                            for item in app.get('download_button')))
        tta = next(item.value for item in app.dataframe if 'Phương án thử' in item.value.columns)
        self.assertIn((191, '96/152', '102/152'),
                      list(tta[['Số lượt rà', 'Cấu hình gốc', 'Nhãn khớp']].itertuples(index=False,name=None)))
        self.assertTrue(any('Bắc Trung Bộ' in item.value and '6/8 và 6/8' in item.value for item in app.caption))
        self.assertTrue(any('58 → 64 nhãn khớp' in item.value and '78 lượt rà' in item.value
                            for item in app.caption))
        self.assertTrue(any(item.proto.label == 'Tải tọa độ để tính lại recall'
                            for item in app.get('download_button')))

    def test_rtc_transfer_shows_both_test_groups_and_source_example(self):
        app = AppTest.from_file(str(ROOT/'scripts/demo_app.py'), default_timeout=60)
        app.query_params['trang'] = 'minh-chung'
        app.run()
        self.assertFalse(app.exception)
        self.assertTrue(any('102/152 → 103/152' in item.value and '191 lượt rà' in item.value
                            for item in app.markdown))
        benchmark = next(item.value for item in app.table if 'Cách phát hiện radar' in item.value.columns)
        self.assertEqual(benchmark.iloc[-1][['116 lượt rà', '191 lượt rà']].tolist(), ['70/152', '103/152'])
        app.toggle(key='rtc_xview_example').set_value(True).run()
        self.assertFalse(app.exception)
        self.assertTrue(any('5 → 6 nhãn khớp' in item.value and '9 lượt rà' in item.value
                            for item in app.caption))
        self.assertTrue(any(item.proto.label == 'Tải thông tin ô ảnh xView3'
                            for item in app.get('download_button')))
        app.radio(key='rtc_transfer_group').set_value('confirmation').run()
        self.assertFalse(app.exception)
        self.assertTrue(any('6/8 → 8/8' in item.value and '10 lượt rà' in item.value
                            for item in app.markdown))

    def test_direct_recall_link_opens_the_benchmark(self):
        app = AppTest.from_file(str(ROOT/'scripts/demo_app.py'), default_timeout=60)
        app.query_params['trang'] = 'minh-chung'
        app.query_params['muc'] = 'recall'
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.radio(key='main_section').value, 'Minh chứng cải tiến')
        self.assertTrue(any('102/152 → 103/152' in item.value for item in app.markdown))
        table = next(item.value for item in app.table if 'Lượt rà' in item.value.columns)
        self.assertEqual(table['Lượt rà'].tolist(), [410, 1483])
        self.assertEqual(table['Thêm ô chồng lấn'].tolist(), ['9/13', '13/13'])
        self.assertTrue(any('191 → 234 lượt rà' in item.value for item in app.markdown))
        self.assertTrue(any('sonarnet-vn/#thu-hang' in item.value for item in app.markdown))
        self.assertTrue(any(item.proto.label == 'Tải số liệu thử gộp thứ hạng'
                            for item in app.get('download_button')))
        study = ROOT/'reports/final/stationary_ais_detection_20261120/dual-band'
        totals = json.loads((study/'results.json').read_text())['totals']
        before, after = (totals['narrow'][method]['100'] for method in ('prior','fused_xview3'))
        transition = f"{before['matched']}/{before['labels']} → {after['matched']}/{after['labels']}"
        self.assertTrue(any(transition in item.value and '410 lượt rà' in item.value for item in app.markdown))
        app.toggle(key='rtc_xview3_ais_example').set_value(True).run()
        self.assertFalse(app.exception)
        sample = json.loads((study/'example.json').read_text())
        self.assertTrue(any(sample['area'] in item.value and f"{sample['reviewed']} lượt rà" in item.value
                            for item in app.caption))
        app.radio(key='main_section').set_value('Hướng dẫn').run()
        self.assertNotIn('muc', app.query_params)

    def test_direct_link_opens_observation_sample(self):
        app = AppTest.from_file(str(ROOT/'scripts/demo_app.py'), default_timeout=60)
        app.query_params['trang'] = 'quan-sat'
        app.query_params['che-do'] = 'ho-so-mau'
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.radio(key='observation_workflow').value, 'Hồ sơ mẫu')
        self.assertTrue(any(item.proto.label == 'Tải ZIP ảnh và hồ sơ mẫu'
                            for item in app.get('download_button')))
        app.toggle(key='review_fixed_sample').set_value(True).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.selectbox(key='review_tile').value, 'cell_0_1')
        self.assertTrue(any(item.proto.label == 'Tải hồ sơ kèm ảnh'
                            for item in app.get('download_button')))
        app.radio(key='main_section').set_value('Minh chứng cải tiến').run()
        self.assertFalse(app.exception)
        self.assertNotIn('che-do', app.query_params)

    def test_review_input_is_bound_to_its_acquisition(self):
        from demo_snapshot import load_snapshot
        tile, images, bundle = load_snapshot(ROOT)
        app = AppTest.from_file(str(ROOT/'scripts/demo_app.py'), default_timeout=60)
        app.query_params['trang'] = 'quan-sat'
        app.query_params['che-do'] = 'ho-so-mau'
        note = lambda: next(item for item in app.text_area if item.label == 'Ghi chú kiểm tra')
        with patch('scan_view.load_snapshot', return_value=(tile, images, bundle)):
            app.run()
            app.toggle(key='review_fixed_sample').set_value(True).run()
            original_key = note().key
            note().set_value('Ghi chú cho lần chụp gốc')
            next(item for item in app.button if item.label == 'Lưu ghi chú ô ảnh').click().run()
            self.assertEqual(note().value, 'Ghi chú cho lần chụp gốc')
        updated = dict(tile, source_acquired_at='2026-09-12T04:00:00Z')
        with patch('scan_view.load_snapshot', return_value=(updated, images, bundle)):
            app.run()
            self.assertFalse(app.exception)
            self.assertNotEqual(note().key, original_key)
            self.assertEqual(note().value, '')
        with patch('scan_view.load_snapshot', return_value=(tile, images, bundle)):
            app.run()
            self.assertEqual(note().key, original_key)
            self.assertEqual(note().value, 'Ghi chú cho lần chụp gốc')

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
