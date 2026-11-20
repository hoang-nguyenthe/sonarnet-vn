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
CHANG1_SUPPLEMENT = {
    'reports/final/independent_sar/global_threshold_failures.json',
    'reports/final/independent_sar/global_threshold_predictions.json',
    'reports/final/opensar_geo_20261118/test_manifest.json.gz',
}
CHANG1_REPORT = 'output/pdf/SonarNet_Bao_cao_Chang1_Giu_cap_AIS_20261118.pdf'
PRESENTATION_FILES = (
    'SonarNet_Chung_ket_20261120.pptx',
    'SonarNet_Kich_ban_5_phut_20261120.md',
)
RANK_EVIDENCE = 'reports/final/vietnam_rtc_transfer_20261119/rank_fusion'
CHANG1_FILES = {
    name for name in FOLLOWUP_FILES
    if not name.startswith('output/') and name not in {
        'scripts/fill_btc_bang_c.py', 'scripts/render_review_videos.py',
    }
} | {
    CHANG1_REPORT,
    'NOP_CHANG_1.md',
    'docs/FINAL_STATUS.md',
    'docs/DEMO_RUNBOOK.md',
    'docs/AI_DECLARATION_CHANG1.md',
    'scripts/build_chang1_public_site.py',
    'scripts/ais_demo_cases.py',
    'web/chang1/index.html',
    'web/chang1/style.css',
    'web/chang1/app.js',
    'assets/models/sonarnet_slc_vv_20261118.pt',
    'scripts/evaluate_ais_trajectories.py',
    'scripts/evaluate_coincident_sar_ais.py',
    'scripts/prepare_multiscene_sar_ais.py',
    'scripts/fetch_multiscene_sar_ais.py',
    'scripts/evaluate_multiscene_sar_ais.py',
    'scripts/verify_multiscene_sar_ais.py',
    'reports/final/multiscene_sar_ais_20261119/results.json',
    'reports/final/multiscene_sar_ais_20261119/example-source.png',
    'reports/final/multiscene_sar_ais_20261119/example.jpg',
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
    'scripts/evaluate_rtc_contrast_recall.py',
    'scripts/evaluate_rtc_map_tta.py',
    'scripts/plot_rtc_recall_comparison.py',
    'scripts/confirm_rtc_equal_review.py',
    'scripts/evaluate_rtc_point_detector.py',
    'scripts/train_rtc_weak_boxes.py',
    'scripts/evaluate_rtc_radiometry.py',
    'scripts/evaluate_rtc_center_refinement.py',
    'scripts/evaluate_rtc_queue_allocation.py',
    'scripts/summarize_rtc_followup.py',
    'reports/final/vietnam_rtc_followup_20261119/summary.json',
    'reports/final/vietnam_rtc_followup_20261119/point/point-step-540.pt',
    'reports/final/vietnam_rtc_followup_20261119/weak_boxes/train/weights/best.pt',
    'scripts/replay_rtc_equal_review.py',
    'scripts/evaluate_rtc_weak_echoes.py',
    'scripts/evaluate_rtc_xview3_transfer.py',
    'scripts/replay_rtc_transfer.py',
    'scripts/export_rtc_transfer_example.py',
    'scripts/replay_rtc_additional_trials.py',
    'scripts/evaluate_rtc_rank_fusion.py',
    'scripts/evaluate_rtc_review_extension.py',
    'scripts/evaluate_rtc_stationary_ais_reference.py',
    'scripts/fetch_stationary_ais_rtc_bands.py',
    'scripts/evaluate_xview3_stationary_ais.py',
    'scripts/export_stationary_ais_transfer_example.py',
    'reports/final/stationary_ais_detection_20261120/dual-band/protocol.json',
    'reports/final/stationary_ais_detection_20261120/dual-band/results.json',
    'reports/final/stationary_ais_detection_20261120/dual-band/review-queues.json',
    'reports/final/stationary_ais_detection_20261120/dual-band/example.json',
    'reports/final/stationary_ais_detection_20261120/dual-band/example-before.png',
    'reports/final/stationary_ais_detection_20261120/dual-band/example-after.png',
    'reports/final/vietnam_rtc_transfer_20261119/extension/protocol.json',
    'reports/final/vietnam_rtc_transfer_20261119/extension/results.json',
    'reports/final/vietnam_rtc_transfer_20261119/extension/review-queues.json',
    'reports/final/vietnam_rtc_transfer_20261119/extension/selection.json',
    'reports/final/stationary_ais_detection_20261120/protocol.json',
    'reports/final/stationary_ais_detection_20261120/results.json',
    'reports/final/stationary_ais_detection_20261120/review-queues.json',
    'reports/final/stationary_ais_detection_20261120/reference.json',
    'reports/final/stationary_ais_detection_20261120/README.md',
    'reports/final/vietnam_rtc_transfer_20261119/summary.json',
    'reports/final/vietnam_rtc_transfer_20261119/README.md',
    'reports/final/vietnam_rtc_transfer_20261119/weak_echoes/protocol.json',
    'reports/final/vietnam_rtc_transfer_20261119/weak_echoes/selection.json',
    'reports/final/vietnam_rtc_transfer_20261119/weak_echoes/results.json',
    'reports/final/vietnam_rtc_transfer_20261119/weak_echoes/review-queues.json',
    'reports/final/vietnam_rtc_transfer_20261119/xview3/protocol.json',
    'reports/final/vietnam_rtc_transfer_20261119/xview3/selection.json',
    'reports/final/vietnam_rtc_transfer_20261119/xview3/results.json',
    'reports/final/vietnam_rtc_transfer_20261119/xview3/review-queues.json',
    'reports/final/vietnam_rtc_transfer_20261119/xview3/recovered-example.json',
    'reports/final/vietnam_rtc_transfer_20261119/xview3/recovered-before.png',
    'reports/final/vietnam_rtc_transfer_20261119/xview3/recovered-after.png',
    'scripts/export_rtc_review_evidence.py',
    'reports/final/vietnam_rtc_contrast_20261119/results.json',
    'reports/final/vietnam_rtc_tta_20261119/results.json',
    'reports/final/vietnam_rtc_tta_20261119/confirmation/results.json',
    'reports/final/vietnam_rtc_tta_20261119/equal-review.png',
    'reports/final/vietnam_rtc_tta_20261119/review-queues.json',
    'reports/final/vietnam_rtc_tta_20261119/recovered-example.json',
    'reports/final/vietnam_rtc_tta_20261119/recovered-before.png',
    'reports/final/vietnam_rtc_tta_20261119/recovered-after.png',
    'scripts/fetch_vn_reference_rtc.py',
    'scripts/score_vn_reference_rtc.py',
    'scripts/build_chang1_adaptation_pdf.py',
    'scripts/export_opensar_adaptation_examples.py',
    'scripts/plot_opensar_adaptation_geography.py',
    'scripts/prepare_opensar_adaptation.py',
    'scripts/verify_chang1_runtime.py',
    'tests/test_demo_snapshot.py',
} | {f'{RANK_EVIDENCE}/{name}' for name in (
    'README.md', 'candidates.json.gz', 'protocol.json', 'selection.json',
    'results.json', 'review-queues.json',
)}


def git_release(repository, commit):
    git = ['git', '-C', str(repository)]
    source = subprocess.check_output(
        git + ['rev-parse', '--verify', '--end-of-options', commit+'^{commit}'],
        text=True,
    ).strip()
    paths = {}
    for row in subprocess.check_output(git + ['ls-tree', '-rz', source]).split(b'\0'):
        if not row:
            continue
        entry, name = row.split(b'\t', 1)
        mode, kind, digest = entry.decode().split()
        if kind == 'blob' and mode in {'100644', '100755'}:
            paths[name.decode()] = digest
    return source, paths


def git_blob_id(data):
    # Git prefixes the file data with a typed header before hashing.
    sha = hashlib.sha1(f'blob {len(data)}\0'.encode())
    sha.update(data)
    return sha.hexdigest()


def file_from_commit(name, path, object_id, repository):
    if path.is_file() and not path.is_symlink():
        data = path.read_bytes()
        if git_blob_id(data) == object_id:
            return data
    data = subprocess.check_output(['git', '-C', str(repository), 'cat-file', 'blob', object_id])
    if git_blob_id(data) != object_id:
        raise ValueError('Git blob does not match pinned source: ' + name)
    return data


def submission_fields(commit, presentations=False):
    github = 'https://github.com/hoang-nguyenthe/sonarnet-vn'
    pdf = 'https://raw.githubusercontent.com/hoang-nguyenthe/sonarnet-vn'
    extra = ('\n## Thuyết trình và phản biện\n\n'
             'Mở thư mục [thuyết trình](thuyet_trinh/) để lấy PowerPoint và lời thoại 5 phút.\n'
             if presentations else '')
    return f'''# Nội dung điền cổng Chặng 1

## Mã nguồn

{github}/tree/{commit}

## Sản phẩm chạy thử

https://sonarnet.streamlit.app/?trang=minh-chung

## Báo cáo PDF

{pdf}/{commit}/{CHANG1_REPORT}

## Phiên bản mã nguồn

{commit}

## Đường dẫn đọc thêm minh chứng

https://hoang-nguyenthe.github.io/sonarnet-vn/

Đường dẫn bổ sung để xem số liệu, thử ca ghép AIS và tải hồ sơ mẫu.

Ba ô liên kết là bắt buộc. Ô phiên bản là tùy chọn. Xem [hướng dẫn nộp](NOP_CHANG_1.md)
để lấy nội dung dùng thử và khai báo AI. Chủ dự án kiểm tra lại cam kết và lưu
biên nhận từ [cổng nộp](https://ai.tainangviet.vn/dashboard/final) sau khi nộp.
{extra}
'''.encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--include-published', action='store_true')
    parser.add_argument('--source-commit',
                        help='Use exactly this Git revision for all tracked Chặng 1 files.')
    parser.add_argument('--git-repository', type=Path, default=ROOT,
                        help='Git repository containing the pinned commit. Defaults to this checkout.')
    parser.add_argument('--include-btc-followup', action='store_true',
                        help='Include the allowlisted Bảng C drafts and 18 Nov evidence.')
    parser.add_argument('--chang1', action='store_true',
                        help='Bundle source, reproducible evidence and the current Chặng 1 report.')
    parser.add_argument('--review-videos', type=Path,
                        help='Include only verified final MP4s, captions and narration from this directory.')
    parser.add_argument('--presentation-dir', type=Path,
                        help='Include the prepared final PowerPoint and five-minute script in the Chặng 1 handoff.')
    args = parser.parse_args()
    if args.chang1 and (args.include_btc_followup or args.review_videos):
        parser.error('--chang1 cannot be combined with previous-round drafts or videos')
    if args.presentation_dir and not args.chang1:
        parser.error('--presentation-dir requires --chang1')
    pinned = bool(args.source_commit)
    if pinned and not args.chang1:
        parser.error('--source-commit requires --chang1')
    if pinned:
        source_commit, published_tree = git_release(args.git_repository, args.source_commit)
        tracked = set(published_tree)
        candidates = tracked | {name for name in CHANG1_SUPPLEMENT if (ROOT / name).is_file()}
    else:
        tracked = set(filter(None, subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')))
        source_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        published_tree = {}
        candidates = set(tracked)
        candidates.update(str(p.relative_to(ROOT)) for p in (ROOT/'reports/final').rglob('*') if p.is_file())
    required = CHANG1_FILES if args.chang1 else FOLLOWUP_FILES if args.include_btc_followup else set()
    missing = sorted(required - tracked) if pinned else sorted(n for n in required if not (ROOT / n).is_file())
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
        earlier_handoff = args.chang1 and name in {'docs/PACKAGE_README.md', 'docs/FINAL_HANDOFF.md'}
        available = name in published_tree or (path.is_file() and not path.is_symlink())
        if private or training or earlier_output or earlier_handoff or (scan_asset and not include_scan) or not available:
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
    presentation_names = set()
    if args.presentation_dir:
        for name in PRESENTATION_FILES:
            path = args.presentation_dir / name
            if not path.is_file() or path.is_symlink() or not path.stat().st_size:
                raise FileNotFoundError(f'Expected finished presentation file: {path}')
            target = 'thuyet_trinh/' + name
            included[target] = path
            presentation_names.add(target)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_suffix('.zip.part')
    hashes = {}
    generated = (
        {'NOI_DUNG_DIEN_CONG.md': submission_fields(source_commit, bool(presentation_names))}
        if pinned else {}
    )
    with zipfile.ZipFile(temp, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=3, allowZip64=True) as archive:
        for i, (name, path) in enumerate(included.items()):
            if name in published_tree:
                data = file_from_commit(name, path, published_tree[name], args.git_repository)
            else:
                data = path.read_bytes()
            hashes[name] = hashlib.sha256(data).hexdigest()
            archive.writestr('SonarNet/'+name, data,
                             compress_type=zipfile.ZIP_STORED if path.suffix == '.mp4' else zipfile.ZIP_DEFLATED)
            if i and i % 1000 == 0:
                print(f'Packed {i}/{len(included)} files', flush=True)
        for name, data in generated.items():
            archive.writestr('SonarNet/'+name, data)
            hashes[name] = hashlib.sha256(data).hexdigest()
        manifest = {
            'schema_version': 3,
            'source_base_commit': source_commit,
            'snapshot': ('Published Git tree at source_base_commit; additional research and presentation files are listed separately.'
                         if pinned else 'Working tree at packaging time; files may differ from source_base_commit.'),
            'untracked_files_included': sorted(set(hashes) - tracked),
            'verified_git_blob_ids': {name: published_tree[name] for name in hashes if name in published_tree},
            'additional_research_files_sha256': {
                name: hashes[name] for name in hashes
                if pinned and name not in tracked and name not in generated and name not in presentation_names
            },
            'presentation_files_sha256': {name: hashes[name] for name in sorted(presentation_names)},
            'generated_files_sha256': {name: hashes[name] for name in generated},
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
