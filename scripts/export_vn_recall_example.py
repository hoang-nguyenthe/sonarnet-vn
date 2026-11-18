"""Export a real RTC crop showing both recovered labels and review burden."""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from shapely import intersects_xy
from shapely.geometry import box
from scipy.optimize import linear_sum_assignment

from evaluate_review_ranking import MATCH_DISTANCE
from land_mask import get_mask
from prepare_opensar_geo import unique_water_support
from score_vn_reference_rtc import ROOT, digest, geographic_distances, valid_water
from sonarnet.data.planetary import gray_rgba

COLORS = {'label':'#42d9f5', 'matched':'#ffbf49', 'unmatched':'#ff7497'}


def pairs(proposals, truth):
    distances = geographic_distances(proposals, truth)
    if not distances.size:
        return set(),set()
    # A large cost for outside-radius pairs maximizes valid pairs before
    # minimizing their distances, including when there are more proposals.
    penalty = (1+min(distances.shape))*(MATCH_DISTANCE+1)
    costs = np.where(distances <= MATCH_DISTANCE,distances,penalty)
    i,j = linear_sum_assignment(costs)
    ok = costs[i,j] < penalty
    return set(i[ok]),set(j[ok])


def candidates_in(items, support):
    return [item for item in items if intersects_xy(support,*item[:2])]


def select(source, data):
    folder=source/'rtc-512'
    manifest=json.loads((folder/'manifest.json').read_text())['cohorts']
    bounds=json.loads((source/'screened.json').read_text())['bounds']
    by_scene={case['scene']:case for case in data}
    land=get_mask(ROOT)[1]['land']
    best=None
    for cohort in manifest:
        case=by_scene.get(cohort['scene'])
        if case is None:
            continue
        source_windows=sorted(cohort['windows'], key=lambda w:w['window_id'])
        chips=[]
        for window in source_windows:
            path=folder/window['file']
            if digest(path)!=window['sha256']:
                raise ValueError('Unexpected source checksum')
            with np.load(path,allow_pickle=False) as data_file:
                gamma=data_file['gamma0']
            water=valid_water(gamma,window['bbox'],box(*bounds[case['region']]),land)
            chips.append((gamma,water))
        scopes=unique_water_support([water for _,water in chips])
        for w,(gamma,_),scope in zip(source_windows,chips,scopes):
            truth=candidates_in(case['truth'],scope)
            if len(truth)<3:
                continue
            old=candidates_in(case['incumbent'],scope)
            lowered=sorted(case['baseline_low'],key=lambda row:-row[2])[:case['budget']]
            new=candidates_in(lowered,scope)
            _,old_hits=pairs(old,truth)
            _,new_hits=pairs(new,truth)
            index=(len(new_hits-old_hits),len(new_hits)-len(old_hits),len(truth),-w['window_id'])
            if best is None or index>best[0]:
                best=(index,cohort,w,gamma,old,new,truth)
    if best is None:
        raise ValueError('No labelled representative crop')
    return best


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True,type=Path)
    p.add_argument('--cache',required=True,type=Path)
    p.add_argument('--font',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    args=p.parse_args()
    with gzip.open(args.cache,'rt') as file:
        selected=select(args.source,json.load(file))
    _,cohort,w,gamma,old,new,truth=selected
    args.output.mkdir(parents=True,exist_ok=True)
    preview=Image.fromarray(gray_rgba(np.ma.masked_less_equal(gamma,0))).convert('RGB')
    px=512
    left, top, gap=26,92,20
    image=Image.new('RGB',(2*(left+px)+gap,655),'#0a1c2a')
    draw=ImageDraw.Draw(image)
    heading=ImageFont.truetype(str(args.font),25)
    labels=ImageFont.truetype(str(args.font),18)
    small=ImageFont.truetype(str(args.font),14)
    draw.text((left,19),'Ảnh SAR thật · hạ ngưỡng thay đổi những gì?',font=heading,fill='#edf8ff')
    west,south,east,north=w['bbox']
    def marker(point, offset, color, radius, diamond=False):
        x=offset+(point[0]-west)/(east-west)*px
        y=top+(north-point[1])/(north-south)*px
        if diamond:
            draw.polygon([(x,y-radius),(x+radius,y),(x,y+radius),(x-radius,y)],outline=color,width=2)
        else:
            draw.ellipse((x-radius,y-radius,x+radius,y+radius),outline=color,width=2)
    summary=[]
    for side,(name,points) in enumerate((('Ngưỡng 0,35',old),('Ngưỡng 0,05',new))):
        offset=left+side*(px+gap)
        matched_points,matched_labels=pairs(points,truth)
        image.paste(preview,(offset,top))
        draw.text((offset,57),f'{name}   ·   {len(matched_labels)}/{len(truth)} nhãn   ·   {len(points)} điểm cần rà',
                  font=labels,fill='#d4ebf9')
        for coord in truth:
            marker(coord,offset,COLORS['label'],6,diamond=True)
        for i,coord in enumerate(points):
            color=COLORS['matched'] if i in matched_points else COLORS['unmatched']
            marker(coord,offset,color,10)
        summary.append(dict(threshold=name,proposal_count=len(points),matched=len(matched_labels)))
    for x,k,caption in [(left,'label','Nhãn điểm Ai2'),(260,'matched','Ứng viên khớp trong 100 m'),
                        (600,'unmatched','Ứng viên chưa khớp nhãn')]:
        draw.ellipse((x,624,x+9,633),fill=COLORS[k])
        draw.text((x+18,619),caption,font=small,fill='#c1dae9')
    image.save(args.output/'example.png',optimize=True)
    (args.output/'example.json').write_text(json.dumps(dict(
        source=cohort['source'],window_id=w['window_id'],raster_sha256=w['sha256'],
        selection='Most newly matched labels within one eligible crop; at least three labels. Low threshold follows scene review cap.',
        measurement='Point matching within this crop; project totals remain calculated over the whole scene.',
        summaries=summary),ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':
    main()
