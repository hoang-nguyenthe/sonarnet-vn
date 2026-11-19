"""Fetch the exact RTC windows and NOAA daily files named by the frozen protocol."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
from pathlib import Path
import subprocess
from zipfile import ZipFile
from urllib.parse import urlencode, urlsplit

from PIL import Image

from evaluate_noaa_ais_replay import NOAA, digest
from sonarnet.data.planetary import RTCProduct, SIGN, get_json, gray_rgba, provenance, validate_asset_url


def archive_day(root, day):
    name = f"AIS_{day.replace('-','_')}.zip"
    path = root/name
    if not path.is_file():
        temp = path.with_suffix('.part')
        subprocess.run(['curl','--fail','--silent','--show-error','--location','--retry','2',
                        '--connect-timeout','20','--max-time','900','--continue-at','-','--output',str(temp),NOAA+name],
                       check=True)
        with ZipFile(temp) as zipfile:
            if zipfile.namelist()!=[path.stem+'.csv']:
                raise ValueError('NOAA archive contains unexpected members')
        temp.replace(path)
    print(day,path.stat().st_size,digest(path),flush=True)


def radar_window(root, item, width):
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import from_bounds
    from rasterio.vrt import WarpedVRT

    product = RTCProduct(item['product'],item['acquired_at'],item['source_asset_url'],item['native_resolution_m'])
    folder=root/item['product']
    folder.mkdir(exist_ok=True)
    evidence=folder/'raster_provenance.json'
    if evidence.is_file():
        previous=json.loads(evidence.read_text())
        expected={int(row['tile']):row['sha256'] for row in previous['images']}
        if previous['source_acquired_at']!=item['acquired_at'] or set(expected)!=set(range(len(item['tiles_wsen']))):
            raise ValueError('Cached raster record does not match protocol')
        for i in expected:
            if digest(folder/f'tile_{i}.png')!=expected[i]:
                raise ValueError('Cached raster was modified')
        return
    missing = [i for i in range(len(item['tiles_wsen'])) if not (folder/f'tile_{i}.png').is_file()]
    if missing:
        # One public signing request per product. Keep all window reads on the
        # same connection and respect any service stop before another product.
        validate_asset_url(product.href)
        signed = get_json(SIGN+'?'+urlencode({'href':product.href}))['href']
        validate_asset_url(signed)
        if urlsplit(signed)._replace(query='').geturl()!=product.href:
            raise ValueError('Signed COG differs from catalogue asset')
        try:
            with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR',
                              CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tiff',GDAL_HTTP_TIMEOUT='45',
                              GDAL_HTTP_MAX_RETRY='1',GDAL_CACHEMAX=64*1024*1024,
                              VSI_CACHE=False,GDAL_HTTP_MULTIRANGE='SERIAL'):
                with rasterio.open(signed) as source:
                    if (source.crs is None or not source.crs.is_projected or source.count!=1
                            or source.dtypes[0]!='float32' or max(abs(x) for x in source.res)>25):
                        raise ValueError('Unexpected RTC metadata')
                    for i in missing:
                        bounds=item['tiles_wsen'][i]
                        if max(bounds[2]-bounds[0],bounds[3]-bounds[1])>.11:
                            raise ValueError('Only bounded RTC windows allowed')
                        with WarpedVRT(source,crs='EPSG:4326',transform=from_bounds(*bounds,width,width),
                                       width=width,height=width,resampling=Resampling.nearest,
                                       nodata=-32768,warp_mem_limit=64) as grid:
                            rgba=gray_rgba(grid.read(1,masked=True))
                        target=folder/f'tile_{i}.png'
                        temp=target.with_suffix('.part')
                        Image.fromarray(rgba).save(temp,format='PNG')
                        temp.replace(target)
                        print(product.product_id,i+1,len(item['tiles_wsen']),flush=True)
        except Exception:
            raise RuntimeError('RTC block read failed. Completed windows stay cached.') from None
    images=[dict(tile=i,sha256=digest(folder/f'tile_{i}.png')) for i in range(len(item['tiles_wsen']))]
    evidence.write_text(json.dumps(dict(provenance(product),images=images),ensure_ascii=False,indent=2)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('root',type=Path)
    p.add_argument('kind',choices=('ais','radar'))
    args=p.parse_args()
    protocol=json.loads((args.root/'protocol.json').read_text())
    products=protocol['products']
    if args.kind=='ais':
        days=sorted({datetime.fromisoformat(p['acquired_at']).date().isoformat() for p in products})
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(lambda day:archive_day(args.root,day),days))
    else:
        for item in products:
            radar_window(args.root,item,protocol['raster']['width'])


if __name__=='__main__':
    main()
