"""Read bounded historical Sentinel-1 RTC windows for the screened Vietnamese point labels."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import file_digest
import json
from pathlib import Path
import re
import time
from datetime import datetime
from urllib.parse import urlencode, urlsplit

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.vrt import WarpedVRT

from sonarnet.data.planetary import PlanetaryAccessError, SIGN, get_json, validate_asset_url

SIZE = 512


def digest(path):
    with path.open('rb') as f:
        return file_digest(f, 'sha256').hexdigest()


def download(row, all_regions, output):
    region = row['region']
    scene_name = row['scene']
    scene = all_regions[region][scene_name]
    ts, orbit = re.search(r'_(\d{8}T\d{6})_\d{8}T\d{6}_(\d{6})_', scene_name).groups()
    props = row['stac_identifiers']
    start = datetime.fromisoformat(props['start_datetime']).replace(tzinfo=None)
    if (int(props['sat:absolute_orbit']) != int(orbit)
            or abs((start - datetime.strptime(ts, '%Y%m%dT%H%M%S')).total_seconds()) >= 1):
        raise ValueError('RTC orbit or start time mismatch')
    href = row['rtc']['source_asset_url']
    validate_asset_url(href)
    signed = None
    out, failed = [], []
    for w in sorted(scene['windows'],key=lambda window:window['window_id']):
        bbox = w['bbox']
        west,south,east,north = bbox
        if east-west>.11 or north-south>.11:
            raise ValueError('Expected bounded source windows')
        p=output/f"window-{w['window_id']}.npz"
        if not p.is_file():
            for attempt in range(3):
                try:
                    if signed is None:
                        signed_url = get_json(SIGN+'?'+urlencode({'href':href}))['href']
                        validate_asset_url(signed_url)
                        if urlsplit(signed_url)._replace(query='').geturl() != href:
                            raise ValueError('Signed source does not match RTC product')
                        signed = signed_url
                    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR',
                                      CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tiff', GDAL_HTTP_TIMEOUT='18',
                                      GDAL_HTTP_MAX_RETRY='0', GDAL_CACHEMAX=64*1024*1024,
                                      VSI_CACHE=False, GDAL_HTTP_MULTIRANGE='SERIAL'):
                        with rasterio.open(signed) as source:
                            if source.count != 1 or source.dtypes[0] != 'float32' or not source.crs.is_projected:
                                raise ValueError('Unexpected source raster format')
                            params=dict(crs='EPSG:4326',transform=from_bounds(*bbox,SIZE,SIZE),width=SIZE,height=SIZE,
                                        resampling=Resampling.nearest,nodata=-32768,warp_mem_limit=32)
                            with WarpedVRT(source,**params) as grid:
                                band=grid.read(1,masked=True)
                                values=np.where(~np.ma.getmaskarray(band) & np.isfinite(band.data) & (band.data>0),
                                                band.data,0).astype(np.float32)
                    temp=p.with_suffix('.partial.npz')
                    np.savez_compressed(temp,gamma0=values)
                    temp.replace(p)
                    break
                except PlanetaryAccessError as e:
                    if '429' not in str(e):
                        raise
                    if attempt == 2:
                        failed.append(dict(window_id=w['window_id'],kind='rate_limit',category='429'))
                        print(region, orbit, 'rate-limited window', w['window_id'],flush=True)
                    else:
                        time.sleep(25 * (attempt+1))
                except (rasterio.errors.RasterioError, OSError) as e:
                    # Do not emit exception text since GDAL can include signed URLs.
                    kind=type(e).__name__
                    reason=str(e).lower()
                    category=next((k for k in ('timeout','403','429','502','503','range','curl','tiffread')
                                   if k in reason),'other')
                    if attempt==2:
                        failed.append(dict(window_id=w['window_id'],kind=kind,category=category))
                        print(region, orbit, 'skipped', w['window_id'], kind, category,flush=True)
                    else:
                        time.sleep(attempt+1)
        if p.is_file():
            with np.load(p,allow_pickle=False) as raw:
                values=raw['gamma0']
            if values.shape!=(SIZE,SIZE) or values.dtype!=np.float32 or not np.isfinite(values).all():
                raise ValueError('Invalid cached gamma0')
            out.append(dict(w,file=p.name,sha256=digest(p),valid_fraction=float(np.mean(values>0))))
    print(region, orbit, len(out), 'bounded RTC windows',flush=True)
    return dict(region=region,scene=scene_name,windows=out,failed_windows=failed,points=scene['points'],source=row['rtc'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path)
    args=parser.parse_args()
    source=args.root/'rtc-matching-with-lineage.json'
    labels=args.root/'screened.json'
    catalogue=json.loads(source.read_text())
    regions=json.loads(labels.read_text())['regions']
    output=args.root/'rtc-512'
    output.mkdir(exist_ok=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        cohorts=list(pool.map(lambda row:download(row,regions,output),catalogue))
    manifest=dict(catalogue_sha256=digest(source),screen_sha256=digest(labels),shape=[SIZE,SIZE],cohorts=cohorts)
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print('Downloaded',sum(len(c['windows']) for c in cohorts),'windows across',len(cohorts),'acquisitions',flush=True)


if __name__=='__main__':
    main()
