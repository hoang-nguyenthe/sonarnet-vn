"""Small, versioned source crops served by Streamlit, outside map HTML."""
import hashlib
import json
import os
from pathlib import Path
import tempfile

from PIL import Image


def evidence_url(root, candidate):
    root = Path(root)
    source = root / candidate['asset_dir'] / 'sar.png'
    if not source.is_file():
        return None
    signature = json.dumps([candidate['asset_dir'], candidate['bbox_px'],
                            source.stat().st_mtime_ns], sort_keys=True)
    name = hashlib.sha256(signature.encode()).hexdigest()[:32] + '.jpg'
    output = root / 'scripts' / 'static' / 'crops'
    target = output / name
    if not target.is_file():
        output.mkdir(parents=True, exist_ok=True)
        with Image.open(source) as image:
            x1, y1, x2, y2 = candidate['bbox_px']
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            half = max(80, (x2-x1)/2 + 42, (y2-y1)/2 + 42)
            crop = image.crop((max(0, int(cx-half)), max(0, int(cy-half)),
                               min(image.width, int(cx+half)), min(image.height, int(cy+half))))
            crop.thumbnail((280, 280), Image.Resampling.LANCZOS)
            fd, temporary = tempfile.mkstemp(dir=output, suffix='.jpg')
            try:
                with os.fdopen(fd, 'wb') as stream:
                    crop.convert('RGB').save(stream, 'JPEG', quality=84)
                os.replace(temporary, target)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
    # A srcdoc map inherits the Streamlit app document's base URL. On
    # Community Cloud that document lives at /~/+/, not the outer site root.
    # A leading slash drops that prefix and returns an HTML auth redirect
    # instead of the JPEG. Keep this relative for Cloud AND local deployments.
    return 'app/static/crops/' + name
