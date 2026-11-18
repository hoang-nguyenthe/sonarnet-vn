"""Fetch a predeclared, balanced OSSDD follow-up cohort from the author archive.

This is cross-dataset exploration, not a claim of verified region/date independence.
Selection uses metadata and hashes only, before opening test pixels or predictions.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import zipfile
import zlib

from download_ls_ssdd import RangeFile

REVISION = '46cee3d9e4ff8b4716e2ea5bbe2934e13cb36460'
URL = f'https://huggingface.co/datasets/sylviaHoch/OpenSARShip-Ship-Detection-Dataset/resolve/{REVISION}/ossdd.zip'
PUBLISHED_ZIP_SHA256 = 'a3954adc83680cef05ca5b5e534ea500f33b8512814a3ab5d47bdb6a3135e043'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--metadata', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    rows = list(csv.DictReader(args.metadata.open()))
    training_prefixes = {r['file_name'].split('_')[0] for r in rows if r['split'] == 'train'}
    selected = []
    quarantined = [r['file_name'] for r in rows if r['split'] in {'val','test'}
                   and r['file_name'].split('_')[0] in training_prefixes]
    for split, number in [('val', 100), ('test', 200)]:
        for category in ['land', 'water']:
            pool = [r for r in rows if r['split'] == split and r['class'] == category
                    and r['file_name'] not in quarantined]
            pool.sort(key=lambda r:hashlib.sha256(('sonarnet-ossdd-v1:'+r['file_name']).encode()).hexdigest())
            if len(pool) < number:
                raise ValueError('Insufficient samples for frozen selection')
            selected.extend(pool[:number])
    args.output.mkdir(parents=True, exist_ok=True)
    protocol = dict(source=URL, revision=REVISION,
        metadata_sha256=hashlib.sha256(args.metadata.read_bytes()).hexdigest(),
        selection='SHA256(sonarnet-ossdd-v1:filename), first 100 per class in val and 200 per class in test; exclude train-shared scene prefixes.',
        selected=selected, quarantined_train_shared_prefixes=quarantined,
        whole_archive_expected_sha256=PUBLISHED_ZIP_SHA256, whole_archive_verified=False,
        limits=['Balanced land/water cohort does not estimate natural operational prevalence.',
                'Acquisition date and geographic region are unavailable in supplied chip metadata.',
                'Scene prefix is a grouping identifier, not proof of date/region independence.',
                'Source paper documents native GRD spacing but inspected TIFFs lack georeferencing tags.',
                'Do not infer absolute geolocation accuracy or AIS identity from these annotations.'])
    pp = args.output/'protocol.json'
    if pp.exists() and json.loads(pp.read_text()) != protocol:
        raise ValueError('Existing cohort has a different protocol; use a new output path')
    pp.write_text(json.dumps(protocol, indent=2))
    remote = RangeFile(URL, block=1024**2)
    with zipfile.ZipFile(remote) as archive:
        wanted = {}
        for row in selected:
            key = Path(row['file_name']).stem
            for prefix, ext in [('Chip_VV','tif'), ('Metadata_aabb','txt')]:
                name = f'{prefix}\\{prefix}_{key}.{ext}'
                wanted[name] = (row['split'], key, prefix+'.'+ext)
        members = sorted((archive.getinfo(n) for n in wanted), key=lambda m:m.header_offset)
        records = []
        for i, member in enumerate(members):
            split, key, filename = wanted[member.filename]
            target = args.output/split/key/filename
            raw = target.read_bytes() if target.is_file() else None
            if raw is None or len(raw) != member.file_size or zlib.crc32(raw) != member.CRC:
                raw = archive.read(member)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
            records.append(dict(member=member.filename, path=str(target.relative_to(args.output)),
                bytes=len(raw), zip_crc32=member.CRC, sha256=hashlib.sha256(raw).hexdigest()))
            if i % 100 == 0:
                print(f'{i}/{len(members)} files; {remote.transferred/1024**2:.1f} MiB transferred', flush=True)
        (args.output/'download_manifest.json').write_text(json.dumps(dict(
            source=URL, whole_archive_verified=False, files=records,
            integrity='ZIP CRC for every member and SHA256 for every saved file'), indent=2))
    print('Finished: 200 validation and 400 test chips, VV and AABB annotations.', flush=True)


if __name__ == '__main__':
    main()
