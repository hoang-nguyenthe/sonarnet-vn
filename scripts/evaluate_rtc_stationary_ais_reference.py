"""Check SAR candidate coverage against independently selected stationary AIS proxies."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image
from shapely import intersects_xy
import torch
from ultralytics import YOLO

from evaluate_coincident_sar_ais import extract_sar, land_geometry
from evaluate_multiscene_sar_ais import stable_window, visible
from evaluate_noaa_ais_replay import read_day
from evaluate_review_ranking import save
from evaluate_rtc_contrast_recall import shortlist
from score_vn_reference_rtc import ROOT, digest, matched, raster_points

RADII = (50, 100, 150)
RULE = {'base_confidence': .35, 'relaxed_confidence': .05,
        'centres_collapse_m': 35, 'grid': [2,2], 'halo_px': 96, 'image_size': 1024,
        'reference': 'Stationary and isolated AIS positions fixed from NOAA and the valid radar footprint before running YOLO.'}


def rendered_masks(item, folder, source, land, raster):
    size = raster['width']
    bounds = item['tiles_wsen']
    tile_masks = []
    for b,row in zip(bounds,source['images'],strict=True):
        path = folder/f"tile_{row['tile']}.png"
        if digest(path)!=row['sha256']:
            raise ValueError('Radar pixels differ from frozen source')
        with Image.open(path) as file:
            rgba = np.asarray(file.convert('RGBA'))
        alpha = rgba[:,:,3]>0
        if rgba.shape != (size,size,4) or alpha.mean() < raster['minimum_valid_fraction']:
            raise ValueError('Missing usable radar coverage in a frozen window')
        w,s,e,n=b
        lon = w+(np.arange(size)+.5)/size*(e-w)
        lat = n-(np.arange(size)+.5)/size*(n-s)
        water = alpha & ~intersects_xy(land,lon[None,:],lat[:,None])
        tile_masks.append((rgba,alpha,water))
    return tile_masks


def local_chips(model, samples, bounds):
    yolo = []
    for (rgba, _, water), bbox in zip(samples,bounds,strict=True):
        height,width = water.shape
        step = height//2
        halo = RULE['halo_px']
        view = rgba[:,:,:3].copy()
        view[~water] = 0
        for top in (0,step):
            for left in (0,step):
                x0,y0=max(0,left-halo),max(0,top-halo)
                chip=view[y0:top+step+halo,x0:left+step+halo]
                prediction = model.predict(Image.fromarray(chip),imgsz=RULE['image_size'],
                    conf=RULE['relaxed_confidence'],iou=.7,device='cpu',verbose=False)[0]
                if prediction.boxes is None:
                    continue
                xyxy = prediction.boxes.xyxy.cpu().numpy()+[x0,y0,x0,y0]
                points = (xyxy[:, :2]+xyxy[:, 2:])*0.5
                x,y = points.T
                inside = (left<=x)&(x<left+step)&(top<=y)&(y<top+step)
                x,y=x[inside],y[inside]
                valid=water[y.astype(int),x.astype(int)]
                lon,lat=raster_points(np.c_[x,y][valid],bbox,(height,width))
                conf=prediction.boxes.conf.cpu().numpy()[inside][valid]
                yolo.extend([float(a),float(b),float(c)] for a,b,c in zip(lon,lat,conf,strict=True))
    return yolo


def collect_reference(root, item, samples, land, config):
    anchor=datetime.fromisoformat(item['acquired_at'])
    day=anchor.date().isoformat()
    timestamp=anchor.timestamp()
    frame, provenance=read_day(root/f"AIS_{day.replace('-','_')}.zip",day,[timestamp])
    w,s,e,n=item['bounds']
    region=frame[frame['LON'].between(w-.03,e+.03)&frame['LAT'].between(s-.03,n+.03)]
    alpha=[row[1] for row in samples]
    accept=lambda p:visible(p,item['tiles_wsen'],alpha,land)
    points,_,__,eligible=stable_window(region,timestamp,config['stationary_reference'],accept)
    reference=[[p.lon,p.lat] for p,keep in zip(points,eligible,strict=True) if keep]
    return reference,provenance


def ordered(rows):
    return sorted(rows,key=lambda row:-row[2])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for opt in ('source','coast','association','output'):
        p.add_argument('--'+opt,type=Path,required=True)
    args=p.parse_args()
    args.output.mkdir(exist_ok=False)
    frozen=args.source/'protocol.json'
    config=json.loads(frozen.read_text())
    association=json.loads(args.association.read_text())
    expected={case['product']:case for case in association['scenes']}
    weights=ROOT/config['raster']['detector']
    if not association['complete'] or association['model_sha256']!=digest(weights):
        raise ValueError('Exact checkpoint for prior archive is required')
    if association['coast_sha256']!=digest(args.coast) or association['protocol_sha256']!=digest(frozen):
        raise ValueError('Prior study source or coastline checksum changed')
    save(args.output/'protocol.json',dict(
        frozen_at=datetime.now(timezone.utc).isoformat(),
        code_sha256=digest(Path(__file__)),source_sha256=digest(frozen),
        previous_association_sha256=digest(args.association),weights_sha256=digest(weights),
        coast_sha256=digest(args.coast),match_metres=RADII,decision=RULE,
        scope='Six previously captured civilian port scenes, no fitting. Eligible AIS positions do not depend on detections. Approximates recall for these references only.'))
    frozen_cases = []
    # Finish all AIS reference selection before processing any detector outputs.
    for item in config['products']:
        identifier = item['product']
        folder=args.source/identifier
        manifest=folder/'raster_provenance.json'
        source=json.loads(manifest.read_text())
        ref=expected[identifier]
        if digest(manifest)!=ref['raster_manifest_sha256']:
            raise ValueError('A radar footprint differs from the archive')
        land=land_geometry(args.coast,item['bounds'])
        samples=rendered_masks(item,folder,source,land,config['raster'])
        truth, ais=collect_reference(args.source,item,samples,land,config)
        if ais!=ref['ais_source'] or len(truth)!=ref['near_stationary']['stable_isolated_positions']:
            raise ValueError('AIS inputs or selection differ from frozen source')
        frozen_cases.append(dict(product=identifier,reference_count=len(truth),labels=truth))
        print(item['area'],item['acquired_at'][:10],len(truth),'frozen AIS references',flush=True)
    save(args.output/'reference.json',frozen_cases)
    torch.set_num_threads(4)
    model=YOLO(str(weights))
    summaries, queues = [], []
    for item,label in zip(config['products'],frozen_cases,strict=True):
        folder=args.source/item['product']
        source=json.loads((folder/'raster_provenance.json').read_text())
        land=land_geometry(args.coast,item['bounds'])
        samples=rendered_masks(item,folder,source,land,config['raster'])
        raster=dict(config['raster'],confidence=RULE['relaxed_confidence'])
        extraction=dict(tiles_wsen=item['tiles_wsen'],render=raster,detector=raster)
        _,__,found=extract_sar(SimpleNamespace(input=folder),source,extraction,land,weights)
        raw=ordered([[point.lon,point.lat,confidence] for _,confidence,point in found])
        baseline=[row for row in raw if row[2]>=RULE['base_confidence']]
        if len(baseline)!=expected[item['product']]['radar_candidates']:
            raise ValueError('Base threshold candidate count differs from published archive')
        windows=local_chips(model,samples,item['tiles_wsen'])
        candidates={
            'base_at_035':baseline,
            'same_count_remove_duplicates':shortlist(raw,baseline,len(baseline),RULE['centres_collapse_m']),
            'same_count_overlap':shortlist(ordered(raw+windows),baseline,len(baseline),RULE['centres_collapse_m']),
            'base_at_005':raw,
            'same_wide_count_overlap':shortlist(ordered(raw+windows),raw,len(raw),RULE['centres_collapse_m']),
        }
        counts={key:matched(value,label['labels'],RADII) for key,value in candidates.items()}
        summaries.append(dict(product=item['product'],area=item['area'],utc=item['acquired_at'],
                              tiles=len(item['tiles_wsen']),counts=counts))
        queues.append(dict(product=item['product'],queues=candidates))
        print(item['area'],item['acquired_at'][:10],{k:v[100] for k,v in counts.items()},flush=True)
    totals={key:{str(radius):{k:sum(s['counts'][key][radius][k] for s in summaries)
                              for k in ('labels','matched','predictions','unmatched')}
                 for radius in RADII} for key in summaries[0]['counts']}
    save(args.output/'results.json',dict(protocol_sha256=digest(args.output/'protocol.json'),
         references_sha256=digest(args.output/'reference.json'),scenes=summaries,totals=totals))
    save(args.output/'review-queues.json',dict(results_sha256=digest(args.output/'results.json'),scenes=queues))
    print('Aggregate', {k:v['100'] for k,v in totals.items()},flush=True)


if __name__ == '__main__':
    main()
