"""Fail closed per tile without making the whole review page unavailable."""
from copy import deepcopy
from datetime import date
import hashlib
import json
import math
from pathlib import Path
from PIL import Image


def validate_tile(root, tile):
    directory = (root / tile['asset_dir']).resolve()
    if not directory.is_relative_to((root / 'assets/real_scan').resolve()):
        raise ValueError('Path outside published scan')
    w,s,e,n = tile['bbox']
    if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
        raise ValueError('Invalid geographic bounds')
    for filename in ['sar.png','detections.jpg']:
        with Image.open(directory/filename) as image:
            if list(image.size) != tile['image_size']:
                raise ValueError('Image dimensions do not match manifest')
            image.verify()
    if hashlib.sha256((directory/'sar.png').read_bytes()).hexdigest() != tile['image_sha256']:
        raise ValueError('Image checksum mismatch')
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
        except (ValueError,KeyError,TypeError,OSError):
            tile['status']='unavailable'
            tile['detections']=[]
    return report
