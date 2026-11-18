"""Draw the published OpenSAR scene footprints by adaptation split."""
import argparse
import json
from pathlib import Path
from zipfile import ZipFile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch, Polygon
import shapefile

STYLES = {
    'fit': ('Học · 7 cảnh', '#148477'),
    'tune': ('Chọn ngưỡng · 1 cảnh', '#e29030'),
    'diagnostic': ('Đối chiếu · 3 cảnh', '#4767bb'),
    'fresh': ('Giữ riêng · 1 cảnh', '#cc4f6e'),
}


def draw(args):
    sources = json.loads(args.screen.read_text())['scenes']
    policy = json.loads(args.policy.read_text())['dates']
    regions = [('Tây Phi', (0, 11, 1, 8.6)), ('Châu Âu và Bắc Đại Tây Dương', (-24, 20, 38, 68))]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.7))
    with ZipFile(args.coast) as archive:
        stem = 'GSHHS_shp/c/GSHHS_c_L1'
        with archive.open(stem+'.shp') as shp, archive.open(stem+'.shx') as shx, archive.open(stem+'.dbf') as dbf:
            reader = shapefile.Reader(shp=shp, shx=shx, dbf=dbf)
            for ax, (title, (west, east, south, north)) in zip(axes, regions):
                ax.set_facecolor('#ecf6f8')
                for land in reader.iterShapes(bbox=(west, south, east, north)):
                    for start, end in zip(land.parts, [*land.parts[1:], len(land.points)]):
                        ax.add_patch(Polygon(land.points[start:end], facecolor='#e6e7df',
                                             edgecolor='#a3b2ab', linewidth=.45, zorder=1))
                for row in sources.values():
                    key = next((group for group, dates in policy.items() if row['day'] in dates), None)
                    if key is None:
                        continue
                    coordinates = row['footprint']['coordinates'][0]
                    color = STYLES[key][1]
                    ax.add_patch(Polygon(coordinates, facecolor=color, edgecolor=color,
                                         linewidth=.95, alpha=.51, zorder=3))
                ax.set(xlim=(west,east), ylim=(south,north), title=title, xlabel='Kinh độ (°)', ylabel='Vĩ độ (°)')
                ax.grid(lw=.45, color='#8da5b3', alpha=.45, zorder=0)
                for spine in ax.spines.values():
                    spine.set_color('#a5b9bf')
    handles = [Patch(facecolor=c, edgecolor=c, label=label) for label,c in STYLES.values()]
    fig.legend(handles=handles, frameon=False, loc='lower center', ncol=4, fontsize=9)
    fig.text(.98,.12,'Footprint từ XML OpenSAR Insight · Đường bờ GSHHG 2.3.7',ha='right',fontsize=8,color='#41606b')
    fig.subplots_adjust(left=.08,right=.98,bottom=.24,top=.92,wspace=.24)
    fig.savefig(args.output,dpi=165,facecolor='white')
    plt.close(fig)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for option in ('screen','policy','coast','output'):
        p.add_argument('--'+option, required=True, type=Path)
    draw(p.parse_args())
