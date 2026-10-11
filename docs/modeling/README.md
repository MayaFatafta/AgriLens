# Rand — NDVI anomaly modeling module (corrected v1.2.0)

**Task:** Forecast next-observation NDVI from past field records and screen unusually negative residuals. This does **not** attribute dust, drought, damage or irrigation need.

Use the main [project README](../../README.md) for scientific context, complete data descriptions and GitHub publication instructions.

## Important corrections since uploaded v1.1.0

- Prefer audited `field_split` rather than `historical_split_recorded`; enforce 9 training / 6 validation / 5 held-out test fields.
- Add `soil_moisture_28_to_100cm` as a *lagged modeled contextual* predictor (changes predictions and alert count; the current run has 16 rather than the previous 15 raw flags).
- Overlay Rama's `validation/results/date_scene_QA.csv` on **existing** raw flags without deleting them. Suspected 17 May scene effects (five current model flags) are placed on **QA hold** and excluded from the 11-row quality-screened review queue.
- Join 20 field centroids from Rama's `validation/results/field_geography.csv` via checked field ID and geographic partition, then export correctly ordered WGS84 GeoJSON points.
- Use positive magnitudes in human-readable below-expected NDVI messages.
- Track quality-overlay and geography input hashes in model metadata, and export both raw and screened spatial maps.
- Add six new deterministic regression tests, bringing the suite to 13.

## Run from repository root

```powershell
python -m pip install -r requirements-modeling.txt
python -m pytest -q tests/test_ndvi_anomaly_detection.py
powershell -ExecutionPolicy Bypass -File .\run_ndvi_modeling.ps1
```

Direct invocation:

```bash
python scripts/ndvi_anomaly_detection.py --input 02_Field_Date_615/agrilens_real_field_date_QA_gated_615.csv --repo-root . --output-dir output/ndvi_anomaly_v1 --scene-qa validation/results/date_scene_QA.csv --coordinate-reference validation/results/field_geography.csv
```

The corrected CLI has optional `--split-col field_split` if desired, plus `--scene-qa` and `--coordinate-reference`. The QA and geography files are explicitly supplied here for provenance; without them the model produces **raw** statistical flags, with no quality-screening guarantee and an empty map unless the source already contains valid WGS84 coordinates.

## Outputs

`output/ndvi_anomaly_v1` contains source-derived scored records, anomaly threshold calibration, evaluation metrics, 16 raw flags, 5 scene-QA held flags, 11 quality-screened review candidates, 16-feature raw map, 11-feature screened map, audit JSON, manifest and figures. Counts are specific to the packaged real-data run and may change if features or software versions change.

**Scientific guardrails:** One-step test forecasting uses earlier observations of the same held-out field, never its future target. Only training-field GroupKFold OOF residuals calibrate the detection threshold; model selection uses validation fields, not test metrics. The retrospective scene-QA overlay uses existing validation records, which may include context learned after an acquisition. Do not present it as a prospective real-time decision engine.

Original uploaded Rand files are retained as `README_ORIGINAL.md` and `CODE_AUDIT_ORIGINAL.md` for audit history.
