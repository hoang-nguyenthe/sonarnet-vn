#!/bin/bash
# Resume training by invoking train_final_sar.py --resume explicitly; never overwrite a run.
set -euo pipefail
repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
work_dir="${1:-/Volumes/SonarNetWork}"
training_python="$work_dir/train-env/bin/python"
run_dir="$work_dir/runs/final_ls_ssdd_20261117"
export YOLO_CONFIG_DIR="$work_dir/ultralytics"
export PYTORCH_ENABLE_MPS_FALLBACK=1
cd "$repo_dir"
"$training_python" scripts/train_final_sar.py \
  --data "$work_dir/independent_ls_ssdd/data.yaml" \
  --output "$run_dir" --initial "$work_dir/models/yolo11n.pt" \
  --epochs 40 --batch 16 --imgsz 640
"$training_python" scripts/evaluate_independent_sar.py \
  --manifest "$work_dir/independent_ls_ssdd/manifest.json" \
  --weights "$run_dir/weights/best.pt" \
  --output "$repo_dir/reports/final/independent_sar" --imgsz 640
cp "$run_dir/provenance.json" "$repo_dir/reports/final/independent_sar/training_provenance.json"
cp "$run_dir/results.csv" "$repo_dir/reports/final/independent_sar/training_curve.csv"
cp "$work_dir/independent_ls_ssdd/quarantine.json" "$repo_dir/reports/final/independent_sar/quarantine.json"
printf '%s\n' 'Training and held-out evaluation completed; inspect results before promoting the model.'
