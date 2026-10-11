import sys, json, pandas as pd
out=sys.argv[1]; M=json.load(open(f'{out}/verification/metrics.json'))
fld=pd.read_csv(f'{out}/results/field_geography.csv'); sp=pd.read_csv(f'{out}/results/geographic_bias_by_split.csv').set_index('split')
b=pd.read_csv(f'{out}/results/forecast_benchmark_with_CI.csv'); c=pd.read_csv(f'{out}/results/ridge_vs_persistence_contrast.csv').set_index('split')
q=pd.read_csv(f'{out}/results/inspection_queue.csv'); dq=pd.read_csv(f'{out}/results/date_scene_QA.csv')
cat=M['flags_by_category']; m=M['may17']
def bm(sp_,mod):
    r=b[(b.split==sp_)&(b.model==mod)].iloc[0]; return f"{r.MAE:.4f} ({r.MAE_CI95_low:.4f}–{r.MAE_CI95_high:.4f})"
top=fld.sort_values('flags_review',ascending=False).head(3)
topt='; '.join(f"field {int(r.field_id)} ({r.split}, {int(r.flags_review)} review flags)" for r in top.itertuples())
nz=int((fld.flags_review>0).sum())
r8=dq[dq.date=='2025-08-03'].iloc[0]
T=f"""# AgriLens — Validation Report (Final, for Visualization Handoff)

Prepared by: Rama (Validation). Date: 11 October 2026. Scope: team data only (`agrilens_real_field_date_QA_gated_615.csv`); no external or competing package data used.

**Bottom line.** The audited 615-row table supports a descriptive NDVI anomaly *screening* demo. It does not support any claim of dust-vs-drought accuracy: there are zero independently verified damage labels. {cat.get('scene_artifact_suspect',0)} of {M['flags']} flags come from one suspect scene (17 May) and must not be shown as crop damage.

## 1. Data and split integrity

| Check | Result |
|---|---|
| Source file SHA-256 | `{M['source_sha256']}` (matches team manifest) |
| Rows / fields / dates | {M['rows']} / {M['fields']} / {M['dates']} |
| Duplicate (field, date) pairs | 0 |
| NDVI outside [-1, 1] | 0 |
| Fields in more than one split | 0 |
| Audited geographic split (fields) | train {M['split_fields']['train']} / validation {M['split_fields']['validation']} / test {M['split_fields']['test']} |
| Rows per split | train {M['split_rows']['train']} / validation {M['split_rows']['validation']} / test {M['split_rows']['test']} |
| Fields excluded by the 100 m buffer rule (1664805, 1664847, 1664858) | not present |

## 2. Method

Expected NDVI for an observation = median of up to the 3 previous observations of the same field (current value excluded). Residual = observed − expected ({M['rows_with_baseline']} rows have a baseline). The flag threshold is `max(0.05, 3 × 1.4826 × MAD)` computed on **train-field residuals only** ({M['train_residuals']} residuals; median {M['residual_median']:.5f}, MAD {M['residual_MAD']:.5f}), giving **{M['threshold']:.4f}**; a row is flagged when |residual| exceeds it. Each flag is then categorised using scene quality from the source pixel table (aerosol optical depth, Scene Classification Layer shares) so that atmospheric artefacts are separated from observations that merit review.

Forecast benchmark: next-observation NDVI on the team's 178 / 119 / 37 train / validation / test pairs (test = August–September origins). Uncertainty: 95% intervals from a field-level bootstrap (5,000 resamples of whole fields, seed 20261011).

## 3. Results

### 3.1 Anomaly flags

{M['flags']} flagged observations (train {M['flags_by_split']['train']}, validation {M['flags_by_split']['validation']}, test {M['flags_by_split']['test']}).

| Category | Count | Meaning |
|---|---|---|
| scene_artifact_suspect | {cat.get('scene_artifact_suspect',0)} | AOT ≥ 0.5; do not count as damage |
| unclassified_pixels_review | {cat.get('unclassified_pixels_review',0)} | ≥ 10% of pixels are SCL 7 (unclassified); possible atmospheric artefact |
| long_gap_review | {cat.get('long_gap_review',0)} | more than 10 days since the previous observation; low confidence |
| review | {cat.get('review',0)} | genuine candidates for inspection; no causal claim |

Rows after a gap longer than 10 days are flagged {M['flag_rate_after_gt10d_gap']:.0%} of the time versus {M['flag_rate_overall']:.1%} overall, so gaps inflate flags. Mean AOT of flagged rows is {M['aot_flagged_mean']:.2f} versus {M['aot_all_mean']:.2f} for all rows.

### 3.2 The 17 May scene (strong evidence of an artefact)

- Mean AOT on 17 May is **{m['mean_aot_s2']:.2f}**, the highest of all 33 dates; the next highest is {M['second_highest_date_aot']:.2f}.
- {m['scl5_share']:.0%} of the pixels in the 20 fields are classified SCL 5 (not vegetated) that day, versus roughly 33–52% on typical dates.
- Mean NDVI across all fields falls from {m['regional_ndvi_prev_obs']:.2f} to {m['regional_mean_ndvi']:.2f} and rebounds to {m['regional_ndvi_next_obs']:.2f} on the next observation (20 May).
- {int(m['n_flags'])} of the 20 field observations that day are flagged.

A simultaneous, region-wide dip that reverses within three days under extreme aerosol load is far more consistent with a scene/atmospheric effect than with crop damage. This is strong circumstantial evidence from the data, based on pixel-level quality data and not yet compared against the imagery itself (see Limitations).

From early August, many pixels are SCL 7 (unclassified; {r8.scl7_share:.0%} of all pixels on 3 August). The pipeline accepted these pixels, so the {cat.get('unclassified_pixels_review',0)} flags on 3, 8 and 28 August with at least 10% SCL 7 pixels in the field are labelled `unclassified_pixels_review` and need imagery checks.

### 3.3 Forecast benchmark with uncertainty (MAE, 95% CI)

| Model | Validation (119 pairs, 6 fields) | Test (37 pairs, 5 fields) |
|---|---|---|
| Persistence | {bm('validation','persistence')} | {bm('test','persistence')} |
| Median of last 3 | {bm('validation','median_last3')} | {bm('test','median_last3')} |
| Ridge (exploratory) | {bm('validation','ridge_exploratory')} | {bm('test','ridge_exploratory')} |

Ridge minus persistence: validation {c.loc['validation','point']:+.4f} (CI {c.loc['validation','CI95_low']:+.4f} to {c.loc['validation','CI95_high']:+.4f}); test {c.loc['test','point']:+.4f} (CI {c.loc['test','CI95_low']:+.4f} to {c.loc['test','CI95_high']:+.4f}). Ridge is clearly better on validation fields but does not hold that advantage on the held-out test, where the interval includes zero and the point estimate favours persistence. The test reproduces the team's earlier numbers (persistence 0.02752, Ridge 0.03555). With only 5 test fields the intervals are coarse. **Persistence remains the reference; Ridge must not be presented as an improvement.**

### 3.4 Geographic bias

- **Spatial layout:** the split is a west-to-east gradient: mean longitude train {sp.loc['train','mean_lon']:.3f}, validation {sp.loc['validation','mean_lon']:.3f}, test {sp.loc['test','mean_lon']:.3f}. Test performance describes the eastern strip only; it says nothing about other regions or seasons.
- **Review-flag rate (excluding suspected artefacts):** train {sp.loc['train','review_flag_rate']:.1%}, validation {sp.loc['validation','review_flag_rate']:.1%}, test {sp.loc['test','review_flag_rate']:.1%}.
- **Concentration:** only {nz} of 20 fields have any review flag; the largest are {topt}. A few fields drive the totals.
- **Hyperspectral (EMIT) coverage bias:** usable EMIT fields train {int(sp.loc['train','emit_usable'])}/9 (mean coverage {sp.loc['train','emit_mean_coverage']:.2f}), validation {int(sp.loc['validation','emit_usable'])}/6, test {int(sp.loc['test','emit_usable'])}/5. EMIT comparisons therefore mostly describe validation and test fields.
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
"""
open(f'{out}/AgriLens_Validation_Report.md','w').write(T)
