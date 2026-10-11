# AgriLens Modeling Module — Code Audit Notes

**Module owner:** Rand — Modeling  
**Version:** 1.1.0  
**Scope:** NDVI forecasting residuals and statistical lower-tail anomaly screening

## Corrections implemented

- Enforced the required existing spatial protocol: exactly 9 train fields, 6 validation fields, and 5 test fields. The script raises an error rather than generating or randomizing a new split.
- Constructed NDVI, NDMI, modeled dust, and modeled soil-moisture predictors from previous valid observations only. Current target NDVI is used only as the prediction target and for post-forecast scoring.
- Used deterministic `GroupKFold` on training fields to generate out-of-fold predictions for threshold calibration; validation and test residuals are never used to fit the threshold.
- Added `threshold_calibration_residuals.csv`, an auditable record of the training-only OOF residuals and fold assignments.
- Capped the operational residual threshold at zero so flags always mean observed NDVI is lower than expected.
- Replaced/retained conditional assignments with explicit `DataFrame.loc[mask, column]` for `pattern_screen`, `cause_interpretation`, and `inspection_recommendation`. A regression test treats `SettingWithCopyWarning` as an error.
- Added `agrilens_spatial_alerts.geojson`, a GeoJSON FeatureCollection containing mapped flagged field-date rows where valid WGS84 latitude/longitude are present. Geometry order is `[longitude, latitude]`. Projected coordinates are not guessed or transformed; missing coordinates result in a valid empty FeatureCollection and an explicit audit status.
- Added tests for exact 9/6/5 split enforcement, OOF-only threshold provenance, coordinate serialization, empty GeoJSON behavior without coordinates, duplicate field-date rejection, and earlier-forecast invariance when a later held-out target changes.
- Kept source dataset loading read-only and retained the source SHA-256 provenance check.

## Verification performed

Command:

```bash
python -m pytest -q tests/test_ndvi_anomaly_detection.py
```

Result: **7 passed**.  
Syntax check: `python -m compileall -q scripts tests` passed.

Tests use deterministic synthetic fixtures only. They verify software behavior and data-flow safeguards; they do **not** demonstrate agronomic performance or dust/drought causal accuracy.

## Remaining dataset-specific checks before final submission

- Run the module against the exact manually audited 615-row source file and verify the printed/recorded input path and SHA-256.
- Inspect `data_audit.json` to reconcile the known 34 pixel-level acquisition dates versus 33 field-table dates; the script records the actual counts rather than forcing them to match.
- Confirm latitude/longitude columns are in WGS84 decimal degrees before using the GeoJSON in the dashboard. If the source contains projected x/y coordinates, transform them explicitly with the correct source CRS upstream; this module intentionally will not guess a CRS.
- Review run-specific MAE/RMSE and alert counts before presenting them. These metrics evaluate forecasting or anomaly screening only, not dust/drought diagnosis.
- No independent damage labels are present, so cause attribution must remain **undetermined**.
