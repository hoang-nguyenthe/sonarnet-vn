"""Plot matched source annotations for each equal-cost SAR review policy."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1] / 'reports/final'


def plot(contrast, tta, output):
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6), sharex=True, layout='constrained')
    colors = ('#718c9c', '#127774', '#2565a3')
    for axis, mode, baseline, count in zip(axes, ('equal_incumbent','equal_relaxed'),
                                          ('map_default','map_lower_threshold'), (116,191)):
        acquisitions = [(contrast,baseline), (contrast,contrast['selected'][mode]), (tta,tta['selected'][mode])]
        totals = []
        for source, policy in acquisitions:
            counts = [c[mode][policy]['100'] for c in source['cases']]
            if sum(c['predictions'] for c in counts) != count:
                raise ValueError('Comparison requires identical review counts')
            totals.append(sum(c['matched'] for c in counts))
        labels = ['Bản đồ', 'Lọc điểm trong 35 m', 'Xoay và lật ảnh' if count == 116 else 'Ô ảnh chồng lấn']
        bars = axis.barh(labels,totals,color=colors,height=.52)
        axis.bar_label(bars, labels=[f'{n}/152' for n in totals], padding=5, color='#183c4b', fontweight='bold')
        axis.set_title(f'{count} lượt rà',fontweight='bold',loc='left',color='#17384b')
        axis.set_xlim(0,152)
        axis.invert_yaxis()
        axis.set_xlabel('Số nhãn khớp trong 100 m',color='#3c5765')
        axis.set_xticks([0,50,100,150])
        axis.tick_params(length=0, colors='#294956',labelsize=9)
        axis.set_axisbelow(True)
        axis.grid(axis='x',alpha=.25)
        axis.spines[['top','left','right','bottom']].set_visible(False)
    fig.savefig(output,dpi=180,facecolor='white')
    plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path,
                        default=ROOT/'vietnam_rtc_tta_20261119/equal-review.png')
    args = parser.parse_args()
    inputs = [json.loads((ROOT/f'vietnam_rtc_{name}_20261119/results.json').read_text())
              for name in ('contrast','tta')]
    plot(*inputs,args.output)
