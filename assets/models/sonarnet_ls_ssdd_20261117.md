# SonarNet LS-SSDD research checkpoint (17 November 2026)

This model is a newly trained research candidate. It does not reproduce the deleted historical checkpoint, and it has not replaced the model hashes in existing Vietnam map observations.

- File: `sonarnet_ls_ssdd_20261117.pt` (5.2 MiB).
- SHA256: `5b1eef4e8e45b17ea3f071285af5693dcb5ecc2c98d272264a570f58a1eb2bb1`.
- Architecture: Ultralytics YOLO11n, one ship class, initialized from official COCO weights.
- Data: original LS-SSDD author annotations, custom scene/region/date split. 3,491 train, 594 validation, 3,000 test. Conservative quarantine of 115 similar train/validation images. Full split manifest and hashes are in `reports/final/dataset_audit/manifest.json`.
- Training: Apple M1 Pro MPS, PyTorch 2.8.0, Ultralytics 8.3.253; 640 px, AdamW, batch 16, seed 20261116. Early stopping at epoch 24 with patience 8. Best checkpoint chosen on validation.
- Operating threshold: 0.25, chosen on validation only. NMS IoU 0.7. Evaluation retains predictions down to 0.001 for AP.
- Holdout: precision 0.6925, recall 0.6354, AP50 0.6618, AP50-95 0.2389 (VOC integral, not COCO AP). 1,511 TP, 671 FP, 867 FN.
- Failure mode: recall on images containing land is 0.2786. Do not infer an empty sea from a negative prediction.
- Physical calibration: metre errors and FP/km² remain unverified. Pixel box errors are conditional on true-positive matches, not absolute geographic accuracy or physical hull dimensions.
- Timing: CPU, four threads, same hardware baseline. Median 61.47 ms and p95 65.05 ms per image, including preprocessing and NMS, excluding I/O. Not a production throughput guarantee.
- Intended use: educational, non-commercial research and human-reviewed demonstration. No autonomous identity or IUU conclusions. Check the upstream dataset and Ultralytics terms before any broader distribution or commercial use.

The full run configuration, environment lock, predictions, failures, code snapshots and results are retained in `reports/final/independent_sar/`. A separate copy of the weights and run provenance exists on the attached SSD.
