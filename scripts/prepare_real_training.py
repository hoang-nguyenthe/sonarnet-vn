"""Audit official SAR-Ship archive and prepare date-grouped Sentinel-only data."""
import hashlib
import json
import re
import zipfile
from collections import Counter
from io import BytesIO
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'data_external/sar_ship/legacy_v0.zip'
EXPECTED = '6a185fbf2f51408d19ca941745581a8e1aabbacd33db6494985621086495481e'
OUT = ROOT / 'data_external/sentinel_training'


def main():
    assert hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() == EXPECTED
    OUT.mkdir(parents=True, exist_ok=True)
    seen, rows, skipped = set(), [], Counter()
    with zipfile.ZipFile(ARCHIVE) as archive:
        images = sorted(n for n in archive.namelist() if '/Sen_' in n and n.endswith('.jpg'))
        for name in images:
            match = re.search(r'_0(20\d{6})', name)
            if not match:
                skipped['unknown_date'] += 1
                continue
            day = match.group(1)
            bucket = int(hashlib.sha256(day.encode()).hexdigest()[:8],16) % 100
            split = 'test' if bucket < 15 else 'val' if bucket < 30 else 'train'
            raw = archive.read(name)
            with Image.open(BytesIO(raw)) as image:
                pixels = image.convert('RGB')
                digest = hashlib.sha256(pixels.tobytes()).hexdigest()
                size = image.size
            if digest in seen:
                skipped['duplicate_pixels'] += 1
                continue
            label = archive.read(str(Path(name).with_suffix('.txt'))).decode().strip()
            parsed = []
            valid = True
            for line in label.splitlines():
                values = list(map(float,line.split()))
                if len(values)!=5 or values[0]!=0 or not all(0<=v<=1 for v in values[1:]) or min(values[3:])<=0:
                    valid = False
                    break
                parsed.append(line)
            if not valid:
                skipped['invalid_label'] += 1
                continue
            seen.add(digest)
            stem = Path(name).stem
            for kind in ['images','labels']:
                (OUT / kind / split).mkdir(parents=True,exist_ok=True)
            (OUT / 'images' / split / f'{stem}.jpg').write_bytes(raw)
            (OUT / 'labels' / split / f'{stem}.txt').write_text('\n'.join(parsed)+'\n')
            rows.append(dict(name=stem, date_group=day, split=split, sha256_pixels=digest, objects=len(parsed),size=size))
    groups = {split:{r['date_group'] for r in rows if r['split']==split} for split in ['train','val','test']}
    assert not groups['train'] & groups['test'] and not groups['train'] & groups['val'] and not groups['test'] & groups['val']
    (OUT / 'dataset.yaml').write_text(f'path: {OUT}\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n  0: ship\n')
    report = dict(source='https://github.com/CAESAR-Radi/SAR-Ship-Dataset/tree/2021-04-update',archive_sha256=EXPECTED,
                  split_rule='SHA256 acquisition-date token from filename; all polarizations of same date stay together',
                  limitations='Filename date inferred, not scene metadata verified. Coastal Vietnam is a separate external domain. Dataset usage rights require review before redistributing images.',
                  counts=dict(Counter(r['split'] for r in rows)),skipped=dict(skipped),images=rows)
    (OUT / 'audit.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='images'},indent=2))


if __name__ == '__main__':
    main()
