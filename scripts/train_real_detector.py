"""Train a separate real-SAR candidate; never auto-promote to production."""
from pathlib import Path
import json
import torch
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[1]


def main():
    if not torch.backends.mps.is_available():
        raise RuntimeError('MPS not available; stop rather than silently start a long CPU run')
    data = ROOT / 'data_external/sentinel_training/dataset.yaml'
    audit = json.loads(data.with_name('audit.json').read_text())
    assert all(audit['counts'].get(s,0)>0 for s in ['train','val','test'])
    destination = ROOT / 'training_real'
    model = YOLO(str(ROOT / 'sonarnet_run/runs/yolo_sar/weights/best.pt'))
    model.train(data=str(data), epochs=30, patience=8, imgsz=512, batch=16,
                device='mps', workers=2, cache=False, seed=20260916,
                project=str(destination), name='sentinel_finetune', exist_ok=False,
                save=True, plots=True, amp=False)
    # Test data are reserved for evaluation after model selection by validation.
    best = YOLO(str(Path(model.trainer.save_dir) / 'weights/best.pt'))
    metrics = best.val(data=str(data), split='test', imgsz=512, batch=16, device='mps', workers=2,
                       project=str(destination), name='heldout_test')
    report = dict(metrics=metrics.results_dict, weights=str(Path(model.trainer.save_dir)/'weights/best.pt'),
                  dataset_sha256=audit['archive_sha256'], split_rule=audit['split_rule'],
                  limitations=audit['limitations'], promotion='NOT APPROVED: requires external Vietnam evaluation and false-positive review')
    (destination / 'evaluation.json').write_text(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
