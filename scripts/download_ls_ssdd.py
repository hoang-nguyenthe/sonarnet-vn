"""Fetch selected original LS-SSDD members using HTTP ranges, not the 8.3 GB archive.

The URL is published in the author's repository history (b0a4d0968e08c990).
ZIP CRC and per-file SHA256 are retained; no whole-archive checksum is claimed.
"""
import argparse
from collections import OrderedDict
import hashlib
import io
import json
from pathlib import Path
import time
import zipfile
import requests

URL = 'https://drive.usercontent.google.com/download?id=1-fSKYsKr5wuYuXJE2CDX_Yfr4Ylwjfqm&export=download&confirm=t'


class RangeFile(io.RawIOBase):
    def __init__(self, url, block=8 * 1024**2):
        self.url, self.block, self.position = url, block, 0
        self.session = requests.Session()
        response = self.session.head(url, timeout=60, allow_redirects=True)
        response.raise_for_status()
        self.length = int(response.headers['Content-Length'])
        self.modified = response.headers.get('Last-Modified')
        self.cache = OrderedDict()
        self.transferred = 0

    def seekable(self): return True
    def readable(self): return True
    def tell(self): return self.position
    def seek(self, offset, whence=0):
        self.position = offset if whence == 0 else self.position + offset if whence == 1 else self.length + offset
        if self.position < 0: raise ValueError('Negative seek')
        return self.position

    def read(self, size=-1):
        end = self.length if size < 0 else min(self.length, self.position + size)
        chunks = []
        while self.position < end:
            block_start = self.position // self.block * self.block
            if block_start not in self.cache:
                block_end = min(self.length, block_start + self.block) - 1
                for attempt in range(4):
                    try:
                        response = self.session.get(self.url, headers={'Range': f'bytes={block_start}-{block_end}'},
                                                    timeout=90, stream=True)
                        if response.status_code != 206:
                            response.close()
                            raise ValueError('Server must honor HTTP Range; refusing a full archive download')
                        content = response.content
                        if len(content) != block_end - block_start + 1:
                            raise ValueError('Incomplete range')
                        self.transferred += len(content)
                        self.cache[block_start] = content
                        while len(self.cache) > 2: self.cache.popitem(last=False)
                        break
                    except (requests.RequestException, ValueError):
                        if attempt == 3: raise
                        time.sleep(1 + attempt)
            data = self.cache[block_start]
            offset = self.position - block_start
            part = data[offset:offset + min(end - self.position, len(data) - offset)]
            chunks.append(part)
            self.position += len(part)
        return b''.join(chunks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--inventory-only', action='store_true')
    args = parser.parse_args()
    remote = RangeFile(URL)
    with zipfile.ZipFile(remote) as archive:
        selected = [i for i in archive.infolist() if not i.is_dir() and any('/' + k + '/' in i.filename
                    for k in ('JPEGImages_sub', 'Annotations_sub', 'Annotations', 'ImageSets', 'Tools'))]
        print(json.dumps({'archive_bytes':remote.length,'selected_files':len(selected),
            'selected_bytes':sum(i.file_size for i in selected),
            'selected_compressed_bytes':sum(i.compress_size for i in selected)}, indent=2), flush=True)
        if args.inventory_only:
            print('\n'.join(i.filename for i in selected if '/Tools/' in i.filename or '/ImageSets/' in i.filename))
            return
        args.output.mkdir(parents=True, exist_ok=True)
        records = []
        for n, member in enumerate(sorted(selected, key=lambda x:x.header_offset)):
            relative = Path(member.filename)
            if relative.is_absolute() or '..' in relative.parts:
                raise ValueError('Unsafe archive path')
            target = args.output / relative
            # Always validate existing members against the source CRC, allowing an interrupted run to resume.
            import zlib
            if target.exists() and target.stat().st_size == member.file_size:
                raw = target.read_bytes()
                if zlib.crc32(raw) != member.CRC: raw = archive.read(member)
            else:
                raw = archive.read(member)
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists() or hashlib.sha256(target.read_bytes()).digest() != hashlib.sha256(raw).digest():
                target.write_bytes(raw)
            records.append({'path':member.filename,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'zip_crc':member.CRC})
            if n % 500 == 0: print(f'{n}/{len(selected)} files; {remote.transferred / 1024**2:.1f} MiB fetched', flush=True)
        (args.output/'download_manifest.json').write_text(json.dumps({'url':URL,
            'author_source':'https://github.com/TianwenZhang0825/LS-SSDD-v1.0-OPEN/blob/b0a4d0968e08c990a583a59045de466c37bbb7de/README.md',
            'archive_bytes':remote.length,'last_modified':remote.modified,'whole_archive_sha256':None,
            'integrity':'ZIP CRC verified by zipfile; SHA256 per extracted member', 'files':records},indent=2))
        print('Completed selected original members', flush=True)


if __name__ == '__main__': main()
