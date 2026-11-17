"""Restore pinned demo images with Git blob checksums, including sparse/ZIP checkouts.

python scripts/restore_published_assets.py --output assets/real_scan/published
Use a path on an external SSD when local storage is limited. This reads a large
GitHub source archive as a stream and stores only the selected published files.
"""
import argparse, hashlib, json, tarfile
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=ROOT/'assets/real_scan/published')
    args=p.parse_args()
    manifest=json.loads((ROOT/'configs/published_assets_3acf068.json').read_text())
    needed=manifest['files'];output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    def blob_sha(data):return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
    missing={}
    for name,expected in needed.items():
        dest=output/name
        if not dest.is_file() or blob_sha(dest.read_bytes())!=expected:missing[name]=expected
    print(f'{len(needed)-len(missing)} verified; {len(missing)} to restore',flush=True)
    if missing:
        url=f"https://codeload.github.com/hoang-nguyenthe/sonarnet-vn/tar.gz/{manifest['revision']}"
        with requests.get(url,stream=True,timeout=(30,180)) as response:
            response.raise_for_status()
            with tarfile.open(fileobj=response.raw,mode='r|gz') as archive:
                for member in archive:
                    parts=member.name.split('/',1)
                    if len(parts)!=2 or not member.isfile():continue
                    prefix='assets/real_scan/published/'
                    if not parts[1].startswith(prefix):continue
                    name=parts[1][len(prefix):]
                    if name not in missing:continue
                    data=archive.extractfile(member).read()
                    if blob_sha(data)!=missing[name]:raise ValueError('Checksum mismatch: '+name)
                    dest=(output/name).resolve()
                    if not dest.is_relative_to(output):raise ValueError('Unsafe member path')
                    dest.parent.mkdir(parents=True,exist_ok=True)
                    temp=dest.with_suffix(dest.suffix+'.part');temp.write_bytes(data);temp.replace(dest)
                    del missing[name]
                    if len(missing)%500==0:print(len(missing),'remaining',flush=True)
                    if not missing:break
        if missing:raise RuntimeError(f'{len(missing)} assets not found in archive')
    (output/'RECOVERY.json').write_text(json.dumps(dict(source_revision=manifest['revision'],files=len(needed),verification='Git blob SHA-1 for every file'),indent=2))
    print('All published demo files verified.',flush=True)

if __name__=='__main__':main()
