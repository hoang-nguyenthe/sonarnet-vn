"""Export exact review queues and one source-image illustration from the frozen runs."""
import argparse
import gzip
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from shapely import intersects_xy
from shapely.geometry import box

from evaluate_rtc_contrast_recall import shortlist
from evaluate_rtc_map_tta import ranked_views
from evaluate_review_ranking import save
from land_mask import get_mask
from prepare_opensar_geo import unique_water_support
from replay_rtc_equal_review import EVIDENCE, POLICIES, ROOT, matching, recount, sha256
from score_vn_reference_rtc import valid_water
from sonarnet.data.planetary import gray_rgba


def queues(case, overlap):
    incumbent = sorted(case['incumbent'],key=lambda p: -p[2])
    low = sorted(case['baseline_low'],key=lambda p: -p[2])
    pooled = ranked_views(low, {'overlap':overlap},'max')
    tight, wide = (min(case['budget'],len(x)) for x in (incumbent,low))
    return {
        'equal_incumbent': {
            'map_default': incumbent[:tight],
            'distinct_35m': shortlist(low,incumbent,tight,35.),
        },
        'equal_relaxed': {
            'map_lower_threshold': low[:wide],
            'overlap_only_max': shortlist(pooled,low,wide,35.),
        },
    }


def illustration(source, cases, font_path, out):
    base, improved = POLICIES['equal_relaxed']
    data = []
    for case in cases:
        points = case['queues']['equal_relaxed']
        before, after = (matching(points[m],case['labels'],100) for m in (base,improved))
        gain = len(after)-len(before)
        data.append((gain,case,points,before,after))
    _,case,points,before,after = max(data,key=lambda x:x[0])
    new_labels = {j for _,j,_ in after}-{j for _,j,_ in before}
    folder = source/'rtc-512'
    manifest = json.loads((folder/'manifest.json').read_text())['cohorts']
    cohort = next(c for c in manifest if c['scene'] == case['scene'])
    bounds = json.loads((source/'screened.json').read_text())['bounds']
    region = box(*bounds[case['region']])
    land = get_mask(ROOT)[1]['land']
    rasters = []
    for item in sorted(cohort['windows'],key=lambda w:w['window_id']):
        raw = folder/item['file']
        if sha256(raw) != item['sha256']:
            raise ValueError('Source chip checksum differs')
        with np.load(raw,allow_pickle=False) as file:
            gamma = file['gamma0']
        rasters.append((item,gamma,valid_water(gamma,item['bbox'],region,land)))
    supports = unique_water_support([x[2] for x in rasters])
    options = []
    for (item,gamma,_),support in zip(rasters,supports):
        w,s,e,n = item['bbox']
        visible = {j for j in new_labels if intersects_xy(support,*case['labels'][j])
                   and any(k==j and w <= points[improved][i][0] <= e and
                           s <= points[improved][i][1] <= n for i,k,_ in after)}
        options.append((len(visible),-item['window_id'],item,gamma,visible))
    gain,_,item,gamma,highlight = max(options, key=lambda x:x[:2])
    if not gain:
        raise ValueError('Selected example must contain a recovered match')
    preview = Image.fromarray(gray_rgba(np.ma.masked_less_equal(gamma,0))).convert('RGB')
    w,s,e,n = item['bbox']
    side = preview.width
    margin = 18
    font = ImageFont.truetype(str(font_path),42)

    def pixel(point):
        lon,lat = point[:2]
        return (lon-w)/(e-w)*side, (n-lat)/(n-s)*side

    contributions = []
    for name,method,matched in (('before',base,before),('after',improved,after)):
        pending = preview.copy()
        draw = ImageDraw.Draw(pending)
        selected = {j: (i,d) for i,j,d in matched if j in highlight}
        for index, label in enumerate(sorted(highlight),1):
            x,y = pixel(case['labels'][label])
            if label in selected:
                i,distance = selected[label]
                px,py = pixel(points[method][i])
                draw.line((x,y,px,py),fill='#ffe098',width=2)
                draw.ellipse((px-13,py-13,px+13,py+13),outline='#ffd266',width=3)
                contributions.append(dict(marker=index,
                    label=case['labels'][label], candidate=points[method][i][:2],
                    distance_m=round(distance,2)))
            draw.polygon(((x,y-8),(x+8,y),(x,y+8),(x-8,y)),outline='#56ecff',width=2)
            tx,ty = min(side-38,max(margin,x+17)),min(side-44,max(margin,y-35))
            draw.text((tx,ty),str(index),font=font,fill='#56ecff',stroke_width=2,stroke_fill='#071219')
        pending.save(out/f'recovered-{name}.png',optimize=True)
    return dict(scene=case['scene'],region=case['region'],source=cohort['source'],window_id=item['window_id'],
                bbox=item['bbox'],input_sha256=item['sha256'],scene_reviews=len(points[base]),
                before_matches=len(before),after_matches=len(after),recovered=contributions,
                selection='Greatest gain by acquisition, then most recovered pairs visible in one window; lowest window ID breaks ties.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('source','cache','views','font'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--out',type=Path,default=EVIDENCE)
    args = p.parse_args()
    contrast_path = EVIDENCE.parent/'vietnam_rtc_contrast_20261119/results.json'
    tta_path = EVIDENCE/'results.json'
    protocol = json.loads((EVIDENCE/'protocol.json').read_text())
    manifest = args.source/'rtc-512/manifest.json'
    if sha256(args.cache) != protocol['neural_cache_sha256']['fresh'] or sha256(manifest) != protocol['held_out_manifest_sha256']:
        raise ValueError('Cached predictions or source manifest differ from protocol')
    raw_views = json.loads(args.views.read_text())
    with gzip.open(args.cache,'rt') as stream:
        cached = json.load(stream)
    if set(raw_views) != {row['scene'] for row in cached}:
        raise ValueError('Baseline and overlap scenes differ')
    packet = dict(
        schema=1, coordinate_order='longitude, latitude in WGS84; proposal score last',
        source_annotation='Ai2 vessel-detection-sentinels at 60b003d059937a9fcddbf6e1c9b64c00c33c0279',
        sha256={key:sha256(path) for key,path in (
            ('neural_cache',args.cache),('held_out_views',args.views),('window_manifest',manifest),
            ('contrast_results',contrast_path),('tta_results',tta_path))},
        cases=[dict(scene=c['scene'],region=c['region'],labels=c['truth'],
                    queues=queues(c,raw_views[c['scene']]['overlap'])) for c in cached])
    totals = recount(packet,json.loads(contrast_path.read_text()),json.loads(tta_path.read_text()))
    args.out.mkdir(exist_ok=True,parents=True)
    example = illustration(args.source,packet['cases'],args.font,args.out)
    save(args.out/'review-queues.json',packet)
    save(args.out/'recovered-example.json',example)
    print(json.dumps(dict(example=example, totals_100m={m:{p:x[100] for p,x in d.items()}
                     for m,d in totals['policies'].items()}),indent=2))


if __name__ == '__main__':
    main()
