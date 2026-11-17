"""Rebuild a real-SAR detector with immutable dataset provenance and resumable logs."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys


def digest(path):
    with Path(path).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--initial',default='yolo11n.pt')
    p.add_argument('--epochs',type=int,default=40)
    p.add_argument('--batch',type=int,default=16)
    p.add_argument('--imgsz',type=int,default=640)
    p.add_argument('--resume',type=Path)
    args=p.parse_args()
    import torch
    import ultralytics
    from ultralytics import YOLO
    if not torch.backends.mps.is_available(): raise RuntimeError('MPS unavailable; no silent fallback')
    audit=json.loads(args.data.with_name('audit.json').read_text())
    if not audit.get('passed'): raise ValueError('Dataset split/duplicate audit has not passed')
    if shutil.disk_usage(args.output.parent).free < 512*1024**2: raise RuntimeError('Insufficient free space for checkpoints')
    if args.output.exists() and not args.resume: raise ValueError('Output exists; use a new run name or --resume')
    args.output.mkdir(parents=True,exist_ok=True)
    torch.set_num_threads(4)
    kwargs=dict(data=str(args.data.resolve()),epochs=args.epochs,patience=8,imgsz=args.imgsz,
        batch=args.batch,device='mps',workers=2,cache=False,seed=20261116,
        deterministic=True,amp=False,optimizer='AdamW',lr0=.001,cos_lr=True,
        hsv_h=0.,hsv_s=0.,hsv_v=.2,degrees=10.,translate=.1,scale=.3,
        fliplr=.5,flipud=.5,mosaic=.5,close_mosaic=5,
        save=True,plots=True,project=str(args.output.parent.resolve()),name=args.output.name,exist_ok=True)
    model=YOLO(str(args.resume) if args.resume else args.initial)
    initial_path=Path(model.ckpt_path)
    metadata=dict(started_at=datetime.now(timezone.utc).isoformat(),hardware=platform.platform(),
        torch=torch.__version__,ultralytics=ultralytics.__version__,python=sys.version,
        initialization=str(initial_path),initial_sha256=digest(initial_path),
        dataset_manifest_sha256=digest(args.data.with_name('manifest.json')),
        audit=audit,training=kwargs,heldout_policy='Test is not used for model selection. Best checkpoint selected on validation.',
        promotion='Research candidate. Do not replace published detector before comparison.')
    (args.output/'provenance.json').write_text(json.dumps(metadata,indent=2))
    (args.output/'requirements-lock.txt').write_text(subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True))
    def progress(trainer):
        state=dict(epoch=trainer.epoch+1,total_epochs=trainer.epochs,
            metrics={k:float(v) for k,v in trainer.metrics.items()},
            updated_at=datetime.now(timezone.utc).isoformat())
        target=args.output/'progress.json'
        target.with_suffix('.tmp').write_text(json.dumps(state,indent=2))
        target.with_suffix('.tmp').replace(target)
        print('SONARNET_EPOCH '+json.dumps(state),flush=True)
    model.add_callback('on_fit_epoch_end',progress)
    if args.resume: model.train(resume=True,device='mps')
    else: model.train(**kwargs)
    metadata.update(completed_at=datetime.now(timezone.utc).isoformat(),
                    best_sha256=digest(args.output/'weights/best.pt'))
    (args.output/'provenance.json').write_text(json.dumps(metadata,indent=2))
    print('Training completed; held-out comparison must run separately.',flush=True)


if __name__=='__main__': main()
