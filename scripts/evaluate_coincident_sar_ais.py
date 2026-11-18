"""Run the frozen coincident Sentinel-1 RTC and NOAA AIS harbor replay."""
import argparse
from datetime import datetime
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from PIL import Image, ImageDraw
import shapefile
from shapely import intersects_xy, make_valid
from shapely.geometry import box, shape
from shapely.ops import unary_union

from evaluate_ais_matching import legacy
from evaluate_noaa_ais_replay import digest, read_day, sample_window
from sonarnet.config import RunConfig
from sonarnet.data.geo import haversine_m
from sonarnet.data.planetary import provenance, render_rtc, search_rtc
from sonarnet.fusion.matching import Detection, SARAISFusion

ROOT = Path(__file__).resolve().parents[1]
MIN_REFERENCE_SEPARATION_M = 250.
MAX_REFERENCE_DISTANCE_M = 100.


def land_geometry(path, bounds):
    ext = box(*bounds).buffer(.03)
    stem = 'GSHHS_shp/f/GSHHS_f_L1'
    with ZipFile(path) as z, z.open(stem+'.shp') as shp, z.open(stem+'.shx') as shx, z.open(stem+'.dbf') as dbf:
        reader = shapefile.Reader(shp=shp, shx=shx, dbf=dbf)
        return unary_union([make_valid(shape(g.__geo_interface__)).intersection(ext)
                            for g in reader.iterShapes(bbox=ext.bounds)])


def distances(detections, positions):
    lat = np.array([p.lat for p in detections])
    lon = np.array([p.lon for p in detections])
    other_lat = np.array([p.lat for p in positions])
    other_lon = np.array([p.lon for p in positions])
    return haversine_m(lat[:,None],lon[:,None],other_lat[None,:],other_lon[None,:])


def weak_reference(detections, withheld, identities):
    residuals = distances(detections, withheld)
    pairs = {}
    for i,j in zip(*np.nonzero(residuals <= MAX_REFERENCE_DISTANCE_M)):
        unique = np.sum(residuals[i,:] <= MIN_REFERENCE_SEPARATION_M) == 1
        reciprocal = np.sum(residuals[:,j] <= MIN_REFERENCE_SEPARATION_M) == 1
        if unique and reciprocal:
            pairs[int(i)] = (identities[j], float(residuals[i,j]))
    return pairs


def fetch_rasters(root, protocol, day, bounds):
    product = next((p for p in search_rtc(bounds,day,day) if p.product_id == protocol['product']),None)
    if product is None or product.acquired_at != protocol['acquisition_center_utc']:
        raise ValueError('Frozen RTC item not found in public catalogue')
    root.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, tile in enumerate(protocol['tiles_wsen']):
        source = root/f'tile_{i}.png'
        source.write_bytes(render_rtc(product,tile,protocol['render']['width']))
        rows.append(dict(tile=i,sha256=digest(source)))
    (root/'raster_provenance.json').write_text(json.dumps(dict(provenance(product),images=rows),indent=2)+'\n')


def extract_sar(args, supporting, protocol, land, weights):
    from ultralytics import YOLO
    import torch

    torch.set_num_threads(4)
    model = YOLO(str(weights))
    detectors = protocol['detector']
    size = protocol['render']['width']
    indexes = {row['tile']:row['sha256'] for row in supporting['images']}
    figures, results, detections = {}, [], []
    for tile, (w,s,e,n) in enumerate(protocol['tiles_wsen']):
        raster = args.input/f'tile_{tile}.png'
        if digest(raster) != indexes[tile]:
            raise ValueError(f'Raster hash mismatch for tile {tile}')
        with Image.open(raster) as im:
            rgba = np.asarray(im.convert('RGBA'))
        if rgba.shape != (size,size,4):
            raise ValueError('Unexpected raster dimensions')
        valid = rgba[:,:,3] > 0
        valid_fraction = float(valid.mean())
        results.append(dict(tile=tile, sha256=indexes[tile], valid_fraction=valid_fraction,
                            usable=valid_fraction >= protocol['render']['minimum_valid_fraction']))
        figures[tile] = Image.fromarray(rgba[:,:,:3])
        if not results[-1]['usable']:
            continue
        x, y = np.meshgrid(w + (np.arange(size)+.5)/size*(e-w), n - (np.arange(size)+.5)/size*(n-s))
        water = valid & ~intersects_xy(land, x, y)
        pixels = rgba[:,:,:3].copy()
        pixels[~water] = 0
        prediction = model.predict(Image.fromarray(pixels), imgsz=detectors['imgsz'],
            conf=detectors['confidence'], iou=detectors['nms_iou'], device='cpu', verbose=False)[0]
        for bbox, score in zip(prediction.boxes.xyxy.cpu().numpy(), prediction.boxes.conf.cpu().numpy()):
            x1,y1,x2,y2 = np.clip(bbox, 0, size)
            cx,cy=(x1+x2)/2,(y1+y2)/2
            if not water[min(size-1,int(cy)),min(size-1,int(cx))]:
                continue
            lon, lat = w+cx/size*(e-w), n-cy/size*(n-s)
            detections.append((tile, float(score), Detection(len(detections), float(lat),float(lon),
                               np.nan,np.nan,tuple(map(float,(x1,y1,x2,y2))))))
        results[-1]['detected_candidates'] = sum(t == tile for t, _, _ in detections)
        print('Tile',tile,'valid',round(valid_fraction,3),'candidates',results[-1]['detected_candidates'],flush=True)
    return figures, results, detections


def main(args):
    protocol = json.loads(args.protocol.read_text())
    when = datetime.fromisoformat(protocol['acquisition_center_utc'])
    bounds = (-74.11, 40.48, -73.96, 40.66)
    if args.fetch_rtc and not (args.input/'raster_provenance.json').exists():
        fetch_rasters(args.input,protocol,when.date(),bounds)
    supporting = json.loads((args.input/'raster_provenance.json').read_text())
    if supporting['source_acquired_at'] != protocol['acquisition_center_utc'] or not supporting['source_item_url'].endswith('/'+protocol['product']):
        raise ValueError('Provenance differs from fixed acquisition')
    anchor = when.timestamp()
    weights = ROOT/protocol['detector']['weights']
    if digest(weights) != protocol['detector']['sha256']:
        raise ValueError('Unexpected checkpoint SHA-256')
    land = land_geometry(args.coast,bounds)
    figures, tiles, detections = extract_sar(args,supporting,protocol,land,weights)
    if not any(t['usable'] for t in tiles):
        raise ValueError('No usable tiles for the coincident run')
    frame, source = read_day(args.input/f"AIS_{when.date().isoformat().replace('-','_')}.zip",
                             when.date().isoformat(), [anchor])
    held, truth, history, _ = sample_window(frame,bounds,anchor)
    points = [item[-1] for item in detections]
    reference = weak_reference(points, held, truth)
    old = RunConfig()
    old.fusion.systematic_bias_guard_m = 0.
    old.fusion.preserve_proposed_pair = False
    cfg = RunConfig()
    matcher = SARAISFusion(cfg)
    estimates = matcher.interpolate_ais(history,anchor)
    archival = RunConfig()
    archival.fusion.preserve_proposed_pair = False
    methods = {'distance_only':legacy(points,estimates),
               'previous_gates':SARAISFusion(old).match(points,estimates)[0],
               '100m_guard':SARAISFusion(archival).match(points,estimates)[0],
               'propose_then_veto':matcher.match(points,estimates)[0]}
    summary = {}
    for method, proposals in methods.items():
        summary[method] = dict(proposed=len(proposals), withheld=len(points)-len(proposals),
            agree=sum(proposals.get(i)==j for i,(j,_d) in reference.items()),
            disagree=sum(i in proposals and proposals[i]!=j for i,(j,_d) in reference.items()),
            labelled_but_withheld=sum(i not in proposals for i in reference),
            proposed_without_reference=sum(i not in reference for i in proposals))
    args.output.mkdir(parents=True, exist_ok=False)
    for tile, fig in figures.items():
        if not tiles[tile]['usable']:
            continue
        draw=ImageDraw.Draw(fig)
        for k,(t, confidence, det) in enumerate(detections):
            if t == tile:
                color = '#56e8e9' if k in reference else '#ffc974'
                draw.rectangle(det.bbox,outline=color,width=3)
                x,y,*_ = det.bbox
                draw.text((x,max(0,y-15)),f'#{k+1} {confidence:.2f}',fill=color)
        target = args.output/f'tile_{tile}_marked.png'
        fig.save(target)
        tiles[tile].update(marked=target.name, marked_sha256=digest(target),
                           spatial_references=sum(t == tile and k in reference for k,(t,_,__) in enumerate(detections)))
    report=dict(protocol_sha256=digest(args.protocol), code_sha256=digest(Path(__file__)),
                fusion_code_sha256=digest(ROOT/'src/sonarnet/fusion/matching.py'),
                raster_source=supporting, ais_source=source, coast_sha256=digest(args.coast), model_sha256=digest(weights),
                radar_candidates=len(points), held_ais_positions=len(held), history_records=len(history), estimated_ais_tracks=len(estimates),
                spatial_references=len(reference), tiles=tiles, matching=summary,
                spatial_reference_distance_m_median=float(np.median([d for _,d in reference.values()])) if reference else None,
                notes='Timestamp is scene center, not azimuth time per vessel. Geo alignment uncertainty and moving-target displacement are unresolved. Weak references reuse the same AIS source. The proposed-pair policy was added later as a replay on the same fixed scene.')
    (args.output/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:report[k] for k in ('radar_candidates','held_ais_positions','estimated_ais_tracks','spatial_references','matching')},
                     indent=2),flush=True)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for option in ('protocol','input','coast','output'):
        p.add_argument('--'+option, required=True, type=Path)
    p.add_argument('--fetch-rtc', action='store_true', help='Fetch the four frozen public RTC windows if absent.')
    main(p.parse_args())
