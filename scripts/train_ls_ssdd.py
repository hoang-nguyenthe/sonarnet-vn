"""Train an isolated real-SAR candidate, keeping test scenes out of selection."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--epochs', type=int, default=30)
    parser.add_argument('--batch', type=int, default=8)
    parser.add_argument('--resume', type=Path)
    args = parser.parse_args()
    if args.epochs < 1 or args.batch < 1:
        parser.error('epochs and batch must be positive')
    import torch
    from ultralytics import YOLO
    if not torch.backends.mps.is_available():
        raise RuntimeError('MPS is unavailable; no implicit CPU training')
    if shutil.disk_usage(ROOT).free < 5 * 1024**3:
        raise RuntimeError('At least 5 GiB free space required')
    directory = ROOT/'data_external/ls_ssdd_yolo'
    provenance = json.loads((directory/'provenance.json').read_text())
    if not provenance['backgrounds_retained']:
        raise ValueError('Background images must be retained')
    for split in ('train', 'val', 'test'):
        images = list((directory/'images'/split).glob('*.jpg'))
        if len(images) != provenance['counts'][split]['images']:
            raise ValueError(f'Incomplete {split} dataset')
    initial = ROOT/'training_real/sentinel_finetune/weights/best.pt'
    if args.resume:
        model = YOLO(str(args.resume.resolve()))
        model.train(resume=True, device='mps')
    else:
        model = YOLO(str(initial))
        model.train(data=str(directory/'data.yaml'), epochs=args.epochs, patience=8,
                    imgsz=800, batch=args.batch, device='mps', workers=2,
                    cache=False, seed=20260917, deterministic=True, amp=False,
                    hsv_h=0, hsv_s=0, hsv_v=.2, save=True, plots=True,
                    project=str(ROOT/'training_real'), name='ls_ssdd_backgrounds', exist_ok=False)
    saved = Path(model.trainer.save_dir)
    weights = saved/'weights/best.pt'
    best = YOLO(str(weights))
    metrics = best.val(data=str(directory/'data.yaml'), split='test', imgsz=800,
                       batch=args.batch, device='mps', workers=2,
                       project=str(saved), name='heldout_test')
    report = dict(metrics=metrics.results_dict, dataset=provenance,
                  weights_sha256=hashlib.sha256(weights.read_bytes()).hexdigest(),
                  promotion='NOT APPROVED: independent Vietnam validation required',
                  limitation='Dataset benchmark does not establish performance on current Copernicus previews.')
    (saved/'evaluation.json').write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
