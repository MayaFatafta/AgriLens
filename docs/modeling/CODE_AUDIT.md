# AgriLens Modeling Module — Code Audit Notes

**Module owner:** Rand — Modeling  
**Version:** 1.2.0  
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

## Corrections in 1.2.0 (integration fixes)

- **Split column:** the old auto-detection took the first column containing "split", which on the real 615-row table is `historical_split_recorded` (13 train / 7 test, no validation) and made the run fail. The audited `field_split` column now has priority; an explicit `--split-col` overrides it; several valid candidates without `field_split` raise "Ambiguous geographic split"; invalid labels in `field_split` never fall back to another column. Disagreements with ignored columns are recorded in `data_audit.json`.
- **Image quality:** `--scene-qa` links the model to Rama's scene QA. Raw flags are preserved; suspected scene artefacts (17 May, high regional AOT) are re-categorised and written to `scene_artifact_suspects.csv`, and the crop-review queue is `quality_screened_review_queue.csv`.
- **GeoJSON:** alerts are joined to audited field coordinates by field ID. Only a single finite WGS84 pair per field (not (0, 0)) is mapped; missing, conflicting, out-of-range or projected values stay unmapped with an audit reason. Coordinates were also re-derived independently from the UTM 36N centroids (max difference 5e-6 degrees).
- **Tests:** 28 tests (was 7): split conflict, ambiguity, invalid audited labels, scene-quality filtering, coordinate join and invalid-coordinate cases, dashboard classification counts, and the real 615-row run.
- The `SettingWithCopyWarning` test guard now adapts to pandas 3, where that warning no longer exists.

## Verification performed

Command:

```bash
python -m pytest -q tests
```

Result: **28 passed** (full log: `docs/test_results.txt`).  
Real-data run (615 records, 20 fields, 33 dates, split 9/6/5 from `field_split`): 15 raw flags, 10 quality-screened, 5 suspected scene artefacts, 15 of 15 flags mapped.  
Syntax check: `python -m compileall -q scripts tests` passed.

Tests use deterministic synthetic fixtures only. They verify software behavior and data-flow safeguards; they do **not** demonstrate agronomic performance or dust/drought causal accuracy.

## Remaining dataset-specific checks before final submission

- Real-data run done (SHA-256 `5919ffbd...1c30c6`, identical to the team dataset copy). Re-run it from the final repository paths before submission.
- The field-date table has 33 dates (matches the reference). The known 34 pixel-level acquisition dates are a separate table and still need reconciling by the data owners.
- Reconcile the 152 test pairs scored here with the 37 test pairs quoted in the dashboard benchmark wording; the pair construction differs and neither number was changed.
- Coordinates come from `validation/results/field_geography.csv` (WGS84 centroids for orientation, not field boundaries). Projected x/y values are never guessed; transform them upstream with the correct CRS.
- Review run-specific MAE/RMSE and alert counts before presenting them. These metrics evaluate forecasting or anomaly screening only, not dust/drought diagnosis.
- No independent damage labels are present, so cause attribution must remain **undetermined**.
