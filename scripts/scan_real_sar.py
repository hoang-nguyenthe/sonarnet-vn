"""Scan every cell in a declared AOI; never select cells based on predictions."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'assets/real_scan'


def cell(task):
    key, bbox = task
    relative = f'assets/real_scan/{key}'
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/build_real_evidence.py'),
                             '--bbox', *map(str, bbox), '--width', '1024', '--output', relative,
                             *(['--reuse-image'] if (ROOT / relative / 'sar.png').exists() else [])],
                            cwd=ROOT, capture_output=True, text=True)
    if result.returncode:
        # Keep failed regions in the report rather than claiming no ships.
        return {'key': key, 'bbox': bbox, 'status': 'unavailable'}
    record = json.loads((ROOT / relative / 'manifest.json').read_text())
    record.update(key=key, status='processed', asset_dir=relative)
    print(f'{key}: {len(record["detections"])} candidates', flush=True)
    return record


def main():
    OUT.mkdir(exist_ok=True)
    tasks = [(f'cell_{row}_{col}', [round(107.7+col*.1, 4), round(10.35+row*.1, 4),
                                   round(107.8+col*.1, 4), round(10.45+row*.1, 4)])
             for row in range(3) for col in range(4)]
    with ThreadPoolExecutor(max_workers=1) as pool:
        records = list(pool.map(cell, tasks))
    report = {'bbox': [107.7, 10.35, 108.1, 10.65], 'observation_day_utc': '2026-09-12',
              'generated_at': datetime.now(timezone.utc).isoformat(),
              'threshold': .35, 'tiles': records,
              'limitations': 'Synthetic-trained model. Candidates unverified; not fishing classification. Daily composite. No ground-truth accuracy measured.'}
    if not any(r['status'] == 'processed' for r in records):
        raise RuntimeError('No cells processed; previous report retained')
    pending = OUT / 'report.pending.json'
    pending.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    pending.replace(OUT / 'report.json')
    print('Completed', sum(r['status'] == 'processed' for r in records), '/', len(records), flush=True)


if __name__ == '__main__':
    main()
