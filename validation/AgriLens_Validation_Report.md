# AgriLens — Validation Report (Final, for Visualization Handoff)

Prepared by: Rama (Validation). Date: 11 October 2026. Scope: team data only (`agrilens_real_field_date_QA_gated_615.csv`); no external or competing package data used.

**Bottom line.** The audited 615-row table supports a descriptive NDVI anomaly *screening* demo. It does not support any claim of dust-vs-drought accuracy: there are zero independently verified damage labels. 13 of 36 flags come from one suspect scene (17 May) and must not be shown as crop damage.

## 1. Data and split integrity

| Check | Result |
|---|---|
| Source file SHA-256 | `5919ffbdc2b33b6f3b3fd9c31f534889d80b2aa80cce4ceed1f04192a21c30c6` (matches team manifest) |
| Rows / fields / dates | 615 / 20 / 33 |
| Duplicate (field, date) pairs | 0 |
| NDVI outside [-1, 1] | 0 |
| Fields in more than one split | 0 |
| Audited geographic split (fields) | train 9 / validation 6 / test 5 |
| Rows per split | train 275 / validation 183 / test 157 |
| Fields excluded by the 100 m buffer rule (1664805, 1664847, 1664858) | not present |

## 2. Method

Expected NDVI for an observation = median of up to the 3 previous observations of the same field (current value excluded). Residual = observed − expected (595 rows have a baseline). The flag threshold is `max(0.05, 3 × 1.4826 × MAD)` computed on **train-field residuals only** (266 residuals; median 0.00012, MAD 0.02481), giving **0.1103**; a row is flagged when |residual| exceeds it. Each flag is then categorised using scene quality from the source pixel table (aerosol optical depth, Scene Classification Layer shares) so that atmospheric artefacts are separated from observations that merit review.

Forecast benchmark: next-observation NDVI on the team's 178 / 119 / 37 train / validation / test pairs (test = August–September origins). Uncertainty: 95% intervals from a field-level bootstrap (5,000 resamples of whole fields, seed 20261011).

## 3. Results

### 3.1 Anomaly flags

36 flagged observations (train 16, validation 13, test 7).

| Category | Count | Meaning |
|---|---|---|
| scene_artifact_suspect | 13 | AOT ≥ 0.5; do not count as damage |
| unclassified_pixels_review | 5 | ≥ 10% of pixels are SCL 7 (unclassified); possible atmospheric artefact |
| long_gap_review | 3 | more than 10 days since the previous observation; low confidence |
| review | 15 | genuine candidates for inspection; no causal claim |

Rows after a gap longer than 10 days are flagged 37% of the time versus 6.1% overall, so gaps inflate flags. Mean AOT of flagged rows is 0.46 versus 0.28 for all rows.

### 3.2 The 17 May scene (strong evidence of an artefact)

- Mean AOT on 17 May is **0.85**, the highest of all 33 dates; the next highest is 0.41.
- 100% of the pixels in the 20 fields are classified SCL 5 (not vegetated) that day, versus roughly 33–52% on typical dates.
- Mean NDVI across all fields falls from 0.47 to 0.36 and rebounds to 0.45 on the next observation (20 May).
- 13 of the 20 field observations that day are flagged.

A simultaneous, region-wide dip that reverses within three days under extreme aerosol load is far more consistent with a scene/atmospheric effect than with crop damage. This is strong circumstantial evidence from the data, based on pixel-level quality data and not yet compared against the imagery itself (see Limitations).

From early August, many pixels are SCL 7 (unclassified; 28% of all pixels on 3 August). The pipeline accepted these pixels, so the 5 flags on 3, 8 and 28 August with at least 10% SCL 7 pixels in the field are labelled `unclassified_pixels_review` and need imagery checks.

### 3.3 Forecast benchmark with uncertainty (MAE, 95% CI)

| Model | Validation (119 pairs, 6 fields) | Test (37 pairs, 5 fields) |
|---|---|---|
| Persistence | 0.0302 (0.0255–0.0349) | 0.0275 (0.0197–0.0374) |
| Median of last 3 | 0.0344 (0.0259–0.0458) | 0.0302 (0.0232–0.0417) |
| Ridge (exploratory) | 0.0215 (0.0165–0.0283) | 0.0355 (0.0292–0.0435) |

Ridge minus persistence: validation -0.0087 (CI -0.0124 to -0.0043); test +0.0080 (CI -0.0032 to +0.0169). Ridge is clearly better on validation fields but does not hold that advantage on the held-out test, where the interval includes zero and the point estimate favours persistence. The test reproduces the team's earlier numbers (persistence 0.02752, Ridge 0.03555). With only 5 test fields the intervals are coarse. **Persistence remains the reference; Ridge must not be presented as an improvement.**

### 3.4 Geographic bias

- **Spatial layout:** the split is a west-to-east gradient: mean longitude train 30.238, validation 30.250, test 30.261. Test performance describes the eastern strip only; it says nothing about other regions or seasons.
- **Review-flag rate (excluding suspected artefacts):** train 3.8%, validation 5.1%, test 2.6%.
- **Concentration:** only 8 of 20 fields have any review flag; the largest are field 1664841 (validation, 7 review flags); field 1664852 (train, 4 review flags); field 1664899 (test, 4 review flags). A few fields drive the totals.
- **Hyperspectral (EMIT) coverage bias:** usable EMIT fields train 3/9 (mean coverage 0.17), validation 6/6, test 5/5. EMIT comparisons therefore mostly describe validation and test fields.
- **Environmental context:** dust, AOD and soil-moisture values are identical for all fields on a given date, so cross-field variation cannot support causal claims.

## 4. What can and cannot be claimed

| Can say | Cannot say |
|---|---|
| Observations whose NDVI departs from the field's recent history are flagged for inspection | Any flag is caused by dust or by drought |
| The 17 May dip coincides with extreme AOT and a region-wide rebound | The 17 May dip is (or is not) real crop stress |
| Persistence had the lowest held-out test error of the three models (differences are within uncertainty) | Ridge improves on persistence |
| Results are for a 3 × 3 km Nile Delta locality, one season | Generalisation to other regions or years |

## 5. Limitations

No independently verified damage labels. One locality and one season. Test = 37 pairs from 5 fields and 9 origin dates, not 37 independent environments. Field centroid coordinates are derived from the sampling frame (EPSG:32636 to WGS84) and are for mapping only. The AOT ≥ 0.5 and SCL 7 ≥ 10% thresholds are screening conventions chosen here, not calibrated standards. The 17 May interpretation rests on pixel-level QA values (AOT, SCL, regional NDVI behaviour), not on visual inspection of the scene. The 34 (pixel table) versus 33 (field table) acquisition-date difference remains unreconciled.

## 6. Changes from the earlier validation package

The earlier `AgriLens_Validation_Final` used the 707-row file with an unaudited historical split and non-comparable metrics, and its 38 flags included the 17 May artefact. It is superseded by this package.
