"""Verify the published SAR/AIS cohort without downloading raw source archives."""
import argparse
import json
from hashlib import file_digest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT/'reports/final/multiscene_sar_ais_20261119'
KINDS = ('near_time','near_stationary')


def sha(path):
    with path.open('rb') as stream:
        return file_digest(stream,'sha256').hexdigest()


def check(condition, label):
    if not condition:
        raise ValueError(label)


def verify(folder):
    protocol_path=folder/'protocol.json'
    protocol=json.loads(protocol_path.read_text())
    report=json.loads((folder/'results.json').read_text())
    check(report['complete'] and len(report['scenes'])==report['expected_scenes']==len(protocol['products']),
          'Frozen radar cohort incomplete')
    check(sha(protocol_path)==report['protocol_sha256'],'Protocol checksum differs')
    check(sha(folder/'catalogue-screen.json')==protocol['catalogue_sha256'],'Catalogue checksum differs')
    sources = {ROOT/'scripts/prepare_multiscene_sar_ais.py':protocol['selection_code_sha256'],
               ROOT/'scripts/evaluate_multiscene_sar_ais.py':report['evaluator_sha256'],
               ROOT/'src/sonarnet/fusion/matching.py':report['fusion_sha256'],
               ROOT/protocol['raster']['detector']:report['model_sha256']}
    for path,digest in sources.items():
        check(sha(path)==digest,f'{path.name} differs')
    output={}
    for product,scene in zip(protocol['products'],report['scenes']):
        check((scene['area'],scene['product'],scene['utc'])==(product['area'],product['product'],product['acquired_at']),
              'Scene and locked catalogue record differ')
        check(scene['raster_provenance']['source_item_url']==product['source_item_url'],'Radar lineage differs')
        check(scene['ais_source']['source'].endswith(scene['utc'][:10].replace('-','_')+'.zip'),
              'AIS and radar acquisition dates differ')
        tile_counts=sum(t.get('detected_candidates',0) for t in scene['tiles'])
        check(len(scene['tiles'])==len(product['tiles_wsen']) and tile_counts==scene['radar_candidates'],
              'Raster tile totals differ')
    for kind in KINDS:
        cases=[row[kind] for row in report['scenes']]
        references=sum(c['paired_references'] for c in cases)
        check(report['aggregate'][kind]['paired_references']==references,'Reference total differs')
        output[kind]={'references':references,'policies':{}}
        for method,row in report['aggregate'][kind]['counts'].items():
            for key,val in row.items():
                check(val==sum(c['counts'][method][key] for c in cases),f'{kind} {method} count differs')
            for scene,case in zip(report['scenes'],cases):
                c=case['counts'][method]
                check(c['agree']+c['disagree']+c['reference_unpaired']==case['paired_references'],
                      'Reference agreement, disagreement and hold do not balance')
                check(c['agree']+c['disagree']+c['proposed_without_reference']==c['proposed'],
                      'Proposed pair count does not balance')
                check(c['proposed']+c['withheld']==scene['radar_candidates'],
                      'Radar candidate count does not balance')
            output[kind]['policies'][method]={'agree':row['agree'],'disagree':row['disagree'],
                                             'held_reference':row['reference_unpaired']}
    example=json.loads((folder/'example.json').read_text())
    source=next(row for row in report['scenes'] if row['product']==example['product'])
    tile=next(row for row in source['tiles'] if row['tile']==example['tile'])
    check(sha(folder/'example.jpg')==tile['marked_sha256'],'Illustration checksum differs')
    check(sha(folder/'example-source.png')==tile['sha256'],'Source raster checksum differs')
    return dict(scenes=len(report['scenes']),radar_candidates=sum(s['radar_candidates'] for s in report['scenes']),
                **output)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence',type=Path,default=DEFAULT)
    print(json.dumps(verify(p.parse_args().evidence),indent=2))
