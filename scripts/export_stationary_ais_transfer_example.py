"""Export a paired SAR crop for a stationary AIS reference recovered by the transfer."""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw

from replay_rtc_equal_review import matching, sha256

WIDTH = 256


def read(path):
    return json.loads(path.read_text())


def best_recovered(cases, rows, references):
    choices = []
    for case, row, reference in zip(cases,rows,references,strict=True):
        if len({item['product'] for item in (case,row,reference)}) != 1:
            raise ValueError('Illustration packets are for different scenes')
        labels = reference['labels']
        queues = row['queues']['narrow']
        previous = matching(queues['prior'],labels,100)
        fused = matching(queues['fused_xview3'],labels,100)
        old = {j for _,j,_ in previous}
        gained = len(fused)-len(previous)
        for index, label, distance in fused:
            if label not in old:
                choices.append((gained,len(previous),len(fused),case,labels[label],
                                queues['fused_xview3'][index][:2],distance))
    if not choices:
        raise ValueError('The comparator produced no new matched reference')
    return max(choices,key=lambda x:(x[0],-x[-1]))


def tile_for(points, folder, manifest, inventory):
    for row in inventory['windows']:
        w,s,e,n = row['bbox']
        if any(not (w<=x<e and s<y<=n) for x,y in points):
            continue
        tile=row['tile']
        path=folder/f'tile_{tile}.png'
        pinned=manifest['images'][tile]['sha256']
        if row['preview_sha256']!=pinned or sha256(path)!=pinned:
            raise ValueError('Source image differs from the evaluated radar')
        return row,path
    raise ValueError('Matched point and reference have no shared raster window')


def crop_pair(image, bounds, points, out):
    w,s,e,n=bounds
    width,height=image.size
    places=[((lon-w)/(e-w)*width,(n-lat)/(n-s)*height) for lon,lat in points]
    center_x,center_y=places[0]
    x0=min(width-WIDTH,max(0,round(center_x-WIDTH/2)))
    y0=min(height-WIDTH,max(0,round(center_y-WIDTH/2)))
    crop=(x0,y0,x0+WIDTH,y0+WIDTH)
    a,b=[(x-x0,y-y0) for x,y in places]
    def diamond(draw, p):
        x,y=p
        draw.polygon([(x,y-9),(x+9,y),(x,y+9),(x-9,y)],outline='#64ecff',width=3)
    images={}
    for side in ('before','after'):
        canvas=image.crop(crop)
        draw=ImageDraw.Draw(canvas)
        if side=='after':
            x,y=b
            draw.line((*a,*b),fill='#ffd577',width=2)
            draw.ellipse((x-13,y-13,x+13,y+13),outline='#ffd577',width=3)
        diamond(draw,a)
        name=f'example-{side}.png'
        canvas.save(out/name,optimize=True)
        images[side]=dict(name=name,sha256=sha256(out/name))
    return list(crop),images


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('source','reference','study'):
        parser.add_argument('--'+flag,type=Path,required=True)
    args=parser.parse_args()
    archive=args.study/'review-queues.json'
    packets=read(archive)
    result_path=args.study/'results.json'
    results=read(result_path)
    if packets['result_sha256']!=sha256(result_path):
        raise ValueError('Review coordinates do not match the recorded result')
    gain, before, after, case, label, candidate, distance=best_recovered(
        results['scenes'],packets['scenes'],read(args.reference))
    product=case['product']
    folder=args.source/product
    inventory_path=args.study/'source-bands'/f'{product}.json'
    if sha256(inventory_path)!=case['raster_manifest_sha256']:
        raise ValueError('Wrong RTC inventory')
    row,path=tile_for((label,candidate),folder,read(folder/'raster_provenance.json'),read(inventory_path))
    with Image.open(path) as source:
        crop,images=crop_pair(source.convert('RGB'),row['bbox'],(label,candidate),args.study)
    labels=case['scores']['narrow']['prior']['100']['labels']
    reviews=case['scores']['narrow']['prior']['100']['predictions']
    result=dict(product=product,area=case['area'],utc=case['utc'],tile=row['tile'],
                reviewed=reviews,reference_count=labels,before=before,after=after,net_gain=gain,
                distance_m=round(distance,2),crop_px=crop,reference=label,candidate=candidate,
                images=images,source_preview_sha256=row['preview_sha256'],review_queues_sha256=sha256(archive))
    (args.study/'example.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':
    main()
