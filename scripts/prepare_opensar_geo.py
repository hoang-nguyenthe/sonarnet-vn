"""Lock a georeferenced Sentinel-1 SLC cohort using publisher XML and ASF footprints."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import xml.etree.ElementTree as ET
import zipfile

import numpy as np
from pyproj import Transformer
from shapely import make_valid
from shapely.geometry import Point, Polygon, box, mapping, shape
from shapely.ops import transform, unary_union
from shapely.strtree import STRtree
import shapefile
import tifffile

ROOT = Path(__file__).resolve().parents[1]
REVISION = 'e90a0c0465cfb8484b4f356ef968d976054f453a'
CHECKSUM = {
    'val_labels.tar.zst': '5abe968a54ad6fc863ab39ef7e7acfa1e2a11cfb9563e9f02d616a15ec64b3fe',
    'test_labels.tar.zst': '649af181e149733f6ddbdea457a50c6ea7fbce6a979797e2557276a68045e4dc',
    'train_labels.tar.zst': 'eacce986c1c63e5ee508bae84c7d8c743f49a8bab32f8ef9046c802d685ec91b',
    'val_patches.tar.zst': '6eddea1165c7daffb17d14e62b006ea6f479fc406ae62b7c8ede467dc62b0379',
    'test_patches.tar.zst': '86bb88b93599c57190ef8baea231df5a0c07af919c42f063bf3e6c502c562ac7',
    'gshhg-shp-2.3.7.zip': '8dbbe7e071e77e9e75f2d639239099ebca8d5c16d6a07df8169729d49f15cf41',
}


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def archive_members(path, pattern):
    """Match regular files and read bytes without unpacking archive paths."""
    with subprocess.Popen(['zstd', '-dc', str(path)], stdout=subprocess.PIPE) as process:
        with tarfile.open(fileobj=process.stdout, mode='r|') as archive:
            for info in archive:
                match = re.fullmatch(pattern, info.name)
                if info.isfile() and match:
                    if not 0 < info.size <= 4 * 1024**2:
                        raise ValueError(f'Unexpected member size: {info.name}')
                    yield match.group(1), archive.extractfile(info).read()
        process.stdout.read()  # consume archive padding before waiting
        if process.wait():
            raise ValueError(f'Corrupt archive: {path}')


def read_annotations(dirname):
    result = {}
    for split in ('train', 'val', 'test'):
        for ident, raw in archive_members(dirname / f'{split}_labels.tar.zst', r'labels/DB_OPENSAR_VD_(\d+)\.xml'):
            if ident in result:
                raise ValueError(f'Reused chip ID: {ident}')
            doc = ET.fromstring(raw)
            scene = doc.findtext('./SARData/SARProduct')
            date = datetime.strptime(doc.findtext('./SARData/Time_Interval/Start'), '%Y%m%d_%H%M%S')
            coord = doc.find('./ProcessingData/Corner_Coord')
            if (coord.findtext('Scene_Sample').split() != ['1', '512', '512', '1'] or
                    coord.findtext('Scene_Line').split() != ['1', '1', '512', '512']):
                raise ValueError(f'Unsupported corner convention: {ident}')
            coords = [[float(s) for s in coord.findtext(name).split()] for name in ('Longitude', 'Latitude')]
            corners = list(map(list, zip(*coords)))
            if len(corners) != 4 or not Polygon(corners).is_valid or Polygon(corners).area <= 0:
                raise ValueError(f'Invalid footprint: {ident}')
            labels = []
            for ship in doc.findall('./ProcessingData/List_of_ships/Ship'):
                b = [float(ship.findtext('./BoundingBox/' + name)) for name in ('Left', 'Top', 'Right', 'Bottom')]
                xy = [float(ship.findtext('./Centroid_Position/' + name)) for name in ('Scene_Sample', 'Scene_Line')]
                ll = [float(ship.findtext('./Centroid_Position/' + name)) for name in ('Longitude', 'Latitude')]
                length = float(ship.findtext('Size', 'NaN'))
                valid = (1 <= b[0] <= b[2] <= 512 and 1 <= b[1] <= b[3] <= 512 and
                         all(1 <= x <= 512 for x in xy) and np.isfinite(ll).all())
                labels.append(dict(box=[b[0]-1, b[1]-1, b[2], b[3]] if valid else None,
                    xml_center_px=[x-.5 for x in xy] if valid else None, xml_center_wgs84=ll if valid else None,
                    is_vessel=ship.findtext('Is_Vessel') == 'True', confidence=ship.findtext('Confidence'),
                    xml_reported_length_m=length if np.isfinite(length) and length > 0 else None))
            if len(labels) != int(doc.findtext('./ProcessingData/StatisticsReport/Number_of_ships')):
                raise ValueError(f'Label count mismatch: {ident}')
            result[ident] = dict(id=ident, split=split, scene_id=scene, day=date.date().isoformat(),
                acquired_utc=date.replace(tzinfo=timezone.utc).isoformat(), corners_wgs84=corners,
                annotation_sha256=hashlib.sha256(raw).hexdigest(), labels=labels)
    return result


def laea(geometry):
    center = geometry.centroid
    crs = f'+proj=laea +lat_0={center.y:.8f} +lon_0={center.x:.8f} +datum=WGS84 +units=m +type=crs'
    return crs, Transformer.from_crs('EPSG:4326', crs, always_xy=True).transform


def screen_scenes(annotations, asf, policy):
    rows = defaultdict(list)
    for r in annotations.values():
        rows[r['scene_id']].append(r)
    footprints = {k: unary_union([Polygon(r['corners_wgs84']) for r in v]).convex_hull for k, v in rows.items()}
    reference = {r['source_product_id']: r for r in policy['scenes'] if r['split'] in ('train', 'val')}
    asf_polys = defaultdict(list)
    for f in asf['features']:
        key = f['properties']['sceneName']
        if key in reference:
            asf_polys[key].append(shape(f['geometry']))
    if set(asf_polys) != set(reference):
        raise ValueError('Missing exact ASF product footprint for LS-SSDD training/tuning lineage')
    training = [(k, unary_union(v), reference[k]['acquired_date_utc']) for k, v in asf_polys.items()]
    result = {}
    for k, v in rows.items():
        split, day, fp = v[0]['split'], v[0]['day'], footprints[k]
        if any((r['split'], r['day']) != (split, day) for r in v):
            raise ValueError(f'Scene crosses official partition/date: {k}')
        reasons = []
        distances = {}
        for ident, ref, refday in training:
            if refday == day:
                reasons.append('shared_utc_date:' + ident)
            # Approximate local metric distance. Skip remote footprints to avoid projecting antipodes.
            if fp.distance(ref) > 1.5:
                continue
            _, forward = laea(fp)
            d = transform(forward, fp).distance(transform(forward, ref))
            distances[ident] = round(d, 2)
            if d <= 20000:
                reasons.append('footprint_distance_at_most_20km:' + ident)
        result[k] = dict(split=split, day=day, chips=len(v), footprint=mapping(fp),
            nearest_checked_reference_distance_m=distances, excluded=bool(reasons), reasons=reasons)
    return result


def validation_buffer(annotations, scenes):
    """Keep all clean test scenes; reserve validation support >=20 km away."""
    tests = []
    for scene in scenes.values():
        if scene['split'] == 'test' and not scene['excluded']:
            footprint = shape(scene['footprint'])
            _, forward = laea(footprint)
            tests.append((scene['day'], footprint, forward, transform(forward, footprint)))
    skip = {}
    for ident, row in annotations.items():
        if row['split'] != 'val' or scenes[row['scene_id']]['excluded']:
            continue
        fp = Polygon(row['corners_wgs84'])
        for day, test_geo, forward, test_projected in tests:
            if day == row['day']:
                skip[ident] = 'date_matches_test'
                break
            if fp.distance(test_geo) <= 1.5 and transform(forward, fp).distance(test_projected) <= 20000:
                skip[ident] = 'validation_chip_within_20km_of_test_hull'
                break
    return skip


def pixel_xy(corners, x, y):
    """Pixel edge coordinates; centers of first/last pixels at 0.5 and 511.5."""
    x, y = np.broadcast_arrays((np.asarray(x)-.5)/511, (np.asarray(y)-.5)/511)
    c = np.asarray(corners)
    return (c[0] + x[..., None]*(c[1]-c[0]) + y[..., None]*(c[3]-c[0]) +
            (x*y)[..., None]*(c[0]-c[1]+c[2]-c[3]))


def invalid_runs(valid):
    """Exact run-length rectangles for the invalid pixel union (no convex filling)."""
    open_runs = {}
    for y, row in enumerate(valid):
        limits = np.flatnonzero(np.diff(np.r_[False, ~row, False]))
        current = set(zip(limits[::2], limits[1::2]))
        for x0, x1 in sorted(open_runs.keys() - current):
            yield x0, open_runs.pop((x0, x1)), x1, y
        for run in current:
            open_runs.setdefault(run, y)
    for (x0, x1), y0 in sorted(open_runs.items()):
        yield x0, y0, x1, len(valid)


def pixel_rect(corners, x0, y0, x1, y1):
    return Polygon(pixel_xy(corners, [x0, x1, x1, x0], [y0, y0, y1, y1]))


def unique_water_support(shapes):
    """Equivalent to union area via disjoint ownership; no global noding of all holes."""
    tree = STRtree(shapes)
    for j, footprint in enumerate(shapes):
        neighbors = sorted(int(k) for k in tree.query(footprint) if k < j)
        common = [shapes[k].intersection(footprint) for k in neighbors]
        yield footprint.difference(unary_union(common)) if common else footprint


def land_shapes(archive, footprint, forward):
    ext = box(*footprint.bounds).buffer(.25)
    stem = 'GSHHS_shp/f/GSHHS_f_L1'
    with zipfile.ZipFile(archive) as z, z.open(stem+'.shp') as shp, z.open(stem+'.shx') as shx, z.open(stem+'.dbf') as dbf:
        reader = shapefile.Reader(shp=shp, shx=shx, dbf=dbf)
        geo = unary_union([make_valid(shape(row.__geo_interface__)).intersection(ext)
                           for row in reader.iterShapes(bbox=ext.bounds)])
    land = transform(forward, geo)
    # Trim any boundary artificially created by clipping the source polygons.
    coast = transform(forward, geo.boundary.intersection(ext.buffer(-.01))) if not geo.is_empty else geo
    return land, coast


def prepare(data, out):
    for name, expected in CHECKSUM.items():
        if digest(data / name) != expected:
            raise ValueError('Checksum mismatch: ' + name)
    annotations = read_annotations(data)
    policy = ROOT / 'configs/ls_ssdd_scenes.json'
    asf_path = data / 'ls_ssdd_asf_footprints.geojson'
    asf = json.loads(asf_path.read_text())
    scenes = screen_scenes(annotations, asf, json.loads(policy.read_text()))
    val_quarantine = validation_buffer(annotations, scenes)
    out.mkdir(parents=True, exist_ok=False)
    # Store only public catalogue identifiers and footprint geometry.
    save(out / 'ls_ssdd_asf_footprints.json', [dict(scene=f['properties']['sceneName'], geometry=f['geometry'])
          for f in asf['features']])
    save(out / 'source_screen.json', dict(dataset_revision=REVISION, archive_sha256=CHECKSUM,
        code_sha256=digest(Path(__file__)), asf_response_sha256=digest(asf_path), ls_ssdd_policy_sha256=digest(policy),
        geography='Reject complete OpenSAR scenes within 20 km of the full LS-SSDD train/val product footprints or with a shared UTC date. Retain eligible test scenes, then quarantine all OpenSAR validation chips within 20 km of the retained test hulls or on the same date. This external partition was revised on source metadata only, before any inference.',
        validation_chip_quarantine=val_quarantine,
        note='OpenSAR train is never used. Audit scope is data actually used to train/tune this checkpoint, not the original source authors’ model.', scenes=scenes))
    roots = data / 'prepared-v1'
    for split in ('val', 'test'):
        kept = {i: r for i, r in annotations.items() if r['split'] == split and not scenes[r['scene_id']]['excluded'] and i not in val_quarantine}
        if not kept:
            raise ValueError('No eligible scenes for ' + split)
        (roots / split).mkdir(parents=True, exist_ok=True)
        geometry, exclusions, inputs, support = {}, Counter(), [], defaultdict(list)
        seen = set()
        for ident, raw in archive_members(data / f'{split}_patches.tar.zst', r'patches/DB_OPENSAR_VD_(\d+)_SLC_VV\.tiff'):
            if ident not in kept:
                continue
            if ident in seen:
                raise ValueError(f'Duplicate raster member: {ident}')
            seen.add(ident)
            r = kept[ident]
            if any(lab['box'] is None for lab in r['labels']):
                exclusions['invalid_source_annotation'] += 1
                continue
            scene = r['scene_id']
            if scene not in geometry:
                footprint = shape(scenes[scene]['footprint'])
                crs, forward = laea(footprint)
                land, coast = land_shapes(data / 'gshhg-shp-2.3.7.zip', footprint, forward)
                geometry[scene] = crs, forward, land, coast
            crs, forward, land, coast = geometry[scene]
            from io import BytesIO
            img = tifffile.imread(BytesIO(raw))
            if img.shape != (512, 512) or img.dtype.kind != 'c':
                raise ValueError(f'Not 512px complex SLC VV: {ident}')
            valid = np.isfinite(img) & (img != 0)
            if valid.mean() < .95:
                exclusions['valid_pixels_below_95_percent'] += 1
                continue
            corners = list(zip(*forward(*zip(*r['corners_wgs84']))))
            raster = pixel_rect(corners, 0, 0, 512, 512)
            nodata = unary_union([pixel_rect(corners, *rect) for rect in invalid_runs(valid)])
            water = raster.difference(land).difference(nodata)
            if water.area <= 1e6:
                exclusions['valid_ocean_le_1_sqkm'] += 1
                continue
            for lab in r['labels']:
                x, y = lab['xml_center_px']
                pos = Point(*pixel_xy(corners, x, y))
                xy_ref = forward(*lab['xml_center_wgs84'])
                lab.update(xml_wgs84_to_corner_transform_residual_m=pos.distance(Point(*xy_ref)),
                    evaluated_sea=bool(water.covers(pos)), sea_distance_to_shore_m=pos.distance(coast) if not coast.is_empty else None)
            r.update(crs=crs, corners_laea_m=corners, valid_sea_wkb_hex=water.wkb_hex,
                valid_sea_km2=water.area/1e6, valid_pixels=int(valid.sum()),
                file_sha256=hashlib.sha256(raw).hexdigest(), raster_path=f'{split}/{ident}.tiff')
            target = roots / r['raster_path']
            if not target.exists() or digest(target) != r['file_sha256']:
                target.write_bytes(raw)
            inputs.append(r)
            support[scene].append(water)
        if missing := sorted(set(kept)-seen):
            raise ValueError(f'Missing eligible source images: {missing[:10]}')
        overlaps = {scene: dict(sum_km2=sum(p.area for p in water)/1e6,
                                union_km2=sum(g.area for g in unique_water_support(water))/1e6)
                    for scene, water in support.items()}
        save(out / f'{split}_manifest.json', dict(split=split, sea_area_by_scene=overlaps,
            exclusions=dict(exclusions), images=sorted(inputs, key=lambda r: int(r['id']))))
        print(split, 'accepted', len(inputs), 'excluded', dict(exclusions), 'area', overlaps, flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    prepare(args.data, args.output)
