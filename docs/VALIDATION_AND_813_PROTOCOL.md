# AgriLens: next validation experiments and Satellite 813 adaptation

## Experiment A — spectral-information gain (no crop-stress labels required)

**Claim:** narrow Tanager bands preserve spectral structure that a sparse band-center approximation does not reproduce.

**Inputs:** *the same physical Tanager scene* for both versions; use the same quality-screened pixel locations. Red-edge interval 680–800 nm; sparse anchors near 665, 705, 740, 783, 842 and 865 nm. These are center-only proxies and **do not reproduce Sentinel-2 spectral response functions (SRFs)**.

**Output:** per-pixel red-edge reconstruction RMSE and its median/p05/p95, sample count, seed, spatial sample pattern and plot. This evaluates representation, **not diagnostic accuracy**. Run `pixelwise` for actual per-pixel measurements. For sensor-faithful benchmark, obtain official Sentinel-2 band SRF curves and convolve the *same* HSI spectra to produce synthetic band-integrated measurements before reconstructing or classifying.

## Experiment B — crop-stress diagnosis (not runnable yet)

**Research target to confirm:** a defined field-observed condition, for example *independently verified water-stress indicator* or *confirmed crop stress status at acquisition date*. Do **not** use NDVI threshold, red-edge index, FTW field ID, or CAMS dust models as the truth label if these are also model inputs.

**Reference evidence:** field observations/leaf-water potential, trusted agronomic assessments or validated in-situ sensors, measured within a justified time window near the imagery. Store crop type, phenological stage, sampling date, field identity and source. Record uncertainty in labels. Dust deposition on leaves needs its own evidence; atmospheric aerosols alone are not proof of crop damage.

**Experiment design:**
1. Choose agricultural polygons with verified geometry in the **same** hyperspectral scene. Collect independent field/site labels.
2. Acquire quality-matched reflectance and ensure comparable spatial support, sampling time and sensor geometry.
3. Construct baseline features from *only sparse, band-integrated measurements* (e.g., true SRF-convolved Sentinel-2 simulation, or a clearly marked approximation).
4. Construct enhanced features adding **predefined** narrow-band traits (red-edge position, selected absorption features), or the full spectrum with controlled regularization.
5. Split by entire fields and preferably add geographic buffers; an additional region/season is needed before claiming broad transferability. Fit scaling, imputation and model selection on training/validation only.
6. Compare the same classification family under the same tuning budget and held-out samples; use macro-F1/precision/recall/confusion matrix (or MAE/RMSE for a genuinely measured continuous target). Include field-level bootstrap confidence intervals.
7. Report the score *difference* and confidence interval. If it crosses zero or the baseline wins, state that hyperspectral superiority **was not demonstrated**.

**No independent labels = no diagnostic-accuracy result.**

### Ground-reference collection schema (empty template included)

`field_id,pixel_row,pixel_col,observation_date,reference_label,label_source,crop_type,phenological_stage,notes`

Labels must not be filled from NDVI or generated with thresholds if the goal is external validation.

## Experiment C — Satellite 813 (requires permission/data)

Current proof: **none**. Do not state we have processed 813 imagery or that Tanager is a 813-equivalent product.

Once the organizers provide an authorized scene, create a sensor adapter with a verified manifest:

- Satellite identifier, institution/provider, product identifier and acquisition timestamp.
- Level (radiance or reflectance), calibration constants, wavelength centers, spectral response functions/FWHM and bad-band indicators.
- HDF5/GeoTIFF/netCDF cube layout, dtype, NoData, scale/offset, cloud/quality bits.
- CRS, pixel size, affine transform, footprint, geolocation accuracy.
- Licensing, permitted distribution and provenance including exact source asset and checksum where provided.
- AOI and clear vegetation samples plus a sensor-specific QA report.

**Adapter API contract:** `load_cube(source) -> (array[band,y,x], wavelengths_nm[band], quality_mask[y,x], spatial_metadata, provenance)`.

Only then run the same vegetation-feature extraction and measure compatibility/performance on 813 observations. Re-tune wavelength choice and account for spectral response and spatial-resolution differences; do not assume 813 features are interchangeable with Tanager.
