"""Compare association policies across frozen, coincident radar/AIS acquisitions."""
import argparse
from datetime import datetime
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageDraw

from evaluate_ais_matching import legacy
from evaluate_coincident_sar_ais import distances, extract_sar, land_geometry, weak_reference
from evaluate_noaa_ais_replay import digest, read_day, sample_window
from sonarnet.config import RunConfig
from sonarnet.fusion.matching import Detection, SARAISFusion

ROOT = Path(__file__).resolve().parents[1]


def visible(point, tiles, alpha, land):
    from shapely.geometry import Point

    if land.intersects(Point(point.lon,point.lat)):
        return False
    for (w,s,e,n),bitmap in zip(tiles,alpha):
        if bitmap is None or not w<=point.lon<e or not s<point.lat<=n:
            continue
        y=int((n-point.lat)/(n-s)*bitmap.shape[0])
        x=int((point.lon-w)/(e-w)*bitmap.shape[1])
        if bitmap[y,x]:
            return True
    return False


def stable_window(frame, anchor, policy, on_radar):
    span = frame[(frame['second']-anchor).abs()<=600].drop_duplicates()
    span = span[~span.duplicated(['MMSI','second'], keep=False)]
    close = (span['second']-anchor).abs() <= policy['holdout_s']
    withheld = span.loc[close]
    history = [dict(mmsi=int(r.MMSI),timestamp=int(r.second),lat=float(r.LAT),lon=float(r.LON))
               for r in span.loc[~close].sort_values('second').itertuples()]
    proxies, ids, stable, compact_fixes = [], [], [], []
    for mmsi,track in withheld.groupby('MMSI',sort=True):
        clock = track['second'].to_numpy()
        near = np.argmin(np.abs(clock-anchor))
        location = track[['LAT','LON']].to_numpy()
        center = np.median(location,axis=0)
        potential = Detection(0,*map(float,center),np.nan,np.nan,(0,0,0,0))
        fixes = [Detection(0,*map(float,row),np.nan,np.nan,(0,0,0,0)) for row in location]
        movement = distances([potential],fixes).max()
        bracket = clock.min() <= anchor <= clock.max()
        stationary = (len(clock)>=policy['minimum_fixes'] and bracket and
                      clock.max()-clock.min()>=policy['minimum_span_s'] and
                      abs(clock[near]-anchor)<=policy['max_nearest_offset_s'] and
                      movement<=policy['max_median_displacement_m'])
        proxies.append(potential if stationary else fixes[near])
        ids.append(int(mmsi))
        stable.append(stationary and on_radar(potential))
        compact_fixes.append(fixes)
    eligible = np.asarray(stable,dtype=bool)
    if len(proxies):
        # An alternative transmitter can disqualify a reference even if that
        # transmitter is moving or lies just outside a usable radar window.
        compared = [fix for track in compact_fixes for fix in track]
        owners = np.repeat(np.arange(len(proxies)),[len(track) for track in compact_fixes])
        eligible_indices = np.flatnonzero(eligible)
        remote = distances([proxies[i] for i in eligible_indices],compared)
        crowded = ((remote <= policy['competitor_m']) &
                   (eligible_indices[:,None]!=owners[None,:])).any(axis=1)
        eligible[eligible_indices[crowded]]=False
    return proxies, ids, history, eligible


def fixed_references(sar, held, ids, eligible, policy):
    residual = distances(sar,held)
    references = {}
    for i,j in zip(*np.nonzero((residual<=policy['unique_match_m']) & eligible[None,:])):
        lonely_sar = (residual[:,j]<=policy['competitor_m']).sum()==1
        lonely_ais = (residual[i,:]<=policy['competitor_m']).sum()==1
        if lonely_sar and lonely_ais:
            references[int(i)] = (ids[j],float(residual[i,j]))
    return references


def methods(points, history, anchor):
    stable = RunConfig()
    current = SARAISFusion(stable)
    estimates = current.interpolate_ais(history,anchor)
    original = RunConfig()
    original.fusion.systematic_bias_guard_m = 0.
    original.fusion.preserve_proposed_pair = False
    guard = RunConfig()
    guard.fusion.preserve_proposed_pair = False
    outputs = {
        'distance_only':legacy(points,estimates),
        'previous_gates':SARAISFusion(original).match(points,estimates)[0],
        '100m_guard':SARAISFusion(guard).match(points,estimates)[0],
        'propose_then_veto':current.match(points,estimates)[0],
    }
    return outputs, len(estimates)


def compare(predicted, references, n):
    return {name:dict(proposed=len(pairs),withheld=n-len(pairs),
                      agree=sum(pairs.get(k)==expected for k,(expected,_) in references.items()),
                      disagree=sum(k in pairs and pairs[k]!=expected for k,(expected,_) in references.items()),
                      reference_unpaired=sum(k not in pairs for k in references),
                      proposed_without_reference=sum(k not in references for k in pairs))
            for name,pairs in predicted.items()}


def accumulate(results):
    return {kind:dict(
        paired_references=sum(r[kind]['paired_references'] for r in results),
        counts={key:{field:sum(r[kind]['counts'][key][field] for r in results)
                     for field in results[0][kind]['counts'][key]}
                for key in results[0][kind]['counts']})
            for kind in ('near_time','near_stationary')}


def scene(source, out, item, frozen, coast, weights):
    radar = source/item['product']
    provenance_path = radar/'raster_provenance.json'
    manifests=json.loads(provenance_path.read_text())
    if (manifests['source_acquired_at'] != item['acquired_at'] or
            manifests['source_item_url'] != item['source_item_url'] or
            manifests['source_asset_url'] != item['source_asset_url']):
        raise ValueError('Radar provenance differs from frozen catalogue')
    settings = frozen['raster']
    extraction=dict(tiles_wsen=item['tiles_wsen'],render=settings,detector=settings)
    land=land_geometry(coast,item['bounds'])
    figures,tiles,detects=extract_sar(SimpleNamespace(input=radar),manifests,extraction,land,weights)
    raw=[p[-1] for p in detects]
    alpha=[]
    for t in tiles:
        if t['usable']:
            with Image.open(radar/f"tile_{t['tile']}.png") as image:
                alpha.append(np.asarray(image.getchannel('A'))>0)
        else:
            alpha.append(None)
    if not any(t['usable'] for t in tiles):
        raise ValueError('Study acquisition has no usable radar')
    when=datetime.fromisoformat(item['acquired_at'])
    anchor=when.timestamp()
    day=when.date().isoformat()
    frame, ais = read_day(source/f"AIS_{day.replace('-','_')}.zip",day,[anchor])
    w,s,e,n=item['bounds']
    region=frame[frame['LON'].between(w-.03,e+.03) & frame['LAT'].between(s-.03,n+.03)]
    held,ids,history,_=sample_window(region,item['bounds'],anchor)
    near=weak_reference(raw,held,ids)
    outputs,tracks=methods(raw,history,anchor)
    nearby=dict(held_positions=len(held), input_records=len(history), tracks=tracks,
                paired_references=len(near), counts=compare(outputs,near,len(raw)))
    rule=frozen['stationary_reference']
    is_visible=lambda point:visible(point,item['tiles_wsen'],alpha,land)
    held,ids,history,eligible=stable_window(region,anchor,rule,is_visible)
    fixed=fixed_references(raw,held,ids,eligible,rule)
    outputs,tracks=methods(raw,history,anchor)
    steady=dict(held_positions=len(held), input_records=len(history), tracks=tracks,
                stable_isolated_positions=int(np.count_nonzero(eligible)),
                paired_references=len(fixed), counts=compare(outputs,fixed,len(raw)))
    scene_out=out/item['product']
    scene_out.mkdir(exist_ok=False)
    for t in tiles:
        i=t['tile']
        if not t['usable']:
            continue
        canvas=figures[i]
        draw=ImageDraw.Draw(canvas)
        for j,(location,confidence,p) in enumerate(detects):
            if location!=i:
                continue
            color='#4de7f5' if j in fixed else '#ffcf76' if j in near else '#c3a4fc'
            draw.rectangle(p.bbox,outline=color,width=2)
            x,y,_,_=p.bbox
            draw.text((x,max(0,y-13)),str(j+1),fill=color)
        image=scene_out/f'tile_{i}_review.jpg'
        canvas.save(image,quality=91,optimize=True)
        t.update(marked=image.name,marked_sha256=digest(image),
                 stationary_pairs=sum(k in fixed and v[0]==i for k,v in enumerate(detects)),
                 near_time_pairs=sum(k in near and v[0]==i for k,v in enumerate(detects)))
    receipt=dict(product=item['product'],area=item['area'],utc=item['acquired_at'],
                 radar_candidates=len(raw),raster_manifest_sha256=digest(provenance_path),
                 raster_provenance=manifests, ais_source=ais,tiles=tiles,
                 near_time=nearby,near_stationary=steady)
    (scene_out/'summary.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(item['area'],day,'SAR',len(raw),'near-time refs',len(near),'stationary refs',
          len(fixed),'eligible stationary AIS',steady['stable_isolated_positions'],flush=True)
    return receipt


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','coast','output'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--ready-only', action='store_true',
                   help='Score inputs that have completed download, and preserve completed results.')
    opts=p.parse_args()
    protocol=opts.source/'protocol.json'
    frozen=json.loads(protocol.read_text())
    weights=ROOT/frozen['raster']['detector']
    opts.output.mkdir(exist_ok=opts.ready_only)
    receipt=opts.output/'results.json'
    lineage=dict(protocol_sha256=digest(protocol),evaluator_sha256=digest(Path(__file__)),
                 fusion_sha256=digest(ROOT/'src/sonarnet/fusion/matching.py'),model_sha256=digest(weights),
                 coast_sha256=digest(opts.coast))
    previous=json.loads(receipt.read_text()) if receipt.is_file() else {}
    if previous and any(previous.get(k)!=v for k,v in lineage.items()):
        raise ValueError('Scored inputs or code changed; use a new output directory')
    scenes={r['product']:r for r in previous.get('scenes',[])}
    for item in frozen['products']:
        if item['product'] in scenes:
            continue
        day=datetime.fromisoformat(item['acquired_at']).date().isoformat()
        sources=(opts.source/item['product']/'raster_provenance.json',
                 opts.source/f"AIS_{day.replace('-','_')}.zip")
        if opts.ready_only and not all(p.is_file() for p in sources):
            continue
        result=scene(opts.source,opts.output,item,frozen,opts.coast,weights)
        scenes[item['product']]=result
        ordered=[scenes[r['product']] for r in frozen['products'] if r['product'] in scenes]
        data=dict(lineage,scenes=ordered,expected_scenes=len(frozen['products']),
                  complete=len(ordered)==len(frozen['products']),aggregate=accumulate(ordered))
        temporary=receipt.with_suffix('.part')
        temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
        temporary.replace(receipt)
    print('Scored acquisitions:',len(scenes),'/',len(frozen['products']),flush=True)
    if scenes:
        print(json.dumps(accumulate(list(scenes.values())),indent=2),flush=True)



if __name__=='__main__':
    main()
