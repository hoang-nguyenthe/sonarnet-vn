"""Build a reproducible Vietnam maritime land mask from GSHHG full resolution.

Usage: python scripts/build_land_mask.py
Build dependencies: pyshp, pyproj, shapely. Source archive is not committed.
L1 deliberately excludes inland lakes too: this is a maritime detector.
"""
import hashlib
import gzip
import json
from pathlib import Path
import zipfile

from shapely.geometry import box, shape, mapping
from shapely.ops import transform, unary_union
from shapely import make_valid

ROOT = Path(__file__).resolve().parents[1]


def offshore_buffer(land_metric, distance_m=500):
    """Only water outside land, not a symmetric band across the shoreline."""
    return land_metric.buffer(distance_m).difference(land_metric)


def display_mapping(geometry):
    """Submetre JSON rounding only for the smaller, non-authoritative overlay."""
    def rounded(value):
        if isinstance(value, (tuple, list)):
            return [rounded(item) for item in value]
        return round(value, 6)
    result = mapping(geometry)
    return dict(result, coordinates=rounded(result['coordinates']))


def main():
    import shapefile
    from pyproj import Transformer
    archive = ROOT / 'data_external/gshhg/gshhg-shp-2.3.7.zip'
    output = ROOT / 'assets/land_mask'
    output.mkdir(parents=True, exist_ok=True)
    coverage = [101, 5, 117, 25]
    padded = box(100, 4, 118, 26)
    with zipfile.ZipFile(archive) as z:
        stem = 'GSHHS_shp/f/GSHHS_f_L1'
        with z.open(stem+'.shp') as shp, z.open(stem+'.shx') as shx, z.open(stem+'.dbf') as dbf:
            reader = shapefile.Reader(shp=shp, shx=shx, dbf=dbf)
            polygons = [make_valid(shape(item.__geo_interface__)).intersection(padded)
                        for item in reader.iterShapes(bbox=padded.bounds)]
        for name in ['LICENSE.TXT', 'COPYING.LESSERv3', 'README.TXT']:
            (output / name).write_bytes(z.read(name))
    land = unary_union(polygons)
    projection = '+proj=aeqd +lat_0=15 +lon_0=109 +datum=WGS84 +units=m'
    forward = Transformer.from_crs('EPSG:4326', projection, always_xy=True).transform
    backward = Transformer.from_crs(projection, 'EPSG:4326', always_xy=True).transform
    metric = transform(forward, land)
    extent = box(*coverage)
    # Buffer before clipping to avoid treating the regional crop as a coast.
    geometries = {
        'land': land.intersection(extent),
        'core': transform(backward, metric.buffer(-500)).intersection(extent),
        'coast': transform(backward, offshore_buffer(metric)).intersection(extent),
        # Take the physical shoreline before the final regional clipping. A
        # rectangular coverage edge must never be drawn as a coastline.
        'shoreline': land.boundary.intersection(extent),
    }
    # Use a small metric tolerance only for display; filtering retains the
    # full source geometry. The display ring remains strictly seaward too.
    display_land = metric.simplify(10, preserve_topology=True)
    display = {
        'coast': transform(backward, offshore_buffer(display_land).simplify(10, preserve_topology=True).difference(display_land)).intersection(extent),
        'shoreline': transform(backward, display_land.boundary).intersection(extent),
    }
    payload = {
        'version': 'gshhg-2.3.7-full-maritime-seaward-500m-v2',
        'source': 'GSHHG 2.3.7 full resolution L1 (2017-06-15)',
        'source_url': 'https://www.soest.hawaii.edu/pwessel/gshhg/',
        'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
        'coverage_bbox': coverage, 'coastal_buffer_m': 500,
        'scope': 'Maritime: inland waters inside L1 polygons are excluded too. Not an administrative boundary.',
        'geometry': {key: mapping(value) for key, value in geometries.items()},
        'display': {key: display_mapping(value) for key, value in display.items()},
        'display_simplification_m': 10,
        'distance_method': 'Regional azimuthal equidistant metres; 500 m engineering exclusion, not a legal limit.',
    }
    (output / 'vietnam.json.gz').write_bytes(gzip.compress(json.dumps(payload, separators=(',', ':')).encode(), mtime=0))
    print('Built', output / 'vietnam.json.gz')


if __name__ == '__main__':
    main()
