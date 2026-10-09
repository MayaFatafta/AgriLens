# AgriLens — Full Research Data & Team Handoff (10 October 2026)

**This is the one package to share across the team.** It combines the original quality-audited Sentinel-2 pixel dataset, the final real-field screening dataset, QA-gated temporal features, EMIT hyperspectral measurements, geospatial identifiers, forecasting results, figures, documentation, provenance and reproducible scripts.

**Registered challenge:** “Dust or Drought?”  The release supports vegetation anomaly monitoring, environmental *context* screening and exploratory hyperspectral analyses; it **does not** establish actual dust- or drought-induced crop damage and has **ZERO independently verified causal damage labels**. Do **not** report dust-vs-drought classification accuracy.

## The folders

| Folder | Contents and role |
|---|---|
| `01_Sentinel2_original/` | Original **707,580 pixel-date** Sentinel-2 dataset (`dataset.parquet`), 707-row field-date input, weather context, field geometries, quality/provenance |
| `02_Field_Date_615/` | **Main real analysis table**: `agrilens_real_field_date_QA_gated_615.csv` (**615 rows, 63 columns**, 20 eligible fields, 33 dates); unmodified base screening and original enhancement; inspection queue and summaries |
| `03_EMIT_hyperspectral/` | **20-field** availability master, **14-field** usable EMIT/S2 comparison, **3,248 field-band** observations over **232 wavelengths**, cloud-mask/missingness audit, derived index raster (not raw hyperspectral cube) |
| `04_NDVI_forecasting/` | Geographically held-out forecasting samples, saved predictions and baseline scores (these evaluate NDVI forecasting, **not** crop damage) |
| `05_Figures/` | Eight final AgriLens figures (PNG and editable SVG), overview, plus supporting legacy spatial/regression figures |
| `06_Audits/` | Data/feature quality, split, screening, missingness and validation reports |
| `06_Documentation/` | Dataset card, dictionary, protocols, acceptance limits and handoff instructions |
| `07_Retrospective_NOT_FOR_MODEL/` | **Future-dependent** temporal pattern annotations — **not for predictive model features or verified labels** |
| `08_Reproduce/` | Processing scripts and unit tests; requirements in `requirements_research.txt` |
| `09_Notebooks/` | Egyptian HSI and research/audit notebooks |
| `10_Metadata/` | Supplied source metadata/search records for provenance; **not additional independent samples** |

## Team instructions

- **Maya:** Treat `01_Sentinel2_original/` and `03_EMIT_hyperspectral/` as source evidence and `02_Field_Date_615` as derived analysis; preserve splits and original filenames; keep SHA256 manifest.
- **Rand:** Start with `02_Field_Date_615/agrilens_real_field_date_QA_gated_615.csv` and use `04_NDVI_forecasting/`. Do not include future-dependent annotations or IDs as predictive variables; no verified stress labels.
- **Rama:** Check `06_Audits/`, especially EMIT geographic representativeness and source mask, and review causal limitations.
- **Nour:** Use `02_Field_Date_615/`, `03_EMIT_hyperspectral/` and `05_Figures/`. The raw EMIT spectral cube was **not supplied** to this bundle; plotted spectra are from the audited field summaries.
- **Omar:** Use `06_Documentation/`, `05_Figures/` and `DATA_INVENTORY_VERIFIED.json` for the registered “Dust or Drought?” challenge narrative.

## Explicit omissions and limits

1. The uploaded `enmap.zip` contains a **271 MB `.TIF.part` incomplete EnMAP download**. We excluded it. It is not a verified EnMAP image.
2. This share package **does not contain the original 286-band June 15 EMIT spectral GeoTIFF**: it was not present in the inspected uploaded archives. It contains the 232-band field-level spectra, quality and provenance instead. If raw-cube reproducibility is required, add the original `data/emit_egypt/agrilens_emit_egypt_hsi.tif` from the working project and regenerate checksums.
3. The pixel-level Sentinel-2 source was earlier reported as having 34 acquisition dates whereas the real field-date table has 33. This exact date difference has **not been reconciled**; do not invent an explanation.
4. Cloud-buffer masks prevent usable June 15 EMIT measurements on six training fields. Train 3/9 eligible EMIT fields; validation 6/6; test 5/5. **Geographic hyperspectral coverage bias remains**.
5. Wind/dust/soil moisture are largely **modeled regional context**, not field-specific cause measurements; canal irrigation makes modeled deep-soil moisture a weak proxy for field water status.
6. Historical features and the forecasting benchmark do not establish predictive accuracy for real dust/drought causes. The only labeled future-dependent temporal annotations are explicitly in `07_Retrospective_NOT_FOR_MODEL/`.
7. We deliberately excluded semi-synthetic benchmark rows and simulated labels; **all 615 rows in the operational analysis table are derived from real Egyptian field observations.**

## Consistency checks executed for this full share

- 615 unique (`field_id`, `date`) rows; 20 fields; 33 dates.
- QA-gated field-date file is byte-identical to the earlier integrated release, not regenerated with changes.
- 20-field EMIT master, 14-field usable comparison, 3,248 complete unique field–wavelength records, 232 wavelengths and zero missing cells in the completed spectral table.
- Sentinel-2 Parquet SHA-256 matches the original Parquet in the supplied `enmap.zip` (only one copy retained).
- No intentionally generated pseudo-observations or synthetic labels included.
- A manifest of all included files is saved as `SHA256_manifest.csv`.

This is a **research data delivery**, not a deployed cloud service or a validated dust/drought diagnosis system.
