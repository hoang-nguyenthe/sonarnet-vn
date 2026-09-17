"""Run the real-SAR candidate over every published image using local MPS.

Research output only: does not alter published detections or claim accuracy.
"""
import hashlib
import json
from pathlib import Path
import sys
from datetime import datetime, timezone
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from refresh_detailed_scan import infer_tile
from land_mask import get_mask
from scan_assets import validate_tile


def main():
    import torch
    from ultralytics import YOLO
    if not torch.backends.mps.is_available():
        raise RuntimeError('MPS unavailable')
    weights = ROOT / 'training_real/ls_ssdd_backgrounds/weights/best.pt'
    model = YOLO(str(weights))
    mask = get_mask(ROOT)
    source = ROOT / 'assets/real_scan/report.json'
    report = json.loads(source.read_text())
    output = ROOT / 'training_real/ls_ssdd_backgrounds/vietnam_observations.json'
    result = dict(device='mps', weights_sha256=hashlib.sha256(weights.read_bytes()).hexdigest(),
                  source_report_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  validation='Unlabelled Vietnam observations; not accuracy evaluation or production approval',
                  tiles=[])
    for tile in report['tiles']:
        if tile['status'] != 'processed':
            continue
        validate_tile(ROOT, tile)
        with Image.open(ROOT / tile['asset_dir'] / 'sar.png') as image:
            detections, _ = infer_tile(model, image, tile['bbox'], mask=mask, device='mps')
        result['tiles'].append(dict(key=tile['key'], image_sha256=tile['image_sha256'],
                                   asset_dir=tile['asset_dir'], bbox=tile['bbox'], detections=detections))
        result['updated_at'] = datetime.now(timezone.utc).isoformat()
        temporary = output.with_suffix('.pending.json')
        temporary.write_text(json.dumps(result, ensure_ascii=False))
        temporary.replace(output)
        print(f"MPS: {len(result['tiles'])}/{len(report['tiles'])} images; {len(detections)} candidates", flush=True)


if __name__ == '__main__':
    main()
