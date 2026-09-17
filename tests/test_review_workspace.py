import json
from pathlib import Path
import sys
import unittest
import hashlib
import zipfile
from io import BytesIO

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from review_workspace import export_workspace, import_workspace, printable_review, evidence_bundle


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tile = dict(key='cell_0',status='processed',image_sha256='a',weights_sha256='b',source='SAR',bbox=[1,2,3,4],detections=[])
        self.report = {'tiles':[self.tile]}

    def test_roundtrip(self):
        notes = {'cell_0':{'status':'Cần kiểm tra tiếp','note':'Điểm sáng ở gần bờ'}}
        self.assertEqual(import_workspace(export_workspace(self.report,notes),self.report),notes)

    def test_new_images_do_not_invalidate_saved_notes(self):
        notes = {'cell_0': {'status': 'Cần kiểm tra tiếp', 'note': 'Giữ lại'}}
        raw = export_workspace(self.report, notes)
        expanded = {'tiles': [dict(self.tile, key='new_cell'), self.tile]}
        self.assertEqual(import_workspace(raw, expanded), notes)

    def test_policy_and_detection_changes_reject_old_notes(self):
        raw = export_workspace(self.report, {})
        for changes in ({'inference_policy_sha256': 'new'}, {'detections': [{'id': 1}]}, {'bbox': [2,3,4,5]}):
            with self.assertRaises(ValueError):
                import_workspace(raw, {'tiles': [dict(self.tile, **changes)]})

    def test_legacy_session_still_opens_on_exact_original_report(self):
        identity = [('cell_0', 'a', 'b', None)]
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        raw = json.dumps({'schema_version': 1, 'report_id': digest, 'reviews': {}})
        self.assertEqual(import_workspace(raw, self.report), {})

    def test_candidate_labels_roundtrip(self):
        report = {'tiles': [dict(self.tile, detections=[{'id': 1}, {'id': 2}])]}
        notes = {'cell_0': {
            'status': 'Cần kiểm tra tiếp',
            'note': 'Đối chiếu ảnh độ phân giải cao hơn',
            'candidate_labels': {'1': 'Có khả năng là tàu', '2': 'Nhiễu / không phải tàu'},
        }}
        self.assertEqual(import_workspace(export_workspace(report,notes),report),notes)

    def test_reject_invalid_candidate_label(self):
        for labels in ({'not-an-id': 'Có khả năng là tàu'}, {'999': 'Có khả năng là tàu'}):
            notes = {'cell_0': {
                'status': 'Chưa xem xét', 'note': '', 'candidate_labels': labels,
            }}
            with self.assertRaises(ValueError):
                import_workspace(export_workspace(self.report,notes),self.report)

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

    def test_evidence_uses_own_acquisition_not_report_date(self):
        tile = dict(self.tile, observation_day_utc='2026-09-12')
        result = printable_review(tile, {'status':'Chưa xem xét','note':''}, '17/09/2026')
        self.assertIn('Ngày ảnh UTC: 12/09/2026', result)
        self.assertNotIn('17/09/2026', result)

    def test_real_bundle_integrity(self):
        root=Path(__file__).resolve().parents[1]
        report=json.loads((root/'assets/real_scan/report.json').read_text())
        tile=next(t for t in report['tiles'] if t['status']=='processed')
        raw=evidence_bundle(root,tile,{'status':'Chưa xem xét','note':'test'},'12/09/2026')
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            checks=json.loads(archive.read('checksums.json'))
            self.assertEqual(set(checks),{'source.png','candidates.jpg','raw-model-candidates.jpg','review.html','evidence.json'})
            for name,digest in checks.items():
                self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(),digest)
        with self.assertRaises(ValueError):
            evidence_bundle(root,dict(tile,asset_dir='../'),{},'')


if __name__ == '__main__':
    unittest.main()
