# AgriLens technical handoff — decision and immediate next steps

## Dataset is available now

The original user-uploaded pixel table `dataset.parquet` is included under `inputs/`. Its earlier project QA and FTW geometry-audit files are retained. The new regression feature table has **334 real derived field-date pairs** across **20 geographically separated FTW model fields**. There are no independently verified yield, dust-stress or drought diagnosis labels.

### Final sampling numbers

| Stage | Fields | Records |
|---|---:|---:|
| Original pixel observations | 31 predicted field IDs | 707,580 pixel-date measurements total (many outside field polygons) |
| Original field summary | 31 | 982 field-date summaries |
| Quality-screened/large-polygon quarantined | 23 | 707 field-date summaries |
| Geographic splitting after 100m buffer | 20 | 9 train + 6 validation + 5 test fields |
| Forecasting target constraints | 20 | 178 train +119 validation +37 test target pairs |

### Model conclusion

The held-out August–September test favors the **simple persistence baseline** (MAE 0.02752) versus exploratory Ridge (MAE 0.03555). Do not present Ridge as an improvement. Accuracy is specifically for predicting *satellite NDVI*, not diagnosing crop stress causes or predicting yield.

### Action plan

**Maya (data)**: deliver `outputs/ftw_aoi_sampling_frame.geojson`, `next_ndvi_regression.csv`, QA JSON and data card. Verify the team's original data versions/checksums; run `src/audit_pixel_parquet.py` on local machine to rederive pixel-level representation figures directly from the original Parquet. Preserve the large FTW polygon exclusion.

**Rand (model)**: integrate persistence first; optionally reproduce Ridge and analyze why it fails in the future+regional test. Do not use original pixel `split` for field generalization. Do not build supervised dust/drought classifier without actual independent target labels.

**Rama (science)**: inspect 2025-05-17 NDVI drop, SCL/visible imagery and AOT; it may be an atmospheric observation artifact. Request crop stage/type and agronomist or farmer references. Report time-coverage and validation uncertainty.

**Nour (integration)**: connect `notebooks/AgriLens_Research_Audit_and_Baseline.ipynb` to main repo; ensure reproducible notebooks and pinned environment. Plot FTW model polygons from the sampling-frame GeoJSON; place disclaimers beside maps.

**Omar (documentation)**: explain Egypt AOI rather than Jordan, distinguish multispectral dataset from 813/Tanager/EnMAP, cite FTW/Sentinel2/Open-Meteo terms, and avoid unsupported performance, causal-diagnosis and water-savings statements.

### Scientific decisions still unresolved

1. Team must confirm that Egypt Nile Delta AOI is the official problem geography and who will use the product.
2. Original Sentinel-2 source-asset QA/atmospheric-offset checks are documented in existing provenance, but have not been independently reprocessed in this workstream.
3. Cropland assignment conflict: approximately 53.2% of field-assigned pixel-date observations are *not* WorldCover 2021 cropland; investigate visually before asserting all model-predicted fields are active 2025 cropland.
4. The full FTW polygon 1665168 (132 km2) is likely merged; remains excluded until supported subdivisions are available.
5. Independent crop outcomes, diagnosis labels, multi-year and multi-region replication are absent.

### Current research statement to use publicly

> We assembled an observational satellite dataset for a 9 km² Nile Delta agricultural landscape, mapped predicted field units to Sentinel-2 vegetation-index time series and regional environmental context, audited spatial and temporal leakage, and benchmarked next-observation NDVI prediction. A transparent persistence baseline outperformed exploratory Ridge regression in the held-out future/regional evaluation; validated dust-versus-drought diagnosis requires independent field reference evidence.
