"""Prepare display projections offline so app visitors never wait for encoding."""
import json
from pathlib import Path
from PIL import Image
from map_raster import project_rgba
from scan_assets import validate_tile

def prepare(root):
    report = json.loads((root/'assets/real_scan/report.json').read_text())
    count = 0
    for tile in report['tiles']:
        if tile['status'] != 'processed':
            continue
        validate_tile(root, tile)
        directory = root/tile['asset_dir']
        if not (directory/'map.webp').exists():
            with Image.open(directory/'sar.png') as image:
                project_rgba(image, tile['bbox'][1], tile['bbox'][3]).save(
                    directory/'map.webp', lossless=True, method=0)
            count += 1
    print(f'Prepared {count} display images; original detection inputs unchanged.')

if __name__ == '__main__':
    prepare(Path(__file__).resolve().parents[1])
