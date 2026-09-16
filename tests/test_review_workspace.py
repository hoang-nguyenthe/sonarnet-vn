import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from review_workspace import export_workspace, import_workspace, printable_review


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tile = dict(key='cell_0',status='processed',image_sha256='a',weights_sha256='b',source='SAR',bbox=[1,2,3,4],detections=[])
        self.report = {'tiles':[self.tile]}

    def test_roundtrip(self):
        notes = {'cell_0':{'status':'Cần kiểm tra tiếp','note':'Điểm sáng ở gần bờ'}}
        self.assertEqual(import_workspace(export_workspace(self.report,notes),self.report),notes)

    def test_reject_wrong_model(self):
        raw = export_workspace(self.report,{})
        self.tile['weights_sha256']='changed'
        with self.assertRaises(ValueError):
            import_workspace(raw,self.report)

    def test_reject_untrusted_content(self):
        for notes in [{'bad':{}}, {'cell_0':{'status':'verified','note':''}}, {'cell_0':{'status':'Chưa xem xét','note':[]}}]:
            with self.assertRaises(ValueError):
                import_workspace(export_workspace(self.report,notes),self.report)
        with self.assertRaises(ValueError):
            import_workspace('x'*1_000_001,self.report)

    def test_print_escapes_notes(self):
        result=printable_review(self.tile,{'status':'Chưa xem xét','note':'<script>alert(1)</script>'},'01/01/2026')
        self.assertNotIn('<script>',result)
        self.assertIn('&lt;script&gt;',result)


if __name__ == '__main__':
    unittest.main()
