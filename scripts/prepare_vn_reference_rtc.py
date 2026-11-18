"""Screen the public Ai2 point-label archive for a historical coastal RTC check."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
from urllib.request import urlretrieve

from sonarnet.data.planetary import get_json, provenance, search_rtc

REVISION = '60b003d059937a9fcddbf6e1c9b64c00c33c0279'
CHECKSUM = 'd3a8bbd6c6685a6f8bb685f122b37fda613649d6da4c450e3240cace353ca2ac'
LABELS_URL = f'https://raw.githubusercontent.com/allenai/vessel-detection-sentinels/{REVISION}/data/metadata.sqlite3'
REGIONS = {
    'hai_phong_nearshore': (106.55, 20.35, 107.3, 20.95),
    'da_nang_nearshore': (108.03, 15.6, 108.8, 16.55),
    'vung_tau_nearshore': (106.84, 9.65, 108.15, 10.57),
}


def lonlat(x, y, zoom):
    size = 512 * (2 ** zoom)
    longitude = x / size * 360 - 180
    latitude = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / size))))
    return longitude, latitude


def label_db(directory):
    file = directory / 'metadata.sqlite3'
    if not file.is_file():
        temporary = file.with_suffix('.partial')
        urlretrieve(LABELS_URL, temporary)
        temporary.replace(file)
    with file.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != CHECKSUM:
            raise ValueError('Ai2 source checksum differs')
    return file


def screen(file):
    regions = {region: {} for region in REGIONS}
    with sqlite3.connect(file.resolve().as_uri() + '?mode=ro', uri=True) as connection:
        rows = connection.execute("""
            SELECT i.name,i.time,i.zoom,w.id,w.column,w.row,w.width,w.height,w.split,
                   l.column,l.row
              FROM windows w JOIN images i ON i.id=w.image_id
              LEFT JOIN labels l ON l.window_id=w.id
             WHERE w.dataset_id=1 AND w.hidden=0 AND i.hidden=0
             ORDER BY w.id,l.id
        """)
        for name, time, zoom, wid, x, y, width, height, split, px, py in rows:
            west, north = lonlat(x, y, zoom)
            east, south = lonlat(x + width, y + height, zoom)
            for region, (w, s, e, n) in REGIONS.items():
                if west >= e or east <= w or south >= n or north <= s:
                    continue
                scene = regions[region].setdefault(name, dict(acquired=time, windows={}, points=set()))
                scene['windows'][wid] = dict(window_id=wid, split=split, bbox=[west, south, east, north])
                if px is not None and py is not None and x <= px < x + width and y <= py < y + height:
                    lon, lat = lonlat(px, py, zoom)
                    if w <= lon <= e and s <= lat <= n:
                        scene['points'].add((lon, lat))
    for scenes in regions.values():
        for scene in scenes.values():
            scene['windows'] = list(scene['windows'].values())
            scene['points'] = sorted(scene['points'])
    return {region: scenes for region, scenes in regions.items() if scenes}


def exact_match(job):
    region, scene, block = job
    platform, timestamp, orbit = re.match(
        r'(S1[A-Z])_IW_GRDH_1SDV_(\d{8}T\d{6})_\d{8}T\d{6}_(\d{6})_', scene,
    ).groups()
    start = datetime.strptime(timestamp, '%Y%m%dT%H%M%S')
    matches = []
    for product in search_rtc(REGIONS[region], start.date(), start.date(), limit=48):
        if not product.product_id.lower().startswith(platform.lower()):
            continue
        if abs((datetime.fromisoformat(product.acquired_at).replace(tzinfo=None)-start).total_seconds()) > 30:
            continue
        rtc = provenance(product)
        props = get_json(rtc['source_item_url'])['properties']
        stac_start = datetime.fromisoformat(props['start_datetime']).replace(tzinfo=None)
        if abs((stac_start - start).total_seconds()) < 1 and int(props['sat:absolute_orbit']) == int(orbit):
            matches.append(dict(region=region, scene=scene, labels=len(block['points']), rtc=rtc,
                stac_identifiers={k:v for k,v in props.items() if k.startswith('sat:') or k in (
                    'sar:product_type','s1:shape','start_datetime','end_datetime','datetime')}))
    if len(matches) != 1:
        raise ValueError(f'Expected one exact RTC match for {scene}, got {len(matches)}')
    return matches[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    regions = screen(label_db(args.output))
    jobs = [(region, scene, block) for region, scenes in regions.items()
            for scene, block in scenes.items() if block['points']]
    with ThreadPoolExecutor(max_workers=3) as pool:
        matches = list(pool.map(exact_match, jobs))
    (args.output/'screened.json').write_text(json.dumps(dict(bounds=REGIONS, regions=regions), indent=2))
    (args.output/'rtc-matching-with-lineage.json').write_text(json.dumps(matches, indent=2))
    print(f"Exact RTC matches: {len(matches)} acquisitions, {sum(r['labels'] for r in matches)} point labels.")


if __name__ == '__main__':
    main()
