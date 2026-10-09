# Derived Feature Definitions and Scientific Restrictions

**Unit:** agricultural field × acquisition date (`field_id`, `date`), with **20 independent geographic field IDs**, not 615 independent crop-stress events. Dates span 33 unique field-level acquisitions. These data do not settle a separate reported 34-date pixel-level count; reconcile source-date differences before submission.

## Exact v2-derived, current/past-only features (57-column file)

- `v2_ndvi_slope3_total`: NDVI(current) − NDVI(two observations earlier). Measured as total change over **three observations**, not change per calendar day. The original v2 implementation did not check historical window quality or gap duration.
- `v2_ndvi_dev_from_prev5_median`: NDVI(current) − median of up to five **previous** observations (minimum three previous observations). Previous observations only; can be distorted by poor-quality/gap history.
- `v2_cusum_neg`: one-sided CUSUM = `min(0, old_cusum + (NDVI(current)−NDVI(previous)) + 0.01)` with initial value zero. In the v2 source, it carries across temporal gaps and quality failures. It is not a classifier.

All three columns are NULL where current-observation quality fails (in these data, all 615 current field-dates were valid under the screening flag). Current/previous history quality is *not* guaranteed for these raw v2 fields. The source's measured `ndvi_mean`, `ndmi_mean`, `evi_mean`, dust/moisture context and screening flags have been copied unchanged.

## Optional QA-gated features (63-column file)

These are **recomputed from real original NDVI** using *only current or preceding observations*, with no learned fit on held-out fields.

- `qa_temporal_pair_ok`: current and immediate previous observation valid, NDVI finite, and calendar gap 1–15 days.
- `qa_window3_ok`: the current and previous two observations are valid, NDVI finite, and both intervening gaps are 1–15 days.
- `qa_ndvi_slope3_total`: NDVI current minus NDVI two observations ago, only where `qa_window3_ok`.
- `qa_window_prev5_ok`: at least three preceding observations, all observations in the trailing 3–5 history and current date valid, with gaps of 1–15 days.
- `qa_ndvi_dev_from_prev5_median`: current NDVI minus median of the last up-to-five preceding NDVI values, only when `qa_window_prev5_ok`.
- `qa_cusum_neg_reset`: historical one-sided negative CUSUM with +0.01 allowance; reset to 0 across invalid quality pairs or gaps above 15 days. Its value is **NULL** if the current-to-previous temporal pair is invalid.

The `qa_` columns are not supervised labels, and passing QA is not the same as evidence of dust or drought damage.

## Retrospective annotations

The separate file `agrilens_retrospective_patterns_NOT_FOR_MODEL.csv` contains `retro_next_delta_ndvi` and `retro_temporal_pattern`. These may depend on the **next** observation. They must not be merged back into operational predictor features or presented as verified dust/drought classes.

## Known scientific caveats

1. Modeled dust concentration, atmospheric indicators and deep-soil moisture are largely shared across fields at a date, not observed independent per-field stressors. Nile Delta irrigation makes regional soil-moisture context especially imperfect.
2. Data contain no independent field damage assessments: **0 verified crop-damage labels**. Pattern associations are screening proxies only.
3. The EMIT June 15 hyperspectral layer has 232 cleaned spectral wavelengths over 14 fields; six eligible train fields have zero accepted EMIT pixels under source cloud-buffer quality flags. Train HSI retention is 3/9; validation 6/6, test 5/5. This selection bias remains.
4. EMIT is an accessible hyperspectral stand-in for exploring techniques relevant to Satellite 813, not 813 imagery or a calibrated cross-sensor simulation.
5. Neither the additive features nor the original screening risk scores have verified lead time, field-specific dust attribution or causal stress classification performance.
6. There are no fabricated/synthetic rows in any real data file of this package.
