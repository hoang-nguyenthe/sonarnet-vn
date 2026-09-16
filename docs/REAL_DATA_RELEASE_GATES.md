# Real SAR release gates

The current model and UI are experimental, not an operational vessel-alert service.

## Evidence currently available

- Official SAR-Ship-Dataset archive pinned by SHA-256 in `prepare_real_training.py`.
- 19,582 Sentinel-prefixed images, date-token grouped splits: 14,216 train,
  3,413 validation, 1,953 test. Date grouping is inferred from filenames,
  not independently verified scene metadata.
- All training examples contain ships. A background-only coastal evaluation
  set is still required; benchmark precision alone cannot establish safe
  operation on large predominantly empty scenes.
- Polarization tokens in the archive: HH 9,486; HV 8,820; VH 635; VV 641.
  Current validation has HH/HV only. Test has 351 VV images, but this test
  subset must not be used for threshold tuning or repeated model selection.
  A separate representative VV validation set is required before deployment
  on the dashboard's VV images. The current MPS run is a mixed-polarization
  research baseline, not a promotion candidate solely on overall AP.
- Vietnam evaluation: 12 fixed cells, 12 September 2026 daily composite,
  baseline 18 candidates, including visible land false positives. No labels
  confirming vessel identity or fishing class exist for those candidates.
- Candidate model training runs separately on MPS; never overwrite baseline
  or deploy automatically on benchmark improvements alone.

## Required before operational claims

1. Held-out real-data precision, recall and AP, including baseline comparison.
2. Independent labelled Vietnam scenes and background-only coastal examples;
   quantify false alarms per observed area and missed vessels.
3. Verify source-scene separation and near-duplicate leakage across splits.
4. Resolve real SAR preprocessing/resolution differences from benchmark chips.
5. Land masking with uncertainty near shore; do not silently delete harbour ships.
6. Preserve input provenance, model hash, processing status and stale-data state.
7. Automated processing and last-good publication with monitored failures.
8. Mobile/desktop review, export and map interactions tested end to end.
9. Review dataset and model usage terms before commercial deployment or redistribution.
10. AIS matching requires compatible time/position data; missing AIS is not a
    violation, and ship detection is not fishing-vessel classification.

No numeric performance target is asserted until an intended-use validation
protocol and representative labels exist. Do not describe completing training
as completing these gates.
