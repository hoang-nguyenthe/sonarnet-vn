"""Prepare real Sentinel-1 positive AND background scenes for local training.

Preserve the official test scenes 11–15; hold out complete train scenes09–10
for validation. No patches from the same source scene cross these splits.
Raw public dataset and generated data remain ignored by git.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def split_for(stem):
    scene = int(stem.split('_')[0])
    if not 1 <= scene <= 15:
        raise ValueError('Unknown source scene')
    return 'train' if scene <= 8 else 'val' if scene <= 10 else 'test'


def labels_from_xml(raw):
    annotation = ET.fromstring(raw)
    width = int(annotation.findtext('size/width'))
    height = int(annotation.findtext('size/height'))
    if width <= 0 or height <= 0:
        raise ValueError('Invalid image dimensions')
    labels = []
    for obj in annotation.findall('object'):
        if obj.findtext('name', '').lower() not in {'ship', 'vessel'}:
            raise ValueError('Unexpected class')
        bounds = obj.find('bndbox')
        x1, y1, x2, y2 = [float(bounds.findtext(k)) for k in ('xmin','ymin','xmax','ymax')]
        # Pascal VOC coordinates are 1-based inclusive.
        x1, y1 = max(0, x1-1), max(0, y1-1)
        x2, y2 = min(width, x2), min(height, y2)
        if x2 <= x1 or y2 <= y1:
            raise ValueError('Empty label box')
        labels.append(f'0 {(x1+x2)/2/width:.8f} {(y1+y2)/2/height:.8f} {(x2-x1)/width:.8f} {(y2-y1)/height:.8f}')
    return labels


def main():
    archive = ROOT/'data_external/ls_ssdd/dataset.zip'
    output = ROOT/'data_external/ls_ssdd_yolo'
    counts = {split: Counter() for split in ('train','val','test')}
    for split in counts:
        for kind in ('images','labels'):
            (output/kind/split).mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as source:
        names = sorted(n for n in source.namelist() if '/Annotations_sub/' in n and n.endswith('.xml'))
        if len(names) != 9000:
            raise ValueError('Unexpected archive; expected 9000 patch annotations')
        for name in names:
            stem = Path(name).stem
            if not all(c.isdigit() or c == '_' for c in stem):
                raise ValueError('Invalid dataset identifier')
            split = split_for(stem)
            labels = labels_from_xml(source.read(name))
            jpeg = source.read(f'LS-SSDD-v1.0-OPEN/JPEGImages_sub/{stem}.jpg')
            (output/'images'/split/f'{stem}.jpg').write_bytes(jpeg)
            (output/'labels'/split/f'{stem}.txt').write_text('\n'.join(labels)+'\n' if labels else '')
            counts[split].update(images=1, objects=len(labels), background=int(not labels))
    (output/'data.yaml').write_text(f'path: {output}\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n  0: ship\n')
    digest = hashlib.file_digest(archive.open('rb'), 'sha256').hexdigest()
    manifest = {'source':'LS-SSDD-v1.0-OPEN', 'source_url':'https://github.com/TianwenZhang0825/LS-SSDD-v1.0-OPEN',
                'archive_sha256':digest, 'split_rule':'Scene01-08 train;09-10 val;11-15 official test',
                'backgrounds_retained':True, 'counts':counts}
    (output/'provenance.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps(manifest, indent=2), flush=True)


if __name__ == '__main__':
    main()
