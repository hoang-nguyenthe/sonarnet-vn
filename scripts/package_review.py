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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--include-published', action='store_true')
    args = parser.parse_args()
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    candidates = set(filter(None, tracked))
    candidates.update(str(p.relative_to(ROOT)) for p in (ROOT/'reports/final').rglob('*') if p.is_file())
    included, omitted = [], []
    for name in sorted(candidates):
        path = ROOT/name
        parts = Path(name).parts
        private = any(p in {'.git', '.venv', '__pycache__', 'prompt_log'} for p in parts)
        private |= path.name == 'secrets.toml' or path.name.startswith('.env')
        private |= name in {'KE_KHAI_CONG_CU_AI.md', 'docs/PROMPT_LOG.md'}
        training = name.startswith('sonarnet_run/data/')
        scan_asset = name.startswith('assets/real_scan/') and name not in {
            'assets/real_scan/report.json', 'assets/real_scan/README.md'}
        published = name.startswith('assets/real_scan/published/')
        include_scan = published and args.include_published
        if private or training or (scan_asset and not include_scan) or not path.is_file():
            omitted.append(name)
            continue
        included.append(name)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_suffix('.zip.part')
    hashes = {}
    with zipfile.ZipFile(temp, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=3, allowZip64=True) as archive:
        for i, name in enumerate(included):
            data = (ROOT/name).read_bytes()
            hashes[name] = hashlib.sha256(data).hexdigest()
            archive.writestr('SonarNet/'+name, data)
            if i and i % 1000 == 0:
                print(f'Packed {i}/{len(included)} files', flush=True)
        manifest = {
            'schema_version': 1,
            'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            'includes_published_map_images': args.include_published,
            'files_sha256': hashes,
            'omitted_tracked_files': omitted,
            'status': 'Review package; see docs/FINAL_STATUS.md for unmet submission requirements.',
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
