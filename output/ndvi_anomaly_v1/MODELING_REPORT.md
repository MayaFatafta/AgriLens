# AgriLens — NDVI Modeling & Anomaly Screening Report

**Generated:** 2026-10-11 15:47 UTC  
**Script version:** 1.2.0  
**Input SHA-256:** `5919ffbdc2b33b6f3b3fd9c31f534889d80b2aa80cce4ceed1f04192a21c30c6`

## Executive summary

This run compares a persistence forecast (next NDVI equals the previous valid NDVI) with a Ridge regression model. The forecasting method is selected using validation fields only. It then calibrates a lower-tail residual threshold using training-only out-of-fold residuals and applies that threshold to produce review flags. The project’s original geographic field split is retained and strictly validated as 9 training fields, 6 validation fields, and 5 test fields. No random train/validation/test split or randomized cross-validation is performed.

**Selected forecast baseline:** `ridge`  
**Selected Ridge alpha:** `1.0`  
**Training-calibrated lower residual threshold:** `-0.09187`  
**Held-out test *raw* anomaly flags:** 3 across 2 field(s).

**Scene-quality integration:** Retrospective scene QA source: `/mnt/data/AgriLens_GitHub_Ready_FINAL/validation/results/date_scene_QA.csv`; 5 raw model flags held for image review across all splits. 11 remain as quality-screened review candidates.

These are **statistical vegetation-change alerts, not confirmed crop damage or dust/drought diagnoses**. No independent damage labels were supplied for this run.

## Data and split audit

| Check | Result |
|---|---:|
| Input rows | 615 |
| Unique fields | 20 |
| Unique parseable dates | 33 |
| Field-date duplicates | passed; no duplicate field-date keys |
| Invalid NDVI values outside [-1, 1] set missing | 0 |
| Rows excluded for unparseable date | 0 |
| Geographic fields by split | `{"test": 5, "train": 9, "validation": 6}` |
| Rows by split | `{"test": 157, "train": 275, "validation": 183}` |

Reference data expectations from the project summary are 615 field-date rows, 20 audited fields, and 33 dates. Actual-count checks: `{"rows_match_615": true, "fields_match_20": true, "dates_match_33": true}`. Any mismatch should be reconciled with the data owner before final submission; this script does not edit or silently deduplicate source data.

## Forecasting evaluation

| Split | Purpose |
|---|---|
| Training | Model fitting; Ridge training errors are calculated out-of-fold by field for calibration/reporting. |
| Validation | Select Ridge alpha and choose between persistence and Ridge. |
| Test | Geographically held-out final evaluation; not used to choose the model or threshold. |

| split        | model            |   n_pairs |   n_fields |     mae |    rmse |   bias_observed_minus_predicted |
|:-------------|:-----------------|----------:|-----------:|--------:|--------:|--------------------------------:|
| train_oof    | Persistence      |       266 |          9 | 0.03379 | 0.04733 |                         0.00018 |
| train_oof    | Ridge(alpha=1.0) |       266 |          9 | 0.03254 | 0.04268 |                         0.00011 |
| train_oof    | Selected(ridge)  |       266 |          9 | 0.03254 | 0.04268 |                         0.00011 |
| validation   | Persistence      |       177 |          6 | 0.03100 | 0.04650 |                        -0.00217 |
| validation   | Ridge(alpha=1.0) |       177 |          6 | 0.03079 | 0.04142 |                        -0.00862 |
| validation   | Selected(ridge)  |       177 |          6 | 0.03079 | 0.04142 |                        -0.00862 |
| test_holdout | Persistence      |       152 |          5 | 0.02957 | 0.04360 |                        -0.00158 |
| test_holdout | Ridge(alpha=1.0) |       152 |          5 | 0.03104 | 0.04038 |                        -0.01137 |
| test_holdout | Selected(ridge)  |       152 |          5 | 0.03104 | 0.04038 |                        -0.01137 |

MAE and RMSE describe **forecasting error only**. They do not measure accuracy at diagnosing dust or drought.

## Anomaly method

For each field, valid NDVI observations are ordered by date. Predictors include lagged NDVI values, prior NDVI changes, time gap between observations, and day-of-year cyclical features. Where present, NDMI/dust/soil-moisture context is included only as a lagged feature. Missing values are imputed from training data within the pipeline.

Residual is defined as:

`residual = observed_NDVI - expected_NDVI`

The alert threshold is calibrated only from deterministic training-field group out-of-fold residuals. No random shuffling is used, and validation/test residuals are excluded from threshold calibration. The operational threshold is capped at zero, so a flag always means observed NDVI is lower than expected. Method: **minimum of training OOF residual 5th percentile and median - 2.5 robust sigmas**. Training OOF residual count: 266; training fields: 9; OOF folds: 5; median: -0.00023; robust sigma: 0.03665; 5th percentile: -0.06863. A row is flagged when its residual is below the calibrated lower threshold. The threshold is statistical and is not calibrated to agronomic ground truth.

The optional `pattern_screen` distinguishes an isolated/abrupt-looking flag from repeated negative changes. This is a descriptive pattern label, not a physical cause diagnosis.

## Held-out test alerts

Flagged test fields: 1664899, 1664931. See `heldout_test_alerts.csv` for the record-level evidence and the original source columns. Every alert uses the wording **cause undetermined** and recommends review rather than an automatic irrigation action.

## Spatial GeoJSON export

The run wrote `/mnt/data/AgriLens_GitHub_Ready_FINAL/output/ndvi_anomaly_v1/agrilens_spatial_alerts.geojson` with status `written` and 16 mapped alert feature(s). Coordinates are interpreted strictly as WGS84 decimal-degree latitude/longitude and GeoJSON coordinates are stored in `[longitude, latitude]` order. Rows with absent or invalid coordinates are not mapped, and no coordinates or CRS transformations are fabricated. Coordinate source columns: latitude `field_latitude_wgs84`, longitude `field_longitude_wgs84`.

## Limitations and scientific guardrails

1. There are no independently verified dust-related or drought-related crop-damage labels in the source dataset; precision/recall for causal classification cannot be calculated.
2. Regional modeled dust is not proof that dust affected a specific field or plant. Modeled soil moisture is not a measurement of irrigation delivered to an individual field.
3. A negative NDVI residual indicates lower-than-expected greenness, not necessarily crop damage.
4. The EMIT spectral observations are from NASA EMIT and are not satellite 813 imagery. Transfer to 813 requires actual 813 data, band-response matching, and independent evaluation.
5. The model’s use of previous observations from each test field is a rolling one-step-ahead setup. Test field identities are not used to fit model coefficients, but their past observations are used as legitimate forecasting inputs.
6. Forecast scores must be reported from the current run. Do not use illustrative values or call anomaly flags validated damage labels.

## Reproducibility and files

- `field_date_ndvi_anomaly_results.csv` — source records with forecast, residual, alert, pattern, confidence, reason, and inspection-recommendation fields added as separate output columns.
- `heldout_test_alerts.csv` — only alerts from geographically held-out test fields.
- `all_split_anomaly_flags.csv` — statistical alerts across all splits (training alerts use out-of-fold Ridge predictions when Ridge is selected).
- `forecast_metrics.csv` — persistence and Ridge metrics for train OOF, validation, and test.
- `field_summary.csv` — field-level summary.
- `data_audit.json` — counts, column mappings, split audit, and source hash.
- `model_run_manifest.json` — run settings, selected model, threshold, and metrics.
- `threshold_calibration_residuals.csv` — training-only OOF residuals used for threshold calibration.
- `agrilens_spatial_alerts.geojson` — **raw** statistical flags with explicit QA status and audited WGS84 points where available.
- `quality_screened_inspection_queue.csv` — flagged observations excluding retrospective suspect-scene flags; not a verified damage set.
- `scene_qa_held_alerts.csv` — retained model alerts with scene-quality hold notes.
- `agrilens_screened_spatial_alerts.geojson` — only quality-screened review candidates with mapped audited centroids.
- `figures/` — calibration and demonstration plots, when plotting dependencies are available.

The source data is read-only; all derived artifacts are written to `/mnt/data/AgriLens_GitHub_Ready_FINAL/output/ndvi_anomaly_v1`.
