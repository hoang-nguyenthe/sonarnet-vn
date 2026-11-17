# Independent SAR evaluation, 17 November 2026

`results.json` contains the frozen holdout run. No test-driven model or threshold selection took place before this run. Both methods use the same 3,000 image cohort and CPU/thread settings.

## Reading the numbers

- AP uses all ranked predictions retained by each detector, with VOC integral interpolation. It is not identical to COCO/Ultralytics AP.
- `n_predictions` counts all retained boxes, including low-confidence YOLO boxes down to 0.001. It is **not** the operating count at confidence 0.25. At the selected threshold there are 2,182 boxes = 1,511 TP + 671 FP.
- Operating TP/FP/FN, precision, recall, coastal recall and localization errors use confidence 0.25 for YOLO and the selected brightness threshold for the simple baseline.
- `nearshore_gt` uses the dataset's image-contains-land definition. It does not imply a distance-to-coast threshold.
- FP/megapixel includes all raster pixels, land included. FP/km² and metre localization/size errors are null pending verified calibration.
- Pixel localization errors concern matched boxes (IoU >= 0.5), not missing targets, absolute geolocation, or hull measurements.
- A very weak global-threshold baseline does not establish superiority to stronger contemporary SAR systems.
- Timing excludes disk I/O and includes preprocessing, inference and NMS. Three warmups and four CPU threads; no throughput or production reliability claim.

## Provenance

Snapshots `evaluator_snapshot.py`, `metric_snapshot.py` and `ap_snapshot.py` correspond to hashes in results.json. Training provenance records initialization and frozen manifest hash. The full unchanged manifest is included in `../dataset_audit/manifest.json`; original images remain in the external work volume and can be reconstructed by the dataset preparation tools.

Reproduce from the repository with:

```sh
python scripts/evaluate_independent_sar.py --manifest /PATH/independent_ls_ssdd/manifest.json --weights assets/models/sonarnet_ls_ssdd_20261117.pt --output /PATH/new-evaluation
```

Do not overwrite this run while investigating improvements. Changes informed by these test errors require a new evaluation protocol or explicit post-test disclosure.
