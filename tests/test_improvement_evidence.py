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
                  'missing_size':'MISSING_DATA','stale':'MISSING_DATA','crossing':'DARK','clean':'AIS_OK'}
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
        for scenario in ['Thiếu AIS','Kích thước mâu thuẫn','Hai quỹ đạo giao nhau']:
            app.selectbox(key='evidence_case').set_value(scenario).run()
            self.assertFalse(app.exception)
            self.assertTrue(any('MÔ PHỎNG' in i.value for i in app.info))
            self.assertGreater(len(app.dataframe),0)


if __name__=='__main__': unittest.main()
