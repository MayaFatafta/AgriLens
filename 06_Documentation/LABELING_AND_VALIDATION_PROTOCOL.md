# AgriLens event-label and validation protocol — Nile Delta, Egypt, 2025

## What we have
- **Field-date satellite-derived observations:** NDVI, NDMI, EVI and historical change on 2025 FTW-predicted field units.
- **Regional environmental context:** Open-Meteo modeled dust, AOD, weather and deep soil moisture, aligned by UTC day to the Sentinel-2 field observation.
- **Geography:** 3 × 3 km study AOI centered 30.25°E, 30.63°N in Egypt, EPSG:32636.
- **Sampling frame:** FTW 2025 predicted polygons; exclude the huge merged polygon `1665168` and keep 3 geographic buffer fields out of supervised evaluation.
- **Event queue:** exploratory NDVI decreases of at least 0.08 between consecutive accepted observations. This is **not** a validated crop stress threshold.

## What is *not* a label
- An NDVI/NDMI decrease is a *measured index change*, NOT diagnosed drought or dust injury.
- Model-derived CAMS dust/AOD and ERA5 soil moisture are contextual covariates, NOT independently verified agronomic outcomes.
- FTW 2025 field membership and ESA WorldCover 2021 cropland status are NOT crop-stress diagnoses.
- Model-output labels derived from the same predictors (e.g. AOD >0.4 => "dust damage") are **circular** and cannot be used for independent model-performance reporting.
- The Brazil Tanager image is not an Egyptian field observation. Do not attach its pixel spectra to Egyptian rows.

## Separate labeling questions (do not collapse)
1. **Remote-sensing change:** Was NDVI lower than the prior quality-screened observation? This is already computed; *observed change*.
2. **Atmospheric dust exposure:** Did a **separate** observing network or independently analyzed satellite product corroborate dust/aerosol at the location and interval? An exposure label does not prove crop injury.
3. **Field moisture deficit:** Do independently collected field sensors or management/irrigation records support a soil-water deficit at this field and time? ERA5-Land alone is not a field label.
4. **Crop outcome:** Did an agronomist / geolocated photo series / vegetation or leaf-water instrument record actual crop damage or water stress, with species and phenological stage? Without this, the *crop-condition* field must remain `unknown`.
5. **Causal diagnosis:** Distinguishing crop damage from dust versus drought usually requires **both** verified environmental exposure and measured crop response plus confounder assessment. The default label remains `unresolved`.

## Label annotation template
In `outputs/independent_annotation_template.csv`, each event is a candidate row with no assigned ground-truth class. For each row record:
- **reviewer, reviewed_utc:** who reviewed and when.
- **satellite_scene_qa_verified:** `pass`, `fail`, or `uncertain` after checking Sentinel-2 RGB/SCL/AOT and scene coverage for the date.
- **satellite_qa_evidence_uri:** link/filename of source imagery and notes.
- **independent_dust_exposure_evidence_uri:** station PM10/PM2.5/AERONET/independent atmospheric verification with timestamp, coordinates, observation method and units.
- **independent_soil_water_evidence_uri:** soil probe or credible farm records with depth and timing.
- **independent_crop_condition_evidence_uri:** timestamped geotagged photos, scout observations, leaf water, crop management or independently measured condition.
- **atmospheric_event_label:** `observed_dust_exposure`, `observed_no_dust_exposure`, `unknown` — only when separately verified.
- **crop_condition_label:** `measured_stress`, `measured_no_stress`, `unknown` — only when independently supported.
- **causal_dust_vs_drought_label:** `dust_related_crop_stress`, `drought_related_crop_stress`, `other`, `unresolved` — defer until multiple independent sources support causal interpretation.
- **label_confidence:** qualitative `high`, `medium`, `low`; include evidence, method and uncertainty, not arbitrary probability.

**Do not fill unknowns as normal or negative.** A lack of evidence is not evidence of healthy crops. A reviewer should not see a candidate's inferred rule-based class before independent annotation if avoidable.

## Conditions to train a supervised classifier
- External reference observations for positive *and* negative cases spanning enough distinct fields, dates, phenological stages and environmental events; the minimum sample size depends on class distribution and intended deployment, not a generic 80:20 recipe.
- Stable field IDs and verified geometry; no single giant merged polygon dominating training.
- Document sensor product, spectral response, dates, QA rules and acquisition limits.
- Prevent field identity leakage and **event/date leakage**: if an atmospheric event affects many fields on 17 May, all rows from that event should be held in the same split or reported with clustered validation. Do not claim 18 independent dust storms from 18 fields on the same day.
- Only use explanatory variables available at inference time; `coverage_ratio_vs_p90` is a *whole-season retrospective QA* value and should not be a future-deployment predictor.
- Split by field and event/date; consider geographic buffers and a later-year external holdout. Fit imputation, scaling, feature selection and thresholds on training data only; tune on validation; test once on a locked independent set.
- Report true reference sources, sample counts **by field and independent event**, confusion matrix, per-class precision/recall, macro-F1, uncertainty, and how ambiguous/unknown cases were handled.
- Compare with simple baseline: satellite QA only, NDVI/NDMI change, and an interpretable meteorological context rule. Show whether a more complex hyperspectral approach improves independently assessed decisions, not just reconstructs band curves.

## If independent field labels cannot be acquired during the PoC
Release **event-review queue and contextual evidence**, plus NDVI forecasting baseline, **without a supervised stress classifier**. Label the result `inspection candidate`, `possible atmospheric contamination`, or `unresolved`; not `confirmed dust damage`/`drought damage`.

## Remaining raw evidence tasks
1. Inspect original Sentinel-2 L2A imagery at 17 May and follow-up dates, including SCL, AOT and true-color composites; compare known same-date changes across fields.
2. Seek local independent dust/air-quality event evidence and dated farm/irrigation/soil-water records for this AOI; record failed searches and missing coverage.
3. Check field crop type and management history to separate phenology/harvest from environmental stress.
4. Verify any event labels in an annotation review with a second reviewer and resolve disagreement before a final evaluation.
5. If available, obtain an **Egypt-overlapping hyperspectral cube** with suitable timing before conducting a direct multispectral/hyperspectral stress-classification comparison. Brazil Tanager is a separate **technical feasibility demonstration only**.
