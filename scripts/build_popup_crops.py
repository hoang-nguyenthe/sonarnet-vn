#!/usr/bin/env python3
"""Build small, click-on-demand radar crops for the public map.

The map must never embed every crop as base64 in its HTML.  These JPEGs are
served only when a visitor opens a marker, so the first national view stays
small while every marker retains its source-image evidence.
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image


def crop_name(tile: dict, candidate: dict) -> str:
    return f"{tile['key']}--{candidate['id']}.jpg"


def build(root: Path) -> int:
    report = json.loads((root / 'assets' / 'real_scan' / 'report.json').read_text())
    output = root / 'scripts' / 'static' / 'crops'
    output.mkdir(parents=True, exist_ok=True)
    count = 0
    for tile in report.get('tiles', []):
        if tile.get('status') != 'processed':
            continue
        source = root / tile['asset_dir'] / 'sar.png'
        if not source.is_file():
            continue
        with Image.open(source) as image:
            for candidate in tile.get('detections', []):
                target = output / crop_name(tile, candidate)
                x1, y1, x2, y2 = candidate['bbox_px']
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                half = max(80, (x2 - x1) / 2 + 42, (y2 - y1) / 2 + 42)
                crop = image.crop((max(0, int(cx - half)), max(0, int(cy - half)),
                                   min(image.width, int(cx + half)), min(image.height, int(cy + half))))
                crop.thumbnail((280, 280), Image.Resampling.LANCZOS)
                crop.convert('RGB').save(target, 'JPEG', quality=84, optimize=True)
                count += 1
    return count


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    print(f'Built {build(root)} popup crops')
