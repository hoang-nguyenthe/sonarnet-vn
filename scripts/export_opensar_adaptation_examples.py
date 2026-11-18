"""Render exact matched and unmatched boxes from a frozen SLC benchmark."""
import argparse
import gzip
import json
from pathlib import Path

import matplotlib
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from evaluate_opensar_geo import assign_unique_support, normalize, open_split
from prepare_opensar_geo import save

BG = '#102e40'
LABEL = '#60e7ff'
HIT = '#fcbb64'
EXTRA = '#fd5973'


def read_json(path):
    with gzip.open(path, 'rt') as stream:
        return json.load(stream)


def draw_panel(canvas, offset, image, row, failures, pred, threshold, title, font, small):
    canvas.paste(image, (offset, 72))
    draw = ImageDraw.Draw(canvas)
    draw.text((offset+14, 12), title, font=font, fill='#ffffff')
    positives = len(failures['matched_indices'])
    misses = len(failures['false_negative_indices'])
    extras = set(failures['false_positive_indices'])
    draw.text((offset+14, 41), f'Khớp {positives} · Bỏ sót {misses} · Không khớp {len(extras)}',
              font=small, fill='#b8dce8')

    def outline(box, tint, width):
        x1, y1, x2, y2 = np.clip(box, 0, 511)
        draw.rectangle((offset+x1, y1+72, offset+x2, y2+72), outline=tint, width=width)

    for box in row['boxes_xyxy']:
        outline(box, LABEL, 3)
    for i, (box, confidence) in enumerate(zip(pred['boxes'], pred['scores'])):
        if confidence >= threshold:
            outline(box, EXTRA if i in extras else HIT, 1)
    draw.text((offset+14, 594), f"OpenSAR Insight · Ô {row['id']} · {row['day']} UTC",
              font=small, fill='#ffffff')


def export(args):
    report = json.loads((args.evaluation/'results.json').read_text())
    specs = (
        ('diagnostic', args.diagnostic/'confirmation_manifest.json', args.data/'prepared-confirmation-v1',
         'reference_ls_ssdd', 'YOLO · học trên LS-SSDD', 'Ô có mức tăng số nhãn khớp cao nhất'),
        ('north_sea', args.adaptation/'fresh_manifest.json', args.adaptation/'rasters',
         'guard_ring_cfar', 'Đối chứng · CFAR vòng nền', 'Ô có tổng số bỏ sót và không khớp cao nhất'),
    )
    args.out.mkdir(parents=True, exist_ok=True)
    path = Path(matplotlib.get_data_path())/'fonts'/'ttf'/'DejaVuSans.ttf'
    font = ImageFont.truetype(str(path), 24)
    small = ImageFont.truetype(str(path), 15)
    gallery = []
    for area, manifest, root, ref, label, title in specs:
        names = (ref, 'adapted_slc_vv')
        failures = {key:{row['id']:row for row in read_json(args.evaluation/f'{area}_{key}_errors.json.gz')}
                    for key in names}
        before, after = (failures[key] for key in names)
        if area == 'diagnostic':
            ident = max(after, key=lambda i: (
                len(after[i]['matched_indices'])-len(before[i]['matched_indices']),
                -len(after[i]['false_positive_indices']), -int(i)))
        else:
            ident = max(after, key=lambda i: (
                len(after[i]['false_positive_indices'])+len(after[i]['false_negative_indices']),
                len(after[i]['false_negative_indices']), -int(i)))
        rows, images = open_split(manifest, root)
        assign_unique_support(rows)
        row = rows[ident]
        image = Image.fromarray(normalize(images[ident], 'log1p')).convert('RGB')
        canvas = Image.new('RGB', (1032, 626), BG)
        for k, (name, caption) in enumerate(zip(names, (label, 'YOLO · học trên SLC VV'))):
            preds = read_json(args.evaluation/f'{area}_{name}_predictions.json.gz')
            cut = report['evaluation'][area]['models'][name]['threshold']
            draw_panel(canvas, k*520, image, row, failures[name][ident], preds[ident], cut, caption, font, small)
        filename = f'comparison_{area}.png'
        canvas.save(args.out/filename)
        gallery.append(dict(cohort=area, file=filename, id=ident, day=row['day'], selection=title))
        del rows, images
    save(args.out/'gallery.json', gallery)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('data', 'adaptation', 'diagnostic', 'evaluation', 'out'):
        parser.add_argument('--'+name, required=True, type=Path)
    export(parser.parse_args())
