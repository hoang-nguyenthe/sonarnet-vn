"""Build a lossless runtime mask without full-resolution Python coordinate trees."""
import gzip
import hashlib
import json
from pathlib import Path
import zipfile
from shapely.geometry import shape


def pack(source, destination):
    raw = source.read_bytes()
    data = json.loads(gzip.decompress(raw))
    geometry = data.pop('geometry')
    data['packed_source_sha256'] = hashlib.sha256(raw).hexdigest()
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('metadata.json', json.dumps(data, ensure_ascii=False))
        for key, value in geometry.items():
            archive.writestr(f'{key}.wkb', shape(value).wkb)


if __name__ == '__main__':
    directory = Path(__file__).resolve().parents[1]/'assets/land_mask'
    pack(directory/'vietnam.json.gz', directory/'vietnam.runtime.zip')
