"""Prepare additional RTC references from acquisition days outside development."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import prepare_vn_reference_rtc as prepare

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--development', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args=parser.parse_args()
    old=json.loads((args.development/'screened.json').read_text())
    reserved={scene for scenes in old['regions'].values() for scene in scenes}
    dest=args.output
    dest.mkdir(exist_ok=False)
    prepare.REGIONS = {
     'quang_ninh_gulf': (107.1,20.25,108.65,21.43),
     'khanh_hoa_binh_thuan': (108.7,10.85,109.65,12.65),
     'south_mekong_coast': (105.85,8.10,107.50,9.55),
     'kien_giang_west': (103.52,9.55,104.45,10.62),
    }
    regions=prepare.screen(prepare.label_db(args.development))
    filtered={r:{actual:c for actual,c in scenes.items() if actual not in reserved and c['points']}
              for r,scenes in regions.items()}
    jobs=[(r,scene,block) for r,scenes in filtered.items() for scene,block in scenes.items()]
    def match(job):
     try:
      return prepare.exact_match(job)
     except (ValueError, AttributeError) as e:
      print('Unmatched catalogue product:',job[0], job[1].split('_')[4],type(e).__name__,flush=True)
      return None
    with ThreadPoolExecutor(max_workers=3) as pool:
     results=list(pool.map(match,jobs))
    acquisitions=[r for r in results if r is not None]
    if not acquisitions:
     raise RuntimeError('No exact additional RTC products')
    print('Fresh regions', len({row['region'] for row in acquisitions}),
          '| exact products', len(acquisitions),'| point labels',sum(row['labels'] for row in acquisitions),
          '| total windows',sum(len(filtered[row['region']][row['scene']]['windows']) for row in acquisitions),flush=True)
    (dest/'screened.json').write_text(json.dumps(dict(bounds=prepare.REGIONS,regions=filtered),indent=2))
    (dest/'rtc-matching-with-lineage.json').write_text(json.dumps(acquisitions,indent=2))


if __name__ == '__main__':
    main()
