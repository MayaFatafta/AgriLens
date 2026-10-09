# AgriLens — Audited Field-Level Research Dataset (Egypt AOI, 2025)

**Status:** Reproducible *observational satellite-index forecasting* research dataset assembled from team-supplied actual field summaries and verified 2025 FTW crosswalk. **Not** a validated crop-yield, drought, dust-damage or irrigation regression dataset.

## Source and scope

- Study location: 3 km × 3 km (~900 ha), 30.25°E, 30.63°N, Nile Delta **Egypt**, UTM EPSG:32636.
- Original inputs: `dataset.parquet` (707,580 satellite pixel-date records, 37 attributes, 22,500 unique pixel centers), `field_timeseries.csv` (982 field-dates, 31 predicted FTW field IDs), `daily_env.csv` (214 modeled environmental context days).
- Satellite observations: 34 Sentinel-2 Level-2A acquisitions, March–September 2025. Environmental features: Open-Meteo modeled air quality/meteorology/soil moisture. ESA WorldCover 2021 is *land-cover context*, not a 2025 crop-health label.
- Verified FTW field crosswalk: 31 of 32 model-predicted 2025 polygons intersecting the AOI correspond to project field IDs. Earlier geometry audit checked 22,500 pixel centers with zero membership mismatches. The source tile has no persistent `field_id`; assigned IDs were recovered from spatial coincidence.
- Problem polygon: Field **1665168** is a 13,196.88-ha full model polygon, of which 639.87 ha falls within the AOI; likely merged prediction, **excluded** from single-field analysis.
- Original full pixel Parquet is bundled under `inputs/dataset.parquet` as a read-only reference; running this project's CSV-based workstream does not require reading it. Original global 70 MB FTW source tile is not bundled; cropped validated geometries and the source URL are provided.

### Public origins (from supplied project provenance)

- Sentinel-2 L2A: https://planetarycomputer.microsoft.com/api/stac/v1 (collection `sentinel-2-l2a`)
- FTW field polygons: https://source.coop/ftw/global-data/predictions/vectors (FTW 2025; maintain attribution and check distribution terms)
- Landcover context: https://planetarycomputer.microsoft.com/api/stac/v1 (`esa-worldcover`, 2021)
- Regional environment: https://archive-api.open-meteo.com/v1/archive and https://air-quality-api.open-meteo.com/v1/air-quality
- Original source manifest: `inputs/provenance.json`; original QA: `inputs/qa_results.json`.

**Acquisition limitation:** This artifact audits *existing exported derived measurements and polygon crosswalk*. The original raw Sentinel-2 band assets, calibration metadata and external field labels were not fetched anew here. The earlier QA report/geometry audit have been retained and attributed, not silently upgraded to independent field or sensor validation.

## Files

| File | Meaning |
|---|---|
| `outputs/sampling_frame_and_splits.csv` | Audited FTW field IDs, area, confidence-native column, centroids and geographic split status |
| `outputs/next_ndvi_regression.csv` | Regression-ready field-date features and *observed next valid Sentinel-2 NDVI* target |
| `outputs/representation_leakage_audit.json` | Original pixel leak flags, new split distances, geographic/temporal restrictions, source SHA256 |
| `outputs/regression_baseline_scores.json` | Held-out Ridge versus persistence evaluation, explicitly exploratory |
| `outputs/regression_predictions.csv` | Traceable observed target, predictor value, model prediction for each used field-date |
| `figures/spatial_sampling_frame.png` | FTW geography and split/exclusion map |
| `figures/regression_baseline_comparison.png` | Baseline performance chart |
| `docs/DATASET_CARD.md` | Research population, bias and scientific interpretation |
| `docs/DATA_DICTIONARY.csv` | Column definitions and time-of-availability notes |
| `src/build_research_dataset.py` | Deterministic geometry/split/target/model generation |
| `src/make_figures.py` | Recreate figures |
| `tests/test_research_dataset.py` | Critical invariants of target, geometry split, timing and allowed predictors |

## Modeling target and method

**One example:** field 1664893 observed on date *t* has satellite vegetation condition NDVI(t), NDMI(t), EVI(t), existing changes vs *earlier* accepted observations and regional environmental values known up to *t*. The desired target is the field's actual mean NDVI on its **next accepted satellite observation** between 3 and 18 days later. The target is derived from observations, not an independent crop-health survey. At operational inference time the exact next clear acquisition date is not guaranteed; its elapsed horizon is **not** used as a predictor.

Source field observations were previously filtered for at least 20 valid pixels and >=50% of each field's *observed whole-season p90* pixel count; this is a retrospective quality filter, not a verified acreage-based or prospective clear-pixel fraction. 707 of 982 field dates across 23 fields remain after filtering and excluding the suspicious large polygon.

Split improvement over original:

1. Form three **geographic centroid zones** with deterministic KMeans (seed 42); west=train, center=validation, east=test. Does not use data labels or scores to choose zones.
2. Keep test group, exclude validation polygons <100m from any test polygon; exclude training polygons <100m from a retained validation/test polygon. Three boundary fields are quarantined rather than reassigned.
3. Training: 9 fields, 178 target pairs; validation: 6 fields, 119 target pairs; held-out test: 5 fields, 37 pairs. Minimum polygon edge-to-edge gap: train-validation **206.8 m**; validation-test **189.6 m**; train-test **1326.9 m**.
4. Only **training and validation target dates earlier than August 1, 2025**; **test input observations are August 1 or later**, with targets also in August–September. This prevents overlapping train/test *dates* and field identities. But all observations still occur within one 3-km region and growing season, so extrapolation beyond it remains untested.
5. The model's predictors include current field NDVI, NDMI, EVI, previous accepted deltas, previously observed date spacing, contemporaneous satellite AOT and environmental context. Excluded from predictor features: `field_id`, future target NDVI, target acquisition date, realized future horizon, the retrospective p90 coverage ratio, previous `split`, and any proxy diagnosis labels.
6. `SimpleImputer` and `StandardScaler` fit exclusively on training rows, then Ridge hyperparameter selected via validation MAE. The frozen choice is checked on held-out test only once.

## Result: simple baseline wins in the temporal holdout

| Split | Rows | Ridge MAE | Persistence MAE | Ridge RMSE | Persistence RMSE |
|---|---:|---:|---:|---:|---:|
| Train | 178 | 0.02497 | 0.03605 | 0.03288 | 0.04981 |
| Validation | 119 | 0.02155 | 0.03024 | 0.02853 | 0.04454 |
| Future held-out test | **37** | **0.03555** | **0.02752** | **0.04490** | **0.03573** |

Ridge underperforms persistence on unseen eastern fields in a later period. Do **not** report higher ML predictive accuracy or infer dust/drought diagnosis. The held-out test has only **5 fields, 9 distinct origin dates, and 37 pairs**. Field-date samples are correlated, and regional dust/weather observations are shared across many fields.

## Reproduce (Python 3.13 environment tested)

From the extracted package directory:

```bash
python -m pip install -r requirements.txt
python src/build_research_dataset.py --evaluate
python src/make_figures.py
python -m unittest discover -s tests -v
```

To regenerate the preceding descriptive field table from uploaded original CSVs (creates a temporary folder):

```bash
python src/build_field_handoff.py --fields inputs/field_timeseries.csv --env inputs/daily_env.csv --out scratch_field_handoff
```

The initial field-level script contains a historical two-way random field split. **Do not use its `split` column** for final regression claims; the second-stage dataset builder discards that split and constructs the spatial + temporal holdouts above.

## Readiness decision

- **READY:** temporal descriptive analysis, honest anomaly screening and exploratory regression on next measured Sentinel-2 NDVI.
- **NOT READY:** dust-versus-drought disease-cause diagnostic model; crop-yield prediction; irrigation-volume regression; 813/Tanager/EnMAP hyperspectral feature claims; scientifically representative sampling of other regions or seasons.
- **NEXT DATA:** independent field-level reference labels or yield/irrigation measurements if those are the desired outcomes; raw scene-level Sentinel-2 QA inspection for suspected aerosol artifacts; true farmland reference or corrected boundaries for merged FTW polygons; additional regions and years for generalization tests.

This dataset is designed for training experiments and a transparent hackathon proof of concept, not agronomic decision automation.

## Optional direct re-audit of original pixel Parquet

This environment could not import a Parquet reader; we therefore use the project's earlier `qa_results.json` and its verified geometry report as evidence for the original pixel dataset. **To independently recompute these checks from the complete original Parquet on your Windows venv**, install `pyarrow` (if not already installed) and run:

```bash
python src/audit_pixel_parquet.py --input inputs/dataset.parquet --out outputs
```

It produces `outputs/original_pixel_deep_audit.json`, `original_pixel_field_representation.csv`, and `original_pixel_date_representation.csv`. This is intentionally *not* claimed as executed here. Confirm that its numbers agree with the earlier QA report before freezing the repository.

### Spatial crosswalk for integration

`outputs/ftw_aoi_sampling_frame.geojson` contains all 32 polygons in the AOI with the new `selection_status` (train / validation / test / excluded buffer / excluded prior QA / quarantined merged polygon / no matched pixel). `outputs/all_ftw_field_selection_inventory.csv` is the matching non-geometry table. The sampling-frame GeoJSON is the source for splitting *field units*, not surveyed farm property boundaries.

### Audit notebook

Open `notebooks/AgriLens_Research_Audit_and_Baseline.ipynb`, use the repository root or notebook folder as the working directory and execute the cells in order. The notebook re-runs Ridge and persistence evaluation using the generated field dataset. It was clean-executed in the test environment using the listed dependencies.
