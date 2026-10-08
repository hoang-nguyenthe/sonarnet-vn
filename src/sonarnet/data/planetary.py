"""Read Sentinel-1 RTC COG windows; no full-scene downloads or paid API.

Source: https://planetarycomputer.microsoft.com/dataset/sentinel-1-rtc
RTC is terrain-corrected gamma0, not Sentinel Hub's gamma0-ellipsoid product.
Public SAS access is checked at runtime; account policies may change. Tokens
are used in memory only and must never be included in manifests or logs.
"""
from dataclasses import dataclass
from datetime import date
from io import BytesIO
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

import numpy as np
from PIL import Image

STAC = 'https://planetarycomputer.microsoft.com/api/stac/v1'
SIGN = 'https://planetarycomputer.microsoft.com/api/sas/v1/sign'
COLLECTION = 'sentinel-1-rtc'


class PlanetaryError(RuntimeError):
    pass


class PlanetaryAccessError(PlanetaryError):
    """Stop this run on access, rate limit, or shared-service failure."""


def get_json(url):
    try:
        with urlopen(Request(url, headers={'User-Agent': 'SonarNet/1.0'}), timeout=45) as response:
            return json.load(response)
    except HTTPError as exc:
        # Do not include URL/query strings: signed asset URLs contain tokens.
        error = PlanetaryAccessError if exc.code in (401, 403, 429, 500, 502, 503, 504) else PlanetaryError
        raise error(f'Planetary Computer HTTP {exc.code}; no credentials or paid fallback attempted') from None
    except URLError:
        raise PlanetaryAccessError('Planetary Computer unavailable; retain published evidence') from None


@dataclass(frozen=True)
class RTCProduct:
    product_id: str
    acquired_at: str
    href: str
    native_resolution_m: float
    polarization: str = 'VV'


def search_rtc(bbox, start: date, end: date, limit=12):
    query = urlencode({'collections': COLLECTION, 'bbox': ','.join(map(str, bbox)),
                       'datetime': f'{start.isoformat()}T00:00:00Z/{end.isoformat()}T23:59:59Z',
                       'sortby': '-datetime', 'limit': min(100, max(1, limit))})
    data = get_json(STAC + '/search?' + query)
    products = []
    for item in data.get('features', []):
        props, assets = item.get('properties', {}), item.get('assets', {})
        if 'vv' not in assets or props.get('sar:instrument_mode') != 'IW':
            continue
        href = assets['vv']['href']
        validate_asset_url(href)
        spacing = float(props.get('sar:pixel_spacing_range', 0))
        if not 0 < spacing <= 25:
            continue
        products.append(RTCProduct(item['id'], props['datetime'], href, spacing))
    return sorted(products, key=lambda p: p.acquired_at, reverse=True)


def validate_asset_url(href):
    url = urlsplit(href)
    if (url.scheme != 'https' or url.hostname != 'sentinel1euwestrtc.blob.core.windows.net'
            or not url.path.startswith('/sentinel1-grd-rtc/') or not url.path.endswith('.tiff')):
        raise PlanetaryError('Unexpected Sentinel-1 RTC asset host or path')


def gray_rgba(values):
    """Linear gamma0 -> dB -> the existing fixed [-25,+5] dB display range."""
    pixels = np.ma.asarray(values)
    raw = np.asarray(pixels.data)
    valid = ~np.ma.getmaskarray(pixels) & np.isfinite(raw) & (raw > 0)
    gray = np.zeros(raw.shape, dtype=np.uint8)
    gray[valid] = np.rint(np.clip((10*np.log10(raw[valid])+25)/30, 0, 1)*255).astype('uint8')
    return np.dstack((gray, gray, gray, valid.astype('uint8')*255))


def render_rtc(product, bbox, width=1024):
    """Read only blocks overlapping the target grid, preserving no-data alpha."""
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import from_bounds
    from rasterio.vrt import WarpedVRT

    if not 64 <= width <= 1024:
        raise ValueError('RTC window must be 64..1024 pixels wide')
    west, south, east, north = bbox
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError('Invalid geographic bounds')
    if east-west > .11 or north-south > .11:
        raise ValueError('Read bounded detailed cells, never full scenes')
    validate_asset_url(product.href)
    signed = get_json(SIGN + '?' + urlencode({'href': product.href}))['href']
    validate_asset_url(signed)
    if urlsplit(signed)._replace(query='').geturl() != product.href:
        raise PlanetaryError('Signed asset does not match requested source')
    height = width
    try:
        with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR',
                          CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tiff', GDAL_HTTP_TIMEOUT='45',
                          GDAL_HTTP_MAX_RETRY='1', GDAL_HTTP_RETRY_DELAY='2',
                          GDAL_CACHEMAX=64*1024*1024, VSI_CACHE=False):
            with rasterio.open(signed) as source:
                if source.crs is None or source.count != 1 or source.dtypes[0] != 'float32':
                    raise PlanetaryError('Unexpected RTC raster metadata')
                if max(abs(source.res[0]), abs(source.res[1])) > 25 or not source.crs.is_projected:
                    raise PlanetaryError('RTC source resolution/CRS is not valid for detailed detection')
                with WarpedVRT(source, crs='EPSG:4326',
                               transform=from_bounds(*bbox, width, height),
                               width=width, height=height, resampling=Resampling.nearest,
                               nodata=-32768, warp_mem_limit=64) as grid:
                    rgba = gray_rgba(grid.read(1, masked=True))
    except PlanetaryError:
        raise
    except Exception:
        # GDAL exceptions may contain the SAS query. Never print or chain them.
        raise PlanetaryAccessError('RTC block read failed; source retained, stop before repeated downloads') from None
    if not rgba[:, :, 3].any():
        raise PlanetaryError('No valid RTC pixels in this cell')
    buffer = BytesIO()
    Image.fromarray(rgba).save(buffer, format='PNG')
    return buffer.getvalue()


def provenance(product):
    return {'source': 'Copernicus Sentinel-1 GRD · RTC by Catalyst · hosted by Microsoft Planetary Computer',
            'band': 'VV', 'source_collection': COLLECTION,
            'source_item_url': STAC + '/collections/' + COLLECTION + '/items/' + product.product_id,
            'source_asset_url': product.href, 'source_acquired_at': product.acquired_at,
            'source_native_pixel_spacing_m': product.native_resolution_m,
            'radiometry': 'terrain-corrected gamma0; 10*log10, fixed [-25,+5] dB; nearest-neighbour',
            'time_scope': 'Single RTC acquisition; exact acquisition time retained, no multi-day mosaic',
            'license': 'CC-BY-4.0', 'source_provider': 'planetary'}
