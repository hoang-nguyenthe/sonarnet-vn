"""Create a verified review ZIP without private caches or full training images.

Run from a Git checkout. --include-published includes the full ~13 GB map archive;
otherwise the ZIP includes the pinned restoration tool and a real export sample.
Every packaged file is checked against its SHA-256 after writing the archive.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FOLLOWUP_FILES = {
    'scripts/prepare_ossdd_followup.py', 'scripts/evaluate_ossdd_followup.py',
    'scripts/evaluate_sar_resolution.py', 'scripts/fill_btc_bang_c.py',
    'scripts/build_ossdd_addendum.py', 'tests/test_ossdd_followup.py',
    'scripts/prepare_opensar_geo.py', 'scripts/evaluate_opensar_geo.py',
    'scripts/export_opensar_geo_examples.py', 'tests/test_opensar_geo.py',
    'scripts/build_opensar_geo_addendum.py',
    'scripts/render_review_videos.py',
    'scripts/evaluate_sar_recall_candidates.py', 'scripts/prepare_opensar_confirmation.py',
    'scripts/confirm_opensar_operating_point.py', 'scripts/diagnose_sar_recall.py',
    'tests/test_sar_recall_candidates.py',
    'scripts/append_sar_confirmation_pdf.py',
    'output/pdf/SonarNet_Bao_cao_Chang1_Cap_nhat_20261118.pdf',
    'output/pdf/SonarNet_Bao_cao_Chang1_SAR_co_toa_do_20261118.pdf',
    'output/pdf/SonarNet_Bao_cao_Chang1_Xac_nhan_SAR_20261118.pdf',
    'output/btc-original/01_DOC_TRUOC_KHI_NOP.md',
    'output/btc-original/02_NHAT_KY_PROMPT_MINH_CHUNG.md',
    'output/btc-original/03_KE_KHAI_SU_DUNG_AI.md',
    'output/btc-original/04_KICH_BAN_QUAY_DEMO.md',
    'output/btc-original/05_PHIEU_RA_SOAT_CA_THAT.md',
    'output/btc-original/06_LOI_DOC_VIDEO.json',
    'output/btc-original/AI2026_Mau_ho_so_BTC.docx',
    'output/btc-original/SonarNet_Ho_so_Bang_C_Mau_BTC.docx',
}
VIDEO_FILES = {'video-verification.json'} | {
    f'SonarNet_Bang_C_{kind}{suffix}'
    for kind in ('Thuyet_trinh', 'Demo')
    for suffix in ('.mp4', '.srt', '_Loi_doc.md')
}
CHANG1_REPORT = 'output/pdf/SonarNet_Bao_cao_Chang1_Giu_cap_AIS_20261118.pdf'
CHANG1_FILES = {
    name for name in FOLLOWUP_FILES
    if not name.startswith('output/') and name not in {
        'scripts/fill_btc_bang_c.py', 'scripts/render_review_videos.py',
    }
} | {
    CHANG1_REPORT,
    'NOP_CHANG_1.md',
    'assets/models/sonarnet_slc_vv_20261118.pt',
    'scripts/evaluate_ais_trajectories.py',
    'scripts/evaluate_coincident_sar_ais.py',
    'scripts/evaluate_frozen_ais_assignment.py',
    'scripts/evaluate_noaa_ais_replay.py',
    'scripts/demo_snapshot.py',
    'scripts/evaluate_opensar_adaptation.py',
    'scripts/evaluate_sar_review_budget.py',
    'scripts/evaluate_sar_multiscale.py',
    'scripts/evaluate_sar_finetune.py',
    'assets/models/sonarnet_slc_vv_640_20261118.pt',
    'scripts/replay_sar_multiscale.py',
    'scripts/evaluation_summary.py',
    'scripts/vn_recall_view.py',
    'scripts/prepare_vn_reference_rtc.py',
    'scripts/prepare_fresh_vn_references.py',
    'scripts/evaluate_review_ranking.py',
    'scripts/export_vn_recall_example.py',
    'scripts/evaluate_polarimetric_ranking.py',
    'scripts/fetch_vn_reference_rtc.py',
    'scripts/score_vn_reference_rtc.py',
    'scripts/build_chang1_adaptation_pdf.py',
    'scripts/export_opensar_adaptation_examples.py',
    'scripts/plot_opensar_adaptation_geography.py',
    'scripts/prepare_opensar_adaptation.py',
    'scripts/verify_chang1_runtime.py',
    'tests/test_demo_snapshot.py',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--include-published', action='store_true')
    parser.add_argument('--include-btc-followup', action='store_true',
                        help='Include the allowlisted Bảng C drafts and 18 Nov evidence.')
    parser.add_argument('--chang1', action='store_true',
                        help='Bundle source, reproducible evidence and the current Chặng 1 report.')
    parser.add_argument('--review-videos', type=Path,
                        help='Include only verified final MP4s, captions and narration from this directory.')
    args = parser.parse_args()
    if args.chang1 and (args.include_btc_followup or args.review_videos):
        parser.error('--chang1 cannot be combined with previous-round drafts or videos')
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    candidates = set(filter(None, tracked))
    candidates.update(str(p.relative_to(ROOT)) for p in (ROOT/'reports/final').rglob('*') if p.is_file())
    required = CHANG1_FILES if args.chang1 else FOLLOWUP_FILES if args.include_btc_followup else set()
    if required:
        missing = sorted(n for n in required if not (ROOT / n).is_file())
        if missing:
            raise FileNotFoundError(f'Expected follow-up files missing: {missing}')
        candidates.update(required)
    included, omitted = {}, []
    for name in sorted(candidates):
        path = ROOT/name
        parts = Path(name).parts
        private = any(p in {'.git', '.venv', '__pycache__', 'prompt_log', '.DS_Store'}
                      or p.startswith('._') for p in parts)
        private |= path.name == 'secrets.toml' or path.name.startswith('.env')
        private |= name in {'KE_KHAI_CONG_CU_AI.md', 'docs/PROMPT_LOG.md'}
        training = name.startswith('sonarnet_run/data/')
        scan_asset = name.startswith('assets/real_scan/') and name not in {
            'assets/real_scan/report.json', 'assets/real_scan/README.md',
            'assets/real_scan/coverage.json', 'assets/real_scan/refresh_status.json'}
        published = name.startswith('assets/real_scan/published/')
        include_scan = published and args.include_published
        earlier_output = args.chang1 and name.startswith('output/') and name != CHANG1_REPORT
        if private or training or earlier_output or (scan_asset and not include_scan) or not path.is_file():
            omitted.append(name)
            continue
        included[name] = path
    if args.review_videos:
        video_report = json.loads((args.review_videos / 'video-verification.json').read_text())
        for name in sorted(VIDEO_FILES):
            path = args.review_videos / name
            if not path.is_file() or path.is_symlink():
                raise FileNotFoundError(f'Expected video artifact: {path}')
            if path.suffix == '.mp4':
                info = next(v for v in video_report.values() if v['file'] == name)
                with path.open('rb') as f:
                    current = hashlib.file_digest(f, 'sha256').hexdigest()
                if current != info['sha256'] or not 0 < info['duration_seconds'] < 300:
                    raise ValueError(f'Video not verified for submission review: {name}')
            included['output/videos/' + name] = path
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_suffix('.zip.part')
    hashes = {}
    with zipfile.ZipFile(temp, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=3, allowZip64=True) as archive:
        for i, (name, path) in enumerate(included.items()):
            data = path.read_bytes()
            hashes[name] = hashlib.sha256(data).hexdigest()
            archive.writestr('SonarNet/'+name, data,
                             compress_type=zipfile.ZIP_STORED if path.suffix == '.mp4' else zipfile.ZIP_DEFLATED)
            if i and i % 1000 == 0:
                print(f'Packed {i}/{len(included)} files', flush=True)
        manifest = {
            'schema_version': 2,
            'source_base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            'snapshot': 'Working tree at packaging time; new and modified files may not be in source_base_commit.',
            'untracked_files_included': sorted(set(hashes) - set(tracked)),
            'includes_published_map_images': args.include_published,
            'files_sha256': hashes,
            'omitted_tracked_files': omitted,
            'status': ('Chặng 1 material; see NOP_CHANG_1.md for submission links and verification.'
                       if args.chang1 else 'Review package; see docs/FINAL_STATUS.md for unmet submission requirements.'),
        }
        archive.writestr('SonarNet/PACKAGE_MANIFEST.json', json.dumps(manifest, ensure_ascii=False, indent=2))
    with zipfile.ZipFile(temp) as archive:
        assert archive.testzip() is None, 'ZIP CRC verification failed'
        for name, expected in hashes.items():
            with archive.open('SonarNet/'+name) as source:
                actual = hashlib.file_digest(source, 'sha256').hexdigest()
            if actual != expected:
                raise ValueError('Packaged content mismatch: '+name)
    temp.replace(args.output)
    with args.output.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    args.output.with_suffix('.zip.sha256').write_text(digest+'  '+args.output.name+'\n')
    print(json.dumps({'zip': str(args.output), 'files': len(hashes), 'bytes': args.output.stat().st_size,
                      'sha256': digest, 'verified': True}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
