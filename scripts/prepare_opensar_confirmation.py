"""Reserve untouched OpenSAR SLC scenes for independent geographic confirmation.

The publisher calls these tiles 'train', but SonarNet has never used their
images to learn or choose a model. The policy below needs source geometry only.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from io import BytesIO
from itertools import chain
from pathlib import Path
import argparse
import hashlib
import json

import numpy as np
from shapely.ops import unary_union, transform
from shapely.geometry import shape, Point
import tifffile

from prepare_opensar_geo import (REVISION, archive_members, digest, invalid_runs,
    laea, land_shapes, pixel_rect, pixel_xy, read_annotations, save, unique_water_support)

TRAIN_RASTER_SHA = 'f0b7e9d5bdde8078b94446240bdd2bff699d0f697d794f1fbe50f72b0fab9245'


def eligible(scenes):
    prior = [v for v in scenes.values() if v['split'] in {'val','test'}]
    redacted = {}
    for ident,row in scenes.items():
        if row['split'] != 'train':
            continue
        reason = list(row['reasons'])
        hull = shape(row['footprint'])
        _, f = laea(hull)
        distances = {}
        for a in prior:
            other = shape(a['footprint'])
            if row['day'] == a['day']:
                reason.append('shared_UTC_day_with_prior_OpenSAR_'+a['day'])
            if hull.distance(other) <= 1.5:
                dist = transform(f,hull).distance(transform(f,other))
                distances[a['day']] = dist
                if dist <= 20000:
                    reason.append('within_20km_of_prior_OpenSAR_'+a['day'])
        redacted[ident] = {**row, 'eligible_for_confirmation':not reason,
                           'reasons':reason,'prior_OpenSAR_distance_m':distances}
    return redacted


def build(data, audit, out):
    out.mkdir(parents=True,exist_ok=False)
    report = json.loads((audit/'source_screen.json').read_text())
    scenes = eligible(report['scenes'])
    archive = data/'train_patches.tar.zst'
    protocol = dict(created_utc=datetime.now(timezone.utc).isoformat(), source_revision=REVISION,
        train_raster_sha256=TRAIN_RASTER_SHA, source_screen_sha256=digest(audit/'source_screen.json'),
        script_sha256=digest(Path(__file__)), geometry_code_sha256=digest(Path(__file__).with_name('prepare_opensar_geo.py')),
        description='Include every source train scene passing the prior LS-SSDD 20 km/day audit and a 20 km/day buffer to all prior OpenSAR val/test scenes; do not inspect predictions.',
        filters='Same SLC VV, >=95 percent finite nonzero raster, >1 km² valid ocean, valid publisher annotations; original scoring confidence policy.',
        scenes=scenes)
    save(out/'selection.json',protocol)
    if digest(archive) != TRAIN_RASTER_SHA:
        raise ValueError('OpenSAR train raster archive checksum mismatch')
    for name,expected in report['archive_sha256'].items():
        if name.endswith('_labels.tar.zst') or name.startswith('gshhg'):
            if digest(data/name)!=expected:
                raise ValueError('Source label/shoreline checksum mismatch: '+name)
    chosen={i:r for i,r in read_annotations(data).items() if r['split']=='train' and scenes[r['scene_id']]['eligible_for_confirmation']}
    root=data/'prepared-confirmation-v1'
    root.mkdir(exist_ok=False)
    geom={}; all_support=defaultdict(list); ignored=Counter(); seen=set(); rows=[]
    for ident,raw in archive_members(archive,r'patches/DB_OPENSAR_VD_(\d+)_SLC_VV\.tiff'):
        if ident not in chosen: continue
        if ident in seen: raise ValueError('Duplicate raster member: '+ident)
        seen.add(ident)
        row=chosen[ident]; sid=row['scene_id']
        if any(lab['box'] is None for lab in row['labels']):
            ignored['invalid_source_annotation']+=1; continue
        image=tifffile.imread(BytesIO(raw))
        if image.shape!=(512,512) or image.dtype.kind!='c': raise ValueError('Invalid SLC: '+ident)
        good=np.isfinite(image)&(image!=0)
        if good.mean()<.95:
            ignored['valid_pixels_below_95_percent']+=1; continue
        if sid not in geom:
            hull=shape(scenes[sid]['footprint']); crs,f=laea(hull)
            geom[sid]=(crs,f,*land_shapes(data/'gshhg-shp-2.3.7.zip',hull,f))
        crs,f,land,coast=geom[sid]
        c=list(zip(*f(*zip(*row['corners_wgs84']))))
        raster=pixel_rect(c,0,0,512,512)
        invalid=unary_union([pixel_rect(c,*coords) for coords in invalid_runs(good)])
        water=raster.difference(land).difference(invalid)
        if water.area<=1e6:
            ignored['valid_ocean_le_1_sqkm']+=1; continue
        for lab in row['labels']:
            pt=Point(*pixel_xy(c,*lab['xml_center_px']))
            lab.update(evaluated_sea=bool(water.covers(pt)),
                xml_wgs84_to_corner_transform_residual_m=pt.distance(Point(*f(*lab['xml_center_wgs84']))),
                sea_distance_to_shore_m=pt.distance(coast) if not coast.is_empty else None)
        row.update(split='confirmation',source_split='train',crs=crs,corners_laea_m=c,valid_sea_wkb_hex=water.wkb_hex,
            valid_sea_km2=water.area/1e6,valid_pixels=int(good.sum()),file_sha256=hashlib.sha256(raw).hexdigest(),raster_path=ident+'.tiff')
        (root/row['raster_path']).write_bytes(raw)
        rows.append(row); all_support[sid].append(water)
    if seen!=set(chosen): raise ValueError('Source archive missing selected IDs')
    save(out/'confirmation_manifest.json',dict(split='confirmation',source_partitions=['train'],exclusions=dict(ignored),
        sea_area_by_scene={s:sum(p.area for p in unique_water_support(shapes))/1e6 for s,shapes in all_support.items()},
        images=sorted(rows,key=lambda r:int(r['id']))))
    print('Confirmed source provenance for',len(rows),'tiles;',dict(ignored),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for opt in ('data','audit','output'): p.add_argument('--'+opt,required=True,type=Path)
    a=p.parse_args(); build(a.data,a.audit,a.output)
