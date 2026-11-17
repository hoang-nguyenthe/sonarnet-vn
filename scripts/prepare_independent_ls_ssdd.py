"""Prepare a fixed scene/region/day-disjoint LS-SSDD cohort before model training."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import numpy as np
from PIL import Image
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from sonarnet.evaluation.independent_sar import audit_manifest
from prepare_ls_ssdd import labels_from_xml


def prepare(source, output, policy):
    metadata = json.loads(policy.read_text())
    scenes = {s['scene_id']:s for s in metadata['scenes']}
    coastal = set((source/'ImageSets/Main/test_inshore.txt').read_text().split())
    offshore = set((source/'ImageSets/Main/test_offshore.txt').read_text().split())
    if coastal & offshore: raise ValueError('Conflicting official shore labels')
    xmls = sorted((source/'Annotations_sub').glob('*.xml'))
    if len(xmls) != 9000: raise ValueError('All 9000 source annotations are required')
    rows, counts = [], Counter()
    for path in xmls:
        ident = path.stem
        scene = scenes[f'{int(ident.split("_")[0]):02d}']
        split = scene['split']
        if split == 'excluded': continue
        image = source/'JPEGImages_sub'/f'{ident}.jpg'
        with Image.open(image) as im:
            if im.size != (800,800): raise ValueError('Unexpected image dimensions')
        raw = path.read_bytes()
        labels = labels_from_xml(raw)
        boxes=[]
        for label in labels:
            _,cx,cy,w,h=map(float,label.split())
            boxes.append([(cx-w/2)*800,(cy-h/2)*800,(cx+w/2)*800,(cy+h/2)*800])
        image_dest=output/'images'/split/image.name
        label_dest=output/'labels'/split/f'{ident}.txt'
        image_dest.parent.mkdir(parents=True,exist_ok=True)
        label_dest.parent.mkdir(parents=True,exist_ok=True)
        # Hard links retain exact bytes without storing a second copy on the SSD.
        if not image_dest.exists(): image_dest.hardlink_to(image)
        label_dest.write_text('\n'.join(labels)+'\n' if labels else '')
        if split == 'test' and ident not in coastal | offshore:
            raise ValueError(f'{ident}: no official inshore/offshore label')
        row=dict(id=ident,image=str(image_dest.relative_to(output)),sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
                 split=split,scene_id=scene['scene_id'],region_id=scene['region_id'],
                 acquired_date_utc=scene['acquired_date_utc'],annotation_status='reviewed',
                 annotation_provenance='Original LS-SSDD author labels; not independently re-annotated by SonarNet',
                 label_sha256=hashlib.sha256(raw).hexdigest(),boxes_xyxy=boxes,
                 nearshore_gt=[ident in coastal]*len(boxes) if split=='test' else None,
                 valid_area_km2=None,gsd_x_m=None,gsd_y_m=None)
        rows.append(row);counts[split]+=1
    manifest=dict(metadata_source=metadata['metadata_source'],selection_rule=metadata['selection_rule'],
                  policy_sha256=hashlib.sha256(policy.read_bytes()).hexdigest(),
                  nearshore_definition=metadata['nearshore_definition'],
                  metric_limits='Physical calibration not assumed from radar resolution. Metre/area metrics await verified pixel spacing.',
                  images=rows)
    output.mkdir(parents=True,exist_ok=True)
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2))
    audit=audit_manifest(manifest,output)
    if not audit['errors'] and audit['review_required']:
        # Conservatively quarantine the lower-priority split. No assertion that
        # perceptual similarity proves duplication, and no change to test data.
        by_id={r['id']:r for r in rows}
        priority={'train':0,'val':1,'test':2}
        removed=set()
        for warning in audit['review_required']:
            left,right=warning.split(': ',1)[1].split(' / ')
            remove=min([left,right],key=lambda k:priority[by_id[k]['split']])
            removed.add(remove)
        quarantine=dict(reason='Conservative cross-split dHash<=3 quarantine; similarity is not confirmed duplication',
                        priority='test retained; val preferred over train',
                        removed_ids=sorted(removed),candidate_pairs=audit['review_required'])
        (output/'quarantine.json').write_text(json.dumps(quarantine,indent=2))
        for ident in removed:
            row=by_id[ident]
            for rel in [Path(row['image']),Path('labels')/row['split']/f'{ident}.txt']:
                destination=output/'quarantine'/rel
                destination.parent.mkdir(parents=True,exist_ok=True)
                (output/rel).replace(destination)
        manifest['images']=[r for r in rows if r['id'] not in removed]
        manifest['quarantine']=dict(removed_images=len(removed),reason=quarantine['reason'])
        (output/'manifest.json').write_text(json.dumps(manifest,indent=2))
        audit=audit_manifest(manifest,output)
        counts=Counter(r['split'] for r in manifest['images'])
    (output/'audit.json').write_text(json.dumps(audit,indent=2))
    if not audit['passed']:
        raise ValueError(f'Audit requires review: {len(audit["errors"])} errors, {len(audit["review_required"])} similarity pairs; see audit.json')
    (output/'data.yaml').write_text(yaml.safe_dump(dict(path=str(output.resolve()),train='images/train',val='images/val',test='images/test',names={0:'ship'})))
    print(json.dumps(dict(counts=counts,audit=audit),indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--policy',type=Path,default=ROOT/'configs/ls_ssdd_scenes.json')
    args=parser.parse_args();prepare(args.source,args.output,args.policy)
