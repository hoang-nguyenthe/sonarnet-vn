import json
from pathlib import Path
import sys
import unittest
import hashlib
import zipfile
from io import BytesIO
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from review_packet import read_evidence_packet
from review_workspace import (export_workspace, import_workspace, printable_review, evidence_bundle,
                              session_reviews, restore_workspace, read_workspace, tile_identity, confirm_operational_review)


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tile = dict(key='cell_0',status='processed',image_sha256='a',weights_sha256='b',source='SAR',bbox=[1,2,3,4],detections=[])
        self.report = {'tiles':[self.tile]}

    def test_roundtrip(self):
        notes = {'cell_0':{'status':'Cần kiểm tra tiếp','note':'Điểm sáng ở gần bờ'}}
        self.assertEqual(import_workspace(export_workspace(self.report,notes),self.report),notes)

    def test_live_notes_survive_added_images(self):
        state = {}
        notes = session_reviews(state, self.report)
        notes['cell_0'] = {'status': 'Cần kiểm tra tiếp', 'note': 'Giữ lại'}
        expanded = {'tiles': [dict(self.tile, key='new'), self.tile]}
        self.assertEqual(session_reviews(state, expanded), notes)

    def test_changed_evidence_clears_widgets_not_archived_notes(self):
        state = {}
        notes = session_reviews(state, self.report)
        notes['cell_0'] = {'status': 'Cần kiểm tra tiếp', 'note': 'Ảnh cũ'}
        state.update(verdict_cell_0='Cần kiểm tra tiếp', note_cell_0='Ảnh cũ',
                     candidate_status_cell_0_1='Có khả năng là tàu')
        changed = {'tiles': [dict(self.tile, image_sha256='new')]}
        self.assertEqual(session_reviews(state, changed), {})
        self.assertNotIn('verdict_cell_0', state)
        self.assertNotIn('note_cell_0', state)
        self.assertNotIn('candidate_status_cell_0_1', state)
        self.assertEqual(session_reviews(state, self.report), notes)

    def test_new_images_do_not_invalidate_saved_notes(self):
        notes = {'cell_0': {'status': 'Cần kiểm tra tiếp', 'note': 'Giữ lại'}}
        raw = export_workspace(self.report, notes)
        expanded = {'tiles': [dict(self.tile, key='new_cell'), self.tile]}
        self.assertEqual(import_workspace(raw, expanded), notes)

    def test_policy_and_detection_changes_reject_old_notes(self):
        notes = {'cell_0': {'status':'Cần kiểm tra tiếp','note':'Ảnh gốc'}}
        raw = export_workspace(self.report, notes)
        for changes in ({'inference_policy_sha256': 'new'}, {'detections': [{'id': 1}]},
                        {'bbox': [2,3,4,5]}, {'source_acquired_at': '2026-09-12T03:01:00Z'},
                        {'reference_product': 'different-source'}):
            with self.assertRaises(ValueError):
                import_workspace(raw, {'tiles': [dict(self.tile, **changes)]})

    def test_partial_restore_keeps_matching_notes_and_identifies_changes(self):
        other = dict(self.tile, key='cell_1', source_acquired_at='2026-09-12T03:01:00Z')
        unrelated = dict(self.tile, key='cell_2')
        report = {'tiles': [self.tile,other,unrelated]}
        notes = {key:{'status':'Cần kiểm tra tiếp','note':key} for key in ('cell_0','cell_1')}
        notes['cell_1']['operational_review'] = confirm_operational_review(
            other,'Người rà A','Cần bổ sung dữ liệu','Cần bản tin AIS cùng thời điểm',True)
        raw = export_workspace(report,notes)
        self.assertEqual(set(json.loads(raw)['tile_identities']),set(notes))
        changed = {'tiles':[self.tile, dict(other,source_acquired_at='2026-09-12T03:02:00Z'),
                            dict(unrelated,image_sha256='new')]}
        self.assertEqual(restore_workspace(raw,changed),({'cell_0':notes['cell_0']},['cell_1']))
        with self.assertRaises(ValueError):
            import_workspace(raw,changed)

    def test_export_keeps_both_versions_and_reactivates_the_right_one(self):
        old = dict(self.tile, source_acquired_at='2026-09-12T03:00:00Z', detections=[{'id':1}])
        new = dict(old, source_acquired_at='2026-09-12T04:00:00Z')
        original, refreshed = {'tiles':[old]}, {'tiles':[new]}
        old_note = {'status':'Cần kiểm tra tiếp','note':'Ảnh lúc 03:00',
                    'candidate_labels':{'1':'Có khả năng là tàu'}}
        old_note['operational_review'] = confirm_operational_review(
            old,'Người rà A','Cần bổ sung dữ liệu','Cần AIS cùng giờ chụp',True)
        new_note = {'status':'Cần kiểm tra tiếp','note':'Ảnh lúc 04:00',
                    'candidate_labels':{'1':'Nhiễu / không phải tàu'}}
        state = {}
        session_reviews(state,original)['cell_0'] = old_note
        current = session_reviews(state,refreshed)
        self.assertEqual(current,{})
        current['cell_0'] = new_note
        saved = export_workspace(refreshed,current,archived=state['review_evidence_bank'])
        self.assertEqual(len(json.loads(saved)['records']),2)

        active, unavailable, waiting = read_workspace(saved,refreshed)
        self.assertEqual(active,{'cell_0':new_note})
        self.assertEqual(unavailable,['cell_0'])
        self.assertEqual(waiting,{('cell_0',tile_identity(old)):old_note})

        restored_state = {}
        session_reviews(restored_state,refreshed).update(active)
        restored_state['review_evidence_bank'].update(waiting)
        self.assertEqual(session_reviews(restored_state,original),{'cell_0':old_note})
        self.assertEqual(session_reviews(restored_state,refreshed),{'cell_0':new_note})

    def test_export_after_opening_previous_format_carries_missing_notes(self):
        old = dict(self.tile,key='old')
        note = {'status':'Cần kiểm tra tiếp','note':'Ảnh lưu trong tệp V3'}
        saved = export_workspace({'tiles':[old]}, {'old':note})
        active, unavailable, bank = read_workspace(saved,self.report)
        self.assertEqual(active,{})
        self.assertEqual(unavailable,['old'])
        again = export_workspace(self.report,active,archived=bank)
        self.assertEqual(import_workspace(again,{'tiles':[old]}),{'old':note})

    def test_schema_two_notes_restore_after_unreviewed_tile_changes(self):
        other = dict(self.tile,key='cell_1')
        original = [self.tile,other]
        notes = {'cell_0':{'status':'Cần kiểm tra tiếp','note':'Ghi chú cũ'}}
        confirmation = confirm_operational_review(
            self.tile,'Người rà A','Cần bổ sung dữ liệu','Cần bản tin AIS',True)
        confirmation.pop('evidence_identity_version')
        confirmation['evidence_identity'] = tile_identity(self.tile,version=2)
        notes['cell_0']['operational_review'] = confirmation
        raw = json.dumps(dict(schema_version=2,reviews=notes,
                              tile_identities={t['key']:tile_identity(t,version=2) for t in original}))
        self.assertEqual(import_workspace(raw,{'tiles':[self.tile,dict(other,image_sha256='new')]}),notes)

    def test_legacy_session_still_opens_on_exact_original_report(self):
        identity = [('cell_0', 'a', 'b', None)]
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        raw = json.dumps({'schema_version': 1, 'report_id': digest, 'reviews': {}})
        self.assertEqual(import_workspace(raw, self.report), {})

    def test_workspace_refuses_duplicate_review_fields(self):
        note = {'status': 'Cần kiểm tra tiếp', 'note': 'Ảnh gốc'}
        raw = export_workspace(self.report, {'cell_0': note})
        raw = raw.replace('"note":', '"note": "Ghi chú trước", "note":', 1)
        with self.assertRaisesRegex(ValueError, 'trường trùng'):
            import_workspace(raw, self.report)

    def test_export_verifies_decision_against_exact_source_evidence(self):
        root = Path(__file__).resolve().parents[1]
        pinned = root/'reports/final/export_verification/sample_evidence.zip'
        tile, images, _ = read_evidence_packet(pinned.read_bytes())
        review = {'status': 'Cần kiểm tra tiếp', 'note': 'Cần AIS cùng giờ chụp'}
        review['operational_review'] = confirm_operational_review(
            tile, 'Người rà A', 'Cần bổ sung dữ liệu', 'Cần AIS cùng giờ chụp', True
        )
        payload = evidence_bundle(root, tile, review, tile['observation_day_utc'], fixed_images=images)
        metadata, files, _ = read_evidence_packet(payload)
        self.assertEqual(metadata['operational_assessment']['authentication'], 'self_declared')
        self.assertEqual(metadata['operational_assessment']['status'], 'confirmed')

        # Updating the component hashes must not hide a decision bound to an older acquisition.
        metadata['observation_day_utc'] = '2026-11-19'
        files['evidence.json'] = json.dumps(metadata).encode()
        hashes = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()
                  if name != 'checksums.json'}
        files['checksums.json'] = json.dumps(hashes).encode()
        inconsistent = BytesIO()
        with zipfile.ZipFile(inconsistent, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in files.items():
                archive.writestr(name, data)
        with self.assertRaisesRegex(ValueError, 'không khớp bằng chứng'):
            read_evidence_packet(inconsistent.getvalue())

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
        raw = export_workspace(self.report,{'cell_0':{'status':'Cần kiểm tra tiếp','note':'Ảnh gốc'}})
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
        timed = dict(tile,source_acquired_at='2026-09-12T10:42:12.031Z')
        result = printable_review(timed, {'status':'Chưa xem xét','note':''}, '17/09/2026')
        self.assertIn('12/09/2026 10:42:12 UTC',result)
        self.assertNotIn('Ảnh ghép trong ngày',result)

    def test_print_includes_individual_review_status(self):
        detections = [dict(id=1,confidence=.55,latitude=3.,longitude=2.),
                      dict(id=2,confidence=.60,latitude=3.,longitude=2.)]
        review = {'status':'Cần kiểm tra tiếp','note':'','candidate_labels':{'1':'Có khả năng là tàu'}}
        html = printable_review(dict(self.tile,detections=detections), review, '12/09/2026')
        self.assertIn('Đánh giá của người rà', html)
        self.assertIn('<td>Có khả năng là tàu</td>', html)
        self.assertIn('<td>Chưa đánh giá</td>', html)

    def test_bundle_refuses_new_source_bytes_with_previous_identity(self):
        from PIL import Image
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = root/'assets/real_scan/cell'
            directory.mkdir(parents=True)
            Image.new('RGB',(24,24),'white').save(directory/'sar.png')
            Image.new('RGB',(24,24),'white').save(directory/'detections.jpg')
            digest = hashlib.sha256((directory/'sar.png').read_bytes()).hexdigest()
            tile = dict(self.tile,asset_dir='assets/real_scan/cell',image_sha256=digest)
            review = {'status':'Cần kiểm tra tiếp','note':'Giữ ảnh ban đầu'}
            evidence_bundle(root,tile,review,'12/09/2026')
            Image.new('RGB',(24,24),'black').save(directory/'sar.png')
            with self.assertRaisesRegex(ValueError,'Ảnh nguồn đã thay đổi'):
                evidence_bundle(root,tile,review,'12/09/2026')

    def test_real_bundle_integrity(self):
        root = Path(__file__).resolve().parents[1]
        package = root / 'PACKAGE_MANIFEST.json'
        fixed_images = None
        if package.is_file() and not json.loads(package.read_text())['includes_published_map_images']:
            from demo_snapshot import load_snapshot
            tile, fixed_images, _ = load_snapshot(root)
        else:
            report = json.loads((root / 'assets/real_scan/report.json').read_text())
            tile = next(t for t in report['tiles'] if t['status'] == 'processed')
        raw = evidence_bundle(
            root, tile, {'status': 'Chưa xem xét', 'note': 'test'}, '12/09/2026',
            fixed_images=fixed_images,
        )
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            checks=json.loads(archive.read('checksums.json'))
            self.assertEqual(set(checks),{'source.png','candidates.jpg','raw-model-candidates.jpg','review.html','evidence.json'})
            for name,digest in checks.items():
                self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(),digest)
        with self.assertRaises(ValueError):
            evidence_bundle(root,dict(tile,asset_dir='../'),{},'')


if __name__ == '__main__':
    unittest.main()
