# Dataset card: AgriLens next-observation NDVI

## Purpose
Small-sample, explainable field-level forecasting experiment: estimate NDVI at the next quality-screened Sentinel-2 observation from previous/current spectral summaries and weather/aerosol context. It is **not** a causal dust-vs-drought, crop health, yield, irrigation or hyperspectral benchmark.

## Population / geographic sampling frame
One approximately 900-ha AOI in Nile Delta, Egypt (30.25°E,30.63°N), March–September 2025. Original observation support consists of 22,500 grid pixels over 34 Sentinel-2 acquisitions; derived table holds 707,580 pixel-dates; 31 FTW model-predicted field IDs with 982 field-date summaries. Year-2025 FTW polygons were matched to original field IDs by spatial coincidence. FTW confidence is a native model score, not field-validated probability. ESA WorldCover 2021 is historical land cover, not 2025 crop ground truth.

## Selection and attrition
- 982 field-date measurements across 31 provisional units.
- Quarantine model-predicted field 1665168 (639.87-ha within AOI; full polygon 13,196.88-ha). It is a likely merged polygon, not a verified farm.
- Earlier screening accepts >=20 clear pixels and >=0.5 of each field's whole-season p90 pixels, leaving 707 rows across 23 field IDs. The filtering can disproportionately remove small, cloud-prone and seasonal fields; this is a *nonrepresentative conditional sample*.
- Centroid geo-zone + 100-m polygon buffer excludes 3 more fields, leaving 9 train/6 validation/5 test fields.
- Next-observation labels are available only for field-date pairs with 3–18 day accepted follow-up, train/validation in March–July and test origin August–September. 334 pairs remain: 178/119/37.
- Tests are observational; 37 test pairs from 5 fields/9 origin dates are **not 37 independent agricultural environments**.

## Leakage controls and what they do not guarantee
- Original pixel split had no repeat pixel or 500-m block between train/test but **15 field IDs overlapped**: invalid for unseen-field generalization.
- New split: disjoint field IDs and polygon geometries separated >100m between groups (actual edge minima 206.8m, 189.6m, 1326.9m).
- Test time window starts August 1, while all train/validation targets end before Aug 1: no exact train/test dates shared.
- All predictors available at original observation date; future target values, future elapsed horizon, field identifiers and retrospective p90 coverage feature excluded.
- Train-only imputation and scaling, validation-only hyperparameter selection, frozen held-out test.
- The date-level environmental products repeat across fields; nearby field climate, management and crop stage can still correlate across groups. The entire study is one 3x3km locality and season; do **not** infer multi-region generalization.

## Outcome / uncertainty
Target = next available satellite NDVI field mean in ~3–18 days. NDVI is not ground truth crop vitality, nitrogen, crop yield, soil moisture or dust damage. Missing clear observations are not missing at random. Data support a descriptive anomaly prototype plus an honest regression benchmark only.

## Baseline
Ridge model trained on 9 western fields before August and tuned on 6 central fields before August: test MAE=0.03555, RMSE=0.04490. Persistence (current NDVI) test MAE=0.02752, RMSE=0.03573. **Persistence is stronger.** Do not market Ridge as outperforming the baseline.

## Known uncertainties
- Original raster reflectance was not re-downloaded for this particular work package; pixel QA/provenance originate from prior project audit.
- Band calibration/offset and cloud SCL logic are described in source provenance and require raw-scene verification for scientific deployment.
- `scl=7` unclassified observations were permitted by the source pipeline; high-dust AOT coincident with NDVI dips could be atmospheric artifacts.
- 2021 WorldCover cropland and 2025 FTW parcels disagree in many pixels; crop identity is not ground truth.
- FTW model polygons are not cadastral property boundaries, and false merges/splits are possible.
- Open-Meteo dust/weather and soil moisture are modeled regional context, not crop-level instruments.
- No independent yield/drought/dust-damage labels. No validated causality.

## Sources and reproducibility
See `inputs/provenance.json`, `inputs/qa_results.json`, `inputs/Maya_FTW_Geometry_Audit.md`, `outputs/representation_leakage_audit.json` (SHA256) and `README.md`. Original Sentinel-2 collection: https://planetarycomputer.microsoft.com/api/stac/v1 ; field polygons: https://source.coop/ftw/global-data/predictions/vectors ; Open-Meteo: https://archive-api.open-meteo.com/v1/archive and https://air-quality-api.open-meteo.com/v1/air-quality . Respect original dataset terms/attribution; reconfirm redistributability before public GitHub publication.
