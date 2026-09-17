from pathlib import Path
import unittest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


class PublicWorkflowTests(unittest.TestCase):
    def test_plain_language_and_evidence_navigation(self):
        app = AppTest.from_file(str(ROOT/'scripts/demo_app.py'), default_timeout=90).run()
        self.assertFalse(app.exception)
        self.assertEqual([tab.label for tab in app.tabs], ['Quan sát', 'Hướng dẫn'])
        controls = ' '.join(x.label for name in ('radio','toggle','button','selectbox') for x in getattr(app, name))
        for forbidden in ('YOLO', 'DEMO', 'giả lập', 'mô phỏng', 'AIS'):
            self.assertNotIn(forbidden, controls)
        evidence_button = next((x for x in app.button if x.label == 'Kiểm tra điểm này'), None)
        if evidence_button:
            evidence_button.click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.radio[0].value, 'Kiểm tra chi tiết')
            self.assertTrue(any(x.label == 'Lưu đánh giá' for x in app.button))
        else:
            app.radio[0].set_value('Kiểm tra chi tiết').run()
            self.assertFalse(app.exception)
