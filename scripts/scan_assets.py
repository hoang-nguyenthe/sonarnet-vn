"""Fail closed per tile without making the whole review page unavailable."""
from copy import deepcopy
from datetime import date
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
from PIL import Image


@lru_cache(maxsize=2048)
def _validate_image(path, fingerprint, size, expected_sha256):
    # Cache only a successful validation, never image bytes. Deployment or
    # file replacement invalidates the key; failed validation is not cached.
    with Image.open(path) as image:
        if image.size != size:
            raise ValueError('Image dimensions do not match manifest')
        image.verify()
    if expected_sha256:
        with path.open('rb') as source:
            digest = hashlib.file_digest(source, 'sha256').hexdigest()
        if digest != expected_sha256:
            raise ValueError('Image checksum mismatch')


def validate_tile(root, tile):
    directory = (root / tile['asset_dir']).resolve()
    if not directory.is_relative_to((root / 'assets/real_scan').resolve()):
        raise ValueError('Path outside published scan')
    w,s,e,n = tile['bbox']
    if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
        raise ValueError('Invalid geographic bounds')
    for filename in ['sar.png','detections.jpg']:
        path = directory / filename
        stat = path.stat()
        fingerprint = (stat.st_dev, stat.st_ino, stat.st_size,
                       stat.st_mtime_ns, stat.st_ctime_ns)
        _validate_image(path, fingerprint, tuple(tile['image_size']),
                        tile['image_sha256'] if filename == 'sar.png' else None)
    width,height = tile['image_size']
    ids=set()
    for candidate in tile['detections']:
        x1,y1,x2,y2 = candidate['bbox_px']
        values=[x1,y1,x2,y2,candidate['latitude'],candidate['longitude'],candidate['confidence']]
        if not all(math.isfinite(v) for v in values):
            raise ValueError('Non-finite detection')
        if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
            raise ValueError('Detection outside image')
        if not (w <= candidate['longitude'] <= e and s <= candidate['latitude'] <= n and 0 <= candidate['confidence'] <= 1):
            raise ValueError('Invalid detection location or score')
        if candidate['id'] in ids:
            raise ValueError('Duplicate detection ID')
        ids.add(candidate['id'])


def validated_report(root: Path):
    report=json.loads((root/'assets/real_scan/report.json').read_text())
    date.fromisoformat(report['observation_day_utc'])
    if not isinstance(report['tiles'],list) or not report['tiles']:
        raise ValueError('Empty scan')
    keys=[t['key'] for t in report['tiles']]
    if len(keys)!=len(set(keys)):
        raise ValueError('Duplicate tile keys')
    report=deepcopy(report)
    for tile in report['tiles']:
        if tile['status'] != 'processed':
            continue
        try:
            validate_tile(root,tile)
            from land_mask import filter_tile
            filter_tile(root, tile)
        except (ValueError,KeyError,TypeError,OSError):
            tile['status']='unavailable'
            tile['detections']=[]
    return report
