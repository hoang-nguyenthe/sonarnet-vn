"""Freeze radar acquisitions by catalogue coverage and time, before reading AIS or pixels."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
import argparse
import json
import math

from shapely.geometry import box, shape
from sonarnet.data.planetary import STAC, get_json, validate_asset_url
from evaluate_noaa_ais_replay import AREAS, digest

DATES = (date(2024,7,14),date(2024,10,1))
EXCLUDED_PRODUCT = 'S1A_IW_GRDH_1SDV_20241213T225129_20241213T225154_056980_07001E_rtc'
PAD_DAYS = 13


def grid(bounds):
    west,south,east,north = bounds
    cols,rows = math.ceil((east-west)/.095),math.ceil((north-south)/.095)
    x = [west+(east-west)*i/cols for i in range(cols+1)]
    y = [south+(north-south)*j/rows for j in range(rows+1)]
    return [[x[i],y[j],x[i+1],y[j+1]] for j in range(rows) for i in range(cols)]


def available(job):
    area,bounds,near = job
    start,end = near-timedelta(days=PAD_DAYS),near+timedelta(days=PAD_DAYS)
    query = urlencode(dict(collections='sentinel-1-rtc',bbox=','.join(map(str,bounds)),
                           datetime=f'{start}T00:00:00Z/{end}T23:59:59Z',limit=100))
    response=get_json(STAC+'/search?'+query)
    if any(link['rel']=='next' for link in response.get('links',[])):
        raise ValueError('Expect complete catalogue window')
    target=box(*bounds)
    candidates=[]
    for item in response['features']:
        prop=item['properties']
        if (prop.get('sar:instrument_mode')!='IW' or item['id']==EXCLUDED_PRODUCT
                or 'vv' not in item['assets'] or not item.get('geometry')):
            continue
        overlap=target.intersection(shape(item['geometry'])).area/target.area
        if overlap < .90:
            continue
        href=item['assets']['vv']['href']
        validate_asset_url(href)
        acquired=datetime.fromisoformat(prop['datetime'])
        n=float(prop['sar:pixel_spacing_range'])
        if not 0<n<=25:
            continue
        candidates.append(dict(product=item['id'], area=area, bounds=bounds, tiles_wsen=grid(bounds),
            acquired_at=acquired.isoformat(),start_datetime=prop['start_datetime'],end_datetime=prop['end_datetime'],
            day_delta=abs((acquired.date()-near).days),coverage_fraction=overlap,
            source_asset_url=href,native_resolution_m=n,orbit_direction=prop.get('sat:orbit_state'),
            source_item_url=f"{STAC}/collections/sentinel-1-rtc/items/{item['id']}"))
    candidates.sort(key=lambda p:(p['day_delta'],p['acquired_at'],p['product']))
    return dict(region=area,target_day=near.isoformat(),eligible=candidates)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    out=p.parse_args().output
    out.mkdir(exist_ok=False)
    jobs=[(area,bounds,day) for (area,bounds) in AREAS.items() for day in DATES]
    with ThreadPoolExecutor(max_workers=3) as pool:
        records=list(pool.map(available,jobs))
    chosen=[]
    for row in records:
        if not row['eligible']:
            raise ValueError(f"No qualifying archive for {row['region']} {row['target_day']}")
        chosen.append(row['eligible'][0])
    if len({r['product'] for r in chosen})!=len(chosen):
        raise ValueError('Acquisition repeated')
    (out/'catalogue-screen.json').write_text(json.dumps(records,indent=2)+'\n')
    protocol=dict(
        frozen_at=datetime.now(timezone.utc).isoformat(),selection_code_sha256=digest(Path(__file__)),
        catalogue_sha256=digest(out/'catalogue-screen.json'),
        selection='Two fixed target dates per harbor. IW VV RTC product covering at least 90% of the harbor polygon; closest UTC day, then earliest time, then lexical product ID. Prior New York proof scene excluded.',
        acquisition_targets=[d.isoformat() for d in DATES],date_window_days=PAD_DAYS,products=chosen,
        raster=dict(width=1024,minimum_valid_fraction=.90,normalization='[-25,+5] dB',
                    detector='assets/models/sonarnet_baseline.pt',confidence=.35,imgsz=1024,nms_iou=.7),
        weak_reference=dict(near_s=20,unique_match_m=100,competitor_m=250),
        stationary_reference=dict(holdout_s=120,max_median_displacement_m=35,minimum_fixes=2,
                                  minimum_span_s=30,require_bracketing=True,max_nearest_offset_s=65,
                                  unique_match_m=100,competitor_m=250),
        history_s=600,
        scope='Commercial US harbors. Radar/reference agreement on recorded approximate positions, withholds AIS around overpass. Center timestamp cannot resolve per-vessel sensing time. No verified identity.',
    )
    (out/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    for row in chosen:
        print(row['area'],row['acquired_at'],len(row['tiles_wsen']),row['product'],flush=True)


if __name__=='__main__':
    main()
