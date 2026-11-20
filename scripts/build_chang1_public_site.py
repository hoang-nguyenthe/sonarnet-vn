"""Export the public Chặng 1 evidence page from a pinned source revision."""
import argparse
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import zipfile


ROOT = Path(__file__).resolve().parents[1]
GITHUB = 'https://github.com/hoang-nguyenthe/sonarnet-vn'
FINAL = 'reports/final'
TRANSFER = f'{FINAL}/vietnam_rtc_transfer_20261119'
DUAL = f'{FINAL}/stationary_ais_detection_20261120/dual-band'
MATCH = f'{FINAL}/multiscene_sar_ais_20261119/results.json'
SAMPLE = f'{FINAL}/export_verification/sample_evidence.zip'
PDF = 'output/pdf/SonarNet_Bao_cao_Chang1_Giu_cap_AIS_20261118.pdf'


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def run_pinned_scenarios(git, commit):
    """Use the engine and scenarios from the evidence revision."""
    script = 'scripts/ais_demo_cases.py'
    entries = subprocess.check_output(
        git + ['ls-tree', '-rz', commit, '--', 'src/sonarnet', script], text=True
    )
    with TemporaryDirectory(prefix='sonarnet-ais-cases-') as directory:
        root = Path(directory)
        for entry in entries.rstrip('\0').split('\0'):
            metadata, name = entry.split('\t', 1)
            mode, kind, object_id = metadata.split()
            target = root / name
            if kind != 'blob' or mode not in {'100644', '100755'}:
                raise ValueError(f'Unexpected Git entry in pinned scenario module: {name}')
            if not target.resolve().is_relative_to(root.resolve()):
                raise ValueError(f'Unexpected path in pinned scenario module: {name}')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(subprocess.check_output(git + ['cat-file', 'blob', object_id]))
        env = {**os.environ, 'PYTHONPATH': str(root / 'src')}
        result = subprocess.check_output([sys.executable, str(root / script)], cwd=root, env=env)
    return json.loads(result)


def export(output, repository, revision):
    git = ['git', '-C', str(repository)]
    commit = subprocess.check_output(
        git + ['rev-parse', '--verify', '--end-of-options', f'{revision}^{{commit}}'],
        text=True,
    ).strip()

    def read(path):
        return subprocess.check_output(git + ['show', f'{commit}:{path}'])

    def read_json(path):
        return json.loads(read(path))

    vietnam = read_json(f'{TRANSFER}/summary.json')['datasets']
    rank_fusion = read_json(f'{TRANSFER}/rank_fusion/results.json')['test']
    dual = read_json(f'{DUAL}/results.json')['totals']
    association = read_json(MATCH)['aggregate']
    scenarios = run_pinned_scenarios(git, commit)
    local_example = read_json(f'{TRANSFER}/xview3/recovered-example.json')
    ais_example = read_json(f'{DUAL}/example.json')
    local_results = read_json(f'{TRANSFER}/xview3/results.json')
    local_case = next(
        row for row in local_results['test']['held_out']
        if row['scene'] == local_example['scene']
    )[local_example['review_mode']]
    first = local_case[local_example['prior_method']]['100']
    second = local_case[local_example['method']]['100']
    if (first['matched'], second['matched'], first['predictions'], second['predictions']) != (
        local_example['before_matches'], local_example['after_matches'],
        local_example['scene_reviews'], local_example['scene_reviews'],
    ):
        raise ValueError('The Vietnam illustration does not match the scene results')

    media = {}
    for state in ('before', 'after'):
        media[f'vn-{state}.png'] = read(f'{TRANSFER}/xview3/recovered-{state}.png')
        media[f'ais-{state}.png'] = read(f'{DUAL}/example-{state}.png')
        if sha256(media[f'vn-{state}.png']) != local_example[f'{state}_image_sha256']:
            raise ValueError('The Vietnam illustration differs from its evidence record')
        if sha256(media[f'ais-{state}.png']) != ais_example['images'][state]['sha256']:
            raise ValueError('The AIS illustration differs from its evidence record')

    sample_zip = read(SAMPLE)
    with zipfile.ZipFile(BytesIO(sample_zip)) as archive:
        sample = json.loads(archive.read('evidence.json'))
        checksums = json.loads(archive.read('checksums.json'))
        for name, checksum in checksums.items():
            if sha256(archive.read(name)) != checksum:
                raise ValueError(f'The sample checksum does not match {name}')
        media['anh-nguon.png'] = archive.read('source.png')
        media['ung-vien-sar.jpg'] = archive.read('candidates.jpg')
    if sample['data_status'] != 'MISSING_DATA' or len(sample['detections']) != 1:
        raise ValueError('The sample no longer represents the published missing-AIS case')
    media['ho-so-mau.zip'] = sample_zip
    media['bao-cao-chang-1.pdf'] = read(PDF)

    ais_offset = f"{ais_example['distance_m']:.2f}".replace('.', ',')
    tree = f'{GITHUB}/tree/{commit}'
    blob = f'{GITHUB}/blob/{commit}'
    data = {
        'commit': commit,
        'vietnam': {key: value['modes'] for key, value in vietnam.items()},
        'rank_fusion': {key: value['totals'] for key, value in rank_fusion.items()},
        'ais': dual,
        'association': association,
        'scenarios': scenarios,
        'examples': {
            'vietnam': {
                'area': 'Vịnh Quảng Ninh, 24/06/2022',
                'reviewed': local_example['scene_reviews'],
                'labels': first['labels'],
                'before': local_example['before_matches'],
                'after': local_example['after_matches'],
                'imagePrefix': 'vn',
                'note': 'Ví dụ từ tập 12 lượt chụp, ở mức 191 lượt rà trên toàn tập và bán kính 100 m.',
            },
            'ais': {
                'area': ais_example['area'] + ', 11/07/2024',
                'reviewed': ais_example['reviewed'],
                'labels': ais_example['reference_count'],
                'before': ais_example['before'],
                'after': ais_example['after'],
                'imagePrefix': 'ais',
                'note': (
                    'Ví dụ ở mức 410 lượt rà trên toàn tập và bán kính 100 m. '
                    f'Ứng viên mới cách mốc tham chiếu {ais_offset} m.'
                ),
            },
        },
        'sample': {
            'zipSha256': sha256(sample_zip),
            'imageSha256': sha256(media['anh-nguon.png']),
            'key': sample['key'],
            'candidateId': sample['detections'][0]['id'],
        },
        'links': {
            'code': tree,
            'vnResults': f'{blob}/{TRANSFER}/summary.json',
            'vnProtocol': f'{blob}/{TRANSFER}/README.md',
            'rankFusionProtocol': f'{blob}/{TRANSFER}/rank_fusion/README.md',
            'aisResults': f'{blob}/{DUAL}/results.json',
            'aisProtocol': f'{blob}/{DUAL}/protocol.json',
            'associationResults': f'{blob}/{MATCH}',
            'scenarioCode': f'{blob}/scripts/ais_demo_cases.py',
        },
    }

    output.mkdir(parents=True, exist_ok=False)
    (output / 'data').mkdir()
    for name in ('index.html', 'style.css', 'app.js'):
        (output / name).write_bytes(read(f'web/chang1/{name}'))
    (output / '.nojekyll').touch()
    for name, contents in media.items():
        (output / 'data' / name).write_bytes(contents)
    (output / 'data/minh-chung.json').write_text(
        json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8'
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New output directory')
    parser.add_argument('--git-repository', type=Path, default=ROOT)
    parser.add_argument('--commit', required=True, help='Revision containing the evidence and report')
    args = parser.parse_args()
    export(args.output, args.git_repository, args.commit)


if __name__ == '__main__':
    main()
