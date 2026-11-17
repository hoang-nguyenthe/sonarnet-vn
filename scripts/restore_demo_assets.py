"""Restore only small selected published assets from the pinned source revision."""
from pathlib import Path
import subprocess
import requests

ROOT = Path(__file__).resolve().parents[1]
REV = '3acf068fbfe151c51b96db699fa4cf019f8ca7e6'

def main():
    result = subprocess.check_output(['git','diff','--name-only','--','assets','sonarnet_run'], cwd=ROOT, text=True)
    for name in result.splitlines():
        if not name.endswith(('.json','.png')):
            continue
        response=requests.get(f'https://raw.githubusercontent.com/hoang-nguyenthe/sonarnet-vn/{REV}/{name}',timeout=60)
        response.raise_for_status()
        if len(response.content)>35_000_000:
            raise ValueError('Asset too large for small demo recovery')
        target=ROOT/name
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(response.content)
        print(name,len(response.content))

if __name__=='__main__':
    main()
