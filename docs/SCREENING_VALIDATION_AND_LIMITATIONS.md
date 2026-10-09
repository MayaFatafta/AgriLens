# AgriLens — Proxy Screening Scientific Validation & Acceptance

## Provenance

- **Geography:** 3×3-km Nile Delta Egypt study AOI; 20 eligible, geographically split fields.
- **Multispectral:** Historical real Sentinel-2 L2A derived field-date index measurements in 2025; 707 initial records, 615 retained because only 20 audited fields are in scope.
- **Environmental:** Open-Meteo / ERA5-Land and modeled dust/AOD auxiliary variables as packaged in the existing field-date analysis; **daily AOI-level modeled data** repeated for fields. The script verifies daily consistency.
- **Hyperspectral:** Real EMIT L2A RFL June 15, 2025; 14 fields matched to Sentinel-2 June 16 as single-date descriptive auxiliary context. Six other training fields remain missing due to original EMIT aggregate/dilated-cloud source-mask flags; no HSI imputation.

## Locked baseline protocol

1. Include only fields in the separately audited 20-ID master.
2. Replace unreliable `field_date_analysis.split` assignments with master `field_split` before computing cutoffs. The script records discrepancies.
3. Reject duplicate `(field_id,date)` observations, duplicate master IDs, invalid dates, environmental inconsistency across same-date fields, physically invalid modeled environmental values.
4. Recompute NDVI/NDMI changes from chronologically prior accepted field observation; never use a later reading. Temporal change gates are evaluated only with a prior observation and gap <=15 days.
5. Count **distinct train dates** once for environmental calibration. No validation/test values enter train quantile estimation. Fixed NDVI drop `-0.08` and NDMI drop `-0.03` are exploratory heuristics.
6. Exposure and moisture indicators are context/proxies, never confirmed crop stress or cause.
7. Avoid labels on low-quality/quarantined observations. No normal/healthy claims from rows without sufficient evidence.
8. Do not alter preserved EMIT source quality masks, geographic splits, original CSVs, or historical regression targets.

## Computed bundled-source exploratory thresholds

- Training dates with modeled environmental measurements: **32**.
- Dust 48h maximum high context: `>=260.75` in source dust units (training-date Q75).
- Modeled soil moisture 28–100 cm low context: `<=0.059` in source units (training-date Q25).
- Modeled AOD 48h high context: `>=0.3725` (training-date Q75; descriptive only).
- NDVI decline: `<=−0.08` per eligible pair with interval <=15 days.
- NDMI decline: `<=−0.03` per eligible pair with interval <=15 days.

These thresholds are **not physiological measurements, not established agricultural guidelines**, and must never be described as dust crop damage or drought crop damage thresholds. The moisture context spans a very narrow range (~0.059–0.069) and is quantized; many dates share values. The distribution is not representative of global drought regimes. Recalibration on any new valid training dates changes the report and must be versioned.

## Descriptive findings (not incidence)

- 615 screened field-dates; 20 fields; 33 distinct observation dates.
- 595 rows have an eligible previous-date observation for rate-of-change screening.
- 30 rows exceed the NDVI-decline heuristic; 79 exceed the NDMI-decline heuristic.
- 150 modeled dust-high context rows; 152 modeled deep-soil-moisture-low context rows.
- 3 dust-high + NDVI-decline co-occurrences; 5 modeled moisture-low + NDMI-decline + NDVI-decline co-occurrences.
- 1 combined dust-high + moisture-stress-proxy co-occurrence (without necessarily an NDVI decline).
- 196 records enter the review queue; 9 are high priority. Multiple high-priority conditions are *non-disjoint*, hence do not sum flagged subcounts without accounting for overlaps.
- 0 independently verified crop-damage cases and 0 verified dust/drought cause labels.

## Hard limits

- **No causal identification:** dust and plant index changes could co-occur for other reasons. The date of a delta spans a potentially 2–15 day gap; the 48-h dust maximum near the final date may be only a partial window of the decline.
- **No clinical-style negative labels:** `no_detected_screening_indicator` does not assert healthy crop, nor absence of dust or drought injury.
- **No independent exposures by field:** modeled environmental covariates are shared across a date; avoid pseudo-replicated confidence intervals or cross-field exposure inference.
- **Selection:** 6/9 training fields lack a usable EMIT sample; 6/6 validation and 5/5 test fields have usable samples. Their difference must remain explicit in any HSI-based analysis.
- **No HSI time series:** 14 fields have only the cited June EMIT acquisition; these values must not be backfilled over the 2025 Sentinel-2 time series.
- **No ground truth:** to claim an independently verified damaged crop, collect separate dated agronomist/field evidence, crop stage, irrigation/management history, compatible timing and adjudication. Supervised dust/drought classification remains unapproved.

## Release gate

- Structural and automated screening tests: **PASS (11/11)**.
- Train-only parameter estimation: **PASS (technical)**.
- Field attribution/split mapping: **PASS for the 20-ID screened cohort**.
- Independently verified dust/drought damage labels: **FAIL / not available**.
- Geographic/EMIT sample representativeness: **FAIL / remains biased**.
- Allowed claims: *candidate environmental exposure context, coincident observed vegetation/multispectral declines, prioritization for manual field review*.
- Prohibited claims: *confirmed dust crop injury, drought-driven yield loss, field-level diagnosed stress causes, supervised stress-classifier accuracy*.
