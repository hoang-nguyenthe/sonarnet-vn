"""Cache aligned, raw RTC VV and VH windows for the fixed stationary AIS experiment."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlencode, urlsplit

import numpy as np
from PIL import Image

from evaluate_noaa_ais_replay import digest
from sonarnet.data.planetary import SIGN, get_json, gray_rgba, validate_asset_url


def retrieve_band(asset, windows, width, folder, name):
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import from_bounds
    from rasterio.vrt import WarpedVRT

    todo = [(i, bounds) for i, bounds in enumerate(windows)
            if not (folder/f'{name}-{i}.npz').is_file()]
    if not todo:
        return
    validate_asset_url(asset)
    signed = get_json(SIGN + '?' + urlencode({'href': asset}))['href']
    validate_asset_url(signed)
    if urlsplit(signed)._replace(query='').geturl() != asset:
        raise ValueError('Signed URL differs from catalogue asset')
    options = dict(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR',
                   CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tiff', GDAL_HTTP_TIMEOUT='35',
                   GDAL_HTTP_MAX_RETRY='0', GDAL_CACHEMAX=64*1024*1024,
                   VSI_CACHE=False, GDAL_HTTP_MULTIRANGE='SERIAL')
    try:
        with rasterio.Env(**options), rasterio.open(signed) as source:
            if not source.crs.is_projected or source.dtypes != ('float32',):
                raise ValueError('Unexpected RTC sensor raster')
            for index, bounds in todo:
                if max(bounds[2]-bounds[0], bounds[3]-bounds[1]) > .11:
                    raise ValueError('Unduly large RTC window')
                with WarpedVRT(source, crs='EPSG:4326', transform=from_bounds(*bounds, width, width),
                               width=width, height=width, resampling=Resampling.nearest,
                               nodata=-32768, warp_mem_limit=64) as grid:
                    raw = grid.read(1, masked=True)
                    valid = (~np.ma.getmaskarray(raw)) & (raw.data > 0) & np.isfinite(raw.data)
                    gamma = np.where(valid, raw.data, 0).astype(np.float32)
                intermediate = folder/f'{name}-{index}.partial.npz'
                np.savez_compressed(intermediate, gamma0=gamma)
                intermediate.replace(folder/f'{name}-{index}.npz')
                print(folder.name, name, index, flush=True)
    except (OSError, rasterio.RasterioError) as error:
        # Never display a failure message containing a signed storage URL.
        raise RuntimeError(f'RTC raster read failed for {folder.name} {name}: {type(error).__name__}') from None


def receipt(source, cache, product, width, assets):
    rows = []
    for i, bbox in enumerate(product['tiles_wsen']):
        paths = {name: cache/f'{name}-{i}.npz' for name in ('vv', 'vh')}
        vv_path = paths['vv']
        with np.load(vv_path, allow_pickle=False) as raw:
            rgba = gray_rgba(raw['gamma0'])
        image_path = source/f'tile_{i}.png'
        with Image.open(image_path) as image:
            equal = np.array_equal(rgba, np.asarray(image.convert('RGBA')))
        if not equal:
            raise ValueError(f'Raw VV raster does not recreate archived preview at tile {i}')
        rows.append(dict(tile=i, bbox=bbox, width=width, preview_sha256=digest(image_path),
                         files={name:dict(name=path.name, sha256=digest(path)) for name,path in paths.items()}))
    return dict(product=product['product'], utc=product['acquired_at'], source_item=product['source_item_url'],
                source_assets=assets, windows=rows)


def fetch_scene(source, target, product, width):
    index = target/'manifest.json'
    if index.is_file():
        old = json.loads(index.read_text())
        if old['product'] != product['product'] or old['utc'] != product['acquired_at']:
            raise ValueError('Cached RTC product differs')
        current = receipt(source,target,product,width,old['source_assets'])
        if old != current:
            raise ValueError('Cached dual-band pixels changed')
        return
    item = get_json(product['source_item_url'])
    if item['id'] != product['product'] or item['assets']['vv']['href'] != product['source_asset_url']:
        raise ValueError('RTC VV item differs from the frozen catalogue')
    assets = {name: item['assets'][name]['href'] for name in ('vv', 'vh')}
    for name, uri in assets.items():
        validate_asset_url(uri)
        retrieve_band(uri, product['tiles_wsen'], width, target, name)
    data = receipt(source,target,product,width,assets)
    staging=index.with_suffix('.part')
    staging.write_text(json.dumps(data,indent=2)+'\n')
    staging.replace(index)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('source','output'):
        parser.add_argument('--'+option,type=Path,required=True)
    args=parser.parse_args()
    frozen=json.loads((args.source/'protocol.json').read_text())
    args.output.mkdir(exist_ok=True)
    for product in frozen['products']:
        target=args.output/product['product']
        target.mkdir(exist_ok=True)
        fetch_scene(args.source/product['product'],target,product,frozen['raster']['width'])


if __name__=='__main__':
    main()
