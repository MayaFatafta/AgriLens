# AgriLens — NDVI Forecasting & Residual Anomaly Detection

**Team responsibility:** Rand — Modeling  
**Project:** *AgriLens — Dust or Drought?*  
**Purpose:** Convert the existing NDVI forecasting baseline into a transparent, geographically evaluated anomaly-screening workflow using the team's audited field-date data.

This module is designed to be copied into the existing `MayaFatafta/AgriLens` repository. It does not replace or edit the official dataset, does not read from the optional `AgriLens_v2_Safe_Additive_Enhancement` package during auto-discovery, does not make a random split, and does not invent damage labels.

## What it does

1. Reads the existing audited field-date CSV/Parquet and its existing geographic assignments.
2. Strictly validates the existing spatial layout: exactly 9 training fields, 6 validation fields, and 5 held-out test fields (20 unique fields total). It never repairs or replaces the split.
3. Builds causal time-series predictors from previous valid NDVI observations, the time gap, calendar seasonality, and optional **lagged** NDMI/dust/soil-moisture features when present.
4. Compares persistence (`expected NDVI = previous observed NDVI`) against a Ridge regression forecast. Ridge alpha and the selected forecasting baseline are selected from validation fields only.
5. Evaluates final forecasting MAE/RMSE on the existing held-out test fields.
6. Calibrates a conservative lower-tail residual threshold using deterministic, training-field GroupKFold out-of-fold residuals only; alerts require a negative observed-minus-expected residual.
7. Writes reproducible CSV/JSON/GeoJSON outputs, figures, and a generated scientific-method report.
8. Preserves all original source columns in the result file and records the input file SHA-256.

**Scientific boundary:** An anomaly is not a verified dust or drought diagnosis. The workflow does not claim causal attribution or validated damage-detection accuracy because the current dataset has zero independently verified damage labels.

## Install

Use the project's existing `.venv_clean` environment. From the repository root:

```bash
python -m pip install -r requirements-modeling.txt
```

The modeling requirements include NumPy, pandas, scikit-learn, matplotlib (optional figures), tabulate (optional report formatting), and pytest (tests). Parquet input additionally requires an appropriate pandas Parquet engine such as `pyarrow`.

## Copy the script into the repository

Merge the bundle into the AgriLens repository root, keeping the existing repository files:

- Copy `scripts/ndvi_anomaly_detection.py` into the repository's `scripts/` folder.
- Copy `run_ndvi_modeling.bat` and `requirements-modeling.txt` into the repository root.
- Copy `tests/test_ndvi_anomaly_detection.py` into `tests/` if the team wants to keep the regression tests.
- Do **not** overwrite the existing project `README.md` or `requirements.txt` with this bundle's files.

Keep the official source dataset unchanged.

## Validate and run

First run the included code tests from the bundle folder (or after copying the files):

```bash
python -m pytest -q tests/test_ndvi_anomaly_detection.py
```

From the AgriLens repository root, auto-discovery tries to identify the small audited field-date dataset while skipping obvious pixel-level/spectral tables and the optional v2 enhancement. **Always check the selected input path printed to the terminal.**

```bash
python scripts/ndvi_anomaly_detection.py --input auto --repo-root . --output-dir output/ndvi_anomaly_v1
```

For the strongest provenance control, pass the exact source file path instead of `auto`:

```bash
python scripts/ndvi_anomaly_detection.py \
  --input "PATH/TO/OFFICIAL_AUDITED_FIELD_DATE_DATA.csv" \
  --repo-root . \
  --output-dir output/ndvi_anomaly_v1
```

If columns cannot be inferred from the actual export, pass their names explicitly:

```bash
python scripts/ndvi_anomaly_detection.py \
  --input "PATH/TO/OFFICIAL_AUDITED_FIELD_DATE_DATA.csv" \
  --field-col field_id --date-col date --ndvi-col NDVI \
  --split-col geographic_split \
  --output-dir output/ndvi_anomaly_v1
```

If geographic split assignments live in a separate official table, point to that existing table; do not create a new random split:

```bash
python scripts/ndvi_anomaly_detection.py \
  --input "PATH/TO/OFFICIAL_AUDITED_FIELD_DATE_DATA.csv" \
  --split-map "PATH/TO/EXISTING_FIELD_SPLIT.csv" \
  --output-dir output/ndvi_anomaly_v1
```

If auto-discovery reports ambiguity, select the official audited file explicitly. Do not choose the optional v2/additive-enhancement merge merely because it is easier to locate.

## Outputs

The default destination is `output/ndvi_anomaly_v1/`:

| Output | Contents |
|---|---|
| `field_date_ndvi_anomaly_results.csv` | Source observations plus forecast, residual, alert reason, inspection recommendation, pattern-screen, and observation-gap fields |
| `heldout_test_alerts.csv` | Only flags from geographically held-out test fields; use for the demo/review queue |
| `all_split_anomaly_flags.csv` | Flags across splits for exploration; training predictions are out-of-fold where Ridge is selected |
| `forecast_metrics.csv` | Persistence and Ridge MAE/RMSE/bias for train OOF, validation, and test |
| `field_summary.csv` | Field-level counts and anomaly summary |
| `threshold_calibration_residuals.csv` | Training-only OOF residuals and field-held-out fold IDs used to calibrate the threshold |
| `agrilens_spatial_alerts.geojson` | GeoJSON `FeatureCollection` for flagged field-dates with valid WGS84 latitude/longitude; valid but empty if coordinates are unavailable |
| `data_audit.json` | Source hash, row/date/field counts, duplicate check, split counts and column mappings |
| `model_run_manifest.json` | Selected forecaster, Ridge alpha, feature list, threshold, metrics, and run time |
| `MODELING_REPORT.md` | Run-specific methods, findings, metrics, limitations, and reproducibility notes |
| `figures/` | Residual threshold, test observed-vs-expected, and a held-out field example (when plotting works) |

## How to read the anomaly output

`residual_observed_minus_expected = observed_ndvi - expected_ndvi`.

A negative residual means NDVI was lower than expected for that forecast. The threshold is learned only from training OOF residuals. The `pattern_screen` field describes an isolated versus repeated negative-change pattern; it is not a physical-cause label. `cause_interpretation` always keeps the cause undetermined. `inspection_recommendation` suggests review of the crop and image quality and checking field irrigation/root-zone moisture before water delivery changes; it does not automatically prescribe irrigation.

A large acquisition gap adds a low-confidence note. Original dust and soil-moisture columns remain context only and must not be described as causal evidence for a specific field.

## Methodology choices relevant to judging

- **No target leakage:** temporal predictors use prior observations only; calendar features are known for the target acquisition date.
- **Geographic separation:** the script requires the existing assignments and enforces exactly 9 train / 6 validation / 5 test fields. Every field must belong to one split. It never creates a random split.
- **Model selection:** Ridge alpha and persistence-vs-Ridge selection use validation only; held-out test results are not used to select the model or anomaly threshold.
- **Threshold calibration:** deterministic `GroupKFold` holds out whole training fields; no shuffle is used. The threshold is based only on training OOF residuals. `threshold_calibration_residuals.csv` makes these values auditable.
- **Lower-tail-only alerts:** the operational threshold is capped at zero so an anomaly always means the observed NDVI is below its expected value.
- **No false validation claims:** forecast MAE/RMSE do not measure dust/drought classification accuracy; the dataset currently contains no verified damage labels.
- **No source mutation:** all derived features and outputs are written to a new folder, and the source hash is recorded.

## Quick checks before submitting

1. Inspect `data_audit.json`; expected project references are 615 field-date rows, 20 audited fields and 33 dates. Investigate mismatches, including the known 34-vs-33 acquisition-date reconciliation, instead of forcing counts to match.
2. Confirm split field counts remain 9 train / 6 validation / 5 test.
3. Check the test MAE in `forecast_metrics.csv` against the prior experiment. Previously reported figures were persistence MAE 0.02752 and Ridge MAE 0.03555 over 37 test pairs; this run may differ if features, source rows or forecast-pair construction differ. Do not overwrite the old result without investigating differences.
4. Look at `heldout_test_alerts.csv` and the generated plot; confirm every flag is described as requiring review, not a diagnosis.
5. Inspect `agrilens_spatial_alerts.geojson`; the GeoJSON coordinate order must be `[longitude, latitude]` and all geometries must be WGS84 decimal-degree points.
6. Open `MODELING_REPORT.md` and ensure the run-specific values and input path are correct before sharing it with the team.

## Limitations to disclose

- The current proof of concept screens unusual changes; it does not reliably distinguish dust-caused damage from drought-caused damage.
- Modeled regional dust and soil moisture are environmental context, not independent field measurements.
- NASA EMIT is not satellite 813 imagery. Transferring the method to 813 requires actual suitable 813 data, spectral-response matching, and independent validation.
- The data summary reports zero independently verified damage labels, so causal detection performance cannot be claimed.
